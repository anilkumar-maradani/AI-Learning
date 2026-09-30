# Bonus — the same taxonomy applied to the demo set

The ten claims we show at the monthly review, run through the identical
assistant (`claims-v1`, `openai/gpt-oss-120b`, temperature 0, index
`fcb177c2d1c17a49`) and logged to `traces/demo_traces.jsonl`, kept in a separate
file from the start so it could never contaminate the random draw.

Not a sample — the whole demo set, all ten, coded with the same five modes.

---

## Open coding — the ten demo traces

1. **`tr_fb62eb0da80e`** — Asked whether E-17 applies and whether a burst supply line is covered, it answered COVERED and read the row as confirming coverage is not withheld, and the source marker was written with a space after the bracket so nothing was recorded.

2. **`tr_31163f4ed286`** — Asked the Named Storm deductible amount, it answered "$5,000 or 2% of the Coverage A limit, whichever is greater", matching CLAUSE NS-2, with the citation recorded.

3. **`tr_38161dfc80fb`** — Asked what "sudden and accidental" means, it returned the WD-1 sentence word for word with the citation recorded.

4. **`tr_3e7970ebf633`** — Asked whether mold is covered after a burst pipe, it gave the MF-1 exclusion, the MF-2 exception, the $10,000 sublimit, the 72-hour condition and the contractor-estimate condition, and addressed the last of those to "HO-0306 | CLAUSE-WD-1", which is a clause of a different form; all three markers had a space after the bracket and none were recorded.

5. **`tr_4f8a822a7cdc`** — Asked whether HO-0308 excludes sinkhole damage, it answered NOT COVERED and quoted the E-33 row, with the marker in full-width brackets and unrecorded.

6. **`tr_7cbad225c3b9`** — Asked whether exclusion E-19 is present in HO-0309, it answered "COVERED: Yes, exclusion E-19 is listed", putting the word COVERED in front of the confirmation that an exclusion exists.

7. **`tr_6ec62207f84d`** — Asked whether scheduled items are subject to the Coverage C jewelry sublimit, it opened with NOT COVERED and then said scheduled items are paid at appraised value *without* those sublimits, so the verdict line and the explanation say opposite things about a lost 3ct ring; the marker was full-width and unrecorded.

8. **`tr_e296a52a1597`** — Asked the Coverage A dwelling limit, it returned the fixed refusal message.

9. **`tr_1fbc472ef1ef`** — Asked what the base policy says about bicycle theft, it returned the fixed refusal message.

10. **`tr_45b4009c2556`** — Asked whether fire following earth movement is covered, it answered COVERED and quoted the EM-3 ensuing-fire exception, with the marker full-width and unrecorded.

---

## The two numbers

**Top mode — "writes the source marker in a format the audit log does not record":**

| | Frequency |
|---|---:|
| Random sample (n=20, seed 20260905) | **40%** — 8 of 20 |
| Demo set (n=10) | **50%** — 5 of 10 |

The top mode is *not* hidden by the demo set. It is slightly more common there.

## Every mode, both sets

| Mode | Random (n=20) | Demo (n=10) |
|---|---:|---:|
| 1 · Marker format the audit log does not record | 40% (8) | 50% (5) |
| 2 · Verdict line contradicts its own explanation | 15% (3) | 20% (2) |
| 3 · Exclusion basis from the wrong form's table | 10% (2) | **0% (0)** |
| 4 · Clause chunk cut mid-sentence or mislabelled | 10% (2) | 10% (1) |
| 5 · Rule quoted but never applied to the facts | 10% (2) | **0% (0)** |

---

## What the team has been telling itself

For a month we have been telling ourselves that the assistant gets coverage
right and occasionally formats a citation oddly, and the demo set is exactly the
instrument that would produce that belief. The two modes that move money are the
two that are absent from it: not one of the ten demo claims produced a wrong or
missing exclusion table, and not one failed to apply a rule to the facts, while
in real traffic those run at 10% each. The reason is in how the demo questions
are written rather than in how the assistant behaves. Eight of the ten name
their form out loud — "under HO-0304", "under HO-0306", "does HO-0308" — so
retrieval never has to *choose* a form, and the failure where it chooses wrong
has no opportunity to happen. Two more are deliberate out-of-corpus questions we
included precisely because we knew they would refuse cleanly. Nothing in the set
resembles the trace that actually frightened me, `tr_1a7c8f8f738b`, where an
adjuster asked about an 18-year-old washing machine without naming a form, the
HO-0304 exclusion table never reached the model, and the assistant told them in
so many words that the endorsement imposes no appliance-age limit — with the
E-16 row sitting in the corpus saying appliances over 15 years old with no
service record are excluded.

The uncomfortable part is that the demo set was never hiding the top mode. It
showed the citation problem at 50%, *higher* than real traffic, and we watched it
every month and filed it as cosmetic because the answers underneath were right.
So the story is not that the demo set lied to us. It is that the demo set showed
us the one failure that costs nothing and structurally could not show us the two
that pay or deny claims — and we took the absence of those as evidence they were
not happening, when it was only evidence that we had not asked a question capable
of producing them.
