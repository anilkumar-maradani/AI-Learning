# Error analysis notes — Week 5, Task Set D

Companion to [taxonomy.md](taxonomy.md). Everything here is evidence for how the
20 traces were chosen, what was seen in them, and what was committed when.

---

## 1. The log

`traces/traces.jsonl` — 130 questions, one JSON object each, written by
`run_week.py` from the 130-question population in `traffic/week_traffic.py`. The
questions were written before any output was inspected and run in seeded
shuffled order. Nothing was graded, filtered or re-run on the way in.

Frozen at commit `9ce4282` before the sample was drawn.

| | |
|---|---|
| Questions in the log | 130 |
| Carrying a completion | 106 |
| Carrying a `RateLimitError` and no output | 24 |
| Prompt version | `claims-v1` (one version, all traces) |
| Model | `openai/gpt-oss-120b`, temperature 0.0, top_p 1.0, max_tokens 800 |
| Index fingerprint | `fcb177c2d1c17a49` (one value, all traces) |

### The sampling frame, and why it is not all 130

The 24 failures are all `RateLimitError` and all fall at the tail of the run:
bulk-loading a week of traffic in one sitting exhausted the free-tier daily
token budget, and every call after that point came back empty. Those are
artefacts of my generation harness, not behaviour of the assistant, and 20
traces drawn from a pool containing them would spend about a fifth of the sample
measuring my own quota.

They are **excluded from the frame, not from the log** — they are still in
`traces.jsonl` and can be counted. The exclusion is content-blind: it looks only
at whether `error` is set, never at what an answer said, and it was applied and
recorded before the draw.

Topic mix, log versus frame — the check that dropping them did not tilt anything:

| Topic | Log (130) | Frame (106) |
|---|---:|---:|
| water | 16.9% | 17.0% |
| earth | 13.8% | 14.2% |
| mold | 13.8% | 14.2% |
| storm | 13.8% | 12.3% |
| business | 12.3% | 12.3% |
| scheduled | 12.3% | 13.2% |
| cross_form | 9.2% | 10.4% |
| out_of_corpus | 7.7% | 6.6% |

No topic moves more than 1.5 points.

---

## 2. The seeded sample

```
seed                   20260905
seed rule              YYYYMMDD of the day the sample was drawn
n                      20
frame                  106 completed traces
population fingerprint 1143f43c1e1573016c319f9a629bb0a3abd7b62bece1f608a5fd40417de4d241
draw method            random.Random(seed).sample(sorted(trace_ids), 20)
                       Python 3.14 Mersenne Twister
command                python src/sample_traces.py --seed 20260905 --n 20
file                   error_analysis/sample_seed_20260905.json
```

The seed is fixed by a rule rather than chosen, which is what stops seed
shopping — I cannot re-roll until the sample contains the traces I wanted.
trace_ids are sorted before the draw, so the same seed against the same log
gives the same 20 regardless of the order the file was written in. The
population fingerprint is a SHA-256 over every trace_id in the frame, so the
draw is provably against the whole frame and not a slice of it.

The 20 selected trace_ids were committed at `15fe9d5` **before a single trace
was read.**

