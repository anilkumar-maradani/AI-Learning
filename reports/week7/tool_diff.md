# Week 7 — tool description diff

Before: `src/tools.py` at commit `75f4192`. After: `src/tools.py` on this branch.

## The bug being fixed: two tools that did the same job

Before Week 7's rework, `get_claim_details` did **not** get a claim. It ran a
hybrid search over the policy corpus, the same thing `check_policy_exclusions`
did with a slightly different query. There was no claim store at all: the
damage estimate and deductible were pasted into the prompt. The old loop dealt
with the resulting thrash by injecting a "Your next call MUST be …" message
into the conversation, which is the prompt patch the task warns against. That
hint is gone. The fix is in the descriptions and in what each tool can reach:

```diff
- get_claim_details(claim_number, loss_description)
-   "Retrieve the endorsement context and policy wording relevant to a claim's
-    loss description. Returns ranked endorsement chunks (form_number, clause_id,
-    text) from the indexed homeowners policy corpus. Call this first ..."
+ get_claim(claim_number: string, pattern ^CLM-\d{4}-\d{5}$)
+   "Return one claim file from the claims system: the policy it is written on
+    (forms attached, Coverage A limit, all-peril deductible, scheduled articles),
+    the first notice of loss, the estimate lines and every dated adjuster note.
+    This is the only source of facts about the loss. It does not contain any
+    policy wording."

- check_policy_exclusions(form_number, exclusion_code, loss_type)
-   "Look up whether a specific exclusion code applies to a given loss type under
-    a named endorsement form. Returns the exact exclusion table row text, the
-    coverage determination (COVERED / NOT_COVERED / PARTIALLY_COVERED) ..."
+ search_policy(query: string, form_number?: string, pattern ^NG-\d{4}$)
+   "Search the wording of the endorsement forms (coverage clauses, exclusion
+    table rows, deductible and sublimit rules) and return the best matching
+    passages with their form number and clause id. It knows nothing about any
+    particular claim; describe the peril or cause of loss you need wording for."
```

`check_policy_exclusions` also returned a "determination" produced by keyword
heuristics (`"subject to" -> PARTIALLY_COVERED`). A retrieval tool should not
make the coverage call, so `search_policy` returns wording only.

## The third tool (added this week)

```diff
+ compute_payout
+   "Arithmetic only: turn a coverage decision you have already made into the
+    amount payable. Applies the deductible from the claim file (or the hurricane
+    deductible, or none for scheduled articles), then any sublimit. It does not
+    look up policy wording and does not decide coverage."
+   parameters:
+     claim_number      string, pattern ^CLM-\d{4}-\d{5}$
+     claim_status      enum ["covered", "covered_subject_to_sublimit", "excluded"]
+     covered_amount    number >= 0
+     deductible_basis  enum ["all_peril", "hurricane", "none_scheduled_article"]
+     sublimit          number >= 0, required only for covered_subject_to_sublimit
```

## Why the three do not overlap

| Tool | Its one job | Can read | Cannot do |
|---|---|---|---|
| `get_claim` | facts about this loss | claim store only | see policy wording |
| `search_policy` | policy wording | policy corpus only | see any claim, decide coverage |
| `compute_payout` | arithmetic | the claim's deductible and Coverage A limit | search, decide coverage |

The deductible amount is read from the claim file inside `compute_payout`.
The model only chooses which *kind* of deductible applies (enum), so it cannot
invent a deductible figure.
