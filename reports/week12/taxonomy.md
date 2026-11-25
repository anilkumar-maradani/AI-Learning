# Error taxonomy, re-scored on the integrated system

**Sample.** The integrated suite, n = 9 (`runs_suite.jsonl`, gpt-oss-20b,
`w12-v2`, prompt `triage-agent-w12-5`), plus the date-blind before arm, n = 5
(`runs_before.jsonl`, gpt-oss-120b, `w12-v1`) for mode 1. Every trace below was
read, not just scored: the referral, every guard rejection and the tool path.
Frequencies are cases with the mode divided by cases in the sample.

| # | Mode | Frequency | Severity | One trace id | Where it comes from |
|---|---|---:|---|---|---|
| 1 | **Wrong-edition citation**: the wording cited was not in force on the loss date | **5/5 = 100%** date-blind (v1, 120b) → **0/9 = 0%** with the date filter (v2) | critical: the brief's 2024-flood-claim wound | `tr_f066271e5ab8` (v1: 2025-08-11 runoff loss cited NG-1101 **ed. 01-26** E-42) | created by putting two editions behind one retriever; inherited from no earlier week, because there was one edition |
| 2 | **Decision language attempted** ("covered", "excluded", "payable") | **4/9 = 44%** attempted · **0/9 shipped** | critical if shipped; contained by the code guard | `tr_e70eb6f9dc72` ("mold from covered water loss", rejected 3×) | inherited: every Week 7–11 system was built to decide coverage |
| 3 | **Gave up after a guard rejection**: the model answers in prose instead of re-calling `refer_to_adjuster`, so the claim goes to manual triage with no facts | **2/9 = 22%** (v1 120b: 3/5) | medium: a safe failure, but the adjuster gets nothing and the run costs 16–20K tokens | `tr_56af4ef1a097` | **NEW, created by integration**: a code-enforced exit (the referral guard) meets a model that ends turns in prose |
| 4 | **Sub-limit dropped or wrong**: deductible, sub-limit and limit not three correct numbers | **2/7 = 29%** of accepted referrals (B1: WE-4 $10,000 omitted; O1: MR-2 $7,500 given with no mold) | high: money | `tr_7bc57a30a81c` | inherited: Week 6 "rule not applied", deductible/sub-limit confusion |
| 5 | **Unsupported fact asserted**, in a fact or a citation reason | **2/9 = 22%** (B6 "escape lasted 45 days"; O1 "inside the structure, requiring tear-out") | high: B6 points the adjuster at E-41 seepage when the file gives no duration | `tr_42a26b6b1516` | inherited: Week 5 "position contradicts body" |
| 6 | **Decisive fact omitted**: the fact that rules an exclusion out is missing | **1/9 = 11%** among referrals with facts (B1: "no watercourse overflowed") | high: the adjuster has to rediscover why E-42 does not apply | `tr_7bc57a30a81c` | inherited: Week 5 "decisive fact buried" |
| 7 | **Provider schema rejection**: Groq rejects the whole generation when a tool call breaks the schema | **1/1** of the first suite run (`maxItems`) → **0/9** after the fix | high: the claim is lost (`error`) | `tr_d70580150a29` | **NEW, created by integration**: a local tool's JSON schema enforced by the provider inside an MCP-discovered toolset |

## The modes integration created

- **#3, gave up after rejection.** No earlier week had a gate the model could
  fail. Week 7's agent answered with whatever it had. W12's
  `refer_to_adjuster` is the only way out, and the guard can say no. gpt-oss's
  habit of finishing a turn in prose then becomes a referral with no facts.
- **#7, provider schema rejection.** The referral tool's schema had `maxItems: 3`.
  Groq validates every tool call against the schema server-side, and four
  questions killed the generation three times. This was fixed by moving every
  limit into `referral.validate`, which returns a message the model can act on
  (seam 20).
- **#1 is the brief's mode, and it only exists because integration put two
  editions behind one retriever.** It is fixed in code by the loss-date filter.
  On the same five straddle cases, the date-blind arm proposed **15 of 19**
  citations from the wrong edition; the filtered arms proposed **0 of 42**.

## What the guard did

| | Cases |
|---|---:|
| decision language attempted | 4/9 |
| recovered after the rejection (quoted fragment + vocabulary) into an accepted referral | 2/4 (N2, O1) |
| fell back to manual triage | 2/4 (B2, B4) |
| decision language shipped | **0/9** |
| `EXCLUSION-TABLE` cited instead of a row code, rejected and recovered | 2/9 (B3, B6) |