| # | trace_id | Question |
|---|---|---|
| 1 | `tr_b5ba07d1f4cc` | What does the base homeowners policy say about theft of a bicycle? |
| 2 | `tr_440a391b6301` | Does the named storm deductible stack with the all-peril deductible? |
| 3 | `tr_148357fb79c3` | What is the NFIP flood policy limit for a single family dwelling? |
| 4 | `tr_e2ea5198b3b4` | What does exclusion E-31 say? |
| 5 | `tr_aed27ca5c15a` | The insured found the leak eleven days after it started. Is that still sudden and accidental? |
| 6 | `tr_937f21bc8667` | The mold was present before the policy started. Which exclusion applies? |
| 7 | `tr_5741e53e8591` | Is business inventory stored in the garage covered? |
| 8 | `tr_86e13c9d80bc` | E-22 appears in two of our endorsements. What does each one exclude? |
| 9 | `tr_1838e4f935f5` | What does exclusion E-25 say? |
| 10 | `tr_f8f386127038` | Does E-23 under HO-0306 exclude dry rot as well as wet rot? |
| 11 | `tr_e662da046c70` | What is exclusion E-11 and how many days of leakage triggers it? |
| 12 | `tr_cf7a87e727de` | Is a pipe under the slab considered a supply line under HO-0304? |
| 13 | `tr_37af7381d522` | Are electronic data and software included in the $2,500 sublimit? |
| 14 | `tr_0e21144d6d39` | When did HO-0305 become effective? |
| 15 | `tr_4cfbcfbbec32` | Coverage A is $300,000. What is the named storm deductible? |
| 16 | `tr_34227f724cb5` | Is the E-17 row an exclusion or a confirmation of coverage? |
| 17 | `tr_1a7c8f8f738b` | If the washing machine hose overflowed and the machine is 18 years old, is it covered? |
| 18 | `tr_1033eb8e542c` | Does the 72 hour reporting requirement apply to all water claims under this form? |
| 19 | `tr_a79da2f07b09` | Which authority has to name the storm for the deductible to apply? |
| 20 | `tr_36d865b6f3ae` | Does the 72 hour reporting rule in HO-0304 also govern the mold sublimit in HO-0306? |

---

## 3. Open coding — one sentence per trace, verbatim

Written while reading, before any clustering. Descriptions of what happened, not
labels for it. **Zero code changes were made during this step.** The check is
one command:

```
$ git diff --name-only 15fe9d5 HEAD -- '*.py'
(no output)

$ git diff --name-only 15fe9d5 HEAD
error_analysis/notes.md
error_analysis/prediction.md
error_analysis/replay_tr_e662da046c70.json
error_analysis/replay_tr_e662da046c70.txt
error_analysis/taxonomy.md
```

Not one Python file moved between drawing the sample and committing the
prediction. Everything added is analysis or replay evidence. The one thing I
wanted to fix at trace 17 — the appliance-age exclusion never reaching the
model — is written down in the taxonomy and left alone in the code.

1. **`tr_b5ba07d1f4cc`** — Asked what the base policy says about bicycle theft, it returned the fixed refusal message, and the five chunks it retrieved came from five different endorsements with no mention of theft in any of them.

2. **`tr_440a391b6301`** — Asked whether the named storm deductible stacks with the all-peril deductible, it opened the answer with the words "NOT COVERED" and then said, correctly, that the two do not stack and the higher of them applies.

3. **`tr_148357fb79c3`** — Asked for the NFIP flood policy limit for a single family dwelling, it returned the fixed refusal message and cited nothing.

4. **`tr_e2ea5198b3b4`** — Asked what exclusion E-31 says, it gave the HO-0307 version and the HO-0308 version separately and both matched their forms, but it wrote both source markers with full-width brackets and the trace recorded no cited chunk_ids.

5. **`tr_aed27ca5c15a`** — Told the leak had run eleven days before discovery, it answered COVERED off the fourteen-day wording alone and never mentioned the 72-hour reporting condition that was sitting in the third chunk it retrieved.

6. **`tr_937f21bc8667`** — Asked which exclusion covers mold present before the policy started, it answered E-26 and quoted the table row, and the citation was recorded.

7. **`tr_5741e53e8591`** — Asked about business stock in a garage damaged by a water loss, it answered NOT COVERED on two bases, HO-0309's E-37 and HO-0305's E-24, the second of which is a row in the named-storm endorsement's table.

8. **`tr_86e13c9d80bc`** — Asked what E-22 excludes in each of the two endorsements that use the code, it gave the storm-surge row for HO-0305 and the mold row for HO-0306, both matching their forms, and four of the five chunks it worked from had no vector rank at all.

9. **`tr_1838e4f935f5`** — Asked what E-25 says, it answered that mold testing and air-sampling costs are not covered, matching the HO-0306 row.

10. **`tr_f8f386127038`** — Asked whether E-23 excludes dry rot as well as wet rot, it opened with "COVERED: Yes" and then said the row excludes both, so the first word of the answer states the opposite of the rest of it.

11. **`tr_e662da046c70`** — Asked what E-11 is and how many days trigger it, it opened with "COVERED:" and then described the gradual seepage exclusion and the fourteen-day threshold correctly.

