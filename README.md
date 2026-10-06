# PolicyLens — a claims assistant built up week by week

One app that grows each week: from chunking and retrieval over homeowners
policy forms (Weeks 3–4), to traced and redacted claim answers (Week 5), to an
evaluated claim-summary writer (Week 6), a tool-using triage agent raced
against a fixed workflow (Week 7), a trajectory eval of that agent (Week 8), and
an agent that finds its tools over MCP, so adding a server is a config change (Week 9).

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
| any | `python chat.py` | interactive grounded Q&A over the forms |

Each week's write-up: [Week 6](reports/week6/README.md) ·
[Week 7](reports/week7/README.md) · [Week 8](reports/week8/README.md) · [Week 9](reports/week9/README.md).

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

## Configuration

| Variable | Default | Purpose |
|---|---|---|
| `GROQ_API_KEY` | — | required for anything that calls a model |
| `GROQ_MODEL` | `openai/gpt-oss-120b` | agent, workflow, judge, chat |
| `GROQ_SMALL_MODEL` | `openai/gpt-oss-20b` | the Week 6 summary writer |
| `POLICYLENS_REDACTION_SALT` | dev salt | key for the pseudonyms in traces |
| `CLAIMS_API_TOKEN` | — | Week 9: token the claims-system MCP server requires |
| `GATEWAY_TOKEN` | — | Week 9 bonus: the agent's scoped token for the gateway |

The free Groq tier allows 8,000 tokens a minute. The eval runners pace
themselves, and reported latency excludes rate-limit waits (see `src/llm.py`).
