"""
test_w12_pii.py: the PII line, held across the agent hop and the MCP hop.

Run:  python tests/test_w12_pii.py

Scans what the integrated system writes:
  traces/w12/requests.jsonl        one line per FNOL triaged (host side)
  traces/w12/coverage_calls.jsonl  one line per tools/call our MCP server answered,
                                   i.e. exactly what it handed to any caller
and asserts that neither holds:
  * a claimant's name or surname (every claim in the claim store)
  * a raw claim number (CLM-...) or policy number (HOP-...)
  * an injury description (redaction.INJURY_RE)
  * a street address (the redaction ADDRESS pattern)
  * any adjuster note, verbatim
A file that does not exist yet passes (nothing written, nothing leaked).
"""

import json
import os
import re
import sys

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(_ROOT, "src"))

from claim_store import load_claims  # noqa: E402
from redaction import INJURY_RE, _PATTERNS  # noqa: E402

import glob  # noqa: E402

# Every W12 log: host request lines (requests*.jsonl, one file per run when runs go in
# parallel), our MCP server's call logs (coverage_calls*.jsonl) and the external
# client's calls (external_calls.jsonl).
FILES = sorted(glob.glob(os.path.join(_ROOT, "traces", "w12", "*.jsonl")))
CLAIM_RE = re.compile(r"\bCLM-\d{4}-\d{5}\b")
POLICY_RE = re.compile(r"\bHOP-\d{5,10}\b")
ADDRESS_RE = dict(_PATTERNS)["ADDRESS"]


def check_file(path: str, names: set, surnames: set, notes: set) -> int:
    if not os.path.exists(path):
        print(f"  {os.path.relpath(path, _ROOT)}: not written yet (passes vacuously)")
        return 0
    with open(path, encoding="utf-8") as fh:
        lines = [l for l in fh if l.strip()]
    for i, line in enumerate(lines, 1):
        where = f"{os.path.relpath(path, _ROOT)} line {i}"
        assert not CLAIM_RE.search(line), f"{where}: raw claim number {CLAIM_RE.search(line).group(0)}"
        assert not POLICY_RE.search(line), f"{where}: raw policy number {POLICY_RE.search(line).group(0)}"
        m = INJURY_RE.search(line)
        assert not m, f"{where}: injury description {m.group(0)!r}"
        m = ADDRESS_RE.search(line)
        assert not m, f"{where}: street address {m.group(0)!r}"
        for s in surnames:
            assert not re.search(rf"\b{re.escape(s)}\b", line), f"{where}: claimant surname {s!r}"
        for n in names:
            assert n not in line, f"{where}: claimant name {n!r}"
        for t in notes:
            assert t not in line, f"{where}: an adjuster note was written verbatim"
    print(f"  {os.path.relpath(path, _ROOT)}: {len(lines)} lines clean")
    return len(lines)


def main() -> None:
    claims = load_claims().values()
    names = {c["claimant_name"] for c in claims}
    surnames = {n.split()[-1] for n in names}
    notes = {n["text"] for c in claims for n in c.get("adjuster_notes") or [] if len(n["text"]) > 30}
    total = sum(check_file(p, names, surnames, notes) for p in FILES)
    print(f"\nPASS: {total} lines checked against {len(names)} claimant names, {len(notes)} notes, "
          f"claim/policy numbers, injuries and addresses")


if __name__ == "__main__":
    main()
