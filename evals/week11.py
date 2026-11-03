#!/usr/bin/env python3
"""
Week 11 — production observability, cost, and the failure -> test loop.

The service (src/triage_service.py -> src/workflow.py, the version Week 7 shipped)
writes one redacted line per request, with spans, to traces/week11/requests.jsonl.

    python evals/week11.py traffic                       # replay three desk days through production (workflow-v2)
    python evals/week11.py plant --n 1                   # SQUADMATE: plant one bad coverage answer yesterday, sealed
    python evals/week11.py drill start --n 1             # FINDER: start the clock
    python evals/week11.py find --day yesterday ...      # slices: time / user / prompt version / input type / cost outlier
    python evals/week11.py show TRACE_ID                 # one request, every span
    python evals/week11.py drill found --n 1 TRACE_ID    # stop the clock, check the seal, print mm:ss
    python evals/week11.py trace TRACE_ID                # -> reports/week11/trace.json
    python evals/week11.py case TRACE_ID                 # -> evals/cases/week11_regressions.jsonl
    python evals/week11.py suite --version V --label L   # 10 Week-6 cases + regression cases, pass counts
    python evals/week11.py diff before after             # case by case: regressed / fixed / still failing
    python evals/week11.py cost TRACE_ID                 # -> reports/week11/cost_by_stage.md
    python evals/week11.py tenx                          # -> reports/week11/tenx.md
    python evals/week11.py outcomes                      # bonus: claims-system decisions -> traces/week11/outcomes.jsonl
    python evals/week11.py find ... --uncited-outcome    # bonus: answers missing an exclusion the adjuster relied on

While a drill is open, every find / show call is appended to its session log with a
timestamp, so time-to-find is read off the log, not remembered.
"""

import argparse
import hashlib
import json
import os
import random
import re
import secrets
import statistics
import sys
import time
from datetime import datetime, timedelta, timezone

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(ROOT, "src"))

from console import enable_utf8  # noqa: E402

enable_utf8()

from observability import (REQUESTS_PATH, cost_fence, read_requests, resolve_day,  # noqa: E402
                           slice_rows, sort_log)

OUT = os.path.join(ROOT, "reports", "week11")
PLANTS = os.path.join(OUT, "plants")
WEEK6_CASES = os.path.join(ROOT, "evals", "cases", "week6_cases.jsonl")
WEEK6_POOL = os.path.join(ROOT, "evals", "cases", "week6_pool.jsonl")
REGRESSIONS = os.path.join(ROOT, "evals", "cases", "week11_regressions.jsonl")
N_WEEK6 = 10          # the same 10 Week-6 cases Week 10 raced
TPM = 8000
SEED = "2026-11-03"   # Week 5 rule: the seed is the date the traffic was generated, no re-rolls

# Replay clock (UTC). Tuesday is "today", so Monday is "yesterday".
DAYS = [("2026-10-30", 14, "06:00", "16:00"),   # Friday
        ("2026-11-02", 18, "06:00", "16:00"),   # Monday  (yesterday)
        ("2026-11-03", 8, "06:00", "08:40")]    # Tuesday (this morning)
RECHECKS = 4          # claims an adjuster looked at again on a later day


def _jsonl(path):
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as fh:
        return [json.loads(l) for l in fh if l.strip()]


def _write(name, text):
    os.makedirs(OUT, exist_ok=True)
    with open(os.path.join(OUT, name), "w", encoding="utf-8") as fh:
        fh.write(text)
    print(f"wrote reports/week11/{name}")


def _now():
    return datetime.now(timezone.utc)


def _warm_up():
    from tools import search_policy
    search_policy("warm up the embedding model and BM25 index")


def _pace(tokens):
    """Let the per-minute token window refill. Not timed."""
    time.sleep(min(70, tokens / TPM * 60))


def _adjuster(claim) -> str | None:
    notes = claim.get("adjuster_notes") or []
    return notes[0]["author"] if notes else None


# -- traffic ------------------------------------------------------------------

def _slot(rng, day, start, end):
    h0, m0 = map(int, start.split(":"))
    h1, m1 = map(int, end.split(":"))
    sec = rng.randint(h0 * 3600 + m0 * 60, h1 * 3600 + m1 * 60)
    ms = rng.randint(0, 999)
    return f"{day}T{sec // 3600:02d}:{sec % 3600 // 60:02d}:{sec % 60:02d}.{ms:03d}+00:00"


