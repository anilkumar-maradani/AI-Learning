# Week 6 — validate the claim-summary judge before trusting its number

| Number | Value |
|---|---:|
| **agreement_before** (judge v1 vs labels) | **72%** (18/25) |
| **agreement_after** (judge v2 vs labels) | **64%** (16/25); 65% on the 23 cases not used as examples |
| Assertions vs judged criteria | **4 vs 1** |
| Pass rate, all 25 (assertions AND judge v2) | 16% |

The app under test is `src/summariser.py`. It writes the closing summary for a
closed claim from the claim file (policy terms, estimate, dated adjuster notes
ending in the decision), and runs on the small model `openai/gpt-oss-20b`.

## One command

```powershell
.\.venv\Scripts\python.exe evals\week6.py
```

```
Week 6 eval — 25 cases, 4 assertions + 1 judged criterion, judge v2

mode                              n  assertions    judge  pass rate
citation-not-machine-readable     5      1/5         5/5        20%
decisive-fact-buried              4      1/4         4/4        25%
position-contradicts-body         5      1/5         3/5        20%
rule-not-applied                  5      1/5         4/5         0%
wrong-form-or-clause              6      1/6         6/6        17%
regression                        2      0/2         1/2         0%
ALL                              25      5/25      22/25        16%

pass = all assertions pass AND judge says PASS
```

The low pass rate comes from the assertions, not the judge: most summaries
write codes and dates with a non-breaking hyphen (see section 2).

## 1. Eval set: 25 cases, each tagged with one Week 5 mode, 2 real regressions

`evals/cases/week6_cases.jsonl`. Each case is tagged with the one Week 5
taxonomy mode ([archive/week5_error_analysis/taxonomy.md](../archive/week5_error_analysis/taxonomy.md))
it is built to provoke:

| Week 5 mode | Tag | What the case contains |
|---|---|---|
| 1. source marker not machine-readable | `citation-not-machine-readable` | a decision with codes and amounts that must survive into the summary in a parseable form |
| 2. opening position contradicts the explanation | `position-contradicts-body` | notes that reverse (insured says "sudden", plumber says 12 days; "truck hit the wall", engineer says settling) |
| 3. rules from the wrong form's table | `wrong-form-or-clause` | two forms attached, or a look-alike exclusion (E-42 vs E-46, VA-2 vs E-73) |
| 4. rests on a truncated chunk | `decisive-fact-buried` | 5–6 notes where the deciding fact is in the last note |
| 5. quotes the rule, doesn't apply it | `rule-not-applied` | a threshold to apply: 10-day seepage, 72-hour drying, 30 days unoccupied, a 15-year-old roof, 2% hurricane deductible |

**Regression cases** come from a traced "production" run of the summariser
over all 30 closed claims (`python evals/week6.py produce`,
`traces/summariser_traces.jsonl`). `select` took two runs that failed an
assertion, from different modes:

| Case | Claim | Source trace | Failed in production |
|---|---|---|---|
| 2 | CLM-2026-10002 | `tr_303b76b2c75e` | date_of_loss_parseable, exclusion_cited_on_denial |
| 5 | CLM-2026-10005 | `tr_a5f0690a354e` | exclusion_cited_on_denial |

"Replayed verbatim" is checked, not asserted. Each regression case stores the
SHA-256 of the exact model input from its trace, and `summarise` refuses to run
if the input rebuilt from the claim store hashes differently.

## 2. Assertions vs judged criteria: 4 vs 1

**Assertions** (`src/assertions.py`: regex and date parsing, no model):

| # | Assertion | Check |
|---|---|---|
| 1 | `claim_number_echoed` | `CLM-\d{4}-\d{5}` present and equal to the file's number |
| 2 | `date_of_loss_parseable` | a date that parses and equals the date of loss |
| 3 | `excess_numeric` | the deductible / excess is written as a number, and it is the right one |
| 4 | `exclusion_cited_on_denial` | whenever the summary states a denial, an `E-NN` code is cited, including the one the adjuster relied on |

**Judged criterion** ([judge_v1.txt](judge_v1.txt)), exactly one and binary:
*faithful outcome*. Would someone reading only the summary get the coverage
outcome and payable amount the adjuster decided, with no unsupported facts?
The four assertion checks are listed in the prompt as things the judge must
not judge.

**What the assertions already found:** 24 of 30 production summaries fail at
least one assertion, and 21 of those failures are `exclusion_cited_on_denial`.
The main cause is the Week 5 top mode again: the model writes `E‑41`,
`CLM‑2026‑10005` and `2026‑05‑14` with a non-breaking hyphen (U+2011), in 29
of 30 outputs. A reader sees the right code, but an audit regex matches
nothing. The assertions deliberately do not normalise this, because the
machine-readable form is the point. (One regex bug of mine, the excess
pattern tripping on "all‑peril", was fixed before the production run that
the cases were drawn from.)

## 3. Blind protocol, enforced in code

