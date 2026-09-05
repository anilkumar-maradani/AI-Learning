"""
week_traffic.py — The population of adjuster questions the claims assistant
handled this week.

This file is written BEFORE any output is inspected. It is not a test set and
it is not curated for failure: the questions are the natural question space of
six homeowners endorsements as an adjuster desk would hit them — code lookups,
deductible arithmetic, definitional questions, coverage calls on a described
loss, condition and deadline questions, and a tail of questions whose answer is
simply not in the indexed corpus.

Volume per form is roughly proportional to how often each endorsement comes up
on a water-and-weather-heavy desk, not to how interesting its failures are.

``demo_set()`` is separate and IS curated: it is the ten claims shown at the
monthly review. It exists for the bonus comparison, not for sampling.
"""

import random

# ---------------------------------------------------------------------------
# Synthetic claimants. Names/numbers/addresses are fabricated; they exist so the
# redaction path has something real-shaped to strip before the trace is written.
# ---------------------------------------------------------------------------

CLAIMANTS = [
    ("Margaret Whitfield", "CLM-2026-04417", "HOP-8842116", "41 Harborview Lane"),
    ("Devon Okafor", "CLM-2026-04422", "HOP-8842190", "1180 Cypress Bend Road"),
    ("Priya Ramanathan", "CLM-2026-04431", "HOP-8843005", "7 Willow Creek Drive"),
    ("Hector Salinas", "CLM-2026-04440", "HOP-8843118", "2290 Ridgemont Avenue"),
    ("Alice Fenwick", "CLM-2026-04448", "HOP-8843204", "58 Marbury Court"),
    ("Tomas Lindqvist", "CLM-2026-04455", "HOP-8843277", "914 Elmsworth Street"),
    ("Nadia Bourne", "CLM-2026-04463", "HOP-8843390", "33 Kestrel Way"),
    ("Reuben Achterberg", "CLM-2026-04470", "HOP-8843412", "605 Tanglewood Terrace"),
    ("Wendy Castellanos", "CLM-2026-04478", "HOP-8843508", "17 Bramble Hill Road"),
    ("Idris Mahmood", "CLM-2026-04485", "HOP-8843590", "4420 Lakeshore Boulevard"),
    ("Colleen Dwyer", "CLM-2026-04492", "HOP-8843644", "88 Ferngully Lane"),
    ("Stefan Nowak", "CLM-2026-04501", "HOP-8843701", "3106 Palmetto Circle"),
    ("Yolanda Pierce", "CLM-2026-04509", "HOP-8843788", "72 Sandhill Place"),
    ("Marcus Delacroix", "CLM-2026-04516", "HOP-8843822", "1509 Ironwood Drive"),
    ("Beatriz Coutinho", "CLM-2026-04524", "HOP-8843901", "24 Foxglove Court"),
    ("Owen Brightwater", "CLM-2026-04533", "HOP-8844017", "861 Quarry Ridge Road"),
    ("Farida Nasser", "CLM-2026-04541", "HOP-8844090", "12 Rosemary Lane"),
    ("Gregor Halloran", "CLM-2026-04550", "HOP-8844155", "3377 Windmere Avenue"),
    ("Simone Aubert", "CLM-2026-04558", "HOP-8844233", "49 Copperfield Way"),
    ("Nathaniel Osei", "CLM-2026-04566", "HOP-8844310", "1720 Sycamore Street"),
    ("Imogen Fairbrother", "CLM-2026-04575", "HOP-8844388", "6 Thistledown Court"),
    ("Rafael Menendez", "CLM-2026-04583", "HOP-8844451", "2044 Northgate Drive"),
    ("Helena Vogt", "CLM-2026-04591", "HOP-8844529", "95 Larkspur Terrace"),
    ("Dominic Achebe", "CLM-2026-04600", "HOP-8844603", "530 Whitmore Road"),
    ("Sarah Kowalczyk", "CLM-2026-04608", "HOP-8844677", "18 Juniper Bend"),
    ("Tobias Reinholt", "CLM-2026-04615", "HOP-8844750", "1263 Ashgrove Lane"),
    ("Meera Chandrasekhar", "CLM-2026-04623", "HOP-8844828", "77 Stonebridge Way"),
    ("Julian Petrakis", "CLM-2026-04631", "HOP-8844901", "3915 Beacon Hill Drive"),
    ("Adaeze Nwosu", "CLM-2026-04640", "HOP-8845019", "22 Heatherfield Court"),
    ("Lars Bjornsson", "CLM-2026-04648", "HOP-8845093", "1408 Meadowlark Avenue"),
]


