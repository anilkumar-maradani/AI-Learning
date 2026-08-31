"""
hybrid_retrieval.py — Hybrid retrieval: BM25 keyword search + dense vector
search, fused with Reciprocal Rank Fusion (RRF).

Motivation
    Dense embeddings capture meaning ("broken supply line" ≈ "burst pipe") but
    blur rare identifiers: "E-17" embeds almost identically to "E-11" or
    "E-15" because they all live in the same exclusion-table context. BM25
    is the opposite — it rewards rare exact tokens heavily. Fusing the two
    rank lists gives us both behaviours.

Fusion
    rrf(chunk) = 1/(k + rank_vector) + 1/(k + rank_bm25),  k = 60
    A chunk appearing in only one list is charged a penalty rank of
    (candidate_count + 1) for the list it is missing from.

Post-fusion rescue
    If the query contains an exclusion code (E-NN), chunks whose text
    contains that code are promoted above chunks that don't, and short
    PREAMBLE chunks are demoted to the bottom.

Dependency: rank-bm25 (listed in requirements.txt).
"""

import os
import sys
import re
import chromadb
from chromadb.utils import embedding_functions
from rank_bm25 import BM25Okapi

sys.path.insert(0, os.path.dirname(__file__))
from ingest import CHROMA_DB_PATH, COLLECTION_SA, get_embedding_fn
from console import enable_utf8

enable_utf8()

# ── RRF constant (standard value) ────────────────────────────────────────────
RRF_K = 60


def _tokenize(text: str) -> list[str]:
    """
    Simple tokenizer for BM25.

    BM25 works on a list of tokens (words). We:
    1. Lowercase everything
    2. Keep SHORT hyphenated codes intact: "E-17" → "e-17", "HO-0304" → "ho-0304"
    3. Split LONG hyphenated compounds (clause_id prefixes like
       EXCLUSION-TABLE-E-11-E-12-E-13-...-E-17-E-18) into their short parts.

    WHY this matters:
        The structure-aware chunker prepends a clause_id like
        "EXCLUSION-TABLE-E-11-E-12-...-E-17-E-18" to every chunk's text.
        If we allow unlimited hyphens, this entire string becomes ONE token:
        "exclusion-table-e-11-e-12-...-e-17-e-18" — and BM25 cannot match
        the query token "e-17" against it.

        By limiting to ONE hyphen per token, we split the compound into:
        ["exclusion-table", "e-11", "e-12", ..., "e-17", "e-18"]
        Now "e-17" appears as a separate token in the clause_id prefix AND
        again in the exclusion table body — TF=2, which correctly boosts
        the EXCLUSION-TABLE chunk's BM25 score for "e-17" queries.

    Example:
        "E-17 burst supply line"              → ["e-17", "burst", "supply", "line"]
        "EXCLUSION-TABLE-E-11-E-12-...-E-17"  → ["exclusion-table", "e-11", ..., "e-17"]
        "HO-0304 ed. 03-24"                   → ["ho-0304", "ed", "03-24"]
    """
    # Max ONE hyphen per token → splits long clause_id compounds correctly
    # while keeping short codes like e-17, ho-0304, 03-24 intact.
    tokens = re.findall(r"[a-zA-Z0-9]+(?:-[a-zA-Z0-9]+)?", text.lower())
    return tokens


class BM25Index:
    """
    Builds a BM25 index from all chunks in the ChromaDB collection.

    Think of this like building a book index:
      1. Load all chunks from ChromaDB
      2. Tokenize each chunk's text
      3. Build the BM25 index over those tokens
      4. When you search, BM25 scores each chunk based on term frequency
    """

    def __init__(self):
        self.chunks: list[dict] = []   # all chunks with text + metadata
        self.bm25 = None               # the BM25 index object
        self._build()

    def _build(self):
        """Load all chunks from ChromaDB and build the BM25 index."""
        client = chromadb.PersistentClient(path=CHROMA_DB_PATH)
        emb_fn = get_embedding_fn()
        col = client.get_collection(COLLECTION_SA, embedding_function=emb_fn)

        # Get ALL chunks from the collection (no query, just list everything)
        # ChromaDB's .get() returns all documents if no ids specified
        print("  [BM25] Loading all chunks from ChromaDB...", end="", flush=True)
        result = col.get(include=["documents", "metadatas"])

        for doc_id, text, meta in zip(
            result["ids"], result["documents"], result["metadatas"]
        ):
            self.chunks.append({
                "chunk_id": doc_id,
                "text": text,
                "metadata": meta,
            })

        print(f" {len(self.chunks)} chunks loaded.")

        # Tokenize each chunk and build BM25
        print("  [BM25] Building BM25 index...", end="", flush=True)
        tokenized_corpus = [_tokenize(chunk["text"]) for chunk in self.chunks]
        self.bm25 = BM25Okapi(tokenized_corpus)
        print(" done.")

    def search(self, query: str, n_results: int = 25) -> list[dict]:
        """
        Search the BM25 index for the top n_results chunks.

        Returns a list of dicts like:
            [{"rank": 1, "chunk_id": ..., "score": ..., "text": ..., "metadata": ...}, ...]
        """
        query_tokens = _tokenize(query)
        scores = self.bm25.get_scores(query_tokens)

        # Pair each chunk with its BM25 score, then sort descending
        scored = sorted(
            enumerate(scores), key=lambda x: x[1], reverse=True
        )[:n_results]

        results = []
        for rank, (idx, score) in enumerate(scored):
            chunk = self.chunks[idx]
            results.append({
                "rank": rank + 1,
                "chunk_id": chunk["chunk_id"],
                "score": float(score),
                "distance": float(-score),   # keep interface consistent
                "text": chunk["text"],
                "metadata": chunk["metadata"],
            })
        return results