def traffic_plan():
    """Every open and closed claim triaged once over the three days, plus a few
    re-checks. Deterministic from SEED; never written to disk, so the log cannot be
    diffed against a plan to spot a planted line."""
    from claim_store import load_claims
    rng = random.Random(SEED)
    claims = sorted(load_claims())
    rng.shuffle(claims)
    users = sorted({_adjuster(c) for c in load_claims().values()} - {None})
    plan, i = [], 0
    for day, n, start, end in DAYS:
        for cn in claims[i:i + n]:
            plan.append((day, start, end, cn))
        i += n
    for cn in rng.sample(claims[:DAYS[0][1] + DAYS[1][1]], RECHECKS):  # re-checked on a later day
        first_day = next(d for d, _s, _e, c in plan if c == cn)
        later = [d for d in DAYS if d[0] > first_day]
        day, _n, start, end = rng.choice(later)
        plan.append((day, start, end, cn))
    rows = []
    for day, start, end, cn in plan:
        c = load_claims()[cn]
        rows.append({"ts_utc": _slot(rng, day, start, end), "claim_number": cn,
                     "user": _adjuster(c) or rng.choice(users),
                     "channel": "mobile" if rng.random() < 0.25 else "adjuster_console"})
    return sorted(rows, key=lambda r: r["ts_utc"])


def cmd_traffic(args):
    from triage_service import handle
    done = {r["ts_utc"] for r in read_requests()}
    todo = [p for p in traffic_plan() if p["ts_utc"] not in done]
    print(f"{len(done)} requests already in the log, {len(todo)} to replay (production = workflow-v2)")
    _warm_up()
    for n, p in enumerate(todo, 1):
        rec, run = handle(p["claim_number"], user=p["user"], channel=p["channel"],
                          ts_utc=p["ts_utc"], version="workflow-v2")
        # Progress only: whoever later runs the drill must not have watched the log being written.
        print(f"  [{n:>2}/{len(todo)}] {rec['totals']['tokens']} tok", flush=True)
        err = rec.get("error") or {}
        if err.get("quota"):
            sys.exit("daily token quota hit; re-run `traffic` later to resume")
        _pace(rec["totals"]["tokens"])
    sort_log()


# -- plant (squadmate) ----------------------------------------------------------

def _seal_path(n):
    return os.path.join(PLANTS, f"plant{n}.seal.json")


def _exclusion_codes(items) -> set[str]:
    out = set()
    for e in items or []:
        out |= {f"E-{m}" for m in re.findall(r"E\W?(\d{2})", str(e))}
    return out


def cmd_plant(args):
    """Plant ONE real bad coverage answer from the production version in yesterday's
    log: a claim the adjuster denied (or partly denied) under an exclusion, answered
    'covered' with that exclusion uncited. Prints nothing that identifies it."""
    from triage_service import handle
    from observability import write_record
    from claim_store import get_claim
    if os.path.exists(_seal_path(args.n)):
        sys.exit(f"plant {args.n} already sealed")
    rng = random.SystemRandom()
    # not a suite claim, and not one an earlier drill already turned into a regression case
    suite = {c["claim_number"] for c in _week6_suite() + _jsonl(REGRESSIONS)}
    pool = [c for c in _jsonl(WEEK6_POOL) if c["expected_decision"] in ("denied", "partially_covered")
            and c["expected_exclusion_ids"] and c["claim_number"] not in suite]
    rng.shuffle(pool)
    day = resolve_day("yesterday")
    taken = {r["ts_utc"] for r in read_requests()}
    _warm_up()
    for k, case in enumerate(pool, 1):
        claim = get_claim(case["claim_number"])
        rec, _run = handle(case["claim_number"], user=_adjuster(claim), version="workflow-v2", write=False,
                           channel="mobile" if rng.random() < 0.25 else "adjuster_console")
        o = rec["output"]
        bad = (o["decision"] in ("covered", "partially_covered")
               and not (_exclusion_codes(o["exclusion_ids"]) & set(case["expected_exclusion_ids"])))
        print(f"  candidate {k}: {'BAD - planting' if bad else 'answered correctly, discarded'}", flush=True)
        if not bad:
            _pace(rec["totals"]["tokens"])
            continue
        ts = _slot(rng, day, "06:00", "16:00")
        while ts in taken:
            ts = _slot(rng, day, "06:00", "16:00")
        rec["ts_utc"] = ts
        tid = write_record(rec, claim["claimant_name"])
        sort_log()
        nonce = secrets.token_hex(16)
        os.makedirs(PLANTS, exist_ok=True)
        with open(_seal_path(args.n), "w", encoding="utf-8") as fh:
            json.dump({"plant": args.n, "sealed_utc": _now().isoformat(timespec="seconds"),
                       "planted_by": args.by, "nonce": nonce,
                       "trace_sha256": hashlib.sha256((nonce + tid).encode()).hexdigest(),
                       "complaint": "an adjuster says it told a claimant something was covered when "
                                    "the policy excludes it, sometime yesterday"}, fh, indent=2)
        print(f"planted 1 bad coverage answer in yesterday's log; seal -> {os.path.relpath(_seal_path(args.n), ROOT)}")
        return
    sys.exit("no candidate produced a bad answer; nothing planted")


# -- drill (finder) -------------------------------------------------------------

def _session_path(n):
    return os.path.join(OUT, f"drill{n}_session.jsonl")


def _open_session():
    for n in (1, 2, 3):
        p = _session_path(n)
        ev = _jsonl(p)
        if ev and not any(e["event"] == "found" for e in ev):
            return p
    return None


