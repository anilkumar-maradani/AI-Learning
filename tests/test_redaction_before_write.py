"""
test_redaction_before_write.py — Evidence for the rubric line
"claimant identifiers are redacted before the trace is written, not after".

Run:  python tests/test_redaction_before_write.py

Four checks:

  1. A record built from raw claim data carries no name, claim number, policy
     number, email, phone or street address once built — i.e. the scrub happens
     while the record is still in memory.
  2. The pseudonym for one claimant is stable across two different traces, so
     analysis can still count recurrence.
  3. The writer REFUSES to append a line that still contains an identifier.
     This is the "not after" half: there is no path that writes dirty and
     cleans later.
  4. The on-disk log for the week contains no identifier from the roster.
"""

import json
import os
import sys
import tempfile

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(_ROOT, "src"))
sys.path.insert(0, os.path.join(_ROOT, "traffic"))

from dataclasses import asdict

from redaction import redact_text, assert_clean
from tracing import TraceRecord, TraceWriter, read_traces, TRACE_PATH

RAW = {
    "claimant_name": "Margaret Whitfield",
    "claim_number": "CLM-2026-04417",
    "question": "Margaret Whitfield asks whether claim CLM-2026-04417 is covered.",
    "loss_summary": ("Whitfield reported a burst line at 41 Harborview Lane, "
                     "policy HOP-8842116, m.whitfield@example.com, (813) 555-0142."),
}

_HITS = [{
    "rank": 1, "chunk_id": "HO-0304_sa_chunk_006", "score": 0.031,
    "vector_rank": 1, "bm25_rank": 1, "text": "irrelevant for this test",
    "metadata": {"form_number": "HO-0304", "edition_date": "03-24",
                 "clause_id": "EXCLUSION-TABLE", "source_file": "HO-0304_03-24.txt"},
}]


def _build(raw_output: str = "Answer mentioning Margaret Whitfield and CLM-2026-04417.") -> TraceRecord:
    return TraceRecord.build(
        question=RAW["question"],
        loss_summary=RAW["loss_summary"],
        claimant_name=RAW["claimant_name"],
        claim_number=RAW["claim_number"],
        prompt_version="claims-v1",
        retrieval_meta={"mode": "hybrid_rrf", "strategy": "structure_aware",
                        "n_results": 1, "rrf_k": 60},
        hits=_HITS,
        model_meta={"provider": "groq", "name": "test", "temperature": 0.0,
                    "max_tokens": 800, "top_p": 1.0, "seed": None},
        raw_output=raw_output,
        timing={"retrieval_ms": 1.0, "generation_ms": 1.0, "total_ms": 2.0},
    )


def check_1_scrubbed_in_memory() -> None:
    rec = _build()
    blob = json.dumps(asdict(rec), ensure_ascii=False)
    leaks = assert_clean(blob, [RAW["claimant_name"]])
    assert not leaks, f"identifier survived into the built record: {leaks}"
    for forbidden in ["Margaret", "Whitfield", "CLM-2026-04417", "HOP-8842116",
                      "m.whitfield@example.com", "555-0142", "41 Harborview Lane"]:
        assert forbidden not in blob, f"{forbidden!r} present in built record"
    assert "[CLAIMANT:" in blob and "[CLAIM_NO:" in blob
    assert rec.redaction["applied"] == "pre_write"
    print("  1. built record carries no raw identifier                      OK")


def check_2_pseudonym_is_stable() -> None:
    a, b = _build(), _build("A different answer about [CLAIMANT] entirely.")
    tok_a = a.input["question"].split("]")[0] + "]"
    assert tok_a.startswith("[CLAIMANT:"), tok_a
    assert tok_a in b.input["question"], "same claimant produced different tokens"
    assert a.trace_id != b.trace_id
    print(f"  2. same claimant -> same token {tok_a} across traces   OK")


def check_3_writer_refuses_dirty_line() -> None:
    rec = _build()
    rec.input["question"] = RAW["question"]          # simulate a redaction bug
    with tempfile.TemporaryDirectory() as td:
        path = os.path.join(td, "t.jsonl")
        writer = TraceWriter(path)
        try:
            writer.write(rec, known_names=[RAW["claimant_name"]])
        except RuntimeError as exc:
            assert "leak detected before write" in str(exc)
            assert not os.path.exists(path) or os.path.getsize(path) == 0, \
                "a dirty line reached disk"
            print("  3. writer refused a leaking line, nothing hit disk           OK")
            return
    raise AssertionError("writer accepted a line containing a claimant name")


def check_4_live_log_is_clean() -> None:
    from week_traffic import CLAIMANTS
    if not os.path.exists(TRACE_PATH):
        print("  4. no trace log yet — skipped")
        return
    names = [c[0] for c in CLAIMANTS]
    raw = open(TRACE_PATH, encoding="utf-8").read()
    leaks = assert_clean(raw, names)
    assert not leaks, f"live log contains identifiers: {leaks[:5]}"
    n = len(read_traces(TRACE_PATH))
    print(f"  4. live log ({n} traces) contains no roster identifier        OK")


if __name__ == "__main__":
    print("redaction-before-write evidence")
    check_1_scrubbed_in_memory()
    check_2_pseudonym_is_stable()
    check_3_writer_refuses_dirty_line()
    check_4_live_log_is_clean()
    print("\nall checks passed")
