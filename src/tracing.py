"""
tracing.py — Trace schema and append-only writer for the claims assistant.

One JSON object per line in ``traces/traces.jsonl``. Everything replay needs is
in the line: prompt version + hash, every retrieved chunk_id with its score and
rank, the model and its parameters, and the raw output before any parsing.

Two properties this module enforces rather than documents:

1. **Redaction happens before write.** ``TraceRecord.build`` runs the redactor on
   the question and loss summary while the record is still in memory. The writer
   then re-checks the serialised line with ``redaction.assert_clean`` and raises
   rather than append if anything got through. There is no code path that writes
   an unredacted line and cleans it afterwards.

2. **Index drift is detectable.** Each trace carries an ``index_fingerprint``:
   a hash over every chunk_id and chunk text in the collection at write time.
   If the corpus is re-ingested with a different chunker, replay of an old trace
   reports "index changed" instead of quietly resolving different chunk text.
"""

import hashlib
import json
import os
import subprocess
import sys
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(__file__))
import prompts
from redaction import redact_text, assert_clean

SCHEMA_VERSION = "1.0"

_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
TRACE_DIR = os.path.join(_PROJECT_ROOT, "traces")
TRACE_PATH = os.path.join(TRACE_DIR, "traces.jsonl")


# ---------------------------------------------------------------------------
# Environment fingerprints
# ---------------------------------------------------------------------------

def git_commit() -> str:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=_PROJECT_ROOT, capture_output=True, text=True, timeout=10,
        )
        return out.stdout.strip() or "unknown"
    except Exception:
        return "unknown"


_index_fp_cache: str | None = None


def index_fingerprint() -> str:
    """
    Hash over (chunk_id, text) for the whole structure-aware collection.

    Computed once per process. This is what lets a replay six weeks later say
    "the index behind this trace is the one that produced it" rather than
    assuming it.
    """
    global _index_fp_cache
    if _index_fp_cache is not None:
        return _index_fp_cache
    try:
        import chromadb
        from ingest import CHROMA_DB_PATH, COLLECTION_SA, get_embedding_fn
        client = chromadb.PersistentClient(path=CHROMA_DB_PATH)
        col = client.get_collection(COLLECTION_SA, embedding_function=get_embedding_fn())
        res = col.get(include=["documents"])
        h = hashlib.sha256()
        for cid, doc in sorted(zip(res["ids"], res["documents"])):
            h.update(cid.encode("utf-8"))
            h.update(b"\x00")
            h.update(doc.encode("utf-8"))
            h.update(b"\x01")
        _index_fp_cache = h.hexdigest()[:16]
    except Exception as exc:  # pragma: no cover - index must exist in practice
        _index_fp_cache = f"unavailable:{type(exc).__name__}"
    return _index_fp_cache


def salt_fingerprint() -> str:
    """Identifies WHICH salt produced the pseudonyms, without revealing it."""
    salt = os.environ.get("POLICYLENS_REDACTION_SALT", "policylens-local-dev-salt")
    return hashlib.sha256(salt.encode("utf-8")).hexdigest()[:8]


# ---------------------------------------------------------------------------
# Record
# ---------------------------------------------------------------------------

