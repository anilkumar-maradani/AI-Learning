# Label sheet: suite

Criterion (BASIS): Does the referral point the adjuster to the facts the claim actually turns on (the decisive fact from the notes, e.g. the leak duration, what broke the pipe, days unoccupied, whether a body of water overflowed, whether drying started in time, whether cover was in force on the loss date), stated accurately, without asserting facts that are not in the claim file? Ignore citations format, editions, numbers and wording choice — code checks those.

Write labels to `reports/week12/labels_suite.json` as `{"labels": {"W12-B1": "PASS", ...}, "sha256": {...}}`; the sha256 block is pre-filled in `labels_suite.template.json`. Do not open any judge output first.

## W12-B1 · CLM-2025-30001

**Claim file**

```
Claim number: CLM-2025-30001
Policy number: HOP-6610301
Status: closed
Date of loss: 2025-08-11
Forms attached: NG-1101
Coverage A limit: $380,000
All-peril deductible: $1,000
First notice of loss: Heavy rain overnight; water came in under the back door and through a basement window well. Basement carpet and drywall soaked.
Adjuster notes:
  [2025-08-12] adj-131: Spoke to the insured, [CLAIMANT:212ab6], at the property, [ADDRESS:ff047f]. About 90 mm of rain fell in three hours. Surface water ran off the neighbouring field, pooled against the rear wall and came in through the basement window well and under the rear door. No river, stream or lake near the house; the creek half a mile away stayed within its banks.
  [2025-08-12] adj-131: While carrying boxes up from the basement, Ms. [CLAIMANT:212ab6] slipped on the wet stairs and [INJURY:69110b]; she was [INJURY:9a3b17]. Noted for the file only; no liability claim made.
  [2025-08-15] adj-131: Estimate agreed: basement carpet $4,200, drywall and paint $3,900, dehumidifier hire $650. Total $8,750.
  [2025-08-20] adj-131: Decision: covered under NG-1101 ed. 07-23 WE-4 (rainwater and surface runoff); E-42 does not apply because no body of water overflowed. Covered loss $8,750 less the $1,000 deductible = $7,750, within the WE-4 sublimit of $10,000. Payable $7,750. Reason code COV-WE4.
```

**Referral**

```
REFERRAL TO ADJUSTER — no coverage decision made
Claim: CLM-2025-30001
Loss date: 2025-08-11
Coverage in force on the loss date: yes (loss date falls in the term 2024-11-27 to 2025-11-26)
Wording to read (edition in force, resolved for the loss date):
  - NG-1101 ed. 07-23 · WE-2 — data/policy/NG-1101_07-23.txt#L22 (in force 2023-07-01 to 2025-12-31; resolved for loss date 2025-08-11) — access and tear-out sublimit applies to restoration
  - NG-1101 ed. 07-23 · WE-4 — data/policy/NG-1101_07-23.txt#L33 (in force 2023-07-01 to 2025-12-31; resolved for loss date 2025-08-11) — rainwater/surface runoff damage
  - NG-1101 ed. 07-23 · WE-1 — data/policy/NG-1101_07-23.txt#L14 (in force 2023-07-01 to 2025-12-31; resolved for loss date 2025-08-11) — sudden escape of water from plumbing not applicable but noted for completeness
Deductible: $1,000.00 (all_peril, policy register term)
Sub-limit: none cited
Policy limit (Coverage A): $380,000.00
Facts the wording turns on:
  - Heavy rain 90mm in 3 hrs
  - water entered through basement window well and under rear door
  - basement carpet and drywall soaked
  - estimate $8,750
  - loss date 2025-08-11
Questions for the adjuster:
  - Is the water entry considered a sudden escape of water under WE-1 or a rainwater/surface runoff event under WE-4?
  - Does the sublimit of $10,000 under WE-4 apply after the $1,000 deductible?
  - Are there any exclusions that might apply, such as E-42 flood or E-41 seepage?
```

Label: PASS / FAIL

## W12-B2 · CLM-2025-30002

**Claim file**

