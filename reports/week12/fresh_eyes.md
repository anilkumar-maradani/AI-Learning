# Fresh eyes: another squad's client on our MCP server

## Who ran it, and how

The client was a raw JSON-RPC 2.0 client, [`evals/external_client.py`](../../evals/external_client.py).
It shares **no code** with the PolicyLens host: no `mcp_client`, no
`ToolRegistry`, no prompt. It identifies itself as `clientInfo.name =
"fresh-eyes-client"`. It starts the server exactly as another squad would, does
the `initialize` handshake and `tools/list`, and then makes the calls a stranger
makes, mistakes included. Full output: [external_client_run.txt](external_client_run.txt).

Every call from any client, ours or theirs, is logged by the server with the
caller's `clientInfo`, the trace id the caller sent (or a fresh one), the
arguments, the latency and **the exact text handed back**, redacted on write:
`traces/w12/external_calls.jsonl` for this run, `traces/w12/coverage_calls.jsonl`
for our own agent.

**How another squad connects:**

```powershell
python policylens.py serve-mcp           # stdio MCP server "northgate-coverage" 1.0.0
# or, in their host's config:
#   "command": "<path>\\.venv\\Scripts\\python.exe", "args": ["mcp_servers/coverage/server.py"]
```

Tools: `lookup_policy(claim_number | policy_number)`,
`check_coverage_in_force(policy_number, loss_date)` and
`search_policy_wording(query, loss_date, form_number?, product?)`. Wording is
always the edition in force on `loss_date`.

## Where it stumbled

| Call | What the stranger got | Verdict |
|---|---|---|
| `search_policy_wording(query="flood")`, no date | `bad arguments: search_policy_wording() missing 1 required positional argument: 'loss_date'`, a Python TypeError | **stumble**: a message for a programmer, not for an agent |
| `product="motor"` | `no motor wording in this library: it holds homeowners endorsements only` | clear |
| `form_number="NG-1110"` (typo) | `form NG-1110 not found: the library holds NG-1101, …, NG-1106` | clear, and lists the valid forms |
| `form_number="NG-1101"`, `loss_date="2019-01-01"` | `no edition of NG-1101 was in force on 2019-01-01; refer the claim` | clear |
| `lookup_policy(claim_number=…)` | policy number, product, plan, terms | no personal data |

## What we changed

`search_policy_wording` now answers a missing date in words a calling agent can
act on:

> loss_date is required (YYYY-MM-DD): the wording that applies depends on the
> date of loss, because editions change. Pass the claim's date of loss.

We did not add a default date, because no default date is safe: "today" is
exactly the bug this week is about.

## What our server handed to another squad's agent

The PII scan of all 10 responses (14,602 characters) came back **clean: no
claimant name, no address, no injury.** That holds by construction. The server
reads only the policy register, which has no names, and the endorsement wording.
It never reads adjuster notes. Policy numbers are returned, because the caller
supplies them. Claimant names, addresses and injuries live only in the
third-party claims server's notes, and our host redacts them before they reach
the model or any log (`tests/test_w12_pii.py`).