def _session_log(event, **kw):
    p = _open_session()
    if p:
        with open(p, "a", encoding="utf-8") as fh:
            fh.write(json.dumps({"event": event, "ts": _now().isoformat(timespec="seconds"), **kw}) + "\n")


def _mmss(seconds):
    return f"{int(seconds) // 60:02d}:{int(seconds) % 60:02d}"


def cmd_drill(args):
    p = _session_path(args.n)
    if args.action == "start":
        if not os.path.exists(_seal_path(args.n)):
            sys.exit(f"no plant {args.n} sealed yet; the squadmate plants first")
        if os.path.exists(p):
            sys.exit(f"drill {args.n} already started")
        os.makedirs(OUT, exist_ok=True)
        with open(p, "w", encoding="utf-8") as fh:
            fh.write(json.dumps({"event": "start", "ts": _now().isoformat(timespec="seconds"),
                                 "finder": args.by, "log_lines": len(read_requests())}) + "\n")
        print(f"drill {args.n} started; complaint: {json.load(open(_seal_path(args.n)))['complaint']}")
        return
    seal = json.load(open(_seal_path(args.n), encoding="utf-8"))
    ok = hashlib.sha256((seal["nonce"] + args.trace_id).encode()).hexdigest() == seal["trace_sha256"]
    ev = _jsonl(p)
    start = datetime.fromisoformat(ev[0]["ts"])
    if not ok:
        _session_log("wrong_guess", trace_id=args.trace_id)
        print(f"{args.trace_id}: NOT the planted answer. Clock still running "
              f"({_mmss((_now() - start).total_seconds())}).")
        return
    now = _now()
    with open(p, "a", encoding="utf-8") as fh:
        fh.write(json.dumps({"event": "found", "ts": now.isoformat(timespec="seconds"),
                             "trace_id": args.trace_id, "seal_match": True,
                             "time_to_find": _mmss((now - start).total_seconds())}) + "\n")
    print(f"{args.trace_id}: MATCHES the seal. time-to-find {_mmss((now - start).total_seconds())}")


# -- bonus: the outcome stream ----------------------------------------------------

OUTCOMES_PATH = os.path.join(ROOT, "traces", "week11", "outcomes.jsonl")
# "denied under E-41", "denied under NG-1106 E-93", "seepage under exclusion E-41";
# NOT "E-51 does not apply" or "this is not E-42".
_RELIED_ON = re.compile(r"\bunder\s+(?:exclusion\s+)?(?:NG-\d{4}\s+)?(E-\d{2})\b", re.I)


def cmd_outcomes(_args):
    """Bonus: the claims system's decision events, one per decided claim, keyed by the
    SAME claim_ref pseudonym as the request log. Codes only, no note text."""
    from claim_store import load_claims
    from redaction import assert_clean, redact_text
    rows = []
    for cn, c in sorted(load_claims().items()):
        notes = c.get("adjuster_notes") or []
        if not notes or not notes[-1]["text"].startswith("Decision:"):
            continue
        d = notes[-1]["text"]
        rows.append({"event": "claim_decided", "claim_ref": redact_text(cn)[0],
                     "decided_on": notes[-1]["date"], "adjuster": notes[-1]["author"],
                     "adjuster_exclusion_ids": sorted(set(_RELIED_ON.findall(d)))})
    pool = {redact_text(c["claim_number"])[0]: c for c in _jsonl(WEEK6_POOL)}
    off = [r["claim_ref"] for r in rows if sorted(pool[r["claim_ref"]]["expected_exclusion_ids"])
           != r["adjuster_exclusion_ids"]]
    with open(OUTCOMES_PATH, "w", encoding="utf-8") as fh:
        for r in rows:
            line = json.dumps(r)
            if assert_clean(line):
                sys.exit(f"refusing to write an outcome line with an identifier: {line}")
            fh.write(line + "\n")
    print(f"{len(rows)} claim_decided events -> {os.path.relpath(OUTCOMES_PATH, ROOT)}; "
          f"parser disagrees with the Week 6 answer key on {len(off)} of {len(rows)}")


def _outcomes():
    return {o["claim_ref"]: o for o in _jsonl(OUTCOMES_PATH)}


def _uncited(r, outcomes):
    o = outcomes.get(r["input"]["claim_ref"])
    if not o:
        return None
    return sorted(set(o["adjuster_exclusion_ids"]) - _exclusion_codes(r["output"]["exclusion_ids"]))


# -- find / show ----------------------------------------------------------------

def _short_ctx(r):
    out = []
    for s in r["spans"]:
        for c in s["attrs"].get("context") or []:
            out.append(f"{c['form_number'][3:]}:{(c['clause_id'] or '?').replace('CLAUSE-', '').replace('EXCLUSION-TABLE', 'EXCL')}")
    return ",".join(out)