# ---------------------------------------------------------------------------
# Questions. (question, loss_summary)
# ---------------------------------------------------------------------------

_WATER = [
    ("Does exclusion E-17 apply under form HO-0304 ed. 03-24, and is a burst supply line covered?",
     "Copper supply line to upstairs bathroom ruptured overnight; water through ceiling into kitchen."),
    ("What does 'sudden and accidental' mean under CLAUSE WD-1 in HO-0304?",
     "Adjuster needs the definition to classify a slow-onset kitchen leak."),
    ("The insured found the leak eleven days after it started. Is that still sudden and accidental?",
     "Under-sink braided line weeping for an estimated 11 days before discovery."),
    ("Insured reported the water loss 5 days after discovering it. Does that affect coverage?",
     "Discovery on the 3rd, first notice of loss on the 8th; laundry room supply line."),
    ("Is a pipe under the slab considered a supply line under HO-0304?",
     "Under-slab line to the guest bath failed; jackhammer access required."),
    ("What is exclusion E-11 and how many days of leakage triggers it?",
     "Water staining on a wall cavity of indeterminate age."),
    ("Does E-13 exclude a backup from the city sewer main?",
     "Sewage backed up through the basement floor drain after heavy rain."),
    ("If the washing machine hose overflowed and the machine is 18 years old, is it covered?",
     "Top-load washer, purchased 2008, hose let go during a cycle."),
    ("Does E-14 cover or exclude water coming up through the basement floor?",
     "Basement standing water after three days of rain; no visible pipe failure."),
    ("Ice dam caused water intrusion at the eaves. Is that covered?",
     "Ice dam on north-facing roof, water into the second floor bedroom ceiling."),
    ("What is the premium for the HO-0304 endorsement?",
     "Underwriting query attached to the claim file."),
    ("Does HO-0304 cover water damage from an automatic fire sprinkler discharge?",
     "Sprinkler head in the finished attic discharged with no fire present."),
    ("The insured deliberately left a hose running to thaw a pipe and flooded the room. Covered?",
     "Insured admits leaving a garden hose running indoors overnight."),
    ("What does HO-0304 say a supply line is, exactly?",
     "Dispute over whether a fixture tailpiece counts as a supply line."),
    ("Is storm runoff entering through a door sill covered under HO-0304?",
     "Two inches of water across the ground floor after a heavy downpour."),
    ("When does HO-0304 take effect and does it override the base policy water wording?",
     "Loss date 2024-02-20; need to confirm which wording governs."),
    ("Which exclusion applies if there is no annual inspection record for an ice dam claim?",
     "No maintenance records produced by the insured."),
    ("Is the E-17 row an exclusion or a confirmation of coverage?",
     "Adjuster reading the exclusion table wants to be sure before denying."),
    ("Does the 72 hour reporting requirement apply to all water claims under this form?",
     "Late-reported dishwasher supply failure."),
    ("Insured's dishwasher supply line burst and soaked the subfloor. What is our coverage position?",
     "Dishwasher inlet line failed while the family was away for the weekend."),
    ("What is the difference between E-11 and E-16?",
     "Old appliance with slow overflow; need the right denial basis if any."),
    ("Water from a burst supply line reached the finished basement. Any sublimit under HO-0304?",
     "Finished basement, laminate flooring and drywall damaged."),
]