| Step | Guard in `evals/week6.py` |
|---|---|
| `label` | refuses to start if any `judge_results_*.json` exists; shows the claim file and summary only (no judge output, no assertion results, no mode tag), in a fixed shuffled order; every label stores the SHA-256 of the exact summary text it was given |
| `judge` | refuses unless `labels_25.json` is **committed and unmodified**; writes the labels commit hash into `judge_results_v1.json`; refuses if any summary changed after it was labelled |
| `iterate` | refuses unless `prediction.txt` is committed |

## 4. Ordering evidence

```
8197651  2026-10-01 00:22:55 +0530  week 6 labels            <- labels_25.json, alone
4dfebe9  2026-10-01 00:28:28 +0530  week 6 judge v1 run
ebd43af  2026-10-01 00:29:23 +0530  week 6 prediction        <- before any iteration
e84367a  2026-10-01 00:29:32 +0530  week 6 judge v2 prompt
```

`judge_results_v1.json` records `labels_commit: 8197651...`. The judge
command refused to run until that commit existed.

**How the labels were entered.** The labels file records a time for each
label. Case 10 was entered through the labelling tool at 18:43:03 UTC. The
other 24 all carry the same second, 18:50:14 UTC, and appear in case-id order,
not the tool's shuffled order. So they were not entered one by one in the
tool. They are committed before any judge run, and that is what the ordering
above proves.

## 5. Agreement before → after

| | Agreement | Disagreements |
|---|---:|---|
| judge v1 | **72%** (18/25) | 7, all "judge PASS, label FAIL": cases 1, 4, 6, 9, 18, 20, 21 |
| judge v2 | **64%** (16/25) | 9: cases 1, 5, 6, 9, 11, 18, 20, 21, 25 |
| judge v2, excluding the 2 few-shot cases | 65% (15/23) | |

**How v2 was built** (`python evals/week6.py iterate`): v1 had no "too strict"
disagreements, so v2 takes the first two "too lenient" ones, cases 1 and 4.
It appends them to the v1 prompt as worked examples ("your earlier verdict:
PASS; correct verdict: FAIL", with the label's reason). Diff:
`git diff 4dfebe9 e84367a -- reports/week6/`.

**What changed between v1 and v2:**

| Case | Label | v1 | v2 | What the claim file shows |
|---|---|---|---|---|
| 1 | FAIL | PASS | PASS | was a few-shot example; the judge still passed it, and the summary does match the decision ($3,600) |
| 4 | FAIL | PASS | **FAIL** | was a few-shot example; v2 now fails it for "adds Hurricane Delia, not in the file", but the adjuster note names Hurricane Delia |
| 5 | PASS | PASS | **FAIL** | v2 says the insured never reported rain entering; the first notice of loss says exactly that |
| 11 | FAIL | FAIL | **PASS** | summary matches the decision (laptop denied under E-93, printer $800); v1's reason was wrong |
| 25 | PASS | PASS | **FAIL** | v2 objects to "the $1,000 deductible applies"; the decision note lists the $1,000 deductible |

Net effect: v2 became stricter, and 3 of its new FAILs (cases 4, 5, 25) rest
on reasons the claim file contradicts. Agreement moved 2 cases in the wrong
direction.

## 6. Two disagreements: who was right

**Case 21, CLM-2026-10022 (scheduled painting): label FAIL, judge PASS in v1
and v2. The judge was right.** The label says "says covered when the decision
was a denial". The adjuster's decision is "covered under VA-1, repair cost
$2,300 paid in full, deductible $0". The summary says covered under VA-1, no
deductible, $2,300 payable. They match, so the label is wrong.

**Case 4, CLM-2026-10004 (hurricane roof): label FAIL, judge PASS in v1, FAIL
in v2. v1 was right; the label and v2 are wrong.** The label says "unsupported
fact added about the cause". The summary's cause (Hurricane Delia, shingles
and flashing lost on the west slope, no water inside), its $6,000 hurricane
deductible and its $7,200 payable all appear in the adjuster notes. v2
reproduced the label because the label was one of its few-shot examples, and
it invented a reason ("Hurricane Delia is not stated in the claim file") to
get there.

Checked against the claim file, **all 7 of v1's disagreements are cases where
the summary matches the adjuster's decision.** The label's reason does not fit
the file in each one (the table in section 5 and the per-case reasons in
`judge_results_v1.json`). This is the common mistake the task warns about,
from the other side. When the ruler is wrong, teaching the judge the ruler's
answers makes the judge worse, and agreement still did not go up.

## 7. Prediction, scored

`prediction.txt` (committed at `ebd43af`, before the iteration):

> 2 will agree with me more because it sees two cases it got wrong

**It was wrong.** Agreement went down, from 72% to 64% (65% on the 23 cases that
were not examples). Where it went wrong:

- Showing the judge two cases did not make it copy them: case 1 stayed PASS.
- Where the judge did adopt the example's verdict (case 4), it generalised to
  "be stricter". That created 2 new disagreements (cases 5 and 25) on
  summaries the label had passed, and flipped case 11 from agree to disagree.
- The prediction assumed the labels were the right answers. On the evidence
  in section 6, the disagreements were label errors, so no judge change could
  have fixed them. The fix is in the labels.
