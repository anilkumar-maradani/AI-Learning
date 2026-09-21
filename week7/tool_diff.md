# Tool Description Diff — Third Tool (`compute_payout`)

The first two tools existed implicitly in the pipeline (retrieval + exclusion lookup).
`compute_payout` is the new, explicitly named third tool added for Week 7.

## Tool Registry Before Week 7

```
Tools: [implicit retrieval via hybrid_search(), implicit exclusion reading]
```

## Tool Registry After Week 7 (`src/tools.py`)

```diff
  TOOLS = [
      {
          "type": "function",
          "function": {
              "name": "get_claim_details",
              "description": "Retrieve the endorsement context and policy wording
                              relevant to a claim's loss description. Returns ranked
                              endorsement chunks (form_number, clause_id, text) from
                              the indexed homeowners policy corpus. Call this first.",
              "parameters": {
                  "claim_number": str,
                  "loss_description": str  [required]
              }
          }
      },
      {
          "type": "function",
          "function": {
              "name": "check_policy_exclusions",
              "description": "Look up whether a specific exclusion code applies to
                              a given loss type under a named endorsement form. Returns
                              the exact exclusion table row text, the coverage
                              determination (COVERED / NOT_COVERED / PARTIALLY_COVERED),
                              and any conditions or sublimits that attach.",
              "parameters": {
                  "form_number": str,        [required]
                  "exclusion_code": str,
                  "loss_type": str           [required]
              }
          }
      },
+     {
+         "type": "function",
+         "function": {
+             "name": "compute_payout",
+             "description": "Compute the net payable amount on a claim given the
+                             damage estimate, the applicable deductible (all-peril
+                             or named-storm), any form-specific sublimits (e.g. the
+                             $10,000 mold remediation cap under HO-0306 MF-2), and
+                             the coverage determination from the exclusion lookup.
+                             Returns the payable amount, the deductible applied, any
+                             sublimit that capped the payment, and a plain-English
+                             explanation. Call this only after check_policy_exclusions
+                             has returned a determination — never before.",
+             "parameters": {
+                 "damage_estimate":  float  [required],
+                 "deductible_amount": float [required],
+                 "sublimit":         float  [optional, nullable],
+                 "claim_status": enum {     [required]
+                     "COVERED",
+                     "NOT_COVERED",
+                     "PARTIALLY_COVERED",
+                     "DEPENDS_ON_FACTS"
+                 }
+             }
+         }
+     },
  ]
```

## Why No Overlap

| Tool | Job | What it does NOT do |
|------|-----|---------------------|
| `get_claim_details` | Semantic search over endorsement corpus | No coverage judgement, no arithmetic |
| `check_policy_exclusions` | Exclusion table lookup → coverage determination | No retrieval of general context, no arithmetic |
| `compute_payout` | Post-lookup arithmetic (damage − excess − sublimit) | No retrieval, no exclusion lookup, no model call |

The `claim_status` enum (4 values) enforces that `compute_payout` is always called
after `check_policy_exclusions` — the enum values are exactly the determinations the
exclusion tool can return, creating an explicit data dependency.