```
Claim number: CLM-2025-30002
Policy number: HOP-6610302
Status: closed
Date of loss: 2025-12-31
Forms attached: NG-1101, NG-1103
Coverage A limit: $300,000
All-peril deductible: $500
First notice of loss: Rainstorm on New Year's Eve; water ran down the driveway and into the garage-level den.
Adjuster notes:
  [2026-01-02] adj-118: Storm on 31 December 2025, roughly 70 mm of rain. The driveway slopes toward the house and runoff entered the den under the garage-side door. No watercourse overflowed anywhere in the area. Drying started the same night with fans the insured owns.
  [2026-01-05] adj-118: Estimate: den flooring $3,900, skirting and paint $1,300, contents (sofa, rug) $900. Total $6,100. No mold found.
  [2026-01-09] adj-118: Decision: covered under NG-1101 ed. 07-23 WE-4, the edition in force on the 2025-12-31 date of loss; the 01-26 edition, which treats runoff as excluded under E-42, took effect the next day and does not apply. $6,100 less the $500 deductible = $5,600, within the $10,000 WE-4 sublimit. Reason code COV-WE4.
```

**Referral**

```
REFERRAL TO ADJUSTER — no coverage decision made
Claim: CLM-2025-30002
Loss date: 2025-12-31
Coverage in force on the loss date: yes (loss date falls in the term 2025-03-12 to 2026-03-11)
MANUAL TRIAGE NEEDED: agent stopped (no_referral) without an accepted referral
Deductible: $500.00 (all_peril, policy register term)
Sub-limit: none cited
Policy limit (Coverage A): $300,000.00
```

Label: PASS / FAIL

## W12-B3 · CLM-2026-30003

**Claim file**

```
Claim number: CLM-2026-30003
Policy number: HOP-6610303
Status: closed
Date of loss: 2026-01-01
Forms attached: NG-1101
Coverage A limit: $340,000
All-peril deductible: $1,000
First notice of loss: Rain overnight into New Year's Day; surface water came in through the back door into the kitchen.
Adjuster notes:
  [2026-01-03] adj-118: Rain ran from the evening of 31 December into the early hours of 1 January 2026. Insured says the water came in at about 03:00 on 1 January, when runoff from the road crossed the yard and entered under the kitchen door. No watercourse overflowed.
  [2026-01-06] adj-118: Estimate: kitchen flooring $4,400, lower cabinets $2,100. Total $6,500.
  [2026-01-08] adj-118: Decision: denied under NG-1101 ed. 01-26 E-42 (surface water and flood: runoff entering from outside). The loss happened on 2026-01-01, when the 01-26 edition was in force; the 07-23 WE-4 runoff cover ended on 2025-12-31. Deductible $1,000. Reason code EXC-E42.
```

**Referral**

```
REFERRAL TO ADJUSTER — no coverage decision made
Claim: CLM-2026-30003
Loss date: 2026-01-01
Coverage in force on the loss date: yes (loss date falls in the term 2025-02-04 to 2026-02-03)
Wording to read (edition in force, resolved for the loss date):
  - NG-1101 ed. 01-26 · WE-1 — data/policy/NG-1101_01-26.txt#L14 (in force 2026-01-01 to open; resolved for loss date 2026-01-01) — water entered dwelling via surface runoff, sudden escape
  - NG-1101 ed. 01-26 · WE-2 — data/policy/NG-1101_01-26.txt#L22 (in force 2026-01-01 to open; resolved for loss date 2026-01-01) — access and tear-out for interior damage
  - NG-1101 ed. 01-26 · WE-3 — data/policy/NG-1101_01-26.txt#L28 (in force 2026-01-01 to open; resolved for loss date 2026-01-01) — deductible application
  - NG-1101 ed. 01-26 · E-42 — data/policy/NG-1101_01-26.txt#L43 (in force 2026-01-01 to open; resolved for loss date 2026-01-01) — surface water and flood exclusion applies to runoff from outside
Deductible: $1,000.00 (all_peril, policy register term)
Sub-limit: none cited
Policy limit (Coverage A): $340,000.00
Facts the wording turns on:
  - Rain overnight into New Year's Day; surface water came in through back door into kitchen
  - Water entered at ~03:00 on 1 Jan via runoff from road crossing yard
  - No watercourse overflowed
  - Estimate kitchen flooring $4,400 lower cabinets $2,100 total $6,500
Questions for the adjuster:
  - Is the water considered a sudden escape under WE-1 or does E-42 exclude it as surface water?
  - Did the loss continue for 10+ days before discovery, affecting applicability of E-41?
  - What is the exact deductible amount after applying the $1,000 all-peril deductible?
```

