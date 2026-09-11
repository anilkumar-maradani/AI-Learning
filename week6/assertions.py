"""
assertions.py — Deterministic checks for claim summaries.

These criteria are assertable with regex and date parsing, so they must NOT
appear in the LLM judge prompt. The judge evaluates only subjective quality.

4 assertions:
  1. claim_number_format   — CLM-YYYY-NNNNN echoed in summary
  2. date_of_loss_parseable — date of loss present and parseable
  3. excess_amount_numeric  — excess/deductible is a numeric value
  4. exclusion_id_cited     — if denial → exclusion ID (E-NN) cited
"""

import re
from dateutil import parser as dateparser


# ───────────────────────────────────────────────────────────────
# 1. Claim number format
# ───────────────────────────────────────────────────────────────

def claim_number_format(summary: str, expected_claim: str) -> dict:
    """Check that the claim number in CLM-YYYY-NNNNN format appears."""
    pattern = re.compile(r"CLM-\d{4}-\d{5}")
    found = pattern.findall(summary)
    passed = expected_claim in found
    return {
        "assertion": "claim_number_format",
        "passed": passed,
        "expected": expected_claim,
        "found": found,
        "reason": (f"Found {expected_claim} in summary" if passed
                   else f"Expected {expected_claim}, found: {found or 'none'}"),
    }


# ───────────────────────────────────────────────────────────────
# 2. Date of loss parseable
# ───────────────────────────────────────────────────────────────

_DATE_PATTERNS = [
    r"\d{4}-\d{2}-\d{2}",
    r"\d{1,2}/\d{1,2}/\d{2,4}",
    r"(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?"
    r"|Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?"
    r"|Dec(?:ember)?)\s+\d{1,2},?\s+\d{4}",
    r"\d{1,2}\s+(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May"
    r"|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?"
    r"|Nov(?:ember)?|Dec(?:ember)?)\s+\d{4}",
]


def date_of_loss_parseable(summary: str, expected_date: str) -> dict:
    """Check that a parseable date appears in the summary."""
    found_dates = []
    for pat in _DATE_PATTERNS:
        found_dates.extend(re.findall(pat, summary, re.IGNORECASE))

    parseable = False
    for d in found_dates:
        try:
            parsed = dateparser.parse(d)
            if parsed:
                parseable = True
                break
        except (ValueError, TypeError):
            continue

    # Also accept if the expected date string itself appears verbatim
    if expected_date in summary:
        parseable = True

    return {
        "assertion": "date_of_loss_parseable",
        "passed": parseable,
        "expected": expected_date,
        "found_dates": found_dates[:5],          # keep output compact
        "reason": ("Parseable date found in summary" if parseable
                   else "No parseable date of loss found in summary"),
    }


# ───────────────────────────────────────────────────────────────
# 3. Excess / deductible amount numeric
# ───────────────────────────────────────────────────────────────

def excess_amount_numeric(summary: str, expected_amount: float | None) -> dict:
    """Check that the excess/deductible amount appears as a number."""
    if not expected_amount:
        return {
            "assertion": "excess_amount_numeric",
            "passed": True,
            "expected": None,
            "reason": "No excess amount expected for this case (N/A)",
        }

    # Dollar amounts or plain numbers
    found = re.findall(r"\$[\d,]+\.?\d*|\d{1,3}(?:,\d{3})*(?:\.\d{2})", summary)

    # Normalise for comparison
    norm = lambda s: s.replace("$", "").replace(",", "")          # noqa: E731
    expected_strs = {
        f"{expected_amount:.2f}",
        f"{expected_amount:.0f}",
        f"{int(expected_amount)}",
    }
    matched = any(norm(f) in expected_strs for f in found)

    return {
        "assertion": "excess_amount_numeric",
        "passed": matched,
        "expected": expected_amount,
        "found_amounts": found[:8],
        "reason": (f"Excess amount {expected_amount} found as numeric value" if matched
                   else f"Expected {expected_amount}, found: {found or 'none'}"),
    }


# ───────────────────────────────────────────────────────────────
# 4. Exclusion ID cited
# ───────────────────────────────────────────────────────────────

def exclusion_id_cited(summary: str, case: dict) -> dict:
    """If there is a denial, check that the exclusion ID (E-NN) is cited."""
    denial_reason = case.get("denial_reason")
    exclusion_id = case.get("exclusion_id")

    if not denial_reason:
        return {
            "assertion": "exclusion_id_cited",
            "passed": True,
            "reason": "No denial stated — assertion not applicable",
        }

    exclusion_refs = re.findall(r"E-\d{1,2}", summary)
    passed = (exclusion_id in exclusion_refs) if exclusion_id else len(exclusion_refs) > 0

    return {
        "assertion": "exclusion_id_cited",
        "passed": passed,
        "expected_exclusion": exclusion_id,
        "found_exclusions": exclusion_refs,
        "reason": (f"Exclusion {exclusion_id} cited in summary" if passed
                   else f"Denial stated but {exclusion_id} not cited "
                        f"(found: {exclusion_refs or 'none'})"),
    }


# ───────────────────────────────────────────────────────────────
# Runner
# ───────────────────────────────────────────────────────────────

def run_all_assertions(summary: str, case: dict) -> list[dict]:
    """Run all 4 deterministic assertions on one summary."""
    return [
        claim_number_format(summary, case["claim_number"]),
        date_of_loss_parseable(summary, case["date_of_loss"]),
        excess_amount_numeric(summary, case.get("excess_amount")),
        exclusion_id_cited(summary, case),
    ]


if __name__ == "__main__":
    # Quick smoke test
    sample_summary = (
        "Claim CLM-2024-10001: Burst supply line on 2024-03-15. "
        "Damage $6,150. Excess $1,500.00. Denied under E-26."
    )
    sample_case = {
        "claim_number": "CLM-2024-10001",
        "date_of_loss": "2024-03-15",
        "excess_amount": 1500.00,
        "denial_reason": "Pre-existing mold",
        "exclusion_id": "E-26",
    }
    for r in run_all_assertions(sample_summary, sample_case):
        status = "✓" if r["passed"] else "✗"
        print(f"  {status} {r['assertion']}: {r['reason']}")
