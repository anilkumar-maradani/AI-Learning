| Mode | Before | After | Change |
|---|---:|---:|---|
| skipped_required_lookup | 0 | 0 | same |
| payout_before_lookup | 0 | 0 | same |
| payout_without_facts | 0 | 0 | same |
| repeated_identical_call | 0 | 0 | same |
| redundant_lookup | 1 | 0 | better |
| unneeded_detour | 0 | 0 | same |
| invalid_argument | 0 | 0 | same |
| invented_tool_name | 1 | 3 | worse |
| stopped_without_answer | 0 | 0 | same |
| wrong_outcome | 1 | 3 | worse |

| Metric | Before | After |
|---|---:|---:|
| tool_choice_accuracy | 80% | 70% |
| argument_validity | 100% | 100% |
| step_efficiency | 1.25 | 1.29 |
| cost_p50 | $0.00133 | $0.00120 |
| cost_max | $0.00365 | $0.00225 |
| cost_mean | $0.00140 | $0.00128 |
| tokens_per_claim | 6,222 | 5,817 |
| latency_p50 | 4.76s | 8.70s |
| outcome_pass_rate | 90% | 70% |
| trajectory_pass_rate | 80% | 70% |
| gap | +0.10 | +0.00 |
