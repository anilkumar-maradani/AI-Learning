# Week 12 capstone (Variant D): Claims Triage & Coverage Assistant

An FNOL comes in. The system checks that cover was in force on the loss date,
reads the policy wording **in force on that date**, and refers the claim to an
adjuster. The referral cites each clause by form, edition and the loss date it
was resolved against, and keeps the deductible, the sub-limit and the policy
limit as three separate numbers. It never decides coverage: code rejects any
referral that does.

| Deliverable | File |
|---|---|
| one entry point, one command | `policylens.py` (below) |
| seam list, each seam marked fixed / accepted | [seams.md](seams.md) |
| one-page architecture | [architecture.md](architecture.md) |
| eval suite output on the integrated system | [eval_report_suite.md](eval_report_suite.md), [score_suite.json](score_suite.json), part 3 below |
| re-scored error taxonomy, with the modes integration created | [taxonomy.md](taxonomy.md) |
| trajectory eval and the outcome-vs-trajectory gap | [trajectory_suite.txt](trajectory_suite.txt), part 5 |
| one end-to-end trace, trace id across the agent and MCP hops | [trace.json](trace.json), part 1 |
| top 3 weaknesses, written before anyone asked | [weaknesses.md](weaknesses.md) |
| cost per claim triaged and the 10× plan | part 8 |
| fresh-eyes note | [fresh_eyes.md](fresh_eyes.md) |
| 10-minute demo script | [demo_script.md](demo_script.md) |

## One command

```powershell
python policylens.py setup                     # index both editions + the triage-time claims snapshot
python policylens.py triage CLM-2025-30001     # FNOL in -> referral out, every tool call printed live
python policylens.py trace <trace id>          # host spans + MCP server spans, same trace id
python policylens.py eval run --version w12-v2 --label suite --model openai/gpt-oss-20b
python policylens.py eval score --label suite  # then: trajectory, label-sheet, judge, agreement, report
python policylens.py serve-mcp                 # our MCP server, for another squad's client
python evals/week12.py                         # retrieval + in-force checks, no model calls
```

## 1. A real run (trace `tr_1de01aa5041b`, gpt-oss-120b)

The FNOL is CLM-2025-30001: heavy rain, water under the back door, loss date
2025-08-11. ([trace.json](trace.json))

| Span | Stage | Latency | Tokens | Cost | What happened |
|---|---|---:|---:|---:|---|
| sp1 | tools (MCP → claims system) | 1.1 ms | 0 | $0 | intake: adjuster notes read over MCP; name, address and injury redacted before the model saw them |
| sp2 | generation | 12.0 s | 1,308 | $0.000238 | lap 1 |
| sp3 | tools (MCP → our coverage server) | 5,953 ms (server: 27.4 ms) | 0 | $0 | `check_coverage_in_force(HOP-6610301, 2025-08-11)`: in force; **NG-1101 ed. 07-23** in force on the loss date |
| sp4 | generation | 3.7 s | 1,542 | $0.000264 | lap 2 |
| sp5 | retrieval (MCP → our coverage server) | 35.4 ms (server: 18.0 ms) | 0 | $0 | `search_policy_wording(NG-1101, 2025-08-11)`: 7 passages, all ed. 07-23 |
| sp6, sp7 | generation | 24.0 s, 30.6 s | 3,386, 3,772 | $0.000898, $0.000830 | the referral |
| sp8 | tools (local) | 9 ms | 0 | $0 | `refer_to_adjuster`: **accepted** by the guard |
| **total** | | 76.4 s | **10,008** | **$0.002231** | |

The trace id `tr_1de01aa5041b` appears on the host spans and, through MCP
`_meta`, on the coverage server's own log lines (parents sp3 and sp5). The
referral:

```
REFERRAL TO ADJUSTER — no coverage decision made
Loss date: 2025-08-11 · Coverage in force on the loss date: yes (term 2024-11-27 to 2025-11-26)
  - NG-1101 ed. 07-23 · WE-4 — data/policy/NG-1101_07-23.txt#L33 (in force 2023-07-01 to 2025-12-31; resolved for loss date 2025-08-11)
Deductible: $1,000.00 (all_peril, policy register term)
Sub-limit: $10,000.00 — NG-1101 ed. 07-23 · WE-4 — data/policy/NG-1101_07-23.txt#L33
Policy limit (Coverage A): $380,000.00
Facts: heavy rain (≈90 mm/3 h) entered through the window well and rear door; no nearby river/stream overflow; creek stayed within banks
```

