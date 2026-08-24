"""
chunkers.py — Two chunking strategies for insurance endorsements.

Strategy A: NAIVE — fixed token-window sliding chunks (400 tokens, 50 overlap).
Strategy B: STRUCTURE-AWARE — splits on clause/section headers; keeps every
            exclusion table row attached to its table header and form number.
"""

import re
import tiktoken

# ---------------------------------------------------------------------------
# Shared token helper
# ---------------------------------------------------------------------------

_ENC = tiktoken.get_encoding("cl100k_base")


def _token_len(text: str) -> int:
    return len(_ENC.encode(text))


def _split_tokens(text: str, max_tokens: int = 400, overlap: int = 50) -> list[str]:
    """Split *text* into token-windows of at most *max_tokens* with *overlap*."""
    tokens = _ENC.encode(text)
    chunks = []
    start = 0
    while start < len(tokens):
        end = min(start + max_tokens, len(tokens))
        chunk_tokens = tokens[start:end]
        chunks.append(_ENC.decode(chunk_tokens))
        if end == len(tokens):
            break
        start += max_tokens - overlap
    return chunks


# ---------------------------------------------------------------------------
# Strategy A — NAIVE chunker
# ---------------------------------------------------------------------------

def naive_chunker(text: str, metadata: dict) -> list[dict]:
    """
    Splits the document using a fixed 400-token sliding window with 50-token
    overlap.  No awareness of headers, tables, or clause boundaries.

    Returns a list of chunk dicts with 'text' and 'metadata' fields.
    """
    windows = _split_tokens(text, max_tokens=400, overlap=50)
    chunks = []
    form = metadata.get("form_number", "UNKNOWN")
    for i, window in enumerate(windows):
        chunk_id = f"{form}_naive_chunk_{i:03d}"
        chunk_meta = {
            **metadata,
            "chunk_id": chunk_id,
            "chunk_index": i,
            "strategy": "naive",
            "clause_id": "N/A",
        }
        chunks.append({"text": window, "metadata": chunk_meta})
    return chunks


# ---------------------------------------------------------------------------
# Strategy B — STRUCTURE-AWARE chunker
# ---------------------------------------------------------------------------

# Header patterns that trigger a new chunk boundary
_HEADER_RE = re.compile(
    r"""(?x)
    (?:^|\n)                         # start of line
    (?:
        SECTION\s+[IVXLCDM\d]+       # SECTION I, II, III ...
        | CLAUSE\s+[A-Z]{2,4}-\d+    # CLAUSE WD-1, EM-2 ...
        | EXCLUSION\s+TABLE          # EXCLUSION TABLE header
        | (?:E-\d{1,3})\s*[\|—]      # Table row starting with E-NN
        | HOMEOWNERS\s+ENDORSEMENT   # document title
        | Form\s+Number:             # metadata header block
        | END\s+OF\s+ENDORSEMENT     # trailer
    )
    """,
    re.MULTILINE,
)

# Pattern to detect exclusion table rows: | E-17 | ... |
_EXCL_ROW_RE = re.compile(r"^\|\s*E-\d{1,3}\s*\|", re.MULTILINE)

# Pattern to detect the EXCLUSION TABLE header line
_TABLE_HEADER_RE = re.compile(
    r"EXCLUSION TABLE\s*[—-]\s*([A-Z0-9-]+\s+ed\.\s+[0-9]{2}-[0-9]{2})",
    re.IGNORECASE,
)


def _detect_clause_id(segment: str, form_number: str) -> str:
    """Best-effort clause ID extraction from a text segment."""
    # Check for exclusion table header
    m = _TABLE_HEADER_RE.search(segment)
    if m:
        return "EXCLUSION-TABLE"
    # Check for specific E-NN codes in table rows
    rows = _EXCL_ROW_RE.findall(segment)
    if rows:
        codes = re.findall(r"E-\d{1,3}", segment)
        if codes:
            return f"EXCLUSION-TABLE-{'-'.join(dict.fromkeys(codes))}"
    # Named clause
    clause_m = re.search(r"CLAUSE\s+([A-Z]{2,4}-\d+)", segment)
    if clause_m:
        return f"CLAUSE-{clause_m.group(1)}"
    # Section
    section_m = re.search(r"SECTION\s+([IVXLCDM\d]+)", segment)
    if section_m:
        return f"SECTION-{section_m.group(1)}"
    return "PREAMBLE"


def _split_on_headers(text: str) -> list[str]:
    """
    Split document text at every structural header boundary.
    Returns list of segments (each starts at a header).
    """
    # Find all split positions
    positions = [0]
    for m in _HEADER_RE.finditer(text):
        pos = m.start()
        if pos > 0 and pos not in positions:
            positions.append(pos)
    positions.append(len(text))

    segments = []
    for i in range(len(positions) - 1):
        seg = text[positions[i]:positions[i + 1]].strip()
        if seg:
            segments.append(seg)
    return segments


def _glue_exclusion_rows(segments: list[str]) -> list[str]:
    """
    Merge any segment that is a bare exclusion table row (no table header)
    with the preceding segment that contains the table header.
    This prevents a row like '| E-17 | ...' from floating alone.
    """
    merged = []
    i = 0
    while i < len(segments):
        seg = segments[i]
        # If this segment starts with a table row but has no table header,
        # glue it onto the previous segment.
        if _EXCL_ROW_RE.search(seg) and not _TABLE_HEADER_RE.search(seg) and merged:
            merged[-1] = merged[-1] + "\n" + seg
        else:
            merged.append(seg)
        i += 1
    return merged


def structure_aware_chunker(text: str, metadata: dict) -> list[dict]:
    """
    Splits on form/clause headers and never separates an exclusion row from
    its table header or form number.

    Every chunk has the form_number prepended so the embedding always sees
    which endorsement the chunk belongs to.

    Returns a list of chunk dicts with 'text' and 'metadata' fields.
    """
    form = metadata.get("form_number", "UNKNOWN")
    edition = metadata.get("edition_date", "")

    segments = _split_on_headers(text)
    segments = _glue_exclusion_rows(segments)

    chunks = []
    for i, seg in enumerate(segments):
        clause_id = _detect_clause_id(seg, form)

        # Prepend the form identifier so embeddings carry provenance
        anchored_text = (
            f"[{form} ed. {edition}] {clause_id}\n{seg}"
        )

        # If a single segment exceeds 400 tokens, sub-split it (keeps header)
        if _token_len(anchored_text) > 400:
            sub_chunks = _split_tokens(anchored_text, max_tokens=400, overlap=50)
            for j, sub in enumerate(sub_chunks):
                chunk_id = f"{form}_sa_chunk_{i:03d}_{j:02d}"
                chunk_meta = {
                    **metadata,
                    "chunk_id": chunk_id,
                    "chunk_index": i * 100 + j,
                    "strategy": "structure_aware",
                    "clause_id": clause_id,
                }
                chunks.append({"text": sub, "metadata": chunk_meta})
        else:
            chunk_id = f"{form}_sa_chunk_{i:03d}"
            chunk_meta = {
                **metadata,
                "chunk_id": chunk_id,
                "chunk_index": i,
                "strategy": "structure_aware",
                "clause_id": clause_id,
            }
            chunks.append({"text": anchored_text, "metadata": chunk_meta})

    return chunks
