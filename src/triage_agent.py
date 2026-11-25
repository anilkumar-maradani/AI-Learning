"""
triage_agent.py: Week 12. The integrated claims triage agent.

The Week 7 loop (the model picks the next tool each lap, four budgets checked
before every model call), with the Week 9 rule that the agent names no MCP
tool: every remote tool is discovered at start-up from mcp_config.w12.json
(tools/list) and called over MCP (tools/call). One tool is local:
refer_to_adjuster, the only way a triage ends.

    FNOL in -> trace id minted -> tools discovered -> laps:
        model (Groq) picks tool calls
        -> MCP tools/call with _meta {trace_id, span_id}     (coverage server logs it)
        -> result REDACTED (names, addresses, injuries) before the model sees it
        -> refer_to_adjuster validated by code (referral.validate)
    -> referral out, ONE request line (redacted on write) in traces/w12/requests.jsonl

Version switch (configuration, like the Week 11 canary):
    w12-v1   the coverage server ignores the loss date when choosing wording
    w12-v2   wording is filtered to the edition in force on the loss date
"""

import hashlib
import json
import os
import time
import uuid

import llm
import referral
from claim_store import SNAPSHOT_DIR, get_claim, write_triage_snapshot
from mcp_client import ToolRegistry
from observability import Tracer, stage_totals
from redaction import PERSONAL_KINDS, redact_text
from tracing import EventWriter

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
CONFIG = os.path.join(ROOT, "mcp_config.w12.json")
LOG_DIR = os.path.join(ROOT, "traces", "w12")
# POLICYLENS_LOG_SUFFIX lets two runs in parallel (one per model) keep separate files.
_SUFFIX = os.environ.get("POLICYLENS_LOG_SUFFIX", "")
REQUESTS_PATH = os.path.join(LOG_DIR, f"requests{_SUFFIX}.jsonl")
CALL_LOG = os.path.join(LOG_DIR, f"coverage_calls{_SUFFIX}.jsonl")

PROMPT_VERSION = "triage-agent-w12-5"

# w12-3: the adjuster notes are read at intake (host step, over MCP, redacted) and
# the FNOL carries the policy number, so the model's path is 3 laps, not 5: the
# smoke run of w12-2 spent 12,350 tokens on 5 serial laps, 1.5K of them re-sending
# the system prompt and six tool definitions every lap.
# w12-5: the FNOL lists the attached forms, so the in-force check and the wording
# read go out in ONE turn (2 model laps instead of 3), and the prompt is cut: the
# system prompt and tool definitions are re-sent on every lap.
SYSTEM = """You triage claims at Northgate Mutual. You never decide coverage; an \
adjuster does. You give the adjuster the facts and the wording IN FORCE ON THE LOSS DATE.

In your FIRST turn make both calls together: check_coverage_in_force(policy_number, \
loss_date) and search_policy_wording(form_number="<every form in the FNOL, \
comma-separated>", loss_date). Then call refer_to_adjuster once; it ends the task. If \
coverage was not in force, refer with no citations.

Cite given chunk_ids with the clause id (WE-4) or exclusion row code (E-42), never \
EXCLUSION-TABLE. Cite every clause and exclusion row the facts could make relevant, \
including exclusions to rule in or out. Give a sublimit only if a sublimit clause applies.

Never write covered, excluded, denied, declined, approved or payable, even when the \
wording does: write "within the scope of WE-1", "E-41 lists ...", "amount for the \
adjuster to set"."""

PROMPT_SHA256 = hashlib.sha256(SYSTEM.encode("utf-8")).hexdigest()

DEFAULT_BUDGETS = {"max_iterations": 7, "max_tokens": 30_000, "max_cost_usd": 0.02, "max_wall_s": 300.0}
# gpt-oss reasoning effort for the agent's laps (config, recorded on every run).
REASONING_EFFORT = os.environ.get("POLICYLENS_REASONING_EFFORT", "low")
MAX_REJECTIONS = 3


def _short(text: str, n: int = 300) -> str:
    return text if len(text) <= n else text[:n] + "..."


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _parse(text: str):
    try:
        return json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return None


def _read_server_spans(trace_id: str, path: str) -> list[dict]:
    if not os.path.exists(path):
        return []
    out = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue
            if r.get("trace_id") == trace_id:
                out.append({k: r.get(k) for k in ("parent_span_id", "server_span_id", "tool", "latency_ms",
                                                  "is_error", "result_sha256", "result_chars", "caller")})
    return out


