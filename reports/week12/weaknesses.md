# Top 3 known weaknesses

Written before anyone asked: after the builds and the smoke runs, before the eval
suite's results were read.

1. **Only code stands between the model and the word "covered".** On W12-B4,
   the model (prompt `triage-agent-w12-3`) put "covered", "excluded" and
   "payable" into its referral three times in a row. It was paraphrasing
   endorsement wording that itself says "stays covered under WE-1". The runtime
   guard in `src/referral.py` rejected all three, so nothing shipped, and the
   claim went to manual triage
   ([evidence](evidence/loop_red_decision_language.txt)). Prompt `w12-4` adds
   replacement vocabulary, and the rejection now quotes the offending fragment.
   But the model's tendency is unchanged. Remove or loosen the guard and
   "covered" ships. Each rejected attempt also re-sends about 5K tokens.
2. **The third-party claims server is the weakest hop.**
   - It still hands claimant names, addresses and injury notes to any caller
     holding a token. We redact at the host, but only for our own pipeline.
   - It ignores `_meta`, so the trace id is lost on that hop; it shows only as a
     host span.
   - It is only answer-key-safe because the host points it at a triage-time
     snapshot (`data/claims_at_triage`). Point it back at `data/claims` and every
     closed-claim eval case leaks its own decision note to the agent.
3. **The Week 11 production workflow is still date-blind.** `workflow-v3` attaches
   each form's complete exclusion table through `tools.exclusion_schedule`,
   which reads the **newest** edition. So a 2025 loss on the shipped workflow is
   still shown the 2026 E-42 runoff row and the 2026 30-day E-44 row: the exact
   failure the brief describes. The date filter protects the W12 agent path
   behind `policylens.py` only. Until the workflow passes the loss date, routing
   any pre-2026 loss to it repeats the 2024-flood-claim wound.