def cmd_find(args):
    rows = read_requests()
    sel = slice_rows(rows, day=args.day, since=args.since, until=args.until, user=args.user,
                     prompt_version=args.prompt_version, input_type_has=args.input_type,
                     decision=args.decision, cost_outlier=args.cost_outlier, grep=args.grep)
    outcomes = _outcomes() if args.uncited_outcome else {}
    if args.uncited_outcome:  # bonus index: the answer left out an exclusion the adjuster relied on
        sel = [r for r in sel if _uncited(r, outcomes)]
    _session_log("find", argv=sys.argv[2:], rows=len(sel))
    print(f"{len(sel)} of {len(rows)} requests"
          + (f"  (cost fence ${cost_fence(rows):.6f})" if args.cost_outlier else ""))
    for r in sel:
        o = r["output"]
        excl = ",".join(o["exclusion_ids"]) or "-"
        pay = "-" if o["payable"] is None else f"{o['payable']:.0f}"
        print(f"{r['ts_utc'][5:16]} {r['trace_id']} {r['user']} {r['prompt']['version']} "
              f"{r['input']['type']:<20} {str(o['decision']):<17} excl={excl:<8} pay={pay:<6} "
              f"${r['totals']['cost_usd']:.6f} {r['totals']['latency_ms']:>7.0f}ms"
              + (f"  adjuster relied on {','.join(_uncited(r, outcomes))}, uncited" if outcomes else ""))
        if args.wide:
            print(f"      fnol: {r['input']['fnol']}")
            print(f"      ctx : {_short_ctx(r)}")
            print(f"      why : {o['reason'][:220]}")


def cmd_show(args):
    r = next((x for x in read_requests() if x["trace_id"] == args.trace_id), None)
    if not r:
        sys.exit(f"no request {args.trace_id}")
    _session_log("show", trace_id=args.trace_id)
    print(json.dumps({k: r[k] for k in ("trace_id", "ts_utc", "user", "channel", "prompt", "input",
                                        "output", "retrieval")}, indent=2, ensure_ascii=False))
    print(f"\n{'span':<26}{'stage':<11}{'latency_ms':>11}{'tokens':>8}{'cost_usd':>12}")
    for s in r["spans"]:
        print(f"{s['name']:<26}{s['stage']:<11}{s['latency_ms']:>11.1f}{s['tokens']['total']:>8}"
              f"{s['cost_usd']:>12.8f}")
        for c in s["attrs"].get("context") or []:
            print(f"    ctx {c['rank']}: {c['chunk_id']}  {c['form_number']} {c['clause_id']}")


# -- trace / case ---------------------------------------------------------------

def _request(trace_id):
    r = next((x for x in read_requests() if x["trace_id"] == trace_id), None)
    if not r:
        sys.exit(f"no request {trace_id} in {os.path.relpath(REQUESTS_PATH, ROOT)}")
    return r


def cmd_trace(args):
    r = _request(args.trace_id)
    out = os.path.join(OUT, args.out)
    os.makedirs(OUT, exist_ok=True)
    with open(out, "w", encoding="utf-8") as fh:
        json.dump(r, fh, indent=2, ensure_ascii=False)
        fh.write("\n")
    print(f"wrote {os.path.relpath(out, ROOT)}")


def _claim_for_ref(claim_ref):
    """The log holds a pseudonym; the claims system of record maps it back."""
    from claim_store import load_claims
    from redaction import redact_text
    for cn in load_claims():
        if redact_text(cn)[0] == claim_ref:
            return cn
    sys.exit(f"no claim maps to {claim_ref}")


def cmd_case(args):
    from claim_store import get_claim
    r = _request(args.trace_id)
    cn = _claim_for_ref(r["input"]["claim_ref"])
    pool = {c["claim_number"]: c for c in _jsonl(WEEK6_POOL)}
    if cn not in pool:
        sys.exit(f"{cn} has no adjuster decision in the Week 6 pool; write the expectation by hand")
    src = pool[cn]
    if r["input"]["notes"]["sha256"] != _notes_sha(cn):
        sys.exit("the claim file changed since the trace was written; the case would not be verbatim")
    existing = _jsonl(REGRESSIONS)
    if any(c["source_trace_id"] == args.trace_id for c in existing):
        sys.exit(f"{args.trace_id} is already a case")
    case = {
        "claim_number": cn, "mode": args.mode, "date_of_loss": get_claim(cn)["date_of_loss"],
        "expected_decision": src["expected_decision"], "expected_excess": src["expected_excess"],
        "expected_exclusion_ids": src["expected_exclusion_ids"],
        "expected_payable": args.payable,
        "is_regression": True, "source": "week11 production log",
        "source_trace_id": args.trace_id, "source_ts_utc": r["ts_utc"],
        "source_prompt_version": r["prompt"]["version"],
        "source_notes_sha256": r["input"]["notes"]["sha256"],
        "source_output": {k: r["output"][k] for k in ("decision", "exclusion_ids", "payable")},
        "why": args.why,
        "id": f"W11-{len(existing) + 1}",
    }
    with open(REGRESSIONS, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(case, ensure_ascii=False) + "\n")
    print(f"case {case['id']} ({cn}) -> {os.path.relpath(REGRESSIONS, ROOT)}")


