# Week 10 race: single agent vs claims squad

Same 10 Week 6 cases (the first 10 of `evals/cases/week6_cases.jsonl`, by id): 1 (CLM-2026-10001), 2 (CLM-2026-10002), 3 (CLM-2026-10003), 4 (CLM-2026-10004), 5 (CLM-2026-10005), 6 (CLM-2026-10006), 7 (CLM-2026-10007), 8 (CLM-2026-10008), 9 (CLM-2026-10009), 10 (CLM-2026-10010).
Same judge: `reports/week6/judge_v2.txt`. Same model (`gpt-oss-120b`), same tools, same output contract (`src/triage.py`).

| | Single agent (`src/agent.py`) | Squad (`src/squad.py`) |
|---|---:|---:|
| Pass rate (Week 6 judge v2) | 40% | 60% |
| p50 latency (s) | 4.61 | 7.85 |
| p99 latency (s) | 91.25 | 27.67 |
| Total tokens (10 cases, every call) | 106,306 | 65,154 |
| Cost per claim (USD) | $0.00213 | $0.00193 |

Context re-send multiplier: squad 65,154 / single 106,306 tokens = 0.6x. Largest share: orchestrator -> exclusions_worker (every lap re-sends the brief, the notes worker's facts and the form wording read so far), 63% of all squad tokens. Largest single hand-off: orchestrator -> exclusions_worker (lap 4) on case 10, 3,462 tokens.

Judge tokens (31,502 over 20 verdicts) are the ruler, not the arms, and are counted in neither column.
p99 over 10 runs is nearest-rank, i.e. the slowest run.

## Per case

| Case | Claim | Mode | Adjuster decided | Single | Squad |
|---|---|---|---|---|---|
| 1 | CLM-2026-10001 | citation-not-machine-readable | covered | PASS: covered  $3600.0 | PASS: covered  $3600.0 |
| 2 | CLM-2026-10002 | rule-not-applied | denied E-41 | PASS: excluded E-41 $0 | PASS: excluded E-41 $0.0 |
| 3 | CLM-2026-10003 | rule-not-applied | partially_covered E-63 | FAIL: partially_covered E-63 $1800 | FAIL: needs_info  no payable |
| 4 | CLM-2026-10004 | rule-not-applied | covered | FAIL: needs_info  no payable | FAIL: needs_info  no payable |
| 5 | CLM-2026-10005 | position-contradicts-body | denied E-52 | PASS: excluded E-52 $0.0 | PASS: excluded E-52 $0.0 |
| 6 | CLM-2026-10006 | wrong-form-or-clause | covered | PASS: covered  $6200 | PASS: covered  $6200.0 |
| 7 | CLM-2026-10007 | wrong-form-or-clause | denied E-73 | FAIL: None  no payable | PASS: excluded E-73 $0.0 |
| 8 | CLM-2026-10008 | decisive-fact-buried | denied E-83 | FAIL: excluded E-83/E-81 $0.0 | PASS: excluded E-83 $0.0 |
| 9 | CLM-2026-10009 | rule-not-applied | denied E-44 | FAIL: None  no payable | FAIL: needs_info  no payable |
| 10 | CLM-2026-10010 | rule-not-applied | partially_covered E-45 | FAIL: None  no payable | FAIL: excluded E-44 $0.0 |
