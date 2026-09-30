# PolicyLens claims assistant — failure taxonomy

**Sample:** 20 traces, seed `20260905`, drawn from 106 completed traces of a
130-question week. **Read:** 2026-09-05, by hand, no fixes applied.
**Population fingerprint:** `1143f43c…de4d241`. Method and full sentences in
[notes.md](notes.md).

| # | Failure mode | Count | % of 20 | Severity | Example trace_id |
|---|---|---:|---:|---|---|
| 1 | **Writes the source marker in a format the audit log does not record**, so a coverage decision is filed with zero machine-readable citations | 8 | 40% | Annoys the adjuster — but every one of these is a coverage position with no citation on file | `tr_4cfbcfbbec32` |
| 2 | **Opens with a COVERED / NOT COVERED line that contradicts the explanation underneath it** | 3 | 15% | Wrongly denies or wrongly pays — the adjuster reads line one and stops | `tr_f8f386127038` |
| 3 | **Rules on coverage from an exclusion table that is not the governing form's** — either the form's table was never retrieved, or another form's table was added | 2 | 10% | Wrongly pays or wrongly denies | `tr_1a7c8f8f738b` |
| 4 | **Rests the answer on a clause chunk that stops mid-sentence, or one labelled with a clause it does not contain** | 2 | 10% | Annoys the adjuster — one produced a refusal on a question the corpus answers | `tr_36d865b6f3ae` |
| 5 | **Quotes the rule and stops, never applying it to the facts on the claim file** | 2 | 10% | Annoys the adjuster — but the unapplied condition was dispositive in one of the two | `tr_aed27ca5c15a` |

**Modes overlap.** 13 of the 20 traces showed at least one mode; 7 showed none
and were correct and properly cited. Two traces show two modes each, so the
counts sum to more than 13.

**What the manager asked about.** "It sometimes gets coverage wrong" is modes 2
and 3 — 5 traces, 25% of the sample. Mode 3 is the one that moves money on its
own: in `tr_1a7c8f8f738b` the assistant told an adjuster that HO-0304 imposes no
appliance-age limit on an 18-year-old washing machine, while the E-16 row
covering appliances over 15 years old was simply not among the five chunks
retrieved.

**What the manager did not ask about is bigger.** Mode 1 is 40% of the sample
and touches every kind of question. The answers are right; the citation marker
is written as `[ SOURCE:` or `【SOURCE:` instead of `[SOURCE:`, and the trace
records nothing. Replaying `tr_e662da046c70` from its trace produced the same
answer with the marker in the *other* format at temperature 0, so this is a
run-to-run coin flip, not a property of particular questions.

**Against the demo set.** The same five modes applied to the ten claims we show
at the monthly review put mode 1 at 50% and modes 3 and 5 at zero. The demo set
was never hiding our biggest mode — it was hiding the two that move money. See
[bonus_demo_set.md](bonus_demo_set.md).

**Next:** the dated prediction in [prediction.md](prediction.md), committed
before any fix.
