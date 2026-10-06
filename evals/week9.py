#!/usr/bin/env python3
"""
Week 9 — MCP: add the claims-system server with nothing but config.

    python evals/week9.py tools  [--rev REV]                 # tools/list against the config at REV (default: working tree)
    python evals/week9.py counts --before REV --after REV    # tool count before -> after, names from tools/list
    python evals/week9.py agent-diff --before REV --after REV  # agent_diff.txt + config_diff.txt
    python evals/week9.py wire                               # raw initialize/tools/list/tools/call vs claims_system
    python evals/week9.py query                              # one model run that calls a claims_system tool
    python evals/week9.py errors --before-rev REV            # same failing call, old vs new policy_docs server
    python evals/week9.py gateway                            # bonus: one front door, audit line, scoped token

Everything except `query`, `errors` and the model half of `gateway` runs
without a model: discovery and the wire exchange never call one.
"""

import argparse
import json
import os
import subprocess
import sys
import tempfile

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(ROOT, "src"))

from console import enable_utf8  # noqa: E402

enable_utf8()

from dotenv import load_dotenv  # noqa: E402

load_dotenv(os.path.join(ROOT, ".env"))

from mcp_client import DEFAULT_CONFIG, MCPServer, ToolRegistry, load_config  # noqa: E402

OUT = os.path.join(ROOT, "reports", "week9")
AGENT_MODULES = ["src/mcp_agent.py", "src/mcp_client.py"]
GATEWAY_CONFIG = os.path.join(ROOT, "mcp_config.gateway.json")

QUERY = ("What is the current status of claim CLM-2026-20103, what do the adjuster notes "
         "say actually caused the damage, and which exclusion does that point to?")

ERROR_QUESTION = ("The insured's agent says endorsement NG-1150 is the form that deals with water "
                  "from a pipe that broke because the ground moved. Look up that form's wording and "
                  "tell me whether such a loss is covered.")

GATEWAY_QUESTION = ("For claim CLM-2026-20106, what is its status and what do the adjuster notes "
                    "say about where the water came from?")


def _git(*args) -> str:
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True,
                          encoding="utf-8", check=True).stdout


def _config_at(rev: str | None) -> str:
    """Path to the mcp_config.json as it was at REV (the working tree if None)."""
    if not rev:
        return DEFAULT_CONFIG
    fd, path = tempfile.mkstemp(suffix=".json", prefix="mcp_config_")
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        fh.write(_git("show", f"{rev}:mcp_config.json"))
    return path


def _write(name: str, text: str):
    os.makedirs(OUT, exist_ok=True)
    with open(os.path.join(OUT, name), "w", encoding="utf-8") as fh:
        fh.write(text)
    print(f"wrote reports/week9/{name}")


def _redact_names(text: str) -> str:
    """Claimant names out before anything is written (the Week 5 rule). Claim numbers stay:
    they are the evidence this week."""
    from claim_store import load_claims
    from redaction import _token
    for c in load_claims().values():
        text = text.replace(c["claimant_name"], _token("CLAIMANT", c["claimant_name"]))
    return text


# -- discovery ----------------------------------------------------------------

def discover(rev: str | None) -> dict[str, list[str]]:
    """{server: [tool names]} exactly as each server's tools/list returned them."""
    reg = ToolRegistry.from_config(_config_at(rev))
    try:
        return {name: [t["name"] for t in srv.tools] for name, srv in reg.servers.items()}
    finally:
        reg.close()


def cmd_tools(args):
    found = discover(args.rev)
    total = sum(len(v) for v in found.values())
    print(f"config at {args.rev or 'working tree'}: {total} tools")
    for server, names in found.items():
        for n in names:
            print(f"  {server}: {n}")


def cmd_counts(args):
    lines = []
    res = {}
    for label, rev in (("before", args.before), ("after", args.after)):
        found = discover(rev)
        res[label] = found
        lines.append(f"{label} ({rev}, mcp_config.json at that commit): "
                     f"{sum(len(v) for v in found.values())} tools from tools/list")
        for server, names in found.items():
            lines += [f"  {server}__{n}" for n in names]
    n_b = sum(len(v) for v in res["before"].values())
    n_a = sum(len(v) for v in res["after"].values())
    names = lambda f: ", ".join(n for v in f.values() for n in v)  # noqa: E731
    lines.insert(0, f"{n_b} before -> {n_a} after   "
                    f"[{names(res['before'])}] -> [{names(res['after'])}]\n")
    _write("tool_counts.txt", "\n".join(lines) + "\n")
    _write("tool_counts.json", json.dumps(res, indent=2) + "\n")
    print("\n".join(lines))