_STORM = [
    ("What is the Named Storm deductible amount under HO-0305 ed. 03-24?",
     "Roof and siding damage during a named tropical storm."),
    ("Coverage A is $300,000. What is the named storm deductible?",
     "Named storm landfall; Cov A limit $300,000 per declarations."),
    ("Coverage A is $200,000. What deductible applies to a named storm loss?",
     "Named storm; Cov A limit $200,000."),
    ("Does the named storm deductible stack with the all-peril deductible?",
     "Adjuster computing net payable on a wind claim."),
    ("The storm was unnamed when it hit us but was named two days later. Which deductible?",
     "System named after passing the risk; damage occurred pre-naming."),
    ("Is storm surge covered under HO-0305?",
     "Coastal property, three feet of surge through the ground floor."),
    ("What does exclusion E-22 exclude?",
     "Adjuster checking a denial basis on a coastal claim."),
    ("What does exclusion E-23 cover?",
     "Pre-loss photographs show some existing shingle damage."),
    ("Is the named storm deductible per storm season or per occurrence?",
     "Two named storms in the same season affected this risk."),
    ("Does E-24 exclude the insured's home office equipment on a storm claim?",
     "Storm damaged a home office setup in the converted garage."),
    ("Total damage came to $4,200 on a named storm claim. Is anything payable?",
     "Named storm, Cov A $300,000, estimate $4,200."),
    ("What is a Named Storm under this endorsement — does it include a tropical depression?",
     "System was a tropical depression at time of loss."),
    ("Does HO-0305 charge additional premium?",
     "Underwriting question on the file."),
    ("When did HO-0305 become effective?",
     "Loss date 2024-03-10; need to confirm applicability."),
    ("Which authority has to name the storm for the deductible to apply?",
     "Storm named by a foreign meteorological agency."),
    ("The declarations page shows a $1,000 all peril deductible. Named storm loss — what do we apply?",
     "Named storm damage, all-peril deductible $1,000 on the dec page."),
    ("Is wind damage from an unnamed thunderstorm subject to the named storm deductible?",
     "Straight-line winds, no named system involved."),
    ("Does the named storm deductible apply if the storm only contributed to the loss?",
     "Roof already aging; named storm accelerated the failure."),
]

_MOLD = [
    ("Is mold covered after a burst pipe under HO-0306?",
     "Mold discovered behind drywall two weeks after a covered supply line burst."),
    ("What is the mold remediation sublimit and what conditions attach to it?",
     "Contractor estimate for remediation is $14,000."),
    ("Does HO-0306 cover air quality testing?",
     "Insured obtained a $900 air sampling report."),
    ("What does exclusion E-25 say?",
     "Adjuster confirming whether lab costs are payable."),
    ("Mold was found but the water event was reported 5 days after discovery. Sublimit available?",
     "Late reporting on the underlying water loss."),
    ("Does the mold exclusion apply if the water event itself was not covered?",
     "Mold following a long-term uncovered seepage."),
    ("What is excluded under E-27 and what maintenance record is required?",
     "HVAC condensate line mold; no service records since 2021."),
    ("The mold was present before the policy started. Which exclusion applies?",
     "Inspection notes pre-existing mold in the crawlspace."),
    ("Remediation estimate is $14,000. How much can we pay under HO-0306?",
     "Licensed remediation contractor's written estimate on file."),
    ("Does HO-0306 override the base policy on mold?",
     "Conflict between base wording and endorsement language raised by counsel."),
    ("What does CLAUSE MF-2 require before we pay remediation?",
     "Verifying preconditions before issuing payment."),
    ("Is wet rot in a floor joist covered?",
     "Wet rot found in joists under a long-term bathroom leak."),
    ("Is bacteria contamination covered under any part of HO-0306?",
     "Sewage-related bacterial contamination in a finished basement."),
    ("Which form and clause defines the water event that MF-2 depends on?",
     "Adjuster needs the cross-referenced definition."),
    ("Does the mold remediation sublimit apply per occurrence or per policy?",
     "Two separate mold findings on the same policy year."),
    ("When did the mold endorsement take effect?",
     "Loss date 2024-03-25; need applicability confirmed."),
    ("Insured wants us to pay for a mold inspection before remediation. Is that covered?",
     "Pre-remediation inspection invoice submitted."),
    ("Does E-23 under HO-0306 exclude dry rot as well as wet rot?",
     "Dry rot found in a window frame."),
]