Label: PASS / FAIL

## W12-B4 · CLM-2026-30004

**Claim file**

```
Claim number: CLM-2026-30004
Policy number: HOP-6610304
Status: closed
Date of loss: 2026-01-20
Forms attached: NG-1101, NG-1103
Coverage A limit: $410,000
All-peril deductible: $1,000
First notice of loss: Pipe burst in the upstairs bathroom wall; water came through the ceiling below. Mold found a week later.
Adjuster notes:
  [2026-01-21] adj-104: Copper supply line in the bathroom wall split overnight; the insured found water coming through the dining-room ceiling at 07:00 and shut the main valve. Drying contractor started within 36 hours.
  [2026-01-29] adj-104: Mold found behind the wall cavity during tear-out. Hygienist confirms it grew from this escape of water; no sign of earlier leaks.
  [2026-02-03] adj-104: Estimate: ceiling and drywall $3,400; mold remediation $9,200.
  [2026-02-06] adj-104: Decision: water damage covered under NG-1101 ed. 01-26 WE-1: $3,400 less $1,000 deductible = $2,400. Mold covered under NG-1103 ed. 07-23 MR-1 (drying began within 48 hours), capped at the MR-2 sublimit of $5,000; the 02-26 edition with its $7,500 sublimit took effect on 2026-02-01, after the date of loss. Total payable $7,400. Reason code COV-MR2.
```

**Referral**

```
REFERRAL TO ADJUSTER — no coverage decision made
Claim: CLM-2026-30004
Loss date: 2026-01-20
Coverage in force on the loss date: yes (loss date falls in the term 2025-12-13 to 2026-12-12)
MANUAL TRIAGE NEEDED: agent stopped (no_referral) without an accepted referral
Deductible: $1,000.00 (all_peril, policy register term)
Sub-limit: none cited
Policy limit (Coverage A): $410,000.00
```

Label: PASS / FAIL

## W12-B5 · CLM-2026-30005

**Claim file**

```
Claim number: CLM-2026-30005
Policy number: HOP-6610305
Status: closed
Date of loss: 2026-02-14
Forms attached: NG-1101, NG-1105
Coverage A limit: $360,000
All-peril deductible: $1,000
First notice of loss: Water came up through the family room floor; a pipe under the slab broke.
Adjuster notes:
  [2026-02-15] adj-121: Visited the insured, [CLAIMANT:0d9941], at [ADDRESS:68e4c4]. Leak detection found the cold water line under the slab sheared.
  [2026-02-20] adj-121: Engineer's report: the slab dropped about 3 cm at the west corner after ground subsidence over an old mine working; the line sheared because the slab moved. The insured's son [INJURY:3fa3db] on the lifted floor tiles; no treatment needed beyond rest.
  [2026-02-24] adj-121: Estimate: flooring and drywall $6,800; slab and line repair $3,500.
  [2026-02-27] adj-121: Decision: the 2026-02-14 date of loss falls under NG-1105 ed. 07-23 (the 03-26 edition took effect on 2026-03-01). Under GM-3 of ed. 07-23 the water damage is given back: flooring and drywall $6,800 covered under NG-1101 ed. 01-26 WE-1, less $1,000 deductible = $5,800 payable. Slab and line repair $3,500 denied under NG-1105 ed. 07-23 E-81. Reason code COV-GM3.
```

**Referral**

