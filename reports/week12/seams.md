# Week 12: seam list

This list was written at the start of integration, after reading the code
and before any of it was changed.

**The original list below is unedited.** Each seam's status (fixed / accepted /
ran-out-of-time) goes only in the status table at the bottom, keyed by number.
Seams found later go under "Found during integration".

## Original list (before any change)

1. **The corpus has one edition per form.** `data/policy/` holds NG-1101 to
   NG-1106, one edition each, all effective in 2026. There is no prior
   endorsement set, so the brief's central failure (a loss judged against the
   wording that came after it) cannot even happen yet, let alone be measured.
2. **Chunk ids are not edition-scoped.** `chunkers.structure_aware_chunker`
   names chunks `{form}_sa_chunk_{i}`. A second edition of NG-1101 produces the
   same ids, and `ingest._upsert_chunks` upserts, so the second file silently
   overwrites the first. The result is a mixed-edition index, not an error.
3. **There is no date metadata and no retrieval filter.** Chunks carry
   `edition_date` as text, with no effective-from/to dates. `hybrid_search(query,
   n_results)` takes no filter of any kind, so the loss date cannot be enforced in
   code. The only option would be a hint in the prompt.
4. **`tools.search_policy(form_number=…)` selects by form number only.** With
   two editions, it returns both editions' chunks interleaved by `chunk_index`.
   `tools.exclusion_schedule` (workflow-v3) does the same.
5. **No policy register, so the in-force check has nothing to check.** Claim
   files carry the deductible and the Coverage A limit, but no policy term,
   inception, cancellation or lapse dates. No data exists for the
   coverage-in-force check against the loss date.
6. **The third-party claims server leaks across the MCP hop.**
   `claims_system.get_claim_status` returns `claimant_name`, and
   `get_adjuster_notes` returns raw notes, including a closed claim's
   `Decision:` note, which is the eval answer key. `tools.get_claim` withholds
   both. The MCP path withholds neither.
7. **Trace ids stop at the MCP hop.** `mcp_client` sends no `_meta`, and the
   servers log nothing that can be joined to a host trace (`policy_docs` logs
   nothing; `claims_system` logs a timestamped line that cannot be correlated).
8. **The agent loop has no observability.** The Week 11 Tracer, spans, per-span
   cost and the request line instrument `workflow.py` only. `agent.py` and
   `mcp_agent.py` return totals, write no request line, and have no per-span
   cost.
9. **The output contract is a coverage decision.** `triage.CONTRACT_TEXT`
   requires `"decision": "covered|partially_covered|excluded|needs_info"` and a
   payable amount. The compliance rule says nothing automated may state a
   coverage decision. Every Week 7–11 system was built to decide.
10. **Redaction has no injury category.** `redaction.py` handles claim and
    policy numbers, email, phone, a narrow address regex, and names (by roster
    or cue word). Injury descriptions pass straight through, and so does any
    family member's name that has no cue word.
11. **The `policy://exclusion-schedule` resource would mix editions.** It
    concatenates every `data/policy/*.txt` file with no edition label. With two
    editions it lists E-42 twice with different scopes, attached to the system
    prompt, so it would itself cause version confusion.
12. **Passages are still cut at 900 characters.** This was a Week 11 follow-up:
    `tools.search_policy` cuts every passage at 900 characters, and the Week 9
    MCP `policy_docs` server goes through it. NG-1101's exclusion table is
    1,609 characters.
13. **The judge was never validated on agent output.** The Week 6 judge reached
    72% (v1) and 64% (v2) agreement on summaries, below the 85% bar. It has
    never been run on a referral or an agent answer.
14. **`trajectory.py` cannot express the W12 path.** Its path tokens are
    `claim`, `policy:NG-xxxx` and `payout`. There is no in-force check, no
    referral, and no check of the loss date passed to a search.
15. **Two claim readers, hard-coded file lists.** `claim_store.CLAIM_FILES` and
    the vendored `claims_system` server each read their own hard-coded file
    names. A new claim file is visible to one and not the other.
16. **The eval may not fit in a day.** The free Groq tier allows 8,000
    tokens/minute and about 200K tokens/day per model, with no prompt caching
    (checked: two identical 1,479-token calls were both billed in full).
    Week 7–10 agent runs cost 4–26K tokens per claim, so a 30-case suite
    plus a before/after comparison does not fit in one model's daily quota
    unless the agent is lean.
17. **Exclusion codes are reused across editions.** E-42 will exist in both
    editions with different scope. Every existing assertion and regex keys on
    `E-NN` alone, so a code without an edition is ambiguous, and a citation like
    "E-42" proves nothing about which wording was read.

## Found during integration

*(appended as found; the list above is not edited)*

18. **Seam 2 is worse than written above.** With the old ids, the
    07-23 files sort after the 01-26 files, so **all 55** 2026 chunks would be
    overwritten by 2023 wording, not "the first edition" as #2 says. Every Week
    7–11 tool would have answered 2026 claims from 2023 wording, with no error.
    Evidence: [evidence/seam2_chunk_id_collision.txt](evidence/seam2_chunk_id_collision.txt).
19. **The Week 5 name-cue regex is case-sensitive.** `_NAME_CUE` only
    matched lower-case cue words, so "Ms. <surname>" and "Insured <first> <last>"
    were never redacted unless the name was already on the roster. Found while
    testing the fix for #10.
