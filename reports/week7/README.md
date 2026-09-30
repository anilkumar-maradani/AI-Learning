# Week 7 — race the claims agent against a fixed workflow

Run date 2026-09-30 · model `openai/gpt-oss-120b` on Groq for both systems ·
same 10 claims, same 3 tools, same output contract (`src/triage.py`).

| Command | What |
|---|---|
| `python evals/week7.py agent` | agent (`src/agent.py`) over the 10 claims → `agent_runs.jsonl` |
| `python evals/week7.py workflow` | workflow (`src/workflow.py`) over the same 10 → `workflow_runs.jsonl` |
| `python evals/week7.py table` | `race.csv` and `race_table.md` |
| `python evals/week7.py budget-demo` | `budget_log.txt` |

## The 8 numbers

| | Agent | Workflow |
|---|---:|---:|
| Pass rate | 90% | 90% |
| p50 latency (s) | 4.76 | 1.90 |
| Total tokens (10 claims, every lap summed) | 62,216 | 14,255 |
| Cost per claim (USD) | $0.00140 | $0.00047 |

Per-claim results and the agent's path for each claim: [race_table.md](race_table.md).

**How each number is measured**
- **Pass**: right decision, payable within $1, and the expected exclusion cited
  (`triage.grade`). It is deterministic; no model grades the race.
- **Latency**: model time plus tool time. Groq's free tier allows 8,000 tokens a
  minute, so rate-limit sleeps are recorded separately (`throttle_s`) and never
  counted. The embedding model is warmed up before timing starts.
- **Tokens**: prompt plus completion tokens for **every** lap. The agent re-sends
  the whole message list each lap, which is why it costs 4.4× more.
- **Cost**: Groq list price for gpt-oss-120b, $0.15/M input and $0.75/M output
  (`src/llm.py`). The same rate applies to both systems, so the ratio does not
  depend on it.

## The input mix

| Class | Claims | What makes it hard |
|---|---|---|
| clean | 20101, 20107, 20109 | nothing hidden; 20109 has a partial exclusion (E-92 data recovery) |
| notes change the rule | 20102, 20104, 20105 | notes give the leak duration (E-41), the storm's name (hurricane deductible) and the drying time (mold sublimit) |
| notes trigger an exclusion lookup | 20103, 20106, 20108 | the first notice says "burst pipe" / "flooded basement" / "hail"; only the notes reveal ground movement (NG-1105 E-83), a municipal sewer backup (E-43) or cosmetic-only dents (E-51) |
| missing notes | 20110 | no adjuster notes yet; the right answer is `needs_info` |

## The two failures

- **Workflow, CLM-2026-20109**: payable right ($2,500), but E-92 was not cited
  for the excluded $600 data-recovery line. This is a retrieval miss caused by
  the fixed path: its one query returned four NG-1106 coverage clauses and no
  exclusion table. The agent passed this claim because it searched again.
- **Agent, CLM-2026-20110**: it reached the right answer (`needs_info`) but tried
  to hand it back by calling a tool named `JSON` that does not exist. Groq
  rejected the call and the run ended with no answer. This failure only exists
  inside a loop.

## Budgets (`src/agent.py`)

All four budgets are checked at the top of every lap, before the next model
call: `max_iterations` 8, `max_tokens` 40,000 (summed over laps), `max_cost_usd`
$0.02 (summed) and `max_wall_s` 240. [budget_log.txt](budget_log.txt) is a real
run of CLM-2026-20105 with `max_tokens` lowered to 6,000. That claim used
16K tokens in the race. The budget fired after lap 5 and the run stopped with
`stop_reason=budget:max_tokens` and no answer, instead of spinning.

**A known limit**: because the check runs before each call, the lap that crosses
the limit still completes. That run spent 8,865 tokens against a 6,000 limit. A
pre-call estimate would tighten this.

## Third tool

`compute_payout`, with the enum `claim_status` ∈ {covered,
covered_subject_to_sublimit, excluded}. The description diff, and the
get_claim / search_policy overlap it removed, are in [tool_diff.md](tool_diff.md).

## Verdict

[verdict.md](verdict.md): the workflow wins. None of the 10 claims needs an agent.