def _notes_sha(cn):
    from observability import sha256
    from tools import get_claim
    return sha256(json.dumps(get_claim(cn).get("adjuster_notes") or [], ensure_ascii=False, sort_keys=True))


# -- suite ----------------------------------------------------------------------

def _week6_suite():
    return sorted(_jsonl(WEEK6_CASES), key=lambda c: c["id"])[:N_WEEK6]


EXPECTED = {"denied": "excluded", "covered": "covered", "partially_covered": "partially_covered"}


def grade_case(case, run) -> dict:
    """Code-checked, from the case's own fields (Week 6 rule: what code can check, code
    checks): decision, every exclusion the adjuster relied on, the deductible actually
    applied, and the payable where the case states one."""
    a = run.get("answer") or {}
    why = []
    want = EXPECTED[case["expected_decision"]]
    if a.get("decision") != want:
        why.append(f"decision {a.get('decision')} != {want}")
    missing = [e for e in case["expected_exclusion_ids"] if e not in _exclusion_codes(a.get("exclusion_ids"))]
    if missing:
        why.append(f"missing {'/'.join(missing)}")
    if want != "excluded":
        ded = (run.get("payout") or {}).get("deductible_applied")
        if ded is None or abs(float(ded) - case["expected_excess"]) > 0.5:
            why.append(f"deductible {ded} != {case['expected_excess']:.0f}")
    if case.get("expected_payable") is not None:
        pay = a.get("payable")
        if not isinstance(pay, (int, float)) or abs(float(pay) - case["expected_payable"]) > 1:
            why.append(f"payable {pay} != {case['expected_payable']:.0f}")
    return {"pass": not why, "why": "; ".join(why) or "ok"}


