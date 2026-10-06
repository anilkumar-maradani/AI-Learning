# Week 9 — the same failing call, old docstring/error vs new

Server: `policy_docs` (ours), tool `search_policy`. Before = the server file at `5c8265b`, after = working tree. Agent, model, prompt, config and question identical; only the server file differs.

The failing call: the adjuster quotes a form number that does not exist (NG-1150; the earth-movement form is NG-1105).

## Tool description the model saw

Before:

```
Search policy documents.
```

After:

```
Read Northgate Mutual endorsement wording: coverage clauses, exclusion-table
rows, deductible and sublimit rules. Use it whenever an answer depends on what
a form actually says; quote the clause ids (e.g. GM-3) and exclusion codes
(e.g. E-83) it returns.

form_number (optional) restricts the search to one form and then returns that
form's COMPLETE wording, so one call per form is enough. Form numbers look
like NG-NNNN. The library holds NG-1101 to NG-1106 only. Without form_number,
returns the best-matching passages across every form for the query.

It knows nothing about any particular claim and does not decide coverage.

Errors are written for you to act on:
  "form NG-xxxx not found"  -> the number is wrong; the message lists every
                               form in the library, retry with the right one
                               or drop form_number.
  "is not a form number"    -> fix the format (NG-NNNN) and retry.
  "policy library unavailable" -> a server fault; do not retry, tell the
                               adjuster the wording could not be read.
```

## Transcripts

### Before

Config: `temporary copy of mcp_config.json, policy_docs pointed at the older server file` · stop: `final_answer` · laps 3 · 4395 tokens · $0.00082

Discovered: `policy_docs__search_policy`, `claims_system__get_claim_status`, `claims_system__get_adjuster_notes`

**Adjuster:** The insured's agent says endorsement NG-1150 is the form that deals with water from a pipe that broke because the ground moved. Look up that form's wording and tell me whether such a loss is covered.

- lap 1: **`policy_docs__search_policy`** (server `policy_docs`, MCP tool `search_policy`) `{"form_number": "NG-1150", "query": ""}`
  - **isError: true** — `Error: lookup failed`
- lap 2: **`policy_docs__search_policy`** (server `policy_docs`, MCP tool `search_policy`) `{"query": "NG-1150"}`
  - `{"passages": [{"chunk_id": "NG-1101_sa_chunk_002", "form_number": "NG-1101", "clause_id": "SECTION-I", "text": "SECTION I — WHAT THIS ENDORSEMENT COVERS"}, {"chunk_id": "NG-1101_sa_chunk_009", "form_number": "NG-1101", "clause_id": "PREAMBLE", "text": "END OF ENDORSEMENT NG-1101 ed. 01-26"}, {"chunk...`

**Final answer:**

> I could not locate any policy document for endorsement **NG‑1150**. The policy‑document search returned only NG‑1101 and NG‑1102 passages; no text for NG‑1150 was found. Without the wording of that endorsement I cannot determine whether water from a pipe that broke because the ground moved is covered. The needed form text is missing.

### After

Config: `mcp_config.json` · stop: `final_answer` · laps 3 · 6065 tokens · $0.00130

Discovered: `policy_docs__search_policy`, `claims_system__get_claim_status`, `claims_system__get_adjuster_notes`

**Adjuster:** The insured's agent says endorsement NG-1150 is the form that deals with water from a pipe that broke because the ground moved. Look up that form's wording and tell me whether such a loss is covered.

- lap 1: **`policy_docs__search_policy`** (server `policy_docs`, MCP tool `search_policy`) `{"form_number": "NG-1150", "query": ""}`
  - **isError: true** — `form NG-1150 not found: the policy library holds only NG-1101 Escape of Water Endorsement; NG-1102 Windstorm, Hurricane and Hail Endorsement; NG-1103 Mold and Wet Rot Limited Coverage Endorsement; NG-1104 Valuable Articles Endorsement; NG-1105 Earth Movement Exclusion Endorsement; NG-1106 Home Busin...`
- lap 2: **`policy_docs__search_policy`** (server `policy_docs`, MCP tool `search_policy`) `{"query": "water escape caused by earth movement"}`
  - `{"passages": [{"chunk_id": "NG-1105_sa_chunk_007", "form_number": "NG-1105", "clause_id": "EXCLUSION-TABLE", "text": "EXCLUSION TABLE — NG-1105 ed. 03-26\n\n| Code | Excluded Peril                        | Scope                                                                 |\n|------|-------------...`

**Final answer:**

> The endorsement that addresses water escaping from a pipe that broke because the ground moved is **NG‑1105 Earth Movement Exclusion Endorsement**. It contains **Exclusion E‑83 – “Water escape caused by earth movement”** and **Clause GM‑3**, which states that a loss caused by earth movement is excluded even when another cause (such as an escape of water) contributed, specifically “water that escapes from a pipe that broke because the ground moved.” Therefore, a loss of that type is **excluded and not covered** under the policy.

