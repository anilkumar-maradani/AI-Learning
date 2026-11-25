# PolicyLens — a claims assistant built up week by week

One app that grows each week: from chunking and retrieval over homeowners
policy forms (Weeks 3–4), to traced and redacted claim answers (Week 5), to an
evaluated claim-summary writer (Week 6), a tool-using triage agent raced
against a fixed workflow (Week 7), a trajectory eval of that agent (Week 8), and
an agent that finds its tools over MCP, so adding a server is a config change (Week 9),
a multi-agent squad raced against the single agent (Week 10), and production
observability for the shipped workflow: one redacted log line per request with
per-span latency, tokens and cost, a timed find-the-bad-answer drill, and the
failure turned into a regression case (Week 11).

All app code lives in `src/`. Each week adds one command under `evals/` and
puts its evidence under `reports/weekN/`. Everything runs locally except the
model calls, which go to Groq.

## Data

Everything in `data/` was written for this project.

| Path | What |
|---|---|
| `data/policy/` | six endorsement forms of a fictional carrier, Northgate Mutual: escape of water (NG-1101), windstorm and hurricane (NG-1102), mold (NG-1103), valuable articles (NG-1104), earth movement (NG-1105), home business (NG-1106) |
| `data/claims/open_claims.jsonl` | 10 open claims (policy terms, estimate lines, dated adjuster notes) that the agent triages |
| `data/claims/closed_claims.jsonl` | 30 closed claims, each ending in the adjuster's decision, for the summary writer |
| `data/claims/w12_claims.jsonl` | 8 closed claims dated either side of an endorsement edition change, two with no cover in force (Week 12) |
| `data/policy/*_07-23.txt` | the prior edition of all six forms (in force from 2023-07-01 until each 2026 edition took effect) |
| `data/policies/policies.jsonl` | policy register: product, plan and every term (dates, status, cancellation, forms, deductible, Coverage A) |

The first version of this repository used an endorsement corpus copied from
another repository. It was removed on 2026-09-30. The Week 3–5 reports that
were produced against it are kept, clearly marked, in
[`reports/archive/`](reports/archive/README.md).

## Setup (Windows)

```powershell
.\setup.ps1                                  # creates .venv, installs deps
copy .env.example .env                       # then paste your GROQ_API_KEY
.\.venv\Scripts\python.exe src\ingest.py     # builds ./chroma_db from data/policy
```

## Commands, by week

| Week | Command | What it shows |
|---|---|---|
| 3 | `python src/evaluate.py` | naive vs structure-aware chunker, hit-in-top-5 |
| 4 | `python src/evaluate_w4.py --strategy both` | vector vs hybrid (BM25 + vector + RRF) on the 12-question golden set |
| 5 | `python tests/test_redaction_before_write.py` | claimant identifiers are removed before a trace is written |
| 6 | `python evals/week6.py` | 25 mode-tagged summary cases: 4 assertions + 1 judged criterion, pass rate by mode |
| 7 | `python evals/week7.py agent` · `... workflow` · `... table` | agent vs workflow race, the 8 numbers |
| 8 | `python evals/week8.py score --runs ... --label ...` · `... compare` | trajectory eval, outcome-vs-path gap, one mitigation |
| 9 | `python evals/week9.py tools` · `... query` · `... wire` · `... errors --before-rev REV` · `... gateway` | MCP: tools discovered from `mcp_config.json`, the claims-system server added by config only |
| 10 | `python evals/week10.py single` · `squad` · `judge` · `table` · `fail --case 2` | orchestrator + 2 workers vs the single agent on 10 Week-6 cases: 4 numbers, re-send multiplier, injected worker failure |
| 11 | `python evals/week11.py traffic` · `plant` · `drill start` · `find` · `show` · `drill found` · `trace` · `case` · `suite` · `diff` · `cost` · `tenx` · `outcomes` | request log with spans for the production workflow, a timed drill to find a planted bad coverage answer, its regression case RED then GREEN, cost by stage, what breaks at 10x |
| 12 | `python policylens.py setup` · `python policylens.py triage CLM-2025-30001` · `python policylens.py eval run --label L` · `python policylens.py serve-mcp` | the integrated capstone: one entry point, FNOL in → coverage-in-force check → wording in force on the loss date (MCP, date filter in code) → referral to an adjuster with citations by clause, edition and loss date; eval suite, judge, trajectory, PII test ([write-up](reports/week12/README.md)) |
| any | `python chat.py` | interactive grounded Q&A over the forms |

Each week's write-up: [Week 6](reports/week6/README.md) ·
[Week 7](reports/week7/README.md) · [Week 8](reports/week8/README.md) · [Week 9](reports/week9/README.md) · [Week 10](reports/week10/README.md) · [Week 11](reports/week11/README.md).

## How the app fits together

```
data/policy/*.txt ──ingest──▶ ChromaDB + BM25 ──hybrid_search──┐
data/claims/*.jsonl ──claim_store──────────────────────────────┤
                                                               ▼
  tools.py      get_claim · search_policy · compute_payout
  agent.py      model picks the next tool each lap, 4 budgets enforced
  workflow.py   the same job as 4 fixed steps
  triage.py     shared output contract + outcome grader
  trajectory.py path scoring: accepted path sets, argument validity, failure modes
  summariser.py / assertions.py / judge.py   Week 6 summary writer and its eval
  tracing.py / redaction.py                  every trace is redacted before it is written
  triage_service.py / observability.py       production front door: canary routing, one request line with spans
```

| Module | Week |
|---|---|
| `chunkers.py`, `ingest.py`, `retrieval.py`, `generation.py`, `evaluate.py` | 3 |
| `hybrid_retrieval.py`, `evaluate_w4.py` | 4 |
| `tracing.py`, `redaction.py`, `prompts.py`, `claims_agent.py`, `replay.py`, `sample_traces.py`, `render_traces.py` | 5 |
| `claim_store.py`, `llm.py`, `summariser.py`, `assertions.py`, `judge.py` | 6 |
| `tools.py`, `agent.py`, `workflow.py`, `triage.py` | 7 |
| `trajectory.py` | 8 |
| `mcp_server.py`, `mcp_client.py`, `mcp_agent.py`, `mcp_servers/` | 9 |
| `squad.py` | 10 |
| `observability.py`, `triage_service.py` | 11 |
| `editions.py`, `policy_register.py`, `referral.py`, `triage_agent.py`, `mcp_servers/coverage/`, `policylens.py` | 12 |

## Configuration

| Variable | Default | Purpose |
|---|---|---|
| `GROQ_API_KEY` | — | required for anything that calls a model |
| `GROQ_MODEL` | `openai/gpt-oss-120b` | agent, workflow, judge, chat |
| `GROQ_SMALL_MODEL` | `openai/gpt-oss-20b` | the Week 6 summary writer |
| `POLICYLENS_REDACTION_SALT` | dev salt | key for the pseudonyms in traces |
| `CLAIMS_API_TOKEN` | — | Week 9: token the claims-system MCP server requires |
| `GATEWAY_TOKEN` | — | Week 9 bonus: the agent's scoped token for the gateway |
| `POLICYLENS_STABLE_VERSION` | `workflow-v2` | Week 11: workflow version every claim gets by default |
| `POLICYLENS_CANARY_VERSION` | `workflow-v3` | Week 11: version under canary |
| `POLICYLENS_CANARY_PERCENT` | `10` | Week 11: share of claims routed to the canary; `0` is the rollback |

The free Groq tier allows 8,000 tokens a minute. The eval runners pace
themselves, and reported latency excludes rate-limit waits (see `src/llm.py`).