# ── Module-level singleton — built once, reused across queries ───────────────
# (Building the index takes ~1-2 seconds; we don't want to rebuild per query)
_bm25_index: BM25Index | None = None


def _get_bm25_index() -> BM25Index:
    global _bm25_index
    if _bm25_index is None:
        _bm25_index = BM25Index()
    return _bm25_index


# ── RRF Fusion ────────────────────────────────────────────────────────────────

def _rrf_fuse(
    vector_results: list[dict],
    bm25_results: list[dict],
    k: int = RRF_K,
    n_results: int = 5,
) -> list[dict]:
    """
    Combine two ranked lists using Reciprocal Rank Fusion.

    ┌──────────────────────────────────────────────────────┐
    │  RRF formula for each chunk:                         │
    │                                                      │
    │  rrf_score = 1/(k + rank_vector) + 1/(k + rank_bm25)│
    │                                                      │
    │  k=60 softens the influence of top ranks.            │
    │  A chunk that appears at rank 1 in BOTH lists gets   │
    │  the highest combined score.                         │
    └──────────────────────────────────────────────────────┘

    Args:
        vector_results: ranked list from vector search
        bm25_results:   ranked list from BM25
        k:              RRF constant (default 60)
        n_results:      how many to return after fusion

    Returns:
        Fused & re-ranked list of top n_results chunks
    """
    # Build lookup: chunk_id → (text, metadata)
    chunk_store: dict[str, dict] = {}
    for r in vector_results + bm25_results:
        if r["chunk_id"] not in chunk_store:
            chunk_store[r["chunk_id"]] = {"text": r["text"], "metadata": r["metadata"]}

    # Build lookup: chunk_id → rank in each list
    vector_rank_by_id = {r["chunk_id"]: r["rank"] for r in vector_results}
    bm25_rank_by_id   = {r["chunk_id"]: r["rank"]  for r in bm25_results}

    # Collect all unique chunk_ids
    all_ids = set(vector_rank_by_id.keys()) | set(bm25_rank_by_id.keys())

    # Calculate RRF score for each chunk
    rrf_scores = {}
    # If a chunk only appears in one list, it gets a penalty rank (len + 1)
    penalty_rank = max(len(vector_results), len(bm25_results)) + 1

    for chunk_id in all_ids:
        v_rank = vector_rank_by_id.get(chunk_id, penalty_rank)
        b_rank = bm25_rank_by_id.get(chunk_id, penalty_rank)
        rrf_scores[chunk_id] = 1.0 / (k + v_rank) + 1.0 / (k + b_rank)

    # Sort by RRF score descending and take top n_results
    sorted_ids = sorted(rrf_scores.items(), key=lambda x: x[1], reverse=True)[:n_results]

    fused = []
    for rank, (chunk_id, score) in enumerate(sorted_ids):
        chunk = chunk_store[chunk_id]
        fused.append({
            "rank": rank + 1,
            "chunk_id": chunk_id,
            "score": round(score, 6),
            "distance": round(1 - score, 6),
            "text": chunk["text"],
            "metadata": chunk["metadata"],
            "rrf_score": round(score, 6),
            # Diagnostic info — which list did this come from?
            "vector_rank": vector_rank_by_id.get(chunk_id, None),
            "bm25_rank": bm25_rank_by_id.get(chunk_id, None),
        })
    return fused


# ── Public API ────────────────────────────────────────────────────────────────

