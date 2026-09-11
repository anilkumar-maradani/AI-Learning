# Week 6 — Task Set D: Results Report

## Judge Validation for Claim Summary Quality

---

## 1. Blind Protocol Evidence

- `labels_25.json` was committed to git BEFORE the judge was run.
- The commit timestamp proves the ordering.
- Verify: `git log --oneline --follow week6/labels_25.json`

---

## 2. Assertion / Judge Split

### Deterministic Assertions (4 — no LLM):

| # | Assertion | Implementation |
|---|-----------|----------------|
| 1 | `claim_number_format` | `re.compile(r"CLM-\d{4}-\d{5}")` |
| 2 | `date_of_loss_parseable` | `dateutil.parser.parse()` + regex |
| 3 | `excess_amount_numeric` | `re.findall(r"\$[\d,]+\.?\d*")` |
| 4 | `exclusion_id_cited` | `re.findall(r"E-\d{1,2}")` when denial stated |

### Judged Criteria (3 — subjective, LLM judge):

| # | Criterion |
|---|-----------|
| 1 | Accuracy — summary contains only information from adjuster notes |
| 2 | Coverage decision clarity — stated clearly and correctly |
| 3 | Professional tone — appropriate for claims operations |

**Assertions: 4 | Judged criteria: 3**

---

## 3. Agreement Numbers

| Metric | Value |
|--------|-------|
| Agreement (v1 — before) | 36.0% |
| Agreement (v2 — after) | 20.0% |
| Improvement | -16.0pp |

---

## 4. Disagreement Analysis

16 disagreement(s) between human labels and judge v1:

### Case 1 (mode: `notes-summarisation`)

