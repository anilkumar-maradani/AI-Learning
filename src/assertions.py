"""
assertions.py — The summary criteria a regex can check, so no judge is paid for them.

  1. claim_number_echoed      CLM-YYYY-NNNNN present and equal to the file's number
  2. date_of_loss_parseable   a date that parses and equals the date of loss
  3. excess_numeric           the deductible/excess is stated as a number and is right
  4. exclusion_cited_on_denial whenever the summary states a denial, an E-NN code
                               is cited (and it is the one the adjuster relied on)

These four are deleted from the judge prompt; the judge keeps one criterion.
"""

import re
from datetime import date

from dateutil import parser as dateparser

CLAIM_RE = re.compile(r"\bCLM-\d{4}-\d{5}\b")
EXCL_RE = re.compile(r"\bE-\d{2}\b")
DENIAL_RE = re.compile(r"\b(denied|denial|declined|not covered|excluded|not payable)\b", re.I)

_MONTH = r"(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?"
_DATE_RES = [
    re.compile(r"\b\d{4}-\d{2}-\d{2}\b"),
    re.compile(r"\b\d{1,2}/\d{1,2}/\d{4}\b"),
    re.compile(rf"\b{_MONTH}\s+\d{{1,2}},?\s+\d{{4}}\b", re.I),
    re.compile(rf"\b\d{{1,2}}\s+{_MONTH}\s+\d{{4}}\b", re.I),
]

_AMOUNT = r"\$?\s?(\d{1,3}(?:,\d{3})*(?:\.\d{2})?|\d+(?:\.\d{2})?)"
# "$1,000 deductible", "deductible of $6,000", "Excess: $0"
# The gap may not cross a sentence break, so "deductible, the payable amount is
# $1,900" is not read as a $1,900 deductible. Words in between may use any
# hyphen ("all-peril" is often written with U+2011); the amount itself may not.
_EXCESS_AFTER = re.compile(rf"(?:deductible|excess)[^$\d\n.,;]{{0,25}}{_AMOUNT}", re.I)
_EXCESS_BEFORE = re.compile(
    rf"{_AMOUNT}\s*(?:[\w‐-―-]+\s+){{0,2}}(?:deductible|excess)", re.I)


def _num(s: str) -> float:
    return float(s.replace(",", "").replace("$", "").strip())


def claim_number_echoed(summary: str, case: dict) -> dict:
    found = CLAIM_RE.findall(summary)
    ok = case["claim_number"] in found
    return {"name": "claim_number_echoed", "passed": ok, "found": found}


def date_of_loss_parseable(summary: str, case: dict) -> dict:
    want = date.fromisoformat(case["date_of_loss"])
    parsed = []
    for rx in _DATE_RES:
        for m in rx.findall(summary):
            try:
                parsed.append(dateparser.parse(m).date())
            except (ValueError, OverflowError):
                pass
    return {"name": "date_of_loss_parseable", "passed": want in parsed,
            "found": [d.isoformat() for d in parsed]}


def excess_numeric(summary: str, case: dict) -> dict:
    amounts = []
    for rx in (_EXCESS_AFTER, _EXCESS_BEFORE):
        for m in rx.findall(summary):
            try:
                amounts.append(_num(m))
            except ValueError:
                pass
    ok = case["expected_excess"] in amounts
    return {"name": "excess_numeric", "passed": ok, "expected": case["expected_excess"],
            "found": amounts}


def exclusion_cited_on_denial(summary: str, case: dict) -> dict:
    states_denial = bool(DENIAL_RE.search(summary))
    cited = sorted(set(EXCL_RE.findall(summary)))
    if not states_denial:
        return {"name": "exclusion_cited_on_denial", "passed": True, "applicable": False,
                "found": cited}
    expected = case.get("expected_exclusion_ids") or []
    ok = bool(cited) and all(e in cited for e in expected)
    return {"name": "exclusion_cited_on_denial", "passed": ok, "applicable": True,
            "expected": expected, "found": cited}


ASSERTIONS = [claim_number_echoed, date_of_loss_parseable, excess_numeric,
              exclusion_cited_on_denial]


def run_assertions(summary: str, case: dict) -> list[dict]:
    return [a(summary, case) for a in ASSERTIONS]
