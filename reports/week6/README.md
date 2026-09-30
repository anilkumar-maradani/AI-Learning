# Week 6 — validate the claim-summary judge before trusting its number

> **Status: waiting on the blind human labels.** The eval set, frozen summaries,
> assertions and judge v1 prompt are committed. The judge has **not** been run.
> Agreement before → after will be filled in only after the labels are
> committed on their own. See [Remaining steps](#remaining-steps).

The app under test is `src/summariser.py`. It writes the closing summary for a
closed claim from the claim file (policy terms, estimate, dated adjuster notes
ending in the decision), and runs on the small model `openai/gpt-oss-20b`.

## One command

```powershell
.\.venv\Scripts\python.exe evals\week6.py
```

Current output (assertions only; the judge column fills in once it has run):

```
mode                              n  assertions    judge  pass rate
citation-not-machine-readable     5      1/5           -          -
decisive-fact-buried              4      1/4           -          -
position-contradicts-body         5      1/5           -          -
rule-not-applied                  5      1/5           -          -
wrong-form-or-clause              6      1/6           -          -
regression                        2      0/2           -          -
ALL                              25      5/25          -          -
```

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

## Remaining steps

1. **Label (human, about 25 minutes):** `.\.venv\Scripts\python.exe evals\week6.py label`
2. Commit the labels alone:
   `git add reports/week6/labels_25.json` then `git commit -m "week 6 blind labels"`
3. `python evals/week6.py judge --version v1` → **agreement_before**
4. Write one sentence in `reports/week6/prediction.txt` saying what the
   iteration will fix, then commit it alone.
5. `python evals/week6.py iterate` → `judge_v2.txt`, built from two of v1's own
   disagreements (one too lenient, one too strict when both exist)
6. `python evals/week6.py judge --version v2` → **agreement_after**, also
   reported on the 23 cases that were not used as examples
7. Commit, then write up the 2 disagreements (who was right) and score the
   prediction here.