def _fnol_message(claim: dict, notes: list[str] | None = None) -> str:
    out = ("New first notice of loss. Triage it and refer it to an adjuster.\n"
           f"claim_number: {claim['claim_number']}\n"
           f"policy_number: {claim['policy_number']}\n"
           f"forms attached: {', '.join(claim.get('forms') or [])}\n"
           f"loss_date: {claim['date_of_loss']}\n"
           f"reported_date: {claim.get('reported_date') or 'unknown'}\n"
           f"description: {claim['fnol_description']}\n")
    out += ("adjuster notes (read at intake from the claims system; names, addresses and "
            "injuries redacted):\n" + ("\n".join(f"- {n}" for n in notes) if notes else "- none yet"))
    return out


# The claims system (third-party MCP server) is read by the HOST at intake, not
# offered to the model: the notes are needed on every claim, so a model lap spent
# deciding to fetch them is pure re-sent context.
INTAKE_TOOL = "claims_system__get_adjuster_notes"


def _intake_notes(registry, claim: dict, roster: list, tracer, trace_id: str) -> tuple[list[str], dict]:
    span_id = f"sp{len(tracer.spans) + 1}"
    with tracer.span(f"tools:{INTAKE_TOOL}", "tools", tool=INTAKE_TOOL, hop="mcp", intake=True) as sp:
        out = registry.call(INTAKE_TOOL, {"claim_number": claim["claim_number"]},
                            meta={"trace_id": trace_id, "span_id": span_id})
        clean, counts = redact_text(out["text"], roster, kinds=PERSONAL_KINDS)
        sp["attrs"].update({"server": out["server"], "mcp_tool": out["tool"], "is_error": out["is_error"],
                            "result_sha256": _sha(out["text"]), "result_chars": len(out["text"]),
                            "redactions": counts})
    parsed = _parse(clean) if not out["is_error"] else None
    notes = [f"[{n.get('date')}] {n.get('text')}" for n in (parsed or {}).get("notes") or []]
    step = {"lap": 0, "tool": INTAKE_TOOL, "server": out["server"], "hop": "mcp", "intake": True,
            "args": {"claim_number": claim["claim_number"]}, "is_error": out["is_error"],
            "result_preview": _short(clean)}
    return notes, step


