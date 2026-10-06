"""
mcp_agent.py — The Week 9 claims assistant: the same loop as agent.py, but it
does not import a single tool. Every tool it can call is discovered at start-up
from the MCP servers listed in a config file (tools/list), and every call goes
out over MCP (tools/call).

So adding a server is a config change. This module names no tool, no server and
no form; if it ever has to, discovery has been thrown away.

Where the model runs: here, in the host, via llm.chat. The servers only expose
capabilities. Per lap:
    model (Groq) picks tool calls -> ToolRegistry.call -> tools/call on a server
    -> result text goes back to the model as a tool message

The four budgets are agent.py's, checked before every model call.
"""

import json
import time

import llm
from mcp_client import DEFAULT_CONFIG, ToolRegistry

MCP_AGENT_PROMPT_VERSION = "mcp-agent-v1"

SYSTEM = """You are PolicyLens, the claims assistant at Northgate Mutual. Answer \
the adjuster's question using the tools you have been given. Every fact about a \
claim and every piece of policy wording must come from a tool result in this \
conversation; never fill a gap from general knowledge. If you could not get \
what you needed, say exactly what is missing. Answer in a few plain sentences \
and name the claim numbers, forms, clauses and exclusion codes you relied on."""

DEFAULT_BUDGETS = {
    "max_iterations": 8,
    "max_tokens": 40_000,
    "max_cost_usd": 0.02,
    "max_wall_s": 240.0,
}


def _short(text: str) -> str:
    return text if len(text) <= 300 else text[:300] + "..."


def build_system(registry: ToolRegistry) -> str:
    parts = [SYSTEM]
    for server, uri, text in registry.attached_context():
        parts.append(f"\n\nREFERENCE ATTACHED BY THE APP ({server}: {uri}):\n{text}")
    return "".join(parts)


def run_mcp_agent(question: str, config_path: str = DEFAULT_CONFIG, budgets: dict | None = None,
                  log=None, wire: list | None = None) -> dict:
    b = {**DEFAULT_BUDGETS, **(budgets or {})}

    def note(msg):
        if log:
            log(msg)

    registry = ToolRegistry.from_config(config_path, wire=wire)
    try:
        tools = registry.openai_tools()
        note(f"  discovered {len(tools)} tools: {registry.names()}")
        messages = [
            {"role": "system", "content": build_system(registry)},
            {"role": "user", "content": question},
        ]
        steps, tokens, cost, api_s, tool_s, throttle_s = [], 0, 0.0, 0.0, 0.0, 0.0
        t0 = time.perf_counter()
        stop, final_text, laps = None, "", 0

        while True:
            elapsed = time.perf_counter() - t0
            checks = [
                ("max_iterations", laps >= b["max_iterations"], f"{laps} laps"),
                ("max_tokens", tokens >= b["max_tokens"], f"{tokens} tokens"),
                ("max_cost_usd", cost >= b["max_cost_usd"], f"${cost:.5f}"),
                ("max_wall_s", elapsed >= b["max_wall_s"], f"{elapsed:.1f}s"),
            ]
            fired = next((c for c in checks if c[1]), None)
            if fired:
                stop = f"budget:{fired[0]}"
                note(f"  BUDGET FIRED {fired[0]} (limit {b[fired[0]]}, used {fired[2]}) -> stopping cleanly")
                break

            laps += 1
            res = llm.chat(messages, tools=tools, max_tokens=2000)
            tokens += res["usage"]["total"]
            cost += res["cost_usd"]
            api_s += res["api_s"]
            throttle_s += res["throttle_s"]
            note(f"  lap {laps}: {res['usage']['total']} tok (cum {tokens}, ${cost:.5f}) "
                 f"tools={[tc['name'] for tc in res['tool_calls']] or 'none'}")
            if res["error"]:
                stop = "error"
                steps.append({"lap": laps, "tool": None, "error": res["error"]})
                break
            if not res["tool_calls"]:
                final_text = res["content"]
                stop = "final_answer"
                break

            messages.append({
                "role": "assistant",
                "content": res["content"] or "",
                "tool_calls": [{"id": tc["id"], "type": "function",
                                "function": {"name": tc["name"], "arguments": tc["arguments"]}}
                               for tc in res["tool_calls"]],
            })
            for tc in res["tool_calls"]:
                ts = time.perf_counter()
                out = registry.call(tc["name"], tc["arguments"])
                tool_s += time.perf_counter() - ts
                try:
                    args = json.loads(tc["arguments"])
                except json.JSONDecodeError:
                    args = {"_raw": tc["arguments"]}
                steps.append({"lap": laps, "tool": tc["name"], "server": out["server"],
                              "mcp_tool": out["tool"], "args": args, "is_error": out["is_error"],
                              "result": _short(out["text"]), "result_full": out["text"]})
                note(f"    -> {tc['name']} {json.dumps(args)} "
                     f"{'ERROR ' if out['is_error'] else ''}{_short(out['text'])[:160]}")
                messages.append({"role": "tool", "tool_call_id": tc["id"],
                                 "content": json.dumps({"isError": out["is_error"], "text": out["text"]},
                                                       ensure_ascii=False)})
    finally:
        registry.close()

    return {
        "system": "mcp_agent",
        "prompt_version": MCP_AGENT_PROMPT_VERSION,
        "config": config_path,
        "discovered_tools": registry.names(),
        "question": question,
        "final_text": final_text,
        "stop_reason": stop,
        "steps": steps,
        "laps": laps,
        "tokens": tokens,
        "cost_usd": round(cost, 6),
        "latency_s": round(api_s + tool_s, 3),
        "throttle_s": round(throttle_s, 1),
        "wall_s": round(time.perf_counter() - t0, 3),
        "budgets": b,
    }