```
REFERRAL TO ADJUSTER — no coverage decision made
Claim: CLM-2026-30005
Loss date: 2026-02-14
Coverage in force on the loss date: yes (loss date falls in the term 2025-12-01 to 2026-11-30)
Wording to read (edition in force, resolved for the loss date):
  - NG-1101 ed. 01-26 · WE-1 — data/policy/NG-1101_01-26.txt#L14 (in force 2026-01-01 to open; resolved for loss date 2026-02-14) — water escaped suddenly from plumbing under slab
  - NG-1101 ed. 01-26 · WE-2 — data/policy/NG-1101_01-26.txt#L22 (in force 2026-01-01 to open; resolved for loss date 2026-02-14) — access and tear-out for interior wall/floor
  - NG-1101 ed. 01-26 · WE-3 — data/policy/NG-1101_01-26.txt#L28 (in force 2026-01-01 to open; resolved for loss date 2026-02-14) — all-peril deductible applies
  - NG-1105 ed. 07-23 · GM-1 — data/policy/NG-1105_07-23.txt#L13 (in force 2023-07-01 to 2026-02-28; resolved for loss date 2026-02-14) — earth movement defined
  - NG-1105 ed. 07-23 · GM-3 — data/policy/NG-1105_07-23.txt#L22 (in force 2023-07-01 to 2026-02-28; resolved for loss date 2026-02-14) — earth movement caused plumbing break and water escape
Deductible: $1,000.00 (all_peril, policy register term)
Sub-limit: none cited
Policy limit (Coverage A): $360,000.00
Facts the wording turns on:
  - Water escaped suddenly from a cold water line under slab
  - Slab movement due to subsidence over old mine
  - Leak caused by earth movement
  - Damage to flooring, drywall, slab and line
  - All-peril deductible $1,000
```

Label: PASS / FAIL

## W12-B6 · CLM-2025-30006

**Claim file**

```
Claim number: CLM-2025-30006
Policy number: HOP-6610306
Status: closed
Date of loss: 2025-12-20
Forms attached: NG-1101
Coverage A limit: $290,000
All-peril deductible: $1,000
First notice of loss: Frozen pipe burst at a holiday cottage while it was empty.
Adjuster notes:
  [2025-12-22] adj-117: Cottage was unoccupied from 2025-11-05 until the caretaker found the burst on 2025-12-20: 45 days. Heating was switched off and the system was not drained. A pipe in the utility room split and water ran through the ground floor.
  [2025-12-29] adj-117: Estimate: floors and skirting $5,600, plaster and paint $1,700, pipe repair $400.
  [2026-01-05] adj-117: Decision: covered under NG-1101 ed. 07-23 WE-1. E-44 in ed. 07-23 applies only after more than 60 days unoccupied; this cottage was empty 45 days. (The 01-26 edition's 30-day threshold was not in force on 2025-12-20.) Pipe repair $400 denied under E-45. Covered $7,300 less $1,000 deductible = $6,300 payable. Reason code COV-WE1.
```

**Referral**

```
REFERRAL TO ADJUSTER — no coverage decision made
Claim: CLM-2025-30006
Loss date: 2025-12-20
Coverage in force on the loss date: yes (loss date falls in the term 2025-08-30 to 2026-08-29)
Wording to read (edition in force, resolved for the loss date):
  - NG-1101 ed. 07-23 · WE-1 — data/policy/NG-1101_07-23.txt#L14 (in force 2023-07-01 to 2025-12-31; resolved for loss date 2025-12-20) — Frozen pipe burst causes sudden escape of water
  - NG-1101 ed. 07-23 · WE-2 — data/policy/NG-1101_07-23.txt#L22 (in force 2023-07-01 to 2025-12-31; resolved for loss date 2025-12-20) — Access and tear-out for interior damage
  - NG-1101 ed. 07-23 · WE-3 — data/policy/NG-1101_07-23.txt#L28 (in force 2023-07-01 to 2025-12-31; resolved for loss date 2025-12-20) — All-peril deductible applies
  - NG-1101 ed. 07-23 · E-44 — data/policy/NG-1101_07-23.txt#L56 (in force 2023-07-01 to 2025-12-31; resolved for loss date 2025-12-20) — Unoccupied for 45 days, heating off, system not drained
Deductible: $1,000.00 (all_peril, policy register term)
Sub-limit: none cited
Policy limit (Coverage A): $290,000.00
Facts the wording turns on:
  - Frozen pipe burst at holiday cottage
  - Cottage unoccupied 45 days, heating off, system not drained
  - Escape lasted 45 days
  - Water ran through ground floor
  - Estimate $5,600 floors, $1,700 plaster, $400 pipe repair
Questions for the adjuster:
  - Is the escape considered continuous or repeated seepage under E-41?
  - Does the 45‑day duration trigger exclusion E-44?
  - What is the actual deductible amount after applying the all‑peril deductible?
```

