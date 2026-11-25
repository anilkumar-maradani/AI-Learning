# Eval report: suite

Integrated system, 9 cases (`evals/cases/week12_cases.jsonl`). Assertions run first, all in code; the judge scores one criterion code cannot.

| Mode | n | Pass rate |
|---|---:|---:|
| not-in-force | 2 | 2/2 = 100% |
| sublimit-vs-deductible | 1 | 0/1 = 0% |
| wrong-edition-risk | 6 | 3/6 = 50% |
| **all** | 9 | **5/9 = 56%** |

| Assertion | Pass rate |
|---|---:|
| referral_made | 7/9 = 78% |
| no_decision_language | 9/9 = 100% |
| in_force_correct | 9/9 = 100% |
| edition_in_force | 9/9 = 100% |
| loss_date_stated | 9/9 = 100% |
| citations_resolve | 9/9 = 100% |
| three_numbers | 5/9 = 56% |
| decisive_clause_surfaced | 7/9 = 78% |

- Wrong-endorsement-version citation rate: **0/6 = 0%** of cases with citations
- Decision language attempted and caught by the guard: 4/9 = 44%; shipped: 0/9 = 0%
- Judge agreement with hand labels: **8/9 = 89%**
- Tool-choice accuracy: 32/33 = 97%
- Outcome pass 5/9 = 56%, trajectory pass 9/9 = 100%, gap -44.4 points
- Cost per claim triaged: mean $0.00155; tokens per claim: mean 11,180; latency p50 41.78 s, p95 123.12 s (model + tool time, rate-limit waits excluded)
