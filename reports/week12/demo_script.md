# 10-minute demo script

Before the clock starts: `.\.venv\Scripts\Activate.ps1`. `python policylens.py setup`
has already run (it builds the index with both editions and the triage-time
snapshot).

## Part 1: a real run (0:00–3:00)

```powershell
python policylens.py triage CLM-2025-30001
```

What the room sees, live:

1. **The FNOL arrives.** A trace id is minted. The tools are discovered over MCP
   at runtime: 3 from our coverage server and 2 from the claims system. The
   module that runs the agent names none of them.
2. **Intake.** The adjuster notes are read over MCP from the third-party claims
   server, and the name, address and injury are redacted *before* the model
   sees them. Point at `Ms. [CLAIMANT:…] … [INJURY:…]`.
3. **Lap 1: the coverage-in-force check, a visible tool call.**
   `check_coverage_in_force(HOP-6610301, 2025-08-11)` returns: in force, term
   2024-11-27 to 2025-11-26, and **NG-1101 ed. 07-23** in force on the loss
   date.
4. **Lap 2: the wording.** `search_policy_wording(NG-1101, loss_date=2025-08-11)`
   returns ed. 07-23 only. The date filter is enforced in the server's code,
   not in the prompt.
5. **Lap 3: the referral.** The citation is `NG-1101 ed. 07-23 · WE-4`, with the
   link `data/policy/NG-1101_07-23.txt#L33`, labelled *resolved for loss date
   2025-08-11*. Three separate lines:
   - deductible $1,000, from the policy register;
   - sub-limit $10,000, WE-4 ed. 07-23;
   - policy limit $380,000, Coverage A.

   The header reads **"no coverage decision made"**.
6. `python policylens.py trace <trace id>`: the same trace id appears on the
   host spans **and** on the coverage server's spans, with latency, tokens and
   cost per span.

## Part 2: the failures we found (3:00–6:00)

- **The brief's wound, on our data.** On the date-blind v1, the August 2025
  runoff claim cited **NG-1101 ed. 01-26 E-42**, the 2026 flood exclusion
  (`tr_f066271e5ab8`). The February 2026 earth-movement claim cited the 2026
  GM-3, which says the opposite of the GM-3 in force that day. The re-scored
  taxonomy puts this mode at **100% → 0%** ([taxonomy.md](taxonomy.md)).
- **The modes integration created** ([taxonomy.md](taxonomy.md)):
  - **gave up after a guard rejection** (2/9, `tr_56af4ef1a097`): the
    code-enforced exit meets a model that ends turns in prose;
  - **provider schema rejection**: Groq validates our tool schema and kills the
    generation.
- **The model reaches for "covered".** The guard rejected it three times on
  W12-B4 ([evidence](evidence/loop_red_decision_language.txt)).
- **The other two weaknesses written down before anyone asked**
  ([weaknesses.md](weaknesses.md)): the third-party claims hop, and the Week 11
  workflow still being date-blind.

## Part 3: a number that moved (6:00–8:00)

- **Wrong-endorsement-version citation rate**, on the same five straddle cases,
  gpt-oss-120b, counting every citation the model proposed:
  - **before** (date-blind): **5/5 cases, 15/19 citations**;
  - **after** (loss-date filter in code): **0/2 cases, 0/7 citations**.
  - The suite on gpt-oss-20b: **0/5 cases, 0/35 citations**.
- **Judge agreement** with hand labels on the integrated referrals: v1 **78%**,
  v2 **89%** (n = 9; v2 was tuned on these same cases, so it is optimistic).
- **What the suite does not measure:** implied decisions with no banned word in
  them ("within the scope of WE-4"). The guard catches words, not meaning.

## Part 4: what's next (8:00–10:00)

- **The eval cases that now guard the failure permanently:** W12-B1 to B6 in
  `evals/cases/week12_cases.jsonl`, the `edition_in_force` assertion, and the
  guard's in-force check on every citation.
- **Cost per claim triaged:** **$0.0029** on gpt-oss-120b (12,857 tokens),
  $0.00155 on 20b.
- **A hailstorm week**, 18,000 FNOLs (about 2,571 a day): **the provider's
  tokens-per-day cap breaks first, at 15 claims a day** (200K TPD against
  33.1M needed, 165× over). Cost is about $52 for the whole week.
- **Next, ranked:**
  1. A paid tier sized at 33.1M tokens a day.
  2. Cut the give-ups after a guard rejection (22% of cases, 2× the tokens of a
     clean referral).
  3. Long-lived MCP servers (a 5.95 s cold start per FNOL today).
  4. Date-aware exclusion tables in the Week 11 workflow.