Label: PASS / FAIL

## W12-N1 · CLM-2025-30007

**Claim file**

```
Claim number: CLM-2025-30007
Policy number: HOP-6610307
Status: closed
Date of loss: 2025-11-02
Forms attached: NG-1101
Coverage A limit: $310,000
All-peril deductible: $1,000
First notice of loss: Washing machine hose burst; laundry room and hallway flooded.
Adjuster notes:
  [2025-11-03] adj-104: Hose split at the tap connector while the machine ran; water ran for about 30 minutes. Laundry and hallway floors wet.
  [2025-11-06] adj-104: Estimate: flooring $3,800, skirting and paint $900.
  [2025-11-10] adj-104: Decision: declined. No cover was in force on the 2025-11-02 date of loss: the policy was cancelled for non-payment with effect from 2025-10-15. Coverage wording not reached. Reason code NIF-CANCELLED.
```

**Referral**

```
REFERRAL TO ADJUSTER — no coverage decision made
Claim: CLM-2025-30007
Loss date: 2025-11-02
Coverage in force on the loss date: NO (term 2025-04-01 to 2026-03-31 was cancelled with effect from 2025-10-15 (non-payment of premium))
Deductible: n/a (none_scheduled_article, policy register term)
Sub-limit: none cited
Policy limit (Coverage A): n/a
Facts the wording turns on:
  - Washing machine hose burst on 2025-11-02
  - Loss occurred while machine was running
  - Floors wet in laundry and hallway
  - Estimate $3,800 flooring, $900 skirting/paint
  - Policy cancelled effective 2025-10-15
```

Label: PASS / FAIL

## W12-N2 · CLM-2025-30008

**Claim file**

```
Claim number: CLM-2025-30008
Policy number: HOP-6610308
Status: closed
Date of loss: 2025-02-26
Forms attached: NG-1101
Coverage A limit: $330,000
All-peril deductible: $1,000
First notice of loss: Water heater failed and flooded the basement utility room.
Adjuster notes:
  [2025-03-04] adj-117: Insured says the water heater tank failed on 26 February and she found the basement wet that evening. Policy shows inception 2025-03-01; the insured says she bought the house on 20 February and arranged cover the following week.
  [2025-03-06] adj-117: Estimate: utility room flooring and drywall $2,900, water heater $1,250.
  [2025-03-12] adj-117: Decision: declined. The loss on 2025-02-26 happened before the policy incepted on 2025-03-01, so no cover was in force. Reason code NIF-PRE-INCEPTION.
```

**Referral**

```
REFERRAL TO ADJUSTER — no coverage decision made
Claim: CLM-2025-30008
Loss date: 2025-02-26
Coverage in force on the loss date: NO (loss date is before the policy first incepted on 2025-03-01)
Wording to read (edition in force, resolved for the loss date):
  - NG-1101 ed. 07-23 · WE-1 — data/policy/NG-1101_07-23.txt#L14 (in force 2023-07-01 to 2025-12-31; resolved for loss date 2025-02-26) — water escape from a household appliance
  - NG-1101 ed. 07-23 · WE-2 — data/policy/NG-1101_07-23.txt#L22 (in force 2023-07-01 to 2025-12-31; resolved for loss date 2025-02-26) — access and tear‑out sublimit
  - NG-1101 ed. 07-23 · WE-3 — data/policy/NG-1101_07-23.txt#L28 (in force 2023-07-01 to 2025-12-31; resolved for loss date 2025-02-26) — all‑peril deductible and sublimit application
  - NG-1101 ed. 07-23 · E-41 — data/policy/NG-1101_07-23.txt#L49 (in force 2023-07-01 to 2025-12-31; resolved for loss date 2025-02-26) — continuous seepage exclusion
  - NG-1101 ed. 07-23 · E-42 — data/policy/NG-1101_07-23.txt#L51 (in force 2023-07-01 to 2025-12-31; resolved for loss date 2025-02-26) — flood exclusion
Deductible: n/a (all_peril, policy register term)
Sub-limit: none cited
Policy limit (Coverage A): n/a
Facts the wording turns on:
  - Water heater failed on 26 Feb 2025
  - Basement utility room flooded
  - Policy inception 01 Mar 2025
  - Loss date 26 Feb 2025
Questions for the adjuster:
  - Is the loss within the scope of WE‑1 despite the policy not being in force?
  - What is the applicable all‑peril deductible?
  - What is the coverage limit for this loss?
```

