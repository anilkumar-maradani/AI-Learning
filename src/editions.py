"""
editions.py: Week 12. Which wording was in force on a given date.

A form can exist in several editions (data/policy/NG-1101_07-23.txt,
NG-1101_01-26.txt, ...). Each file's header gives its form number, edition
and effective date. An edition stays in force until the next edition of the
same form takes effect, so its window ends the day before. Nothing here is
hard-coded: add a file and the windows follow from its header.

    edition_in_force("NG-1101", "2025-08-11")  -> the 07-23 edition
    edition_in_force("NG-1101", "2026-01-01")  -> the 01-26 edition
    edition_in_force("NG-1101", "2023-06-30")  -> None (no wording in the library)

This module also turns a clause id into a citation an adjuster can click: the
source file and the line where the clause or exclusion row starts, plus the
edition and the loss date the citation was resolved against.
"""

import glob
import os
import re
from datetime import date, datetime, timedelta
from functools import lru_cache

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
POLICY_DIR = os.path.join(ROOT, "data", "policy")
OPEN_END = date(9999, 12, 31)

_HEADER = {"Form Number": "form_number", "Edition Date": "edition_date",
           "Policy Line": "policy_line", "Effective Date": "effective_date", "Title": "title"}


def as_date(value) -> date:
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value).strip()[:10])


def date_int(value) -> int:
    """2025-08-11 -> 20250811: the form Chroma can range-filter on."""
    d = as_date(value)
    return d.year * 10000 + d.month * 100 + d.day


def read_header(text: str) -> dict:
    meta = {}
    for line in text.splitlines()[:10]:
        key, _, val = line.partition(":")
        if key.strip() in _HEADER and val.strip():
            meta[_HEADER[key.strip()]] = val.strip()
    return meta


@lru_cache(maxsize=1)
def editions() -> dict[str, list[dict]]:
    """{form_number: [edition, ...]} oldest first. Each edition: form_number,
    edition_date, policy_line, title, source_file, effective_from, effective_to."""
    out: dict[str, list[dict]] = {}
    for path in sorted(glob.glob(os.path.join(POLICY_DIR, "*.txt"))):
        with open(path, encoding="utf-8") as fh:
            head = read_header(fh.read())
        if "effective_date" not in head:
            raise ValueError(f"{os.path.basename(path)}: header has no 'Effective Date'")
        ed = {
            "form_number": head["form_number"],
            "edition_date": head["edition_date"],
            "policy_line": head.get("policy_line", ""),
            "title": head.get("title", ""),
            "source_file": os.path.basename(path),
            "effective_from": datetime.strptime(head["effective_date"], "%B %d, %Y").date(),
        }
        out.setdefault(ed["form_number"], []).append(ed)
    for eds in out.values():
        eds.sort(key=lambda e: e["effective_from"])
        for older, newer in zip(eds, eds[1:]):
            older["effective_to"] = newer["effective_from"] - timedelta(days=1)
        eds[-1]["effective_to"] = OPEN_END
    return out


def get_edition(form_number: str, edition_date: str) -> dict | None:
    return next((e for e in editions().get(form_number, []) if e["edition_date"] == edition_date), None)


def edition_in_force(form_number: str, loss_date) -> dict | None:
    d = as_date(loss_date)
    return next((e for e in editions().get(form_number, [])
                 if e["effective_from"] <= d <= e["effective_to"]), None)


def latest_edition(form_number: str) -> dict | None:
    eds = editions().get(form_number)
    return eds[-1] if eds else None


def window(ed: dict) -> str:
    end = "open" if ed["effective_to"] == OPEN_END else ed["effective_to"].isoformat()
    return f"{ed['effective_from'].isoformat()} to {end}"


def label(ed: dict) -> str:
    return f"{ed['form_number']} ed. {ed['edition_date']}"


def products() -> set[str]:
    return {e["policy_line"] for eds in editions().values() for e in eds}


# ---------------------------------------------------------------------------
# Clauses: where they are, what they say
# ---------------------------------------------------------------------------

_ROW_START = re.compile(r"^\|\s*(E-\d+)\s*\|")
_CLAUSE_START = re.compile(r"^CLAUSE\s+([A-Z]{2,4}-\d+)\b")