_SCHEDULED = [
    ("Are scheduled items subject to the Coverage C jewelry sublimit?",
     "A scheduled 3ct diamond ring was lost."),
    ("Is a scheduled ring covered if it is lost overseas?",
     "Ring lost during travel in Portugal."),
    ("One earring of a scheduled pair was lost. How do we value the loss?",
     "Single earring from a scheduled pair of appraised diamond studs."),
    ("What does the pair and set clause say under HO-0307?",
     "Valuation dispute on a partial set loss."),
    ("The appraisal is four years old. Does the schedule still apply?",
     "Appraisal dated 2021 for a scheduled watch."),
    ("Does E-28 apply to a scheduled item that simply disappeared?",
     "Scheduled watch missing with no evidence of theft."),
    ("Does E-28 apply to an unscheduled item that disappeared?",
     "Unscheduled bracelet missing from the bedroom."),
    ("Is earthquake damage to a scheduled item covered under HO-0307?",
     "Scheduled porcelain collection shattered during an earthquake."),
    ("What does exclusion E-31 say?",
     "Adjuster checking whether an earth movement denial is supportable."),
    ("What does exclusion E-32 exclude?",
     "Items seized during a municipal action."),
    ("Is gradual deterioration of a scheduled musical instrument covered?",
     "Cracked soundboard on a scheduled violin, developed over years."),
    ("Are scheduled firearms covered worldwide?",
     "Scheduled shotgun stolen while out of state."),
    ("How current must an appraisal be under this endorsement?",
     "Confirming the appraisal window."),
    ("What happens to coverage if the appraisal has expired?",
     "Expired appraisal on a scheduled necklace."),
    ("Is a scheduled item covered for all risks or named perils?",
     "Broad coverage question from the insured's agent."),
    ("Is war damage to scheduled property covered?",
     "General coverage question raised in an underwriting referral."),
]

_EARTH = [
    ("Does HO-0308 exclude sinkhole damage?",
     "Sinkhole opened under the driveway and cracked the foundation."),
    ("An earthquake ruptured a supply line and flooded the house. Is the water damage covered?",
     "Magnitude 4.6 quake; copper line sheared, water through the ground floor."),
    ("What is the concurrent causation rule under HO-0308?",
     "Wind and soil subsidence both contributed to a wall failure."),
    ("If earth movement causes a fire, is the fire damage covered?",
     "Gas line severed by ground shift, ensuing fire destroyed the kitchen."),
    ("Does the earth movement exclusion cover man-made subsidence from nearby mining?",
     "Active mine two miles away; floor slab cracked."),
    ("Foundation cracks from expansive clay soil. Covered?",
     "Seasonal soil movement, stair-step cracking in the block foundation."),
    ("What does E-34 exclude?",
     "Adjuster confirming the denial code for a settlement claim."),
    ("What does E-35 exclude?",
     "Mudflow from a hillside entered the garage."),
    ("Is normal foundation settling excluded under HO-0308?",
     "Hairline cracks, house built in 2019."),
    ("Does the broadened definition include volcanic eruption?",
     "Ashfall and ground tremor damage."),
    ("Which clause defines earth movement under this form?",
     "Need the clause reference for the denial letter."),
    ("If a landslide damages the house and a covered peril also contributed, how much do we pay?",
     "Landslide plus wind-driven rain on the same date of loss."),
    ("Is debris flow treated the same as mudslide here?",
     "Debris flow after a wildfire burn scar upslope."),
    ("When did HO-0308 take effect?",
     "Loss date 2024-04-28; confirming applicability."),
    ("Does HO-0308 exclude damage from excavation next door?",
     "Neighbouring construction excavation; our insured's wall cracked."),
    ("Is there any exception at all to the earth movement exclusion?",
     "Insured's counsel is arguing for an ensuing loss exception."),
    ("Water pipe broke because of ground shifting. Which form controls, HO-0304 or HO-0308?",
     "Both water damage and earth movement present on one loss."),
    ("What does E-33 cover?",
     "Sudden sinkhole collapse under the rear addition."),
]