12. **`tr_cf7a87e727de`** — Asked whether an under-slab pipe counts as a supply line, it quoted the WD-2 definition word for word and then said the under-slab pipe meets it, a step the quoted text does not speak to either way.

13. **`tr_37af7381d522`** — Asked whether electronic data and software sit inside the $2,500 sublimit, it answered NOT COVERED and addressed the citation to CLAUSE-BP-2, while the chunk it pointed at is headed "SECTION III — BUSINESS EQUIPMENT SUBLIMIT".

14. **`tr_0e21144d6d39`** — Asked when HO-0305 became effective, it answered March 15 2024, which matches the form, and neither of its two source markers was recorded.

15. **`tr_4cfbcfbbec32`** — Given a $300,000 Coverage A limit, it answered $6,000, which matches the worked example in the form's own deductible schedule, and neither source marker was recorded.

16. **`tr_34227f724cb5`** — Asked whether the E-17 row is an exclusion or a confirmation of coverage, it answered that the row confirms coverage is not withheld, quoted the row, and came back in about one second.

17. **`tr_1a7c8f8f738b`** — Told the washing machine was 18 years old, it answered COVERED and stated that the endorsement imposes no age limitation on appliances; the HO-0304 exclusion table, whose E-16 row is about appliances over 15 years old with no service record, was not among the five chunks it retrieved.

18. **`tr_1033eb8e542c`** — Asked whether the 72-hour reporting requirement applies to all water claims under the form, it answered yes and paraphrased the SECTION III sentence, and the marker was not recorded.

19. **`tr_a79da2f07b09`** — Asked which authority must name the storm, it answered the National Hurricane Center or the equivalent national meteorological authority, and said nothing about the foreign agency named in the loss summary in front of it.

20. **`tr_36d865b6f3ae`** — Asked whether HO-0304's 72-hour rule governs the HO-0306 mold sublimit, it returned the fixed refusal message, and the MF-2 chunk it retrieved at rank 1 stops mid-sentence at "as defined in form HO-0304 ed. 03-24," with the 72-hour condition not present in it.

### One thing I could not explain

I do not know why `tr_34227f724cb5` came back in 1.0 second when the median
across the sample is around 10 seconds, on a question of ordinary length against
five ordinary chunks. Nothing in the trace distinguishes it. I looked and I
still do not know.

---

## 4. Replay evidence

**Trace picked at random by trace_id, seeded:**

```
seed     20260905
method   random.Random(20260905).choice(sorted(sampled_trace_ids))
selected tr_e662da046c70
command  python src/replay.py --trace-id tr_e662da046c70
```

`src/replay.py` never re-runs retrieval and never touches the original question
object. It reads the trace line, resolves each stored chunk_id back to its text,
reassembles the context block in the stored rank order with the stored scores,
rebuilds the user turn from the stored prompt version, and re-issues with the
stored model parameters.

**Preflight — all three drift checks clean:**

```
prompt version: claims-v1 (sha 748e912c3377)   matches the registry
index fingerprint fcb177c2d1c17a49              matches the live collection
chunks        HO-0304_sa_chunk_006, HO-0304_sa_chunk_007, HO-0304_sa_chunk_003,
              HO-0308_sa_chunk_008, HO-0307_sa_chunk_007      all resolve
scores        0.032258, 0.031250, 0.031778, 0.029958, 0.028589
model         openai/gpt-oss-120b  temp=0.0  top_p=1.0  max_tokens=800  seed=None
```

**Original output (from the trace):**

```
COVERED: Exclusion E‑11 is the "Gradual seepage or leakage" exclusion. It applies
when any water seeps, leaks, or flows continuously for more than fourteen (14)
days (i.e., 14 + days). [SOURCE: HO-0304_sa_chunk_006 | HO-0304 | EXCLUSION-TABLE]
```

**Replayed output (regenerated from the trace alone):**

```
COVERED: **Exclusion E‑11** – "Gradual seepage or leakage."
It applies when any water **seeps, leaks, or flows continuously for more than 14
days** (i.e., 14 + days) [ SOURCE: HO-0304_sa_chunk_006 | HO-0304 | EXCLUSION‑TABLE ].
```

`identical: False`, `similarity: 0.8051`. Same substance, same figure, same
chunk cited, different surface form.