def run_triage(claim_number: str, version: str = "w12-v2", model: str | None = None, log=None,
               write: bool = True, config: str = CONFIG, budgets: dict | None = None,
               requests_path: str = REQUESTS_PATH, call_log: str = CALL_LOG) -> dict:
    b = {**DEFAULT_BUDGETS, **(budgets or {})}
    model = model or llm.MAIN_MODEL
    trace_id = f"tr_{uuid.uuid4().hex[:12]}"

    def note(msg):
        if log:
            log(msg)

    claim = get_claim(claim_number)
    if claim is None:
        raise ValueError(f"no claim {claim_number} in the claim store")
    roster = [claim["claimant_name"]] if claim.get("claimant_name") else []
    loss_date = claim["date_of_loss"]

    # The servers this host starts read these (mcp_config.w12.json ${...}).
    os.makedirs(LOG_DIR, exist_ok=True)
    if not os.path.exists(os.path.join(SNAPSHOT_DIR, "closed_claims.jsonl")):
        write_triage_snapshot()
    os.environ["POLICYLENS_WORDING_VERSION"] = "v1" if version == "w12-v1" else "v2"
    os.environ["POLICYLENS_CALL_LOG"] = os.path.abspath(call_log)
    os.environ["CLAIMS_DATA_DIR"] = os.path.abspath(SNAPSHOT_DIR)

    ctx = {"claim_number": claim["claim_number"], "loss_date": loss_date, "version": version,
           "in_force_check": None, "retrieved": {}}
    tracer = Tracer()
    steps, rejections = [], []
    tokens, cost, api_s, tool_s, throttle_s = 0, 0.0, 0.0, 0.0, 0.0
    t0 = time.perf_counter()
    stop, laps, accepted = None, 0, None
    discovered = []
    intake_steps = []
    tool_name_retries = 0
    reprompts = 0

    registry = ToolRegistry.from_config(config)
    try:
        discovered = registry.names()
        # Every tool the coverage server reports in tools/list is offered, unnamed in
        # this module; the claims-system tools are read by the host at intake instead.
        tools = [t for t in registry.openai_tools()
                 if not t["function"]["name"].startswith(INTAKE_TOOL.split("__")[0] + "__")]
        tools += [referral.REFER_TOOL]
        note(f"[{trace_id}] {version} · discovered over MCP: {discovered} + local refer_to_adjuster")
        notes, intake_step = _intake_notes(registry, claim, roster, tracer, trace_id)
        intake_steps = [intake_step]
        note(f"  intake: {INTAKE_TOOL} -> {len(notes)} notes (redacted before the model)")
        messages = [{"role": "system", "content": SYSTEM},
                    {"role": "user", "content": _fnol_message(claim, notes)}]

        while True:
            elapsed = time.perf_counter() - t0
            checks = [("max_iterations", laps >= b["max_iterations"]),
                      ("max_tokens", tokens >= b["max_tokens"]),
                      ("max_cost_usd", cost >= b["max_cost_usd"]),
                      ("max_wall_s", elapsed >= b["max_wall_s"])]
            fired = next((c for c in checks if c[1]), None)
            if fired:
                stop = f"budget:{fired[0]}"
                note(f"  BUDGET FIRED {fired[0]} -> stopping cleanly")
                break

            laps += 1
            with tracer.span(f"generation:lap{laps}", "generation", model=model, lap=laps) as sp:
                res = llm.chat(messages, model=model, tools=tools, max_tokens=2500,
                               reasoning_effort=REASONING_EFFORT)
                Tracer.record_llm(sp, res)
                sp["attrs"]["tools_requested"] = [tc["name"] for tc in res["tool_calls"]]
            tokens += res["usage"]["total"]
            cost += res["cost_usd"]
            api_s += res["api_s"]
            throttle_s += res["throttle_s"]
            note(f"  lap {laps}: {res['usage']['total']} tok (cum {tokens}, ${cost:.5f}) "
                 f"tools={[tc['name'] for tc in res['tool_calls']] or 'none'}")
            if res["error"]:
                steps.append({"lap": laps, "tool": None, "server": None, "hop": None, "args": {},
                              "is_error": True, "result_preview": str(res["error"])[:300]})
                # gpt-oss sometimes leaks its channel marker into the tool name
                # ("refer_to_adjuster<|channel|>commentary"); Groq rejects the whole
                # generation with tool_use_failed. Retry the lap, at most twice per run,
                # and count it: it is a failure mode, not noise (Week 8: invented_tool_name).
                if "tool_use_failed" in str(res["error"].get("message")) and tool_name_retries < 2:
                    tool_name_retries += 1
                    note(f"  lap {laps}: tool_use_failed (malformed tool name) -> retrying the lap")
                    continue
                stop = "error"
                break
            if not res["tool_calls"]:
                # A triage ends only with an accepted referral. One reminder, carrying the
                # last rejection, then give up (the claim still goes to a person).
                if reprompts < 1:
                    reprompts += 1
                    last = rejections[-1]["errors"] if rejections else []
                    messages.append({"role": "assistant", "content": res["content"] or ""})
                    messages.append({"role": "user", "content":
                                     "Triage ends only with an accepted refer_to_adjuster call. Call it now"
                                     + (", fixing: " + " | ".join(last) if last else "") + "."})
                    note("  no tool call -> one reminder to call refer_to_adjuster")
                    continue
                stop = "no_referral"
                break

            messages.append({
                "role": "assistant", "content": res["content"] or "",
                "tool_calls": [{"id": tc["id"], "type": "function",
                                "function": {"name": tc["name"], "arguments": tc["arguments"]}}
                               for tc in res["tool_calls"]]})

            for tc in res["tool_calls"]:
                args = _parse(tc["arguments"])
                if not isinstance(args, dict):
                    args = {"_raw": tc["arguments"]}
                span_id = f"sp{len(tracer.spans) + 1}"
                ts = time.perf_counter()

                if tc["name"] == "refer_to_adjuster":
                    with tracer.span("tools:refer_to_adjuster", "tools", tool="refer_to_adjuster",
                                     hop="local", server=None) as sp:
                        errors, ref = referral.validate(args, ctx)
                        sp["attrs"]["is_error"] = bool(errors)
                        sp["attrs"]["guard_errors"] = errors
                    tool_s += time.perf_counter() - ts
                    if errors:
                        rejections.append({"lap": laps, "errors": errors})
                        text = "referral rejected: " + " | ".join(errors)
                        note(f"    -> refer_to_adjuster REJECTED: {_short(text, 240)}")
                    else:
                        accepted = ref
                        text = json.dumps({"accepted": True, "referral_id": trace_id})
                        note("    -> refer_to_adjuster ACCEPTED")
                    steps.append({"lap": laps, "tool": "refer_to_adjuster", "server": None, "hop": "local",
                                  "args": args, "is_error": bool(errors), "result_preview": _short(text)})
                    messages.append({"role": "tool", "tool_call_id": tc["id"],
                                     "content": json.dumps({"isError": bool(errors), "text": text},
                                                           ensure_ascii=False)})
                    continue

                stage = "retrieval" if tc["name"].endswith("search_policy_wording") else "tools"
                with tracer.span(f"{stage}:{tc['name']}", stage, tool=tc["name"], hop="mcp") as sp:
                    out = registry.call(tc["name"], args, meta={"trace_id": trace_id, "span_id": span_id})
                    clean, counts = redact_text(out["text"], roster, kinds=PERSONAL_KINDS)
                    sp["attrs"].update({"server": out["server"], "mcp_tool": out["tool"],
                                        "is_error": out["is_error"], "result_sha256": _sha(out["text"]),
                                        "result_chars": len(out["text"]), "redactions": counts})
                    parsed = _parse(out["text"]) if not out["is_error"] else None
                    if tc["name"].endswith("check_coverage_in_force") and isinstance(parsed, dict) \
                            and "in_force" in parsed:
                        ctx["in_force_check"] = parsed
                        sp["attrs"]["in_force"] = parsed.get("in_force")
                    if stage == "retrieval" and isinstance(parsed, dict):
                        context = []
                        for i, p in enumerate(parsed.get("passages") or [], 1):
                            ctx["retrieved"][p["chunk_id"]] = p
                            context.append({"rank": i, "chunk_id": p["chunk_id"],
                                            "form_number": p.get("form_number"), "edition": p.get("edition"),
                                            "clause_id": p.get("clause_id"),
                                            "text_sha256": _sha(p.get("text", ""))})
                        sp["attrs"]["context"] = context
                        sp["attrs"]["loss_date_arg"] = args.get("loss_date")
                tool_s += time.perf_counter() - ts
                steps.append({"lap": laps, "tool": tc["name"], "server": out["server"], "hop": "mcp",
                              "args": args, "is_error": out["is_error"], "result_preview": _short(clean)})
                note(f"    -> {tc['name']} {json.dumps(args, ensure_ascii=False)} "
                     f"{'ERROR ' if out['is_error'] else ''}{_short(clean, 140)}")
                messages.append({"role": "tool", "tool_call_id": tc["id"],
                                 "content": json.dumps({"isError": out["is_error"], "text": clean},
                                                       ensure_ascii=False)})

            if accepted:
                stop = "referred"
                break
            if len(rejections) >= MAX_REJECTIONS:
                stop = "no_referral"
                note("  guard rejected the referral 3 times -> manual triage")
                break
    finally:
        registry.close()

    ref = accepted or referral.fallback_referral(ctx, f"agent stopped ({stop}) without an accepted referral")
    run = {
        "trace_id": trace_id,
        "version": version,
        "model": model,
        "prompt_version": PROMPT_VERSION,
        "prompt_sha256": PROMPT_SHA256,
        "claim_number": claim["claim_number"],
        "loss_date": loss_date,
        "stop_reason": stop,
        "referral": ref,
        "guard_rejections": rejections,
        "intake": intake_steps,          # host steps (not model choices): kept out of `steps`
        "steps": steps,
        "spans": tracer.spans,
        "server_spans": _read_server_spans(trace_id, call_log),
        "laps": laps,
        "tokens": tokens,
        "cost_usd": round(cost, 6),
        "latency_s": round(api_s + tool_s, 3),
        "throttle_s": round(throttle_s, 1),
        "wall_s": round(time.perf_counter() - t0, 3),
        "discovered_tools": discovered,
        "tool_name_retries": tool_name_retries,
        "reasoning_effort": REASONING_EFFORT,
        "budgets": b,
    }
    if write:
        write_request(run, claim, requests_path)
    return run


