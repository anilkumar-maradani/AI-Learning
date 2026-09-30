| | Agent | Workflow |
|---|---:|---:|
| Pass rate | 90% | 90% |
| p50 latency (s) | 4.76 | 1.90 |
| Total tokens (10 claims, all laps) | 62,216 | 14,255 |
| Cost per claim (USD) | $0.00140 | $0.00047 |

| Claim | Class | Expected | Agent | Workflow | Agent path |
|---|---|---|---|---|---|
| CLM-2026-20101 | clean | covered / 5300 | PASS | PASS | get_claim → search_policy → compute_payout |
| CLM-2026-20102 | notes_change_rule | excluded / 0 | PASS | PASS | get_claim → search_policy |
| CLM-2026-20103 | notes_trigger_exclusion_lookup | excluded / 0 | PASS | PASS | get_claim → search_policy → compute_payout |
| CLM-2026-20104 | notes_change_rule | covered / 9800 | PASS | PASS | get_claim → search_policy → compute_payout |
| CLM-2026-20105 | notes_change_rule | partially_covered / 7500 | PASS | PASS | get_claim → search_policy → search_policy → search_policy → search_policy → compute_payout |
| CLM-2026-20106 | notes_trigger_exclusion_lookup | excluded / 0 | PASS | PASS | get_claim → search_policy → compute_payout |
| CLM-2026-20107 | clean | covered / 8500 | PASS | PASS | get_claim → search_policy → compute_payout |
| CLM-2026-20108 | notes_trigger_exclusion_lookup | excluded / 0 | PASS | PASS | get_claim → search_policy |
| CLM-2026-20109 | clean | partially_covered / 2500 | PASS | FAIL: missing exclusion E-92 | get_claim → search_policy → compute_payout |
| CLM-2026-20110 | missing_notes | needs_info / None | FAIL: no parseable final answer | PASS | get_claim → error |