def cmd_suite(args):
    from workflow import run_workflow
    cases = [{**c, "suite": "week6"} for c in _week6_suite()] + \
            [{**c, "suite": "week11"} for c in _jsonl(REGRESSIONS)]
    _warm_up()
    rows = []
    for c in cases:
        run = run_workflow(c["claim_number"], version=args.version)
        g = grade_case(c, run)
        a = run.get("answer") or {}
        rows.append({"case": c["id"], "suite": c["suite"], "claim_number": c["claim_number"],
                     "expected": f"{EXPECTED[c['expected_decision']]} {'/'.join(c['expected_exclusion_ids'])}".strip(),
                     "got": {"decision": a.get("decision"), "exclusion_ids": a.get("exclusion_ids"),
                             "payable": a.get("payable"),
                             "deductible_applied": (run.get("payout") or {}).get("deductible_applied")},
                     "pass": g["pass"], "why": g["why"], "prompt": run["prompt"],
                     "tokens": run["tokens"], "cost_usd": run["cost_usd"], "latency_s": run["latency_s"],
                     "spans": run["spans"], "error": (run["spans"][-1]["attrs"].get("error")
                                                      if run["spans"] else None)})
        print(f"  {str(c['id']):>5} {c['claim_number']} {'PASS' if g['pass'] else 'FAIL'}  {g['why']}", flush=True)
        if any((s["attrs"].get("error") or {}).get("quota") for s in run["spans"]):
            sys.exit("daily token quota hit; this suite run is void")
        _pace(run["tokens"])
    with open(os.path.join(OUT, f"suite_{args.label}.jsonl"), "w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    w6 = [r for r in rows if r["suite"] == "week6"]
    w11 = [r for r in rows if r["suite"] == "week11"]
    lines = [f"Week 11 suite, label={args.label}, workflow version={args.version}, "
             f"run {_now().isoformat(timespec='seconds')}",
             f"cases: the first {N_WEEK6} Week-6 cases (same 10 as Week 10) + "
             f"{len(w11)} regression case(s) from evals/cases/week11_regressions.jsonl", "",
             f"{'case':>6}  {'claim':<15} {'expected':<26} {'got':<38} result",
             ]
    for r in rows:
        g = r["got"]
        got = f"{g['decision']} {'/'.join(sorted(_exclusion_codes(g['exclusion_ids']))) or '-'} pay={g['payable']}"
        lines.append(f"{str(r['case']):>6}  {r['claim_number']:<15} {r['expected']:<26} {got:<38} "
                     f"{'PASS' if r['pass'] else 'FAIL  ' + r['why']}")
    passed = sum(r["pass"] for r in rows)
    lines += ["",
              f"Week-6 cases      : {sum(r['pass'] for r in w6)}/{len(w6)}",
              f"regression cases  : {sum(r['pass'] for r in w11)}/{len(w11)}",
              f"SUITE             : {passed}/{len(rows)}  {'GREEN' if passed == len(rows) else 'RED'}",
              f"tokens {sum(r['tokens'] for r in rows):,}  cost ${sum(r['cost_usd'] for r in rows):.5f}"]
    _write(f"suite_{args.label}.txt", "\n".join(lines) + "\n")
    print("\n".join(lines))


def cmd_diff(args):
    """Case-by-case before -> after, so a regression elsewhere cannot hide in a total."""
    b = {str(r["case"]): r for r in _jsonl(os.path.join(OUT, f"suite_{args.before}.jsonl"))}
    a = {str(r["case"]): r for r in _jsonl(os.path.join(OUT, f"suite_{args.after}.jsonl"))}
    groups = {"regressed (PASS -> FAIL)": [], "fixed (FAIL -> PASS)": [], "still failing": [], "still passing": []}
    for k in a:
        was, now = b[k]["pass"], a[k]["pass"]
        key = ("still passing" if was and now else "regressed (PASS -> FAIL)" if was else
               "fixed (FAIL -> PASS)" if now else "still failing")
        groups[key].append(f"{k} {a[k]['claim_number']}" + ("" if now else f" ({a[k]['why']})"))
    vb = next(iter(b.values()))["prompt"]["version"]
    va = next(iter(a.values()))["prompt"]["version"]
    lines = [f"suite {args.before} ({vb}) -> {args.after} ({va}): "
             f"{sum(r['pass'] for r in b.values())}/{len(b)} -> {sum(r['pass'] for r in a.values())}/{len(a)}"]
    for g, items in groups.items():
        lines.append(f"  {g:<26} {len(items):>2}  {'; '.join(items) or '-'}")
    _write(f"suite_diff_{args.before}_{args.after}.txt", "\n".join(lines) + "\n")
    print("\n".join(lines))


# -- cost by stage ----------------------------------------------------------------

BLOCK_STAGE = {"system": "generation", "template_and_chat_format": "generation",
               "claim_file": "tools", "policy_passages": "retrieval", "exclusion_schedules": "retrieval"}


def attribute(spans) -> dict:
    """Direct cost per stage (what each stage is billed for) and attributed cost (the
    generation bill split by which stage put each input token into the prompt)."""
    import llm
    direct = {st: {"cost_usd": 0.0, "latency_ms": 0.0, "tokens": 0} for st in ("retrieval", "generation", "tools")}
    attr = {st: {"input_tokens": 0, "output_tokens": 0, "cost_usd": 0.0} for st in direct}
    for s in spans:
        d = direct[s["stage"]]
        d["cost_usd"] += s["cost_usd"]
        d["latency_ms"] += s["latency_ms"]
        d["tokens"] += s["tokens"]["total"]
        if s["stage"] != "generation":
            continue
        p_in, p_out = llm.PRICES.get(s["attrs"].get("model"), llm.PRICES[llm.MAIN_MODEL])
        for block, n in (s["attrs"].get("prompt_tokens_by_block") or {}).items():
            st = BLOCK_STAGE[block]
            attr[st]["input_tokens"] += n
            attr[st]["cost_usd"] += n * p_in / 1e6
        attr["generation"]["output_tokens"] += s["tokens"]["completion"]
        attr["generation"]["cost_usd"] += s["tokens"]["completion"] * p_out / 1e6
    return {"direct": direct, "attributed": attr}


def _mean_attr(spans_list):
    acc = None
    for spans in spans_list:
        a = attribute(spans)
        if acc is None:
            acc = json.loads(json.dumps(a))
            continue
        for kind in a:
            for st in a[kind]:
                for k in a[kind][st]:
                    acc[kind][st][k] += a[kind][st][k]
    n = len(spans_list)
    for kind in acc:
        for st in acc[kind]:
            for k in acc[kind][st]:
                acc[kind][st][k] /= n
    return acc


def _stage_table(a, title):
    d, t = a["direct"], a["attributed"]
    tot_d = sum(v["cost_usd"] for v in d.values())
    tot_t = sum(v["cost_usd"] for v in t.values())
    rows = [f"**{title}**", "",
            "| Stage | Latency (ms) | Billed tokens | Direct cost | Prompt tokens it put in front of the model | Attributed cost | Share |",
            "|---|---:|---:|---:|---:|---:|---:|"]
    for st in ("retrieval", "generation", "tools"):
        tokens_in = t[st]["input_tokens"] + (t[st]["output_tokens"] if st == "generation" else 0)
        label = (f"{t[st]['input_tokens']:,.0f} in + {t[st]['output_tokens']:,.0f} out"
                 if st == "generation" else f"{t[st]['input_tokens']:,.0f}")
        rows.append(f"| {st} | {d[st]['latency_ms']:,.0f} | {d[st]['tokens']:,.0f} | ${d[st]['cost_usd']:.6f} | "
                    f"{label} | ${t[st]['cost_usd']:.6f} | {t[st]['cost_usd'] / tot_t:.0%} |")
    rows.append(f"| **total** | {sum(v['latency_ms'] for v in d.values()):,.0f} | "
                f"{sum(v['tokens'] for v in d.values()):,.0f} | **${tot_d:.6f}** | | **${tot_t:.6f}** | 100% |")
    return rows


def cmd_cost(args):
    r = _request(args.trace_id)
    lines = ["# Cost per query, by stage", "",
             f"Request `{r['trace_id']}` ({r['ts_utc']}, {r['prompt']['version']}, {r['model']}). "
             "Prices: `src/llm.py` (gpt-oss-120b $0.15 / $0.75 per 1M input / output tokens).", "",
             "Two views. **Direct** is what each stage is billed for. Retrieval (MiniLM + BM25) and the tools "
             "(claims system, payout arithmetic) run locally, so they bill $0. **Attributed** splits the one "
             "model call's bill by the stage that put each prompt token there, so a saving can be traced to "
             "a stage. Prompt blocks are counted with o200k_base; `template_and_chat_format` is the provider's "
             "`prompt_tokens` minus the counted blocks.", "",
             "## Spans of this request", "",
             "| Span | Stage | Latency (ms) | Prompt tok | Completion tok | Cost (USD) |", "|---|---|---:|---:|---:|---:|"]
    for s in r["spans"]:
        lines.append(f"| `{s['name']}` | {s['stage']} | {s['latency_ms']:,.1f} | {s['tokens']['prompt']:,} | "
                     f"{s['tokens']['completion']:,} | ${s['cost_usd']:.8f} |")
    gen = next(s for s in r["spans"] if s["stage"] == "generation")
    lines += ["", "Prompt tokens of `generation:decide`, by block: " + ", ".join(
        f"{k} {v:,}" for k, v in gen["attrs"]["prompt_tokens_by_block"].items()) + ".", ""]
    lines += _stage_table(attribute(r["spans"]), "This request") + [""]
    day = r["ts_utc"][:10]
    same_day = [x for x in read_requests() if x["ts_utc"].startswith(day) and x["totals"]["tokens"]]
    lines += _stage_table(_mean_attr([x["spans"] for x in same_day]),
                          f"Mean per query, all {len(same_day)} answered requests on {day}") + [""]
    after = _jsonl(os.path.join(OUT, f"suite_{args.after}.jsonl")) if args.after else []
    before = _jsonl(os.path.join(OUT, f"suite_{args.before}.jsonl")) if args.before else []
    if after and before:
        cn = _claim_for_ref(r["input"]["claim_ref"])
        b = next((x for x in before if x["claim_number"] == cn), None)
        a = next((x for x in after if x["claim_number"] == cn), None)
        lines += ["## After the fix", ""]
        if b and a:
            lines += _stage_table(attribute(b["spans"]), f"Same claim, suite run before the fix ({b['prompt']['version']})") + [""]
            lines += _stage_table(attribute(a["spans"]), f"Same claim, suite run after the fix ({a['prompt']['version']})") + [""]
        mb = _mean_attr([x["spans"] for x in before if x["tokens"]])
        ma = _mean_attr([x["spans"] for x in after if x["tokens"]])
        tb = sum(v["cost_usd"] for v in mb["attributed"].values())
        ta = sum(v["cost_usd"] for v in ma["attributed"].values())
        lines += [f"Mean over the {len(after)} suite cases: ${tb:.6f} -> ${ta:.6f} per query "
                  f"({(ta - tb) / tb:+.0%}). By stage (attributed): " + ", ".join(
                      f"{st} ${mb['attributed'][st]['cost_usd']:.6f} -> ${ma['attributed'][st]['cost_usd']:.6f}"
                      for st in ("retrieval", "generation", "tools")) + ".", ""]
    _write("cost_by_stage.md", "\n".join(lines))


# -- 10x ------------------------------------------------------------------------

def cmd_tenx(args):
    import llm
    rows = read_requests()
    day = resolve_day(args.day)
    today = [r for r in rows if r["ts_utc"].startswith(day)]
    answered = [r for r in today if r["totals"]["tokens"]]
    after = [x for x in _jsonl(os.path.join(OUT, f"suite_{args.after}.jsonl")) if x["tokens"]] if args.after else []
    tok_req = statistics.mean(x["tokens"] for x in after) if after else statistics.mean(r["totals"]["tokens"] for r in answered)
    cost_req = statistics.mean(x["cost_usd"] for x in after) if after else statistics.mean(r["totals"]["cost_usd"] for r in answered)
    share = len(answered) / len(today)          # needs_info requests make no model call
    n = len(today)
    lat = sorted(r["totals"]["latency_ms"] / 1000 for r in answered)
    p50, p99 = statistics.median(lat), lat[-1]
    # busiest hour of the day, as a per-minute rate
    hours = {}
    for r in answered:
        hours[r["ts_utc"][11:13]] = hours.get(r["ts_utc"][11:13], 0) + 1
    peak_h = max(hours.values())
    lim = {"tpm": TPM, "tpd": 200_000, "rpd": 1000}
    x10 = {"requests_day": 10 * n, "tokens_day": 10 * n * share * tok_req,
           "peak_tpm": 10 * peak_h * tok_req / 60, "cost_day": 10 * n * share * cost_req}
    tpd_breaks_at = lim["tpd"] / (n * share * tok_req)
    src = f"suite_{args.after}" if after else "production log"
    detail = [
        "# What breaks first at 10x", "",
        f"**Rate limit, the tokens-per-day cap: 10x today's {n} claims is {x10['tokens_day']:,.0f} tokens/day "
        f"against Groq's {lim['tpd']:,} TPD for gpt-oss-120b ({x10['tokens_day'] / lim['tpd']:.1f}x the cap, "
        f"reached at {tpd_breaks_at:.1f}x today's volume), while cost is only ${x10['cost_day']:.2f}/day.**", "",
        "## The numbers", "",
        f"- Today's volume: **{n} triage requests on {day}** (the last full desk day in `traces/week11/requests.jsonl`), "
        f"{len(answered)} of them with a model call"
        + (f" (the other {n - len(answered)} were `needs_info` with no notes, no model call)." if n > len(answered) else "."),
        f"- Per answered request: **{tok_req:,.0f} tokens** and **${cost_req:.6f}** (from {src}"
        + (", i.e. after the workflow-v3 fix, which is what would ship)" if after else ")") + ".",
        f"- Latency today: p50 {p50:.2f} s, p99 {p99:.2f} s (model + tool time; nearest-rank p99 = slowest).",
        f"- Limits, read from Groq's response headers on 2026-11-03: `x-ratelimit-limit-tokens: 8000` (per minute), "
        f"`x-ratelimit-limit-requests: 1000` (per day). Tokens per day: 200,000 for gpt-oss-120b (the free-tier cap "
        f"that stopped Week 10's first squad run; see `reports/week10/README.md`).", "",
        "| At 10x | Value | Limit | Headroom |", "|---|---:|---:|---:|",
        f"| tokens / day | {x10['tokens_day']:,.0f} | {lim['tpd']:,} TPD | **{lim['tpd'] / x10['tokens_day']:.2f}x (breaks)** |",
        f"| tokens / minute, busiest hour ({peak_h} requests) | {x10['peak_tpm']:,.0f} | {lim['tpm']:,} TPM | {lim['tpm'] / x10['peak_tpm']:.1f}x |",
        f"| requests / day | {x10['requests_day']:,} | {lim['rpd']:,} RPD | {lim['rpd'] / x10['requests_day']:.1f}x |",
        f"| cost / day | ${x10['cost_day']:.2f} | none set | n/a |",
        f"| latency | p99 {p99:.2f} s per request | n/a | does not depend on volume until a limit throttles |", "",
        "Why the token-per-day cap and not the per-minute one: requests arrive spread over a ten-hour desk day, so even "
        "the busiest hour at 10x stays under the 8,000-token minute. The daily total does not: "
        f"the quota runs out after about {lim['tpd'] / (x10['tokens_day'] / 10):.1f} hours of a 10-hour day. "
        "`src/llm.py` fails fast on the daily cap, so every claim after that point gets no answer at all, not a "
        "slow one. Cost is the last thing to break: 10x is still cents a day.", ""]
    _write("tenx.md", "\n".join(detail))
    print(detail[2])


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("traffic")
    p = sub.add_parser("plant"); p.add_argument("--n", type=int, default=1)
    p.add_argument("--by", default="squadmate (scripted planter)")
    p = sub.add_parser("drill"); p.add_argument("action", choices=["start", "found"])
    p.add_argument("trace_id", nargs="?"); p.add_argument("--n", type=int, default=1)
    p.add_argument("--by", default="finder")
    p = sub.add_parser("find")
    p.add_argument("--day"); p.add_argument("--since"); p.add_argument("--until")
    p.add_argument("--user"); p.add_argument("--prompt-version"); p.add_argument("--input-type")
    p.add_argument("--decision"); p.add_argument("--cost-outlier", action="store_true")
    p.add_argument("--grep"); p.add_argument("--wide", action="store_true")
    p.add_argument("--uncited-outcome", action="store_true",
                   help="bonus: only answers that left out an exclusion the adjuster relied on")
    sub.add_parser("outcomes")
    p = sub.add_parser("show"); p.add_argument("trace_id")
    p = sub.add_parser("trace"); p.add_argument("trace_id"); p.add_argument("--out", default="trace.json")
    p = sub.add_parser("case"); p.add_argument("trace_id"); p.add_argument("--mode", required=True)
    p.add_argument("--payable", type=float, required=True); p.add_argument("--why", required=True)
    p = sub.add_parser("suite"); p.add_argument("--version", required=True); p.add_argument("--label", required=True)
    p = sub.add_parser("diff"); p.add_argument("before"); p.add_argument("after")
    p = sub.add_parser("cost"); p.add_argument("trace_id")
    p.add_argument("--before", default="before"); p.add_argument("--after", default="after")
    p = sub.add_parser("tenx"); p.add_argument("--day", default="yesterday")
    p.add_argument("--after", default="after")
    args = ap.parse_args()
    {"traffic": cmd_traffic, "plant": cmd_plant, "drill": cmd_drill, "find": cmd_find,
     "show": cmd_show, "trace": cmd_trace, "case": cmd_case, "suite": cmd_suite,
     "diff": cmd_diff, "outcomes": cmd_outcomes, "cost": cmd_cost, "tenx": cmd_tenx}[args.cmd](args)


if __name__ == "__main__":
    main()