def hybrid_search(
    query: str,
    n_results: int = 5,
    bm25_candidates: int = 25,
    vector_candidates: int = 25,
) -> list[dict]:
    """
    Perform hybrid search: BM25 + Vector Search fused with RRF.

    This is a DROP-IN REPLACEMENT for retrieval.search().
    It returns the same format so existing code (chat.py, evaluate) works unchanged.

    Steps:
      1. Run vector search → top 25 results
      2. Run BM25 search   → top 25 results
      3. Fuse with RRF (k=60) → top n_results

    Args:
        query:             The user's question
        n_results:         Number of results to return (default 5)
        bm25_candidates:   How many candidates BM25 provides to RRF (default 25)
        vector_candidates: How many candidates vector search provides (default 25)

    Returns:
        List of chunk dicts with rank, score, text, metadata
    """
    # Import here to avoid circular imports
    from retrieval import search as vector_search_fn

    # Step 1: Vector search (semantic — finds meaning)
    vector_results = vector_search_fn(
        query, strategy="structure_aware", n_results=vector_candidates
    )

    # Step 2: BM25 search (keyword — finds exact tokens like "E-17")
    bm25_index = _get_bm25_index()
    bm25_results = bm25_index.search(query, n_results=bm25_candidates)

    # Step 3: Fuse with RRF — fetch extra candidates so rescue step has room
    fused = _rrf_fuse(vector_results, bm25_results, k=RRF_K, n_results=max(n_results * 3, 15))

    # Step 4: Exact-token rescue
    # ─────────────────────────────────────────────────────────────────────────
    # Problem: the structure-aware chunker prepends "[FORM ed. DATE]" to every
    # chunk. PREAMBLE chunks are short and this prefix dominates their embedding,
    # giving them very high vector similarity for any form-number query.
    # Result: PREAMBLE chunks (which carry no clause content) flood the top of
    # the RRF list even when BM25 correctly identifies the EXCLUSION-TABLE chunk.
    #
    # Solution: detect exact query tokens (E-XX codes, form numbers).
    # Any fused chunk that CONTAINS an exact query token gets promoted above
    # chunks that do NOT contain it, regardless of RRF score.
    # Chunks that neither contain the token nor are PREAMBLE stay in RRF order.
    # ─────────────────────────────────────────────────────────────────────────
    exact_tokens = re.findall(r"\bE-\d{1,3}\b", query, re.IGNORECASE)

    if exact_tokens:
        def _contains_exact(chunk: dict) -> bool:
            text = chunk["text"]
            return any(tok.upper() in text.upper() for tok in exact_tokens)

        def _is_preamble(chunk: dict) -> bool:
            return chunk["metadata"].get("clause_id", "").upper() == "PREAMBLE"

        # Split into: chunks with exact-token match vs the rest
        with_token = [c for c in fused if _contains_exact(c)]
        without_token_non_preamble = [
            c for c in fused if not _contains_exact(c) and not _is_preamble(c)
        ]
        without_token_preamble = [
            c for c in fused if not _contains_exact(c) and _is_preamble(c)
        ]

        # Re-merge: exact matches first, then non-preamble, then preamble
        reranked = with_token + without_token_non_preamble + without_token_preamble
        fused = reranked[:n_results]

        # Re-number ranks after rescue
        for i, chunk in enumerate(fused):
            chunk["rank"] = i + 1
    else:
        # No exact tokens → just trim to n_results
        fused = fused[:n_results]

    return fused


def format_hybrid_results(results: list[dict], max_text_chars: int = 200) -> str:
    """Pretty-print hybrid search results with RRF diagnostic info."""
    lines = []
    for r in results:
        meta = r["metadata"]
        snippet = r["text"][:max_text_chars].replace("\n", " ")
        v_rank = r.get("vector_rank", "N/A")
        b_rank = r.get("bm25_rank", "N/A")
        lines.append(
            f"  Rank {r['rank']} | rrf={r['score']:.5f} | "
            f"vector_rank={v_rank} | bm25_rank={b_rank}\n"
            f"           chunk_id={r['chunk_id']}\n"
            f"           form={meta.get('form_number','?')} | "
            f"clause={meta.get('clause_id','?')}\n"
            f"           snippet: {snippet}..."
        )
    return "\n".join(lines)


# ── Quick test ────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("Testing hybrid search...\n")

    test_queries = [
        "Does exclusion E-17 apply under HO-0304 ed. 03-24?",
        "What is the named storm deductible under HO-0305?",
        "Is mold covered after a burst pipe?",
    ]

    for query in test_queries:
        print(f"Query: {query}")
        results = hybrid_search(query, n_results=3)
        print(format_hybrid_results(results))
        print()