def write_request(run: dict, claim: dict, path: str = REQUESTS_PATH) -> str:
    """ONE line per FNOL, redacted on write (claim/policy numbers pseudonymised, names,
    addresses and injuries removed). Tool result text is never logged: spans keep
    its SHA-256 and size, wording spans keep chunk ids + editions + text hashes."""
    spans = run["spans"]
    rec = {
        "trace_id": run["trace_id"],
        "schema": "w12-request/1",
        "service": "triage-agent",
        "version": run["version"],
        "model": run["model"],
        "reasoning_effort": run.get("reasoning_effort"),
        "prompt": {"version": run["prompt_version"], "sha256": run["prompt_sha256"]},
        "input": {"claim_ref": claim["claim_number"], "loss_date": run["loss_date"],
                  "fnol": claim.get("fnol_description", "")},
        "discovered_tools": run["discovered_tools"],
        "intake": [{k: s[k] for k in ("lap", "tool", "server", "hop", "args", "is_error")}
                   for s in run.get("intake") or []],
        "steps": [{k: s[k] for k in ("lap", "tool", "server", "hop", "args", "is_error")} for s in run["steps"]],
        "spans": spans,
        "server_spans": run["server_spans"],
        "referral": run["referral"],
        "guard_rejections": run["guard_rejections"],
        "tool_name_retries": run["tool_name_retries"],
        "stop_reason": run["stop_reason"],
        "totals": {
            "latency_ms": round(sum(s["latency_ms"] for s in spans), 1),
            "throttle_ms": round(sum(s["throttle_ms"] for s in spans), 1),
            "tokens": sum(s["tokens"]["total"] for s in spans),
            "cost_usd": round(sum(s["cost_usd"] for s in spans), 8),
            "by_stage": stage_totals(spans),
        },
    }
    names = [claim["claimant_name"]] if claim.get("claimant_name") else None
    return EventWriter(path).write(rec, known_names=names)