def normalise_clause_id(clause_id: str) -> str:
    """'CLAUSE-WE-4', 'clause WE-4', 'E‑42' (U+2011), 'EXCLUSION-TABLE-E-42' -> 'WE-4' / 'E-42'."""
    c = str(clause_id or "").replace("‑", "-").replace("‐", "-").strip().upper()
    c = re.sub(r"^NG-\d{4}\s*(ED\.\s*\d{2}-\d{2})?\s*[:/ ·]*\s*", "", c)
    c = re.sub(r"^(CLAUSE|EXCLUSION-TABLE)[-\s]+", "", c)
    m = re.search(r"\b(E-\d{2,3}|[A-Z]{2,4}-\d+)\b", c)
    return m.group(1) if m else c


@lru_cache(maxsize=64)
def _lines(source_file: str) -> tuple[str, ...]:
    with open(os.path.join(POLICY_DIR, source_file), encoding="utf-8") as fh:
        return tuple(fh.read().splitlines())


def clause_line(ed: dict, clause_id: str) -> int | None:
    """1-based line where the clause heading or the exclusion row starts."""
    cid = normalise_clause_id(clause_id)
    for i, line in enumerate(_lines(ed["source_file"]), 1):
        m = _ROW_START.match(line) or _CLAUSE_START.match(line)
        if m and m.group(1) == cid:
            return i
    return None


def clause_text(ed: dict, clause_id: str) -> str | None:
    """The clause paragraph, or the exclusion row with its continuation lines."""
    start = clause_line(ed, clause_id)
    if start is None:
        return None
    lines = _lines(ed["source_file"])
    out = [lines[start - 1]]
    is_row = lines[start - 1].startswith("|")
    for line in lines[start:]:
        if is_row:
            if not line.startswith("|") or _ROW_START.match(line):
                break
            out.append(line)
        else:
            if not line.strip() or _CLAUSE_START.match(line) or line.startswith("SECTION"):
                break
            out.append(line)
    if is_row:
        cells = [[c.strip() for c in l.strip().strip("|").split("|")] for l in out]
        code = cells[0][0]
        peril = " ".join(c[1] for c in cells if len(c) > 1 and c[1]).strip()
        scope = " ".join(c[2] for c in cells if len(c) > 2 and c[2]).strip()
        return f"{code} | {peril} | {scope}"
    return " ".join(l.strip() for l in out)


def clause_ids(ed: dict) -> list[str]:
    ids = []
    for line in _lines(ed["source_file"]):
        m = _ROW_START.match(line) or _CLAUSE_START.match(line)
        if m:
            ids.append(m.group(1))
    return ids


_MONEY = re.compile(r"\$\s?(\d{1,3}(?:,\d{3})+|\d+)")


def amounts_in(text: str) -> list[float]:
    return [float(m.replace(",", "")) for m in _MONEY.findall(text or "")]


def citation(form_number: str, edition_date: str, clause_id: str, loss_date) -> dict:
    """A citation the adjuster can click, naming the edition and the loss date it
    was resolved against. ``in_force`` says whether that edition was in force on
    the loss date; ``exists`` whether the clause is in that edition at all."""
    ed = get_edition(form_number, edition_date)
    cid = normalise_clause_id(clause_id)
    if ed is None:
        return {"form_number": form_number, "edition": edition_date, "clause_id": cid,
                "exists": False, "in_force": False, "loss_date": str(loss_date),
                "label": f"{form_number} ed. {edition_date} · {cid}", "link": None,
                "why_invalid": f"no edition {edition_date} of {form_number} in the library"}
    line = clause_line(ed, cid)
    d = as_date(loss_date)
    in_force = ed["effective_from"] <= d <= ed["effective_to"]
    rel = f"data/policy/{ed['source_file']}"
    return {
        "form_number": form_number, "edition": edition_date, "clause_id": cid,
        "exists": line is not None, "in_force": in_force, "loss_date": d.isoformat(),
        "edition_window": window(ed),
        "label": f"{label(ed)} · {cid}",
        "link": f"{rel}#L{line}" if line else None,
        "why_invalid": None if (line and in_force) else (
            f"{cid} does not exist in {label(ed)}" if not line else
            f"{label(ed)} was not in force on {d.isoformat()} (in force {window(ed)})"),
    }
