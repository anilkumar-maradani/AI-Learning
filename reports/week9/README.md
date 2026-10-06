# Week 9 (Set D): add the claims-system server without touching the agent

Run date 2026-10-06 · model `openai/gpt-oss-120b` on Groq · host `src/mcp_agent.py`
· servers `policy_docs` (ours) and `claims_system` (the claims platform team's).

| Command | What it writes |
|---|---|
| `python evals/week9.py agent-diff --before 5c8265b --after 7190235` | [agent_diff.txt](agent_diff.txt), [config_diff.txt](config_diff.txt) |
| `python evals/week9.py counts --before 5c8265b --after 7190235` | [tool_counts.txt](tool_counts.txt), `tool_counts.json` |
| `python evals/week9.py wire` | `wire_raw.json`; the hand-annotated copy is [wire.json](wire.json) |
| `python evals/week9.py query` | [query_trace.md](query_trace.md), `query_run.json` |
| `python evals/week9.py errors --before-rev 5c8265b` | [error_before_after.md](error_before_after.md), `error_run_*.json` |
| `python evals/week9.py gateway` | [gateway_demo.md](gateway_demo.md), `gateway_run.json` (bonus) |

`5c8265b` is the commit with only `policy_docs` in the config (and the old
`search_policy` docstring); `7190235` adds the claims-system server and nothing else.

## 1. Server two, added by config only

`mcp_config.json` gained one entry, `claims_system` ([config_diff.txt](config_diff.txt)).
One run of the agent then called both claims tools ([query_trace.md](query_trace.md)):

```
discovered 3 tools: policy_docs__search_policy, claims_system__get_claim_status, claims_system__get_adjuster_notes
lap 1: claims_system__get_claim_status   {"claim_number": "CLM-2026-20103"}
lap 2: claims_system__get_adjuster_notes {"claim_number": "CLM-2026-20103"}
lap 3: final answer: open; pipe sheared by slab subsidence; excluded under NG-1105 E-83
```

The model cited E-83 without calling `search_policy` because the app had already
attached the exclusion schedule as a resource (section 6).

## 2. Agent module: 0 changed lines

The agent module is `src/mcp_agent.py` (the loop) plus `src/mcp_client.py`
(discovery and calls). `git diff 5c8265b..7190235` on those two files is empty
(**0 lines**). The whole commit changed `.env.example`, `mcp_config.json`, and
added the third party's server file. The agent module in the final tree is
still identical to `5c8265b`.

## 3. Tool count, from tools/list

**1 before → 3 after.** Before: `search_policy`. After: `search_policy`,
`get_claim_status`, `get_adjuster_notes`. These names come from running
tools/list against the config at each revision, not from notes
([tool_counts.txt](tool_counts.txt)).

## 4. The wire

[wire.json](wire.json) holds the seven raw messages:
initialize → result, notifications/initialized, tools/list → result,
tools/call → result. Every top-level field is annotated.

**Where the model call happens:** nowhere on this wire, in neither client nor
server. It happens only in the host (`mcp_agent.py` → `llm.chat` → Groq),
between tools/list and tools/call. The model reads the tool list as function
definitions and writes the tools/call arguments.

## 5. Docstring as prompt, and a recoverable error (our server)

On `policy_docs.search_policy`, the docstring IS the tool description
(`src/mcp_server.py`). It went from `Search policy documents.` to a prompt that
covers when to use the tool, the form-number format, the forms that exist, what
the tool does not do, and what each error means. The error paths were split:

| Case | Before | After |
|---|---|---|
| unknown form (`NG-1150`) | `Error: lookup failed` | `form NG-1150 not found: the policy library holds only NG-1101 Escape of Water …; NG-1105 Earth Movement Exclusion …` + what to do |
| malformed (`1105`) | `Error: lookup failed` | `'1105' is not a form number: form numbers look like NG-NNNN …` |
| index down | `Error: lookup failed` | `policy library unavailable … server fault … retrying will not help` |

Same question, same failing first call (`form_number: NG-1150`), and only the
server file differs ([error_before_after.md](error_before_after.md)):

| | Before | After |
|---|---|---|
| lap 2 | searched for the string "NG-1150", got NG-1101 preamble chunks | searched "water escape caused by earth movement", got the NG-1105 exclusion table |
| answer | "I could not locate … cannot determine whether … is covered" | NG-1105, E-83 and GM-3: **excluded** |
| tokens | 4,395 | 6,065 |

The new error costs 1,670 more tokens and turns a non-answer into the right one.

## 6. Exclusion schedule: a resource, not a tool

`policy_docs` exposes `policy://exclusion-schedule` (all 22 exclusion rows, one
line each) as a **resource**. The config's `attach_resources` makes the host read
it and put it in the system prompt, so the model never has to decide to fetch
it. Clause wording still comes through the `search_policy` tool.

## 7. Supply-chain risk note

[risk_note.md](risk_note.md), five lines. Verdict: do not wire it direct-to-agent.
Ship it only behind the gateway.

One change came out of writing it: `mcp_client.py` used to pass the host's
whole environment, `GROQ_API_KEY` included, to every server. A server now gets
only the OS basics plus the variables its config entry declares.

## Bonus: one front door

`mcp_config.gateway.json` lists a single server, `mcp_servers/gateway/server.py`,
which fans out to both servers, re-exports their tools and resources, and writes
one JSON audit line per tools/call to `logs/gateway_audit.jsonl`
(`ts, caller, tool, claim_number, outcome`). The caller's `GATEWAY_TOKEN` is
looked up by SHA-256 in `gateway_config.json`. The dev token `triage-agent`
denies `claims_system__get_adjuster_notes`.

Model run ([gateway_demo.md](gateway_demo.md)): status OK; the notes call came
back `isError: true`, "permission denied … this is a permission decision, not an
outage … answer from the tools you can use". The model answered with the status
and said someone with notes access must check the water source. It did not retry.
