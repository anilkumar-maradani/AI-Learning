# Prompt version bump: workflow-v2 → workflow-v3, and how it ships

| | workflow-v2 (stable) | workflow-v3 (canary) |
|---|---|---|
| System prompt SHA-256 | `cf7def97607979273fd8ad24bb15af42c91a2874f1dfc4cbba7387d5d8046967` | `cf7def97607979273fd8ad24bb15af42c91a2874f1dfc4cbba7387d5d8046967` (**unchanged**) |
| User template SHA-256 | `7153ddf8595d9858c2fac1c2fefa8773c9003cea49ec6542f333d04885d41e51` | `92c74eb35d19ef16d870a5f694abd1983a685a74879c9048c03aa1dcfed54be2` |
| Retrieval | one fixed hybrid query, top 4 passages, each cut at 900 characters | the same, **plus step 2b**: the complete, uncut exclusion table of every attached form (`tools.exclusion_schedule`) |
| Found from | — | production trace `tr_03c4501f8140` (E-93 never in context); regression case W11-1 |
| Suite (10 Week-6 cases + W11-1) | 7/11, W11-1 **RED** | 10/11, W11-1 **GREEN**, 0 regressions ([suite_diff_before_after.txt](suite_diff_before_after.txt)) |
| Suite re-run (+ W11-2 from drill 2) | 7/12, both regression cases **RED** | 12/12 **GREEN**, 0 regressions ([suite_diff_before2_after2.txt](suite_diff_before2_after2.txt)); case 4 is flaky, see [suite.md](suite.md) |
| Cost per query (suite mean) | $0.000538 | $0.000597 (**+11%**, all of it from retrieval-attributed prompt tokens: $0.000078 → $0.000128) |

**What changed, and why it is a retrieval fix.** The system prompt is byte-identical. The only
change to the model's input is a new user-template block, `EXCLUSION SCHEDULES`, that carries
the tables step 2b fetched. Nothing tells the model to behave differently; it now sees the
rows. Prompt versions are append-only (`workflow.PROMPTS`), so v2 still exists and can be
served. Every request line records `prompt.version` and both SHA-256s, which is how the canary
and stable arms are told apart in the log.

**Routing.** `src/triage_service.py`: `POLICYLENS_STABLE_VERSION` (default `workflow-v2`),
`POLICYLENS_CANARY_VERSION` (default `workflow-v3`) and `POLICYLENS_CANARY_PERCENT` (default
`10`). The bucket is a hash of the claim number, so a claim never flips version between two
looks. Today 4 of the 40 claims in the store land in the canary.

## Two-line canary and rollback plan

1. **Canary:** serve workflow-v3 to a sticky 10% of claims (`POLICYLENS_CANARY_PERCENT=10`) for two desk days, then 50%, then promote (`POLICYLENS_STABLE_VERSION=workflow-v3`) only while the suite (12 cases) keeps every regression case GREEN with 0 regressions against v2, canary lines show 0 `find --uncited-outcome` hits, cost per query stays ≤ $0.00075 and p99 ≤ 5 s.
2. **Rollback:** on a canary `--uncited-outcome` hit, any suite regression, or canary p99 > 5 s, set `POLICYLENS_CANARY_PERCENT=0`. Every claim is back on workflow-v2 from its next request, with no deploy, and the v3 lines stay in the log under `prompt.version=workflow-v3` for the post-mortem.