20. **The provider enforces our tool schema, and kills the generation when it
    is violated.** gpt-oss-20b sent 4 `questions_for_adjuster` against
    `maxItems: 3`. Groq rejected the whole generation with a 400 three times, and
    the run ended in `error`. A cosmetic overrun became a lost claim
    ([evidence](evidence/aborted_first_runs/runs_suite_maxitems_failure.jsonl)).
21. **The model reaches for decision words when it paraphrases wording that
    contains them.** On W12-B4, the guard rejected "covered", "excluded" and
    "payable" three times in a row, and the claim fell back to manual triage
    ([evidence](evidence/loop_red_decision_language.txt)).
22. **Five serial laps re-sent 1.5K tokens of prompt and tool definitions each.**
    An accepted referral cost 12,350 tokens, which made the 25-case suite
    larger than one model's daily quota.

## Status

| # | Status | Where / why |
|---|---|---|
| 1 | fixed | `data/policy/NG-110x_07-23.txt`: a prior edition of all six forms, effective 2023-07-01, with material changes (NG-1101 WE-4 runoff cover and a narrower E-42, the E-44 60-day threshold, WE-2 $2,500; the NG-1103 $5,000 mold sublimit and 48 h drying; the NG-1104 $1,000 VA-3; NG-1105 GM-3 gives water damage back and has no E-83; the NG-1106 $250 HB-2) |
| 2 | fixed | `chunkers._id_prefix`: ids carry the edition (`NG-1101_07-23_sa_chunk_006`); `ingest` refuses a repeated id instead of upserting over it |
| 3 | fixed | `editions.py` derives each edition's in-force window from the file headers; chunks carry `effective_from`/`effective_to`; `hybrid_search(..., loss_date=)` filters both the vector and BM25 legs before ranking (`chunk_filter`) |
| 4 | fixed | `tools.search_policy` / `exclusion_schedule` read exactly one edition: the one in force on `loss_date` when given, else the newest (identical to before for every Week 7–11 claim, all dated after every 2026 edition) |
| 5 | fixed | `data/policies/policies.jsonl` (48 policies, terms, one cancellation, one pre-inception loss) and `policy_register.coverage_in_force(policy, loss_date)`, which also names the wording edition in force per attached form |
| 6 | fixed | the claims server now reads a triage-time snapshot (`claim_store.write_triage_snapshot`, `CLAIMS_DATA_DIR`): every claim, decision notes withheld (38 withheld). Its results are redacted by the host (names, addresses, injuries) before the model or any log sees them. The server file itself is untouched (third-party). |
| 7 | fixed | `mcp_client` sends `params._meta = {trace_id, span_id}`; our coverage server logs every call with that trace id and the parent span id, and `policylens.py trace ID` joins both hops. **Accepted:** the third-party claims server ignores `_meta`, so its hop is visible only as a host span. |
| 8 | fixed | `src/triage_agent.py`: a span per lap (tokens, cost, latency) and per tool call (server, hop, result hash, chunk ids with editions); one redacted request line per FNOL (`traces/w12/requests*.jsonl`) |
| 9 | fixed | `refer_to_adjuster` (`src/referral.py`) is the only way a triage ends; a code guard rejects decision words, citations not read in this conversation, clause ids missing from the edition, and editions not in force on the loss date. **Accepted:** the Week 7–11 systems keep their decision contract; they are not behind `policylens.py`. |
| 10 | fixed | `redaction.py`: `INJURY` category (body-part and medical-care anchored; property facts such as "the supply line broke" survive), address leak check, `PERSONAL_KINDS` |
| 11 | fixed | `policy://exclusion-schedule` lists the newest edition of each form only |
| 12 | fixed (W12 path) | the coverage server returns wording uncut (NG-1101's exclusion table arrives whole, 1,851 characters). **Accepted:** the legacy `tools.search_policy` keeps the cut; only Weeks 7–11 use it. |
| 13 | fixed | judge `reports/week12/judge_w12.txt` (one criterion), re-checked on the integrated system's referrals against blind labels; agreement in [README.md](README.md) |
| 14 | fixed | `evals/week12.py trajectory`: in-force check before any wording search, every required form read with the claim's loss date, referral last, no repeated call |
| 15 | fixed | the triage-time snapshot is built from `claim_store`, so the vendored server sees exactly the claims `claim_store` sees, `w12_claims.jsonl` included |
| 16 | fixed | the agent went from 5 serial laps and 12,350 tokens to intake plus 3 laps (notes read by the host over MCP at intake, policy number in the FNOL, every form in one wording call); the suite runs on gpt-oss-20b's quota and the before/after comparison on gpt-oss-120b's |
| 17 | fixed | every citation carries form, edition, clause, loss date and in-force window; the `edition_in_force` assertion checks each one against the edition in force on the loss date |
| 18 | fixed | as #2 |
| 19 | fixed | `_NAME_CUE` cue words are now case-insensitive (`(?i:...)`); the name must still be capitalised |
| 20 | fixed | `maxItems` and `enum` removed from the `refer_to_adjuster` schema; `referral.validate` truncates, or returns a message the model can act on |
| 21 | fixed | the closed loop: prompt `triage-agent-w12-4` gives replacement vocabulary, and the rejection quotes the offending fragment. The guard is unchanged; result in [README.md](README.md) |
| 22 | fixed | the adjuster notes are read at intake over MCP, the FNOL carries the policy number, one wording call covers every form, and the agent runs at `reasoning_effort=low` |