@dataclass
class TraceRecord:
    trace_id: str
    ts_utc: str
    schema_version: str
    git_commit: str
    index_fingerprint: str
    prompt: dict
    input: dict
    retrieval: dict
    model: dict
    output: dict
    timing: dict
    redaction: dict
    error: dict | None = None
    tags: list = field(default_factory=list)

    @staticmethod
    def build(
        *,
        question: str,
        loss_summary: str,
        claimant_name: str,
        claim_number: str,
        prompt_version: str,
        retrieval_meta: dict,
        hits: list[dict],
        model_meta: dict,
        raw_output: str,
        timing: dict,
        error: dict | None = None,
        tags: list | None = None,
        channel: str = "adjuster_console",
    ) -> "TraceRecord":
        """
        Construct a trace with redaction already applied.

        ``question``, ``loss_summary``, ``claimant_name`` and ``claim_number``
        arrive raw. They leave this function pseudonymised. Nothing between here
        and the file handle sees the raw values.
        """
        roster = [n for n in [claimant_name] if n]
        red_question, c1 = redact_text(question, roster)
        red_loss, c2 = redact_text(loss_summary, roster)
        red_output, c3 = redact_text(raw_output, roster)
        # The claim number is redacted through the same path, so the claim_ref
        # stored on the trace is the pseudonym and never the real number.
        red_claim, c4 = redact_text(claim_number, roster)

        counts: dict[str, int] = {}
        for c in (c1, c2, c3, c4):
            for k, v in c.items():
                counts[k] = counts.get(k, 0) + v

        return TraceRecord(
            trace_id=f"tr_{uuid.uuid4().hex[:12]}",
            ts_utc=datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
            schema_version=SCHEMA_VERSION,
            git_commit=git_commit(),
            index_fingerprint=index_fingerprint(),
            prompt=prompts.prompt_fingerprint(prompt_version),
            input={
                "question": red_question,
                "loss_summary": red_loss,
                "claim_ref": red_claim,
                "channel": channel,
            },
            retrieval={
                **retrieval_meta,
                "chunks": [
                    {
                        "rank": h.get("rank"),
                        "chunk_id": h["chunk_id"],
                        "score": h.get("score"),
                        "vector_rank": h.get("vector_rank"),
                        "bm25_rank": h.get("bm25_rank"),
                        "form_number": h["metadata"].get("form_number"),
                        "edition_date": h["metadata"].get("edition_date"),
                        "clause_id": h["metadata"].get("clause_id"),
                        "source_file": h["metadata"].get("source_file"),
                    }
                    for h in hits
                ],
            },
            model=model_meta,
            output={
                "raw": red_output,
                "is_refusal": red_output.strip().startswith("REFUSAL:"),
                "cited_chunk_ids": _extract_citations(red_output),
                "chars": len(red_output),
            },
            timing=timing,
            redaction={
                "applied": "pre_write",
                "counts": counts,
                "salt_fingerprint": salt_fingerprint(),
            },
            error=error,
            tags=tags or [],
        )


_CITATION_PREFIX = "[SOURCE:"


def _extract_citations(text: str) -> list[str]:
    """Pull chunk_ids out of [SOURCE: chunk_id | form | clause] markers."""
    out, i = [], 0
    while True:
        i = text.find(_CITATION_PREFIX, i)
        if i == -1:
            break
        j = text.find("]", i)
        if j == -1:
            break
        body = text[i + len(_CITATION_PREFIX):j]
        cid = body.split("|")[0].strip()
        if cid and cid not in out:
            out.append(cid)
        i = j + 1
    return out


# ---------------------------------------------------------------------------
# Writer
# ---------------------------------------------------------------------------

class TraceWriter:
    """Append-only JSONL writer with a pre-write leak check."""

    def __init__(self, path: str = TRACE_PATH):
        self.path = path
        os.makedirs(os.path.dirname(path), exist_ok=True)

    def write(self, record: TraceRecord, known_names: list[str] | None = None) -> str:
        line = json.dumps(asdict(record), ensure_ascii=False)
        leaks = assert_clean(line, known_names)
        if leaks:
            raise RuntimeError(
                "Refusing to write trace: redaction leak detected before write -> "
                + "; ".join(leaks)
            )
        with open(self.path, "a", encoding="utf-8") as fh:
            fh.write(line + "\n")
        return record.trace_id


def read_traces(path: str = TRACE_PATH) -> list[dict]:
    if not os.path.exists(path):
        return []
    out = []
    with open(path, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                out.append(json.loads(line))
    return out


def get_trace(trace_id: str, path: str = TRACE_PATH) -> dict | None:
    for t in read_traces(path):
        if t["trace_id"] == trace_id:
            return t
    return None