_BUSINESS = [
    ("Is exclusion E-19 present in HO-0309 ed. 05-24?",
     "Liability claim from a delivery courier injured on the porch."),
    ("Does the business pursuits exclusion apply to remote work from home?",
     "Insured works remotely for an employer; visitor injured during a work call."),
    ("What is the business equipment sublimit for an in-home office?",
     "Laptop, monitors and a desk chair damaged by a water loss."),
    ("The insured's home is their primary place of business. Does the office exception apply?",
     "Full-time home-based consultancy; client slipped in the hallway."),
    ("Is a home day care operation covered under HO-0309?",
     "Child injured at an in-home day care run by the insured."),
    ("Does the day care exclusion apply if no money changed hands?",
     "Insured watches neighbours' children without charge."),
    ("How many business visitors per week does the exception allow?",
     "Two client visits in one week; injury on the second visit."),
    ("Is professional liability covered under HO-0309?",
     "Insured is an accountant working from home; client alleges an error."),
    ("Is business inventory stored in the garage covered?",
     "Online reseller with stock in the garage, damaged by a water loss."),
    ("Are electronic data and software included in the $2,500 sublimit?",
     "Business laptop destroyed; insured claims the software licences too."),
    ("Is a household cleaner's injury claim covered under this form?",
     "Weekly housekeeper fell on the stairs."),
    ("What does E-37 exclude?",
     "Stock-in-trade damaged in a covered water loss."),
    ("Is the $2,500 sublimit per occurrence or per policy year?",
     "Two separate losses to business equipment in one year."),
    ("Does the in-home office exception apply if the office use is incidental?",
     "Insured has a small desk used for occasional evening work."),
    ("When did HO-0309 become effective?",
     "Loss date 2024-05-20; confirming applicability."),
    ("Business equipment worth $6,000 was damaged. What do we pay?",
     "Home office equipment total $6,000 damaged in a covered loss."),
]

_CROSS = [
    ("A burst supply line caused mold. Which forms apply and what do we pay in total?",
     "Supply line burst reported within 24 hours; mold found on day 12; remediation $9,000."),
    ("Earth movement broke a pipe and mold grew afterwards. What is our position?",
     "Soil subsidence sheared a pipe; mold found three weeks later."),
    ("A named storm drove rain in and mold followed. Which deductible and what mold limit?",
     "Named storm; roof breach; mold in the attic; Cov A $300,000."),
    ("Scheduled jewelry was lost in an earthquake. Does HO-0307 or HO-0308 control?",
     "Scheduled items destroyed when shelving collapsed in a quake."),
    ("What exclusion code covers earth movement, and does it differ between HO-0307 and HO-0308?",
     "Two endorsements on the same policy, both mention earth movement."),
    ("The insured has both HO-0305 and HO-0306. Storm caused water intrusion and mold. What is payable?",
     "Named storm, Cov A $250,000, remediation estimate $11,500."),
    ("Home office equipment was damaged by a burst supply line. What is the limit?",
     "Water loss reached the home office; equipment value $4,000."),
    ("Does the 72 hour reporting rule in HO-0304 also govern the mold sublimit in HO-0306?",
     "Water reported at 80 hours; mold claim follows."),
    ("Which exclusion code number is used for business pursuits, and which form is it in?",
     "Need the code for a denial letter."),
    ("E-22 appears in two of our endorsements. What does each one exclude?",
     "Adjuster wants to avoid citing the wrong form in a denial."),
    ("E-31 appears in two endorsements. Is the wording the same in both?",
     "Earth movement denial being drafted; two forms on the policy."),
    ("If the loss date is before an endorsement's effective date, does the endorsement apply?",
     "Loss date 2024-02-10; several endorsements on file with later effective dates."),
]

_OUT_OF_CORPUS = [
    ("What is the Coverage A dwelling limit on this policy?",
     "Adjuster needs the limit to compute the deductible."),
    ("What does the base homeowners policy say about theft of a bicycle?",
     "Bicycle stolen from an unlocked shed."),
    ("Is there a hurricane deductible under the Florida statute?",
     "Coastal claim, insured cites a state statute."),
    ("What is the NFIP flood policy limit for a single family dwelling?",
     "Insured also carries a separate flood policy."),
    ("Does the auto policy cover the car damaged in the garage collapse?",
     "Vehicle crushed when the garage roof failed."),
    ("What is the loss of use limit under Coverage D?",
     "Insured is in a hotel while repairs proceed."),
    ("How long does the insured have to file suit against us in this state?",
     "Coverage dispute heading towards litigation."),
    ("What is the replacement cost provision in the base policy?",
     "Actual cash value vs replacement cost dispute."),
    ("Does the policy have an appraisal clause for disputed amounts?",
     "Insured demanded appraisal of the loss amount."),
    ("What is the roof surfacing payment schedule for a 20 year old roof?",
     "Aged roof, insured expects full replacement cost."),
]

