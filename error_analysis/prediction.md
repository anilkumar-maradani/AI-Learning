# Dated prediction — 2026-09-05

Written after reading the 20 traces, **before any fix is applied**. Committed on
its own so the commit date is the evidence that it was made in advance.

## The one mode I will attack

**Mode 1 — "Writes the source marker in a format the audit log does not
record."** 8 of 20 traces, 40%.

I am attacking this one and not the higher-severity mode 3 for a stated reason:
mode 3 appears twice in 20 traces, and a delta on n=2 cannot be distinguished
from noise on a fresh sample of 20. Mode 1 is measurable now. Mode 3 gets a
purpose-built sample of coverage-position questions the week after.

## The change

Two edits, both small:

1. `src/tracing.py` — `_extract_citations` currently matches the literal
   `[SOURCE:`. Replace it with a regex accepting an optional space after the
   opening bracket, the full-width bracket `【`, and an optional space before
   the colon: `[\[【]\s*SOURCE\s*:`.
2. `src/prompts.py` — mint prompt version `claims-v2`, identical to `claims-v1`
   except rule 2 gains: *"Write the marker exactly as `[SOURCE: ...]` — an ASCII
   square bracket, no space after it, and no full-width brackets."*

## The prediction, in numbers

Regenerate the same 130-question week against `claims-v2`, draw 20 traces with
seed `20260912` from the completed traces, and count traces where the answer
emits at least one source marker but the trace records zero cited chunk_ids.

| Metric | Now (seed 20260905) | Predicted (seed 20260912) |
|---|---:|---:|
| Mode 1: markers emitted, none recorded | 8 / 20 (40%) | **0 or 1 / 20 (0–5%)** |
| Mode 2: verdict line contradicts body | 3 / 20 (15%) | 2 – 4 / 20 (unchanged ±1) |
| Mode 3: exclusion basis from the wrong form | 2 / 20 (10%) | 1 – 3 / 20 (unchanged ±1) |

**I am wrong if mode 1 lands at 2 or more of 20.** I am also wrong if mode 2 or
mode 3 moves outside its ±1 band, because neither depends on the marker format
and a change there would mean the prompt edit had effects I did not predict.

## What I expect to still be broken afterwards

The 40% does not become 40% of claims decided correctly. Mode 1 never changed an
answer — it changed whether the citation was filed. Modes 2, 3, 4 and 5 will all
still be there at roughly their current counts, and the money is in modes 2
and 3.
