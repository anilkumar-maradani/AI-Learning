# Week 10 (Set D): race the claims squad against the single agent

Run date 2026-10-12 · model `openai/gpt-oss-120b` on Groq for both arms and the judge ·
the same 10 Week-6 cases · the same judge (`reports/week6/judge_v2.txt`).

| Command | What it writes |
|---|---|
| `python evals/week10.py single` | `single_runs.jsonl`: `src/agent.py` over the 10 cases |
| `python evals/week10.py squad` | `squad_runs.jsonl`: `src/squad.py` over the same 10 |
| `python evals/week10.py judge` | the Week-6 judge v2 verdict added to every run (resumable) |
| `python evals/week10.py table` | [race_table.md](race_table.md), [handoffs.log](handoffs.log), [multiplier.txt](multiplier.txt) |
| `python evals/week10.py fail --case 2` | `failure_run.jsonl`; write-up in [failure_case.md](failure_case.md) |

Verdict: [verdict.md](verdict.md) · AgentCard (bonus): [agent_card.json](agent_card.json).

## The two arms

- **Single agent:** `src/agent.py`, unchanged from Weeks 7–8. It has three tools
  (`get_claim`, `search_policy`, `compute_payout`) and an 8-lap budget.
- **Squad:** `src/squad.py`, a new orchestrator with two workers:
  1. **`orchestrator:plan`** sees only the claim header and writes one brief per
     worker.
  2. **`orchestrator -> notes_worker`**: one call, no tools. It reads the notes and
     returns the facts that decide coverage, as JSON.
  3. **`orchestrator -> exclusions_worker`**: it gets those facts, **not the raw
     note history**. It has **one tool** (`search_policy`) and at most 4 laps, and
     makes the coverage call.
  4. **`compute_payout`** is code, not a model call.
  5. **`workers -> orchestrator:synthesis`** writes the final answer. It is told
     never to upgrade a partial or excluded call to covered.

**Fairness rules.**
- **Cases:** the first 10 of `evals/cases/week6_cases.jsonl`, by id. They weren't
  picked, and they cover all four decision types and both regression cases.
- **No answer key:** both arms see the claim file with the adjuster's decision
  note withheld. `tools.get_claim` now drops a closed claim's final `Decision:`
  note; open claims have none, so Weeks 7–8 are unaffected. The judge sees the
  whole file, exactly as in Week 6.
- **Identical rendering:** both arms' answers are rendered the same way for the
  judge (decision, exclusions, payable).
- **Latency:** model plus tool time. Rate-limit sleeps are excluded for both arms.

## The four numbers ([race_table.md](race_table.md))

| | Single agent | Squad |
|---|---:|---:|
| Pass rate | 40% | 60% |
| p50 latency (s) | 4.61 | 7.85 |
| p99 latency (s) | 91.25 | 27.67 |
| Total tokens | 106,306 | 65,154 |
| Cost per claim | $0.00213 | $0.00193 |

**Multiplier ([multiplier.txt](multiplier.txt)):** squad 65,154 / single 106,306 =
**0.6×**. The largest share is the **orchestrator → exclusions_worker re-send, 63%
of all squad tokens**: every lap of that worker re-sends the brief, the notes
worker's facts and all the form wording read so far. The largest single hand-off
is that worker's lap 4 on case 10, at 3,462 tokens. On the single-agent side,
**91% of its tokens are laps 2+ re-sending the whole conversation**
([handoffs.log](handoffs.log)).

The multiplier is below 1 for a reason, not by luck:

- The single agent looped into its 8-lap budget on cases 9 and 10, and those two
  runs alone used 49K tokens.
- The squad's context strategy re-sends little: the note history goes to the
  notes worker once and nowhere else.

The syllabus's 6–15× is for squads that re-send the full history to every worker.

## What the per-case table shows

- **The squad wins 2 cases.**
  - Case 7: the single agent reached "excluded E-73", then called a non-existent
    `json` tool and produced no answer.
  - Case 8: the single agent cited E-81 on top of E-83.
- **Both arms fail 4 cases** (3, 4, 9, 10). Case 4 is a hurricane-deductible claim
  that both answered `needs_info`.
- **The squad has its own real failures,** which are kept in the results:
  - Case 3: the exclusions worker had the right call, then invented a `JSON` tool,
    so the answer was lost.
  - Case 9: it called a tool on its no-tools final lap.
  - Case 10: it excluded the whole loss under E-44 (freezing in an unoccupied
    home), although the notes say the insured lived there. The adjuster paid
    $1,900 and excluded only the $450 pipe under E-45.
- **A judge caveat that applies to both arms:** the single agent's case 3
  (partially covered, E-63, $1,800) matches the adjuster's decision, but the judge
  failed it because the one-line rendering didn't spell out which part was
  covered. Judge v2's validated agreement is 64%, so treat a 2-case gap as
  indicative, not proof.

## Infrastructure note

Groq's free tier caps each model at 200K tokens per day. The first squad pass hit
that cap on case 10, and the first judge pass hung on retries; a failed judge call
would have been recorded as FAIL. No verdict was written from those runs.

- `src/llm.py` now fails fast on the daily cap and flags the error as `quota`.
- `evals/week10.py` re-runs flagged cases (`--cases 10`), resumes judging, and
  refuses to build the table while any case is quota-hit or unjudged.
- Squad case 10 was re-run on fresh quota.

## Failure injection ([failure_case.md](failure_case.md))

The exclusions worker returned a 500 on case 2. The orchestrator **retried once,
then degraded** to `needs_info` and named the failed worker. It **did not lie**. The
first injected run crashed on a retry-path bug (`UnboundLocalError`), which is
fixed and recorded.