# -- the zero-line proof ------------------------------------------------------

def cmd_agent_diff(args):
    rng = f"{args.before}..{args.after}"
    numstat = _git("diff", "--numstat", rng, "--", *AGENT_MODULES)
    patch = _git("diff", rng, "--", *AGENT_MODULES)
    changed = sum(int(a) + int(d) for a, d, _ in (l.split("\t") for l in numstat.splitlines()))
    text = (f"$ git diff --numstat {rng} -- {' '.join(AGENT_MODULES)}\n{numstat}"
            f"$ git diff {rng} -- {' '.join(AGENT_MODULES)}\n{patch}"
            f"\nchanged lines in the agent module ({' + '.join(AGENT_MODULES)}): {changed}\n"
            f"\n$ git diff --stat {rng}\n{_git('diff', '--stat', rng)}")
    _write("agent_diff.txt", text)
    _write("config_diff.txt", f"$ git diff {rng} -- mcp_config.json .env.example\n"
                              + _git("diff", rng, "--", "mcp_config.json", ".env.example"))
    print(text)


# -- the wire -----------------------------------------------------------------

def cmd_wire(args):
    spec = load_config()[args.server]
    wire = []
    srv = MCPServer(args.server, spec, wire=wire).start()
    try:
        srv.initialize()
        srv.list_tools()
        srv.call_tool(args.tool, {"claim_number": args.claim})
    finally:
        srv.close()
    # The exchange exactly as sent, except the claimant name is pseudonymised before writing.
    _write("wire_raw.json", _redact_names(json.dumps(wire, indent=2, ensure_ascii=False)) + "\n")


# -- model runs ---------------------------------------------------------------

def _config_label(path: str) -> str:
    path = os.path.abspath(path)
    if path.startswith(ROOT + os.sep):
        return os.path.relpath(path, ROOT).replace(os.sep, "/")
    return "temporary copy of mcp_config.json, policy_docs pointed at the older server file"


def render(run: dict, title: str) -> str:
    out = [f"### {title}", "",
           f"Config: `{_config_label(run['config'])}` · "
           f"stop: `{run['stop_reason']}` · laps {run['laps']} · {run['tokens']} tokens · ${run['cost_usd']:.5f}",
           "", f"Discovered: {', '.join(f'`{n}`' for n in run['discovered_tools'])}", "",
           f"**Adjuster:** {run['question']}", ""]
    for s in run["steps"]:
        if s["tool"] is None:
            out.append(f"- lap {s['lap']}: model error `{s.get('error')}`")
            continue
        out += [f"- lap {s['lap']}: **`{s['tool']}`** (server `{s['server']}`, MCP tool `{s['mcp_tool']}`) "
                f"`{json.dumps(s['args'], ensure_ascii=False)}`",
                f"  - {'**isError: true** — ' if s['is_error'] else ''}`{s['result']}`"]
    out += ["", "**Final answer:**", "", "> " + (run["final_text"] or "(none)").replace("\n", "\n> "), ""]
    return _redact_names("\n".join(out))


def _save_run(run: dict, name: str):
    _write(name, _redact_names(json.dumps(run, indent=2, ensure_ascii=False)) + "\n")


def cmd_query(args):
    from mcp_agent import run_mcp_agent
    run = run_mcp_agent(args.question, config_path=args.config or DEFAULT_CONFIG, log=print)
    _save_run(run, "query_run.json")
    _write("query_trace.md", "# Week 9 — one query through both servers\n\n" + render(run, "Run") +
           "\nclaims_system tools called: "
           + (", ".join(f"`{s['tool']}`" for s in run["steps"] if s.get("server") == "claims_system")
              or "NONE") + "\n")


def _old_server_config(rev: str) -> tuple[str, str]:
    """A config identical to the current one, except policy_docs runs the server file from REV."""
    old = os.path.join(ROOT, "mcp_servers", "policy_docs", f"_server_at_{rev[:7]}.py")
    with open(old, "w", encoding="utf-8") as fh:
        fh.write(_git("show", f"{rev}:mcp_servers/policy_docs/server.py"))
    cfg = {"mcpServers": load_config()}
    cfg["mcpServers"]["policy_docs"] = {**cfg["mcpServers"]["policy_docs"],
                                        "args": [os.path.relpath(old, ROOT).replace(os.sep, "/")]}
    fd, path = tempfile.mkstemp(suffix=".json", prefix="mcp_config_old_")
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        json.dump(cfg, fh)
    return path, old


