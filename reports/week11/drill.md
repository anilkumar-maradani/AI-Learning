# Drill: find the coverage answer that ignored an exclusion

**Complaint, the only input:** "an adjuster says it told a claimant something was covered when
the policy excludes it, sometime yesterday." There was no trace id, claim number or time.

| | Drill 1 (Week 11 log as built) | Drill 2 (bonus: one field added) |
|---|---|---|
| **Time-to-find** | **00:21** | **00:09** |
| Slice that found it | **time** (yesterday) + the indexed output `decision` (covered / partially_covered) | **time** + `decision` + the new `adjuster_exclusion_ids` join |
| Queries | 1 `find`, 1 `show` | 1 `find` |
| Rows to read | 10 of 19 (yesterday) | 2 (one was drill 1's plant, already case W11-1) |
| Found | `tr_03c4501f8140`, 2026-11-02 07:03 UTC, adj-104 | `tr_5d0758c1e3af`, 2026-11-02 07:26 UTC, adj-109 |
| Seal | matched | matched |
| Session log (timestamps) | [drill1_session.jsonl](drill1_session.jsonl) | [drill2_session.jsonl](drill2_session.jsonl) |

**Who did what (please read).**
- **Planter:** `python evals/week11.py plant --n N`, standing in for the squadmate. It draws
  claims at random (`random.SystemRandom`) from those the adjuster denied, or partly denied,
  under an exclusion. It skips the 10 suite claims and any claim already turned into a
  regression case. It runs each draw through production (workflow-v2) until one comes back
  covered with the exclusion uncited, then writes that line at a random time yesterday. The
  log is re-sorted by time, and only a salted SHA-256 of the trace id is sealed
  (`plants/plantN.seal.json`). Neither the planter nor the replay printed a trace id or a
  decision.
- **Finder:** Claude, the coding agent that built the log, not a human squadmate.
- **Clock:** the `drill start` and `drill found` timestamps in the session log.
  `drill found` checks the guess against the seal.
- **Bias:** I had read every claim file before drill 1 (to build the system), so I recognised
  the home-office claim on sight. The 00:21 is therefore a lower bound. Without that
  knowledge, the logs alone narrow the 10 rows only to 7 "covered without the complete
  exclusion table of every attached form in context" (the signal below).
- **Re-run this with a real squadmate before Monday.** They run
  `plant --n 3 --by "<their name>"`; you run `drill start --n 3`, then `find`, then
  `drill found --n 3 <id>`.

## Drill 1, query by query

1. `find --day yesterday --decision covered,partially_covered --wide` → **10 of 19
   requests** (the slice combines time with output). The complaint describes the *output*
   ("said it was covered"), so the output decision has to be an indexed field. Searching
   inputs alone gets nowhere: every one of the 19 inputs looks like an ordinary claim.
2. One row stood out: *"Radiator leak in the home office damaged equipment"* →
   `partially_covered`, $2,500 (HB-1 sublimit), no exclusion cited. Its context column read
   `1106:HB-1, 1101:WE-1, 1106:HB-2, 1101:WE-2`: **two forms attached, and neither form's
   exclusion table in context.**
3. `show tr_03c4501f8140` → spans and context ids confirmed it. Then `drill found` → seal
   match at **00:21**.

How each of the five slices alone would have done on yesterday's 19:

| Slice | Rows left | Verdict |
|---|---:|---|
| time (yesterday) | 19 | necessary, not sufficient |
| user (adj-104) | 4 | only if you already knew the adjuster; the complaint doesn't say |
| prompt version | 19 | no help: every request ran workflow-v2 |
| input type (`home_business`) | 3 | only after you suspect a business-property exclusion |
| cost outlier (Tukey fence $0.000795) | 1, and it was `tr_94ff620a501e` | **misses it**: a wrong coverage call costs the same as a right one |

## Under 5 minutes, but this field was missing

Drill 1 finished inside five minutes. The log still could not tell a right "covered" from a
wrong one without outside knowledge. The missing field:

> **`adjuster_exclusion_ids`**: the exclusions the adjuster actually relied on, from the
> claims system's decision event, joined to the request line by `claim_ref`.

The answer is logged at triage time. The adjuster's decision arrives later in the claims
system, and nothing joined the two. Without the join, the only logs-alone signal was "covered
while an attached form's exclusion table was missing from context". On workflow-v2 that is
true of 7 of the 10 covered answers, because the retrieval bug is systemic (see the
diagnosis below).

A second gap showed up in drill 2. The context ids **can mislead** when a passage was
truncated. `tr_5d0758c1e3af` lists `1101:EXCL` in context, but `search_policy` cuts every
passage at 900 characters, so E-44 to E-46 never reached the model. The line records which
chunk was sent, not how much of it. Logging `chars_sent` per context entry would expose that;
it is in the follow-ups.

## Bonus: the field that closed the gap

`python evals/week11.py outcomes` writes `traces/week11/outcomes.jsonl`: one
`claim_decided` event per decided claim, holding `claim_ref` (the same HMAC pseudonym as the
request log), the decision date, the adjuster id and `adjuster_exclusion_ids` (the E-codes
after "denied/excluded under …"). It holds **no note text**, so it carries no PII. The parser
agrees with the Week 6 answer key on 30 of 30 claims.
`find --uncited-outcome` keeps only answers that left out an exclusion the adjuster relied
on.

Drill 2 was then **one query, 2 rows, 00:09**:

```
find --day yesterday --decision covered,partially_covered --uncited-outcome --wide
11-02T07:03 tr_03c4501f8140 adj-104 workflow-v2 water+home_business partially_covered excl=- pay=2500  adjuster relied on E-93, uncited
11-02T07:26 tr_5d0758c1e3af adj-109 workflow-v2 water               covered           excl=- pay=0     adjuster relied on E-46, uncited
      fnol: Water in the basement after a storm.
      ctx : 1102:WH-2,1102:EXCL,1101:EXCL,1103:MR-1
      why : The water entered through wall cracks after three days of rain, which does not meet the
            10-day threshold of exclusion E-41 nor the flood definition of exclusion E-42, so the loss
            is covered under the dwelling form.
```

**Time: 00:21 → 00:09. The one field that closed the gap: `adjuster_exclusion_ids`, joined
on `claim_ref`.** The same join is also a monitor: "answers that disagree with the adjuster"
per day and per prompt version would have raised both of these before anyone complained.

## Diagnosis: retrieval missed the schedule (one hop, from the context ids)

| | Drill 1: `tr_03c4501f8140` (CLM-2026-10011) | Drill 2: `tr_5d0758c1e3af` (CLM-2026-10014) |
|---|---|---|
| Forms attached | NG-1101, NG-1106 | NG-1101 |
| What production said | partially_covered, $2,500, no exclusion | covered, no exclusion |
| What the adjuster decided | employer's laptop denied under **E-93**; printer $1,300 − $500 = **$800** | denied under **E-46** (groundwater) |
| Exclusion rows in front of the model | **none**: retrieval returned HB-1, WE-1, HB-2, WE-2 | NG-1101's table, cut at 900 characters: E-41 to E-43 plus a stub of E-44; **E-46 missing** |
| Retrieval missed it, or the model ignored it? | **retrieval missed it**: the row never reached the model | **retrieval missed it**: the row was cut off; the model's reason names E-41 and E-42, the only rows it saw |

Both are fixed at the retrieval layer by workflow-v3 ([canary.md](canary.md)) and both are now
regression cases: W11-1 and W11-2 in `evals/cases/week11_regressions.jsonl`.