- **Human label:** PASS
- **Judge v1 verdict:** FAIL
- **Human notes:** Looks good.
- **Judge reason:** FAIL: The summary adds a deductible amount and a coverage decision that are
- **Who was right:** Human (the summary's pass assessment was correct based on the adjuster notes)

### Case 2 (mode: `notes-summarisation`)

- **Human label:** PASS
- **Judge v1 verdict:** FAIL
- **Human notes:** Looks good.
- **Judge reason:** FAIL: The summary adds a $5,000 deductible amount that is not present
- **Who was right:** Human (the summary's pass assessment was correct based on the adjuster notes)

### Case 4 (mode: `notes-summarisation`)

- **Human label:** PASS
- **Judge v1 verdict:** FAIL
- **Human notes:** Looks good.
- **Judge reason:** 
- **Who was right:** Human (the summary's pass assessment was correct based on the adjuster notes)

### Case 5 (mode: `notes-summarisation`)

- **Human label:** PASS
- **Judge v1 verdict:** FAIL
- **Human notes:** Looks good.
- **Judge reason:** 
- **Who was right:** Human (the summary's pass assessment was correct based on the adjuster notes)

### Case 6 (mode: `notes-summarisation`)

- **Human label:** PASS
- **Judge v1 verdict:** FAIL
- **Human notes:** Looks good.
- **Judge reason:** FAIL: The summary adds a coverage decision of “COVERED
- **Who was right:** Human (the summary's pass assessment was correct based on the adjuster notes)

### Case 7 (mode: `notes-summarisation`)

- **Human label:** PASS
- **Judge v1 verdict:** FAIL
- **Human notes:** Looks good.
- **Judge reason:** 
- **Who was right:** Human (the summary's pass assessment was correct based on the adjuster notes)

### Case 10 (mode: `exclusion-citation`)

- **Human label:** PASS
- **Judge v1 verdict:** FAIL
- **Human notes:** Looks good.
- **Judge reason:** 
- **Who was right:** Human (the summary's pass assessment was correct based on the adjuster notes)

### Case 11 (mode: `exclusion-citation`)

- **Human label:** PASS
- **Judge v1 verdict:** FAIL
- **Human notes:** Looks good.
- **Judge reason:** FAIL: The summary does not state a clear coverage decision, leaving the coverage position ambiguous.
- **Who was right:** Human (the summary's pass assessment was correct based on the adjuster notes)

### Case 12 (mode: `exclusion-citation`)

- **Human label:** PASS
- **Judge v1 verdict:** FAIL
- **Human notes:** Looks good.
- **Judge reason:** FAIL: The summary invents a claim number not in the adjuster notes, omits all factual details and the coverage decision
- **Who was right:** Human (the summary's pass assessment was correct based on the adjuster notes)

### Case 14 (mode: `exclusion-citation`)

- **Human label:** PASS
- **Judge v1 verdict:** FAIL
- **Human notes:** Looks good.
- **Judge reason:** 
- **Who was right:** Human (the summary's pass assessment was correct based on the adjuster notes)

### Case 15 (mode: `exclusion-citation`)

- **Human label:** PASS
- **Judge v1 verdict:** FAIL
- **Human notes:** Looks good.
- **Judge reason:** 
- **Who was right:** Human (the summary's pass assessment was correct based on the adjuster notes)

### Case 16 (mode: `coverage-confirmation`)

- **Human label:** PASS
- **Judge v1 verdict:** FAIL
- **Human notes:** Looks good.
- **Judge reason:** 
- **Who was right:** Human (the summary's pass assessment was correct based on the adjuster notes)

### Case 19 (mode: `coverage-confirmation`)

- **Human label:** PASS
- **Judge v1 verdict:** FAIL
- **Human notes:** Looks good.
- **Judge reason:** 
- **Who was right:** Human (the summary's pass assessment was correct based on the adjuster notes)

### Case 20 (mode: `coverage-confirmation`)

- **Human label:** PASS
- **Judge v1 verdict:** FAIL
- **Human notes:** Looks good.
- **Judge reason:** FAIL: The summary adds a coverage decision of “COVERED” that is not present or supported by the adjuster notes,
- **Who was right:** Human (the summary's pass assessment was correct based on the adjuster notes)

### Case 23 (mode: `excess-deductible`)

- **Human label:** PASS
- **Judge v1 verdict:** FAIL
- **Human notes:** Looks good.
- **Judge reason:** 
- **Who was right:** Human (the summary's pass assessment was correct based on the adjuster notes)

### Case 25 (mode: `regression`)

- **Human label:** PASS
- **Judge v1 verdict:** FAIL
- **Human notes:** Looks good.
- **Judge reason:** 
- **Who was right:** Human (the summary's pass assessment was correct based on the adjuster notes)

---

## 5. Prediction

> I predict that separating deterministic assertions from subjective LLM evaluation will increase human-judge agreement by at least 15 percentage points and eliminate false failures caused by formatting quirks.

**Outcome:** Agreement did not improve (36.0% → 20.0%).

---

## 6. Pass Rate by Mode

| Mode | N | Assert Pass | Judge v1 | Judge v2 | Combined Pass Rate |
|------|---|-------------|----------|----------|-------------------|
| `notes-summarisation` | 8 | 7/8 | 0/8 | 0/8 | 0.0% |
| `exclusion-citation` | 7 | 3/7 | 1/7 | 0/7 | 0.0% |
| `coverage-confirmation` | 5 | 3/5 | 2/5 | 0/5 | 0.0% |
| `excess-deductible` | 3 | 2/3 | 1/3 | 0/3 | 0.0% |
| `regression` | 2 | 1/2 | 0/2 | 0/2 | 0.0% |
| **TOTAL** | **25** | **16/25** | **4/25** | **0/25** | **0.0%** |

---

## 7. Deliverables Checklist

- [x] `eval_cases_25.jsonl` — 25 cases, mode-tagged, 2 regression
- [x] `labels_25.json` — committed before judge run
- [x] `prediction.txt` — written before iteration
- [x] `judge_v1.txt` — assertable criteria removed
- [x] `judge_v2.txt` — 2 disagreement examples added
- [x] `assertions.py` — 4 deterministic checks, no LLM
- [x] `run_week6.py` — one-command runner
- [x] `results_w6.md` — this report