def cmd_errors(args):
    from mcp_agent import run_mcp_agent
    cfg_old, old_file = _old_server_config(args.before_rev)
    try:
        print("BEFORE (policy_docs at", args.before_rev, ")")
        before = run_mcp_agent(ERROR_QUESTION, config_path=cfg_old, log=print)
    finally:
        os.remove(old_file)
    print("AFTER (policy_docs in working tree)")
    after = run_mcp_agent(ERROR_QUESTION, config_path=DEFAULT_CONFIG, log=print)
    _save_run(before, "error_run_before.json")
    _save_run(after, "error_run_after.json")
    write_error_report(before, after, args.before_rev)


def write_error_report(before: dict, after: dict, before_rev: str):
    before_doc = _git("show", f"{before_rev}:mcp_servers/policy_docs/server.py")
    _write("error_before_after.md", "\n".join([
        "# Week 9 — the same failing call, old docstring/error vs new",
        "",
        f"Server: `policy_docs` (ours), tool `search_policy`. Before = the server file at "
        f"`{before_rev[:7]}`, after = working tree. Agent, model, prompt, config and question "
        f"identical; only the server file differs.",
        "",
        "The failing call: the adjuster quotes a form number that does not exist (NG-1150; the "
        "earth-movement form is NG-1105).",
        "",
        "## Tool description the model saw",
        "",
        "Before:", "", "```", _docstring(before_doc), "```", "",
        "After:", "", "```", _docstring(open(os.path.join(ROOT, "mcp_servers", "policy_docs", "server.py"),
                                             encoding="utf-8").read()), "```", "",
        "## Transcripts", "",
        render(before, "Before"), render(after, "After"),
    ]) + "\n")


def _docstring(src: str) -> str:
    import ast
    import inspect
    for node in ast.walk(ast.parse(src)):
        if isinstance(node, ast.FunctionDef) and node.name == "search_policy":
            return inspect.cleandoc(ast.get_docstring(node) or "")
    return ""


# -- bonus: the gateway -------------------------------------------------------

def cmd_gateway(args):
    from mcp_agent import run_mcp_agent
    print("Gateway tools/list, and a direct tools/call per tool (no model):")
    reg = ToolRegistry.from_config(GATEWAY_CONFIG)
    try:
        print("  discovered:", reg.names())
        direct = []
        for name in reg.names():
            if "claims_system" in name:
                r = reg.call(name, {"claim_number": "CLM-2026-20106"})
                direct.append(f"- `{name}` → isError={r['is_error']}: `{r['text'][:220]}`")
                print(" ", direct[-1])
    finally:
        reg.close()
    run = None
    if not args.no_model:
        run = run_mcp_agent(GATEWAY_QUESTION, config_path=GATEWAY_CONFIG, log=print)
        _save_run(run, "gateway_run.json")
    audit_path = os.path.join(ROOT, "logs", "gateway_audit.jsonl")
    audit = open(audit_path, encoding="utf-8").read() if os.path.exists(audit_path) else ""
    _write("gateway_demo.md", _redact_names("\n".join([
        "# Week 9 bonus — one front door, scoped token", "",
        "Agent config: `mcp_config.gateway.json` (one server: the gateway). The gateway fans out to "
        "`policy_docs` and `claims_system` from `mcp_servers/gateway/gateway_config.json`.", "",
        "## Direct tools/call through the gateway (token `triage-agent`, notes denied)", "",
        *direct, "",
        *([render(run, "Model run through the gateway")] if run else ["(model run skipped)"]),
        "## Audit log (`logs/gateway_audit.jsonl`, one line per tools/call)", "",
        "```", audit.strip(), "```", ""])) + "\n")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["tools", "counts", "agent-diff", "wire", "query", "errors", "gateway"])
    ap.add_argument("--rev")
    ap.add_argument("--before")
    ap.add_argument("--after", default="HEAD")
    ap.add_argument("--before-rev")
    ap.add_argument("--config")
    ap.add_argument("--question", default=QUERY)
    ap.add_argument("--server", default="claims_system")
    ap.add_argument("--tool", default="get_claim_status")
    ap.add_argument("--claim", default="CLM-2026-20103")
    ap.add_argument("--no-model", action="store_true")
    args = ap.parse_args()
    {"tools": cmd_tools, "counts": cmd_counts, "agent-diff": cmd_agent_diff, "wire": cmd_wire,
     "query": cmd_query, "errors": cmd_errors, "gateway": cmd_gateway}[args.cmd](args)


if __name__ == "__main__":
    main()