**The replay accidentally proved a taxonomy mode.** The original wrote
`[SOURCE:` and the trace recorded the citation. The replay wrote `[ SOURCE: ]`
and it would not have been recorded. Same prompt, same context, same model, same
temperature 0 — the marker format flipped between the two runs. Mode 1 in the
taxonomy is a run-to-run coin flip, not a property of certain questions, and I
would not have known that without replaying.

### Fields I had to add, and what I could not reconstruct

The Week 4 app wrote **no trace of any kind**. Every field below was added this
week (commit `77eef13`) before the traffic was run:

| Field | Status |
|---|---|
| prompt version | Added — `src/prompts.py`, a versioned registry, plus a SHA-256 of the body in each trace so a prompt edited in place is caught at replay |
| retrieved chunk_ids + scores | Added — per chunk: rank, chunk_id, fused score, vector_rank, bm25_rank, form_number, edition_date, clause_id, source_file |
| model + params | Added — provider, model name, temperature, top_p, max_tokens, seed, finish reason, token usage, system fingerprint |
| raw output | Added — the completion before any parsing |
| index fingerprint | Added — not asked for, but without it a replay six weeks from now cannot tell whether the chunk text it resolves is the text the model actually saw |

**Could not reconstruct: the token sampling.** The provider is not bit-reproducible
at temperature 0 — batching and expert routing vary between calls, and no field I
can store changes that. The `seed` parameter is recorded and was `None`; Groq's
`seed` is best-effort in any case. Everything upstream of the sampler — prompt,
context, chunk order, scores, parameters — reconstructs exactly, which is what
makes the diff above interpretable: the only thing that could have differed is
the sampling, so that is what did.

---

## 5. Redaction

**Claimant names and claim numbers are redacted before the trace is written, not
after** — `TraceRecord.build` runs the scrub while the record is still in memory,
and `TraceWriter.write` re-checks the serialised line and raises instead of
appending if anything survived, so there is no code path that writes a dirty
line and cleans the log afterwards.

Evidence: `python tests/test_redaction_before_write.py`

```
  1. built record carries no raw identifier                      OK
  2. same claimant -> same token [CLAIMANT:89cd2c] across traces  OK
  3. writer refused a leaking line, nothing hit disk              OK
  4. live log (130 traces) contains no roster identifier          OK
```

Identifiers become stable HMAC pseudonyms rather than blanks, so
`Margaret Whitfield` is `[CLAIMANT:89cd2c]` in every trace and recurrence stays
countable without the log ever holding a name.

---

## 6. The dated prediction

Full text in [prediction.md](prediction.md). Dated **2026-09-05**, committed
before any fix.

> Mode 1 ("writes the source marker in a format the audit log does not record")
> drops from **8/20 (40%)** to **0 or 1 of 20 (0–5%)** on a fresh seeded sample
> at seed `20260912`, after widening the citation regex in `src/tracing.py` and
> minting prompt `claims-v2` with the marker format pinned. **I am wrong if it
> lands at 2 or more.** Modes 2 and 3 must stay within ±1 trace of 3/20 and
> 2/20; if either moves outside that band I am also wrong.

**Commit hash: `8a8d92a`**  (full: `8a8d92af8944690a3635169d37f032e10c51a367`, authored 2026-09-05)

---

## 7. Why a public benchmark would not have surfaced my top three modes

A public benchmark grades the text of an answer against a reference answer, so it
would have scored all eight of my top-mode traces as correct — the answers were
right and the thing that broke was the bracket style of a citation marker that
only my own log parses, which no public benchmark knows exists. The second mode
is only a failure because our adjusters read the first line as the decision and
stop reading, so a benchmark scoring the whole paragraph would mark
"COVERED: Yes… E-23 excludes both dry rot and wet rot" correct on the strength
of the body while an adjuster acts on the word COVERED and pays a claim we
exclude. The third mode cannot exist outside this corpus at all: it needs
HO-0304's E-16 appliance row to be absent from the retrieved context and needs
E-22 and E-31 each to mean different things in two different forms, and a
benchmark built on public insurance text has no HO-0304 and no colliding code
numbers, so there is nothing there for a model to get wrong.