Label: PASS / FAIL

## W12-O1 · CLM-2026-20101

**Claim file**

```
Claim number: CLM-2026-20101
Policy number: HOP-5510201
Status: open
Date of loss: 2026-06-03
Forms attached: NG-1101, NG-1103
Coverage A limit: $400,000
All-peril deductible: $1,000
First notice of loss: Supply hose behind the washing machine split and water spread across the laundry room and hallway.
Estimate lines:
  - Laminate flooring, laundry and hallway: $4,100
  - Baseboards and paint: $1,350
  - Drying equipment, 3 days: $850
Adjuster notes:
  [2026-06-04] adj-104: Braided hose split at the crimp while the machine was running. Insured heard it and shut the valve within about 20 minutes. Laundry and hallway floors wet; drying contractor on site the same day.
  [2026-06-06] adj-104: Estimate reviewed and agreed. No sign of earlier leaks, no mold.
```

**Referral**

```
REFERRAL TO ADJUSTER — no coverage decision made
Claim: CLM-2026-20101
Loss date: 2026-06-03
Coverage in force on the loss date: yes (loss date falls in the term 2025-11-28 to 2026-11-27)
Wording to read (edition in force, resolved for the loss date):
  - NG-1101 ed. 01-26 · WE-1 — data/policy/NG-1101_01-26.txt#L14 (in force 2026-01-01 to open; resolved for loss date 2026-06-03) — water escaped suddenly from a household appliance (hose) and continued for fewer than ten days, meeting the definition of a sudden escape of water.
  - NG-1101 ed. 01-26 · WE-2 — data/policy/NG-1101_01-26.txt#L22 (in force 2026-01-01 to open; resolved for loss date 2026-06-03) — the escape occurred inside the dwelling’s structure (laundry room and hallway), requiring access and tear‑out.
  - NG-1101 ed. 01-26 · WE-3 — data/policy/NG-1101_01-26.txt#L28 (in force 2026-01-01 to open; resolved for loss date 2026-06-03) — the all‑peril deductible applies once per occurrence before any sublimit is considered.
  - NG-1103 ed. 02-26 · MR-1 — data/policy/NG-1103_02-26.txt#L13 (in force 2026-02-01 to open; resolved for loss date 2026-06-03) — mold is within the scope of MR‑1 when it originates from a water loss that is itself within the scope of WE‑1 and when drying began within 72 hours of discovery.
  - NG-1103 ed. 02-26 · MR-2 — data/policy/NG-1103_02-26.txt#L20 (in force 2026-02-01 to open; resolved for loss date 2026-06-03) — the mold sublimit of $7,500 applies to all mold, fungi, and wet rot in one policy period, after the deductible is subtracted.
Deductible: $1,000.00 (all_peril, policy register term)
Sub-limit: $7,500.00 — NG-1103 ed. 02-26 · MR-2 — data/policy/NG-1103_02-26.txt#L20
Policy limit (Coverage A): $400,000.00
Facts the wording turns on:
  - Supply hose behind washing machine split, causing water to spread across laundry room and hallway.
  - Insured shut the valve within about 20 minutes of noticing the leak.
  - Drying contractor on site the same day.
  - No mold noted by 2026‑06‑06.
  - Loss date falls within the policy term (2025‑11‑28 to 2026‑11‑27).
Questions for the adjuster:
  - Confirm that the water escape qualifies as a “sudden” escape under WE‑1 (i.e., did the hose split and water escape for fewer than ten days before discovery?).
  - Verify that the drying began within 72 hours of discovery to satisfy MR‑1(b).
  - Determine the amount for the adjuster to set after applying the all‑peril deductible and the mold sublimit, if applicable.
```

Label: PASS / FAIL

