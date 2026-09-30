# Week 8 — the outcome-vs-trajectory gap in the claims agent

Agent: `src/agent.py` (gpt-oss-120b on Groq). Claims: the same 10 as Week 7.
Scorer: `src/trajectory.py`, driven by `evals/week8.py`.

| Command | What |
|---|---|
| `python evals/week8.py paths` | prints the 10 expected path sets → [expected_paths.txt](expected_paths.txt) |
| `python evals/week8.py score --runs reports/week7/agent_runs.jsonl --label before` | scores the Week 7 agent runs → `trajectory_before.json` |
| `python evals/week8.py run --label after` | re-runs the agent with the mitigation and scores it → `agent_runs_after.jsonl`, `trajectory_after.json` |
| `python evals/week8.py compare` | before/after tables → [compare.md](compare.md) |

## 1. Expected tool sequences (10 cases, alternates asserted as sets)

A path is written as `claim` (get_claim), `policy:NG-XXXX` (a search_policy call
that retrieved that form's wording) and `payout` (compute_payout). Each case in
`evals/cases/trajectory_10.jsonl` is a spec that `accepted_paths()` expands into
an explicit **set** of valid sequences. A run passes the trajectory eval only
if its path equals one of them **and** every argument it passed was real.

| Claim | Must read | May also read | compute_payout | Accepted paths |
|---|---|---|---|---:|
| 20101 | NG-1101 | NG-1103, either order | required | 3 |
| 20102 | NG-1101 | — | optional (excluded, $0) | 2 |
| 20103 | NG-1105 | NG-1101, **before or after** NG-1105 | optional | 6 |
| 20104 | NG-1102 | — | required | 1 |
| 20105 | NG-1103 | NG-1101, before or after | required | 3 |
| 20106 | NG-1101 | — | optional | 2 |
| 20107 | NG-1104 | — | required | 1 |
| 20108 | NG-1102 | — | optional | 2 |
| 20109 | NG-1106 | — | required | 1 |
| 20110 | — | NG-1101 | **forbidden** (no notes: needs_info) | 2 |

Six of the ten cases legitimately accept more than one path. For example, on
the earth-movement claim, reading the water form before or after the
earth-movement form is equally right, and on a $0 exclusion calling
compute_payout is allowed but not needed. The full expanded sets are in
[expected_paths.txt](expected_paths.txt).

## 2. The four trajectory numbers (before any mitigation)

| Metric | Value |
|---|---:|
| Tool-choice accuracy (right tools in an accepted order) | **80%** |
| Argument validity (57 arguments: claim numbers, form numbers, covered amounts, sublimits, cited exclusion and clause IDs, all checked against the claim store and corpus) | **100%** |
| Step efficiency (steps taken / steps needed) | **1.25** |
| Cost per claim, p50 / max | **$0.00133 / $0.00365** |

Argument validity is 100%: no invented claim numbers, forms, exclusion codes or
amounts in these 10 runs. The first version of the checker flagged
`NG-1103:CLAUSE-MR-1` and `EXCLUSION-TABLE` as fiction. Both are real corpus
references, so the checker now asks only whether the reference exists
anywhere in the corpus.

The max cost is 2.7× the p50, and it comes from exactly one claim, which is
the one in section 3.

## 3. The gap

| | |
|---|---:|
| Outcome pass rate | 90% |
| Trajectory pass rate | 80% |
| **Gap (outcome − trajectory)** | **+10 points** |

**Right answer, wrong path: CLM-2026-20105** (mold after a dishwasher leak).
The outcome eval passes it: partially covered, $7,500 payable. The path it took:

```
1 get_claim      {"claim_number": "CLM-2026-20105"}
2 search_policy  {"form_number": "NG-1101", "query": "mold"}
3 search_policy  {"form_number": "NG-1103", "query": "mold"}
4 search_policy  {"form_number": "NG-1101", "query": "sudden escape of water"}   <- NG-1101 again
5 search_policy  {"form_number": "NG-1103", "query": "limited amount"}          <- NG-1103 again
6 compute_payout {"claim_status": "covered_subject_to_sublimit", "covered_amount": 11200,
                  "deductible_basis": "all_peril", "sublimit": 7500}
```

It read both forms twice (`redundant_lookup`). That cost 15,967 tokens, 2.6×
the next most expensive claim. The cause is in the tool: with `form_number`
set, search_policy returned the top 4 ranked chunks, and on NG-1103 two of the
four were the form's header. The sublimit clause MR-2 was not among them, so
the agent searched again. On a form with a longer exclusion table, the same
behaviour would loop until a budget fired.

The other failed run, CLM-2026-20110, fails both evals, so it does not count
toward the gap. It got the answer right (`needs_info`) but tried to return it
by calling a tool named `JSON`, which does not exist.

## 4. One mitigation: sharpen the search_policy tool

Before, the failure-mode counts tied at one each: `redundant_lookup` (20105) and
`invented_tool_name` (20110). I picked `redundant_lookup` because it is the one
the outcome eval cannot see (it *is* the gap), and it set the max cost.

**The change** (commit `6cf2a91`, `src/tools.py`, one tool): with `form_number`,
search_policy now returns that form's complete wording in document order,
without header chunks, and the description says so ("one call per form is
enough, and repeating it returns nothing new"). The agent prompt, model,
budgets and the other tools are unchanged.

| Top mode | Before | After |
|---|---:|---:|
| `redundant_lookup` | 1 | **0** |

On CLM-2026-20105 the path is now
`get_claim → search_policy(NG-1101) → search_policy(NG-1103) → compute_payout`,
an accepted path. It used 10,355 tokens instead of 15,967.

**The price, measured**

| | Before | After | Change |
|---|---:|---:|---|
| p50 latency (model + tool time) | 4.76 s | 8.70 s | **+3.94 s (+83%)** |
| Tokens per claim (mean) | 6,222 | 5,817 | −6% |
| Cost per claim p50 | $0.00133 | $0.00120 | −10% |
| Cost per claim max | $0.00365 | $0.00225 | −38% |
| Outcome pass rate | 90% | **70%** | −20 pts (see section 5) |

The latency cost is real: each form lookup now returns the whole form, so later
laps carry a larger prompt. Tokens and cost fell only because the
redundant lookups disappeared.

## 5. Regression check: every mode, before → after

| Mode | Before | After | |
|---|---:|---:|---|
| skipped_required_lookup (payout without opening the governing form) | 0 | 0 | same |
| payout_before_lookup | 0 | 0 | same |
| payout_without_facts (payout on a claim with no notes) | 0 | 0 | same |
| repeated_identical_call | 0 | 0 | same |
| **redundant_lookup** | 1 | 0 | better (the target) |
| unneeded_detour | 0 | 0 | same |
| invalid_argument (fluent fiction) | 0 | 0 | same |
| **invented_tool_name** | 1 | **3** | **worse** |
| stopped_without_answer (other errors, budgets) | 0 | 0 | same |
| **wrong_outcome** | 1 | **3** | **worse** |

**`invented_tool_name` got worse**, from 1 to 3 (claims 20106, 20107, 20108). In each case the
model had the right decision and tried to hand it back by calling a tool
named `json` or `JSON`, which Groq rejected. It drove the outcome pass rate from
90% to 70%, and the trajectory pass rate fell from 80% to 70%. The gap is now
0, but only because these runs fail both evals, not because the agent improved.

With 10 claims I cannot show that the mitigation caused this. The failure
existed before (20110), and one run per claim is a small sample. A plausible
link: the larger whole-form tool results sit right before the final turn. The
honest reading is that the mitigation fixed its target mode and the run
surfaced `invented_tool_name` as the top mode. The next single mitigation
should target it (catch `tool_use_failed` and re-plan, or parse the rejected
generation). It is **not** applied here, because two mitigations at once would
make neither result readable.