ALL_QUESTIONS = (
    [("water", q, l) for q, l in _WATER]
    + [("storm", q, l) for q, l in _STORM]
    + [("mold", q, l) for q, l in _MOLD]
    + [("scheduled", q, l) for q, l in _SCHEDULED]
    + [("earth", q, l) for q, l in _EARTH]
    + [("business", q, l) for q, l in _BUSINESS]
    + [("cross_form", q, l) for q, l in _CROSS]
    + [("out_of_corpus", q, l) for q, l in _OUT_OF_CORPUS]
)

CHANNELS = ["adjuster_console", "adjuster_console", "adjuster_console", "batch_review"]


def build_traffic(seed: int = 20260901) -> list[dict]:
    """
    Pair every question with a claimant. Seeded so the week's traffic is
    reproducible; the seed is the date the assistant was switched on.
    """
    rng = random.Random(seed)
    traffic = []
    for i, (topic, question, loss) in enumerate(ALL_QUESTIONS):
        name, claim_no, policy_no, address = CLAIMANTS[rng.randrange(len(CLAIMANTS))]
        traffic.append({
            "claimant_name": name,
            "claim_number": claim_no,
            "policy_number": policy_no,
            "question": question,
            "loss_summary": f"{loss} Property at {address}. Policy {policy_no}.",
            "channel": rng.choice(CHANNELS),
            "tags": [f"topic:{topic}", "population:week_traffic"],
        })
    rng.shuffle(traffic)
    return traffic


# ---------------------------------------------------------------------------
# The demo set — the ten claims shown at the monthly review. Curated on purpose.
# Kept in a separate log so it can never contaminate the random sample.
# ---------------------------------------------------------------------------

_DEMO = [
    ("Does exclusion E-17 apply under form HO-0304 ed. 03-24, and is a burst supply line covered?",
     "Copper supply line ruptured overnight; water through the ceiling."),
    ("What is the Named Storm deductible amount under HO-0305 ed. 03-24?",
     "Roof damage during a named tropical storm."),
    ("What does 'sudden and accidental' mean under CLAUSE WD-1 in HO-0304?",
     "Classifying a kitchen leak."),
    ("Is mold covered after a burst pipe under HO-0306?",
     "Mold behind drywall after a covered supply line burst."),
    ("Does HO-0308 exclude sinkhole damage?",
     "Sinkhole under the driveway cracked the foundation."),
    ("Is exclusion E-19 present in HO-0309 ed. 05-24?",
     "Courier injured on the porch."),
    ("Are scheduled items subject to the Coverage C jewelry sublimit?",
     "Scheduled 3ct diamond ring lost."),
    ("What is the Coverage A dwelling limit on this policy?",
     "Out-of-scope question kept in the demo to show the refusal behaviour."),
    ("What does the base homeowners policy say about theft of a bicycle?",
     "Out-of-scope question kept in the demo to show the refusal behaviour."),
    ("If earth movement causes a fire, is the fire damage covered?",
     "Gas line severed by ground shift, ensuing fire in the kitchen."),
]


def demo_set(seed: int = 20260901) -> list[dict]:
    rng = random.Random(seed + 1)
    out = []
    for question, loss in _DEMO:
        name, claim_no, policy_no, address = CLAIMANTS[rng.randrange(len(CLAIMANTS))]
        out.append({
            "claimant_name": name,
            "claim_number": claim_no,
            "policy_number": policy_no,
            "question": question,
            "loss_summary": f"{loss} Property at {address}. Policy {policy_no}.",
            "channel": "monthly_review_demo",
            "tags": ["population:demo_set"],
        })
    return out


if __name__ == "__main__":
    t = build_traffic()
    print(f"week traffic: {len(t)} questions")
    print(f"demo set:     {len(demo_set())} questions")
    from collections import Counter
    print(Counter(tag for c in t for tag in c["tags"] if tag.startswith("topic:")))