Under the 2026 wording this runoff loss would be **excluded** (E-42 "runoff
entering from outside"). Under the 2023 wording in force on the loss date, WE-4
covers it up to $10,000. The citation proves which wording was read.

## 2. What was integrated

The Week 3–4 hybrid retriever now has a **loss-date filter enforced in code** on
both legs. The Week 7 agent loop discovers its tools over MCP at runtime. Our MCP
server exposes the wording search scoped by product and date, and another squad
calls it. The Week 6 assertions-then-judge suite runs against the integrated
system. The Week 8 trajectory eval runs on the same runs. The Week 11
per-request log follows the trace id across the agent and MCP hops, and
redaction holds the PII line.

Diagram: [architecture.md](architecture.md). Every seam found and how it was
handled: [seams.md](seams.md).

## 3. The eval suite on the integrated system

`evals/cases/week12_cases.jsonl` defines 25 cases.

- **This run:** 9 of them, on gpt-oss-20b, `w12-v2`, prompt `triage-agent-w12-5`.
  They are the 6 edition-boundary cases (5 straddling the 2026 editions, plus
  the 2026-01-01 control), both not-in-force cases, and the first open claim.
- **Before/after arms:** gpt-oss-120b, on the five straddle cases.

**Assertions first** (code only, no judge):

| Assertion | Pass |
|---|---:|
| `referral_made` (an accepted referral, not a fallback) | 7/9 = 78% |
| `no_decision_language` (enforced at runtime by the guard and checked again here) | **9/9 = 100%** |
| `in_force_correct` | 9/9 = 100% |
| `edition_in_force` (every citation's edition was in force on the loss date) | **9/9 = 100%** |
| `loss_date_stated` | 9/9 = 100% |
| `citations_resolve` (clause exists in that edition, link resolves) | 9/9 = 100% |
| `three_numbers` (deductible, sub-limit and limit each right) | 5/9 = 56% |
| `decisive_clause_surfaced` | 7/9 = 78% |

**Pass rate per taxonomy mode** (all assertions):

| Mode | n | Pass |
|---|---:|---:|
| wrong-edition-risk (edition-boundary cases) | 6 | 3/6 = 50% |
| not-in-force | 2 | 2/2 = 100% |
| sublimit-vs-deductible | 1 | 0/1 = 0% |
| **all** | **9** | **5/9 = 56%** |

The boundary cases lose on the referral, not on the edition: two gave up after a
guard rejection, and one dropped the WE-4 sub-limit (part 4).

**The judge, re-checked on integrated outputs.** One binary criterion, BASIS:
does the referral point the adjuster to the facts the decision turns on, without
asserting facts the file does not contain? The judge model was
`qwen/qwen3.8-27b`.

- **Labels came first.** All 9 referrals were labelled blind from
  [label_sheet_suite.md](label_sheet_suite.md). The labels were frozen with the
  SHA-256 of each referral text ([labels_suite.json](labels_suite.json))
  before any judge output existed. They were written by the reviewer, Claude, not
  by a human adjuster.
- **Judge v1** ([judge_w12.txt](judge_w12.txt)): **7/9 = 78%**. Both misses lean
  the same way, judge PASS against label FAIL ([judge_suite_v1.json](judge_suite_v1.json)).
- **Judge v2** ([judge_w12_v2.txt](judge_w12_v2.txt)), after a prediction was
  written first ([judge_v2_prediction.txt](judge_v2_prediction.txt)): **8/9 = 89%**,
  which clears the 85% bar ([judge_suite_v2.json](judge_suite_v2.json)).
  - Confusion: 4 PASS/PASS, 4 FAIL/FAIL, 1 judge-PASS/label-FAIL (W12-O1: an
    invented "requires tear-out" inside a citation reason still gets past it).
  - v2 was tuned on these same 9 cases, so 89% is an optimistic number, not a
    held-out one.

**What this suite does NOT measure:**

- **Implied decisions.** "Falls within the scope of WE-4" contains no banned word.
  The guard and the assertion catch words, not meaning.
- **The adjuster's experience of the referral**, or any outcome after referral.
- **Motor claims.** The library is homeowners only; a `motor` query is refused.
- **Renewal-based edition rules.** Real carriers attach editions at renewal; this
  system uses the edition in force on the loss date.
- **Whether the referral's facts are complete** beyond the one decisive fact the
  judge checks.

## 4. A number that moved: wrong-endorsement-version citation rate

The same five straddle cases (B1, B2, B4, B5, B6; loss dates from 2025-08-11 to
2026-02-14, one of them **2025-12-31, the day before ed. 01-26 took effect**).
The table counts every citation the model proposed in `refer_to_adjuster`,
including attempts the guard rejected, because that is what would have shipped
with no guard.

| Arm | Model | Retrieval | Cases with a wrong-edition citation | Wrong-edition citations |
|---|---|---|---:|---:|
| **before** (`w12-v1`) | gpt-oss-120b | date-blind: best match wins | **5/5 = 100%** | **15/19 = 79%** |
| **after** (`w12-v2`) | gpt-oss-120b | loss-date filter, enforced in code | **0/2 = 0%** | **0/7 = 0%** |
| **after** (`w12-v2`), suite | gpt-oss-20b | loss-date filter, enforced in code | **0/5 = 0%** | **0/35 = 0%** |

What the "before" cited:
- the 2025-08-11 runoff loss: NG-1101 **ed. 01-26** E-42, the 2026 flood
  exclusion (`tr_f066271e5ab8`);
- the 2026-02-14 earth-movement loss: NG-1105 **ed. 03-26** GM-3 and E-83, where
  the 2023 GM-3 in force that day *gives the water damage back*;
- the 2026-01-20 mold loss: NG-1103 **ed. 02-26** MR-2 (the $7,500 mold sub-limit) instead of ed. 07-23 MR-2 ($5,000).

The judge's agreement on the integrated outputs is 8/9 = 89% (part 3).

**Bonus: loss-date-aware retrieval, proven at the retrieval layer**
(`python evals/week12.py`, [eval_output.txt](eval_output.txt), no model calls):

| | Before (no filter) | After (filter) |
|---|---:|---:|
| straddle cases with a wrong-edition passage in the top 3 | 5/5, plus the control: 6/6 | 0/6 |
| straddle cases red → green (deciding clause from the right edition in top 3, no wrong edition) | 5/5 red | 4/5 green (B6: the E-44 row ranks outside the top 3 from either edition; the agent reads the whole form, so it gets the row anyway) |
| hit-rate@3 on cases that do not straddle a boundary (Week 4 golden set, n = 12) | 12/12 = 100% | **12/12 = 100%: the filter cost 0 points** |
| wrong-edition passages among those 36 top-3 slots | 15 | 0 |

## 5. Trajectory eval (n = 9, the suite runs)

| | |
|---|---:|
| tool-choice accuracy | **32/33 = 97%** |
| trajectory pass (in-force check before any wording read, every form read with the claim's loss date, referral last) | **9/9 = 100%** |
| outcome pass (all assertions) | 5/9 = 56% |
| **outcome − trajectory gap** | **−44 points** |

The gap runs the embarrassing way: the agent takes the right path every time and
still writes a referral that fails. Every outcome failure sits in the referral
content: a gave-up fallback, a dropped sub-limit, a mis-set sub-limit. None sits
in the path. The one wrong call: W12-N2 read wording after the in-force check
said no cover.

## 6. Error taxonomy, re-scored

Seven modes, each with a frequency, severity and trace id, are in
[taxonomy.md](taxonomy.md). Two were **created by integration**:

- **Gave up after a guard rejection** (2/9): a code-enforced exit meets a model
  that ends turns in prose.
- **Provider schema rejection** (fixed): a local tool's schema enforced by Groq
  kills the whole generation.

The brief's mode, **wrong-edition citation**, went from **100% to 0%** (part 4).

## 7. Logging across both hops, and the PII line

- **One request line per FNOL** (`traces/w12/requests_*.jsonl`), redacted on
  write. It holds the spans with latency, tokens and cost per span; for every
  passage put in front of the model, the chunk id, edition and text SHA-256; and
  the prompt version and SHA-256, the model, `reasoning_effort` and the
  referral.
- **One line per MCP call on our server** (`traces/w12/coverage_calls_*.jsonl`),
  with the host's trace id and parent span from `_meta`, the caller, the
  latency, and the exact result handed out.
- **`tests/test_w12_pii.py`: PASS.** 62 log lines across both hops and the
  external client hold no claimant name, address, injury, raw claim or policy
  number, or verbatim note ([pii_test_output.txt](pii_test_output.txt)).
- **What our MCP server handed another squad's client:** policy terms and
  wording only. The PII scan of every response was clean ([fresh_eyes.md](fresh_eyes.md)).

## 8. Cost per claim triaged, and the 10× plan

| Config | Tokens per claim (mean) | Cost per claim triaged |
|---|---:|---:|
| gpt-oss-120b, n = 7 (before + after arms) | 12,857 | **$0.0029** |
| gpt-oss-20b, n = 9 (suite) | 11,180 | **$0.00155** |
| of which retrieval, the in-force check, MCP and the guard | 0 | $0 |

A clean referral costs about 9–10K tokens in 3–4 laps. Each guard rejection
re-sends the whole context: +4–5K tokens. A give-up costs 16–20K.

**A hailstorm week: 18,000 FNOLs, about 2,571 a day.** At 12,857 tokens per
claim on gpt-oss-120b:

| Limit (Groq free tier, read from response headers) | Need at 2,571/day | Breaks at |
|---|---:|---:|
| **tokens per day, 200,000** | **33.1M** | **15 claims/day: what breaks first, 165× over** |
| requests per day, 1,000 (4.57 model calls per claim, measured: 32 over 7 claims) | about 11,750 | 219 claims/day |
| tokens per minute, 8,000 | | 0.62 claims/minute, 896/day |
| cost | $7.46/day | does not break |
| latency | p50 41.8 s of model time per claim (20b), plus a 5.95 s MCP cold start per FNOL | |

**The provider's tokens-per-day cap breaks first, at 15 claims a day.** Even the
client's normal 1,800 FNOLs a month (60 a day) is 4× over it. Cost never binds:
the whole hailstorm week is about $52. The plan, ranked:

1. A paid tier sized at **at least 33.1M tokens/day**: about 55K tokens a minute
   over a 10-hour desk day.
2. Cut the give-ups. Each costs about 2× a clean referral, and 22% of suite cases
   gave up.
3. Keep the MCP servers running between FNOLs: the 5.95 s cold start is paid
   per FNOL today.
4. Hail FNOLs are nearly all NG-1102: the date-filtered whole-form read is
   cacheable per (form, edition).

## 9. The closed failure → test loop

- **Failure:** a loss judged against wording that took effect after it.
- **Tests:** W12-B1 to B6 in `evals/cases/week12_cases.jsonl`, the
  `edition_in_force` assertion, and the guard's in-force check on every citation.
- **Red:** `eval run --version w12-v1 --label before --ids W12-B1,...` gave 5/5
  cases with wrong-edition citations.
- **Green:** `--version w12-v2` gave 0/7 on 120b and 0/35 on 20b.

A second loop, decision language:

- **Red:** prompt w12-3 on W12-B4 drew 3 rejections, then manual triage
  ([evidence](evidence/loop_red_decision_language.txt)).
- **Fix:** the rejection now quotes the offending fragment and offers
  replacement vocabulary. The guard is unchanged.
- **Green:** with w12-5, 2 of the 4 suite cases that tried a decision word
  recovered to an accepted referral, and **0 of 9 shipped one**.

## 10. The hostile questions

- **"How many cases have a loss date between two versions, and what do they
  score?"** Six: five straddle cases and the day-of control. Wrong-edition
  citations: 5/5 cases date-blind, 0/5 with the filter (20b) and 0/2 (120b). All
  assertions together: 3/6, and the failures are give-ups and a dropped
  sub-limit, not editions.
- **"Does it ever say covered? Show me the assertion, not the prompt."**
  - The runtime guard: `src/referral.py`, `DECISION_RE` and `validate()`. It
    rejects the referral, so it never ships.
  - The eval assertion: `no_decision_language` in `evals/week12.py`.
  - The numbers: 4/9 cases tried, 0/9 shipped.
- **"Show me the trace where it got the sub-limit right, and the assertion that
  would have caught it."** Right: `tr_1de01aa5041b`, $10,000 WE-4 ed. 07-23.
  Caught: `three_numbers`, on `tr_7bc57a30a81c`, where 20b dropped that same
  sub-limit.
- **"Reproduce claim 4471-A's answer in 18 months."**
  - **Wording:** the request line pins the model, the prompt version and its
    SHA-256, and for every passage the chunk id, the edition and the text
    SHA-256, plus the index fingerprint and the git commit. A new edition is a
    new file, so the same wording version and the same context can be checked
    against the trace hash by hash.
  - **The model's words:** they are not bit-reproducible. The same input at
    temperature 0 gave different answers in Week 11.
- **"What is in your logs, and what did your MCP server hand another squad?"**
  - **Logs:** pseudonyms for claim and policy numbers, no names, addresses or
    injuries, and notes as hashes (PII test: PASS, 62 lines).
  - **Our server:** policy terms and wording only. The third-party claims server
    is the hop that carries PII, and the host redacts its results before the
    model or any log sees them (weakness #2).
