"""
retrieval.py — Search functions for both ChromaDB collections.

Provides:
  • search(query, strategy, n_results, where_filter)
  • search_both_strategies(query, n_results) — returns results from both
  • metadata_filter_demo(query, policy_line) — demonstrates filtering effect
"""

import os
import sys
import chromadb
from chromadb.utils import embedding_functions

sys.path.insert(0, os.path.dirname(__file__))
from ingest import CHROMA_DB_PATH, COLLECTION_NAIVE, COLLECTION_SA, get_embedding_fn

# ---------------------------------------------------------------------------
# Core search
# ---------------------------------------------------------------------------

def search(
    query: str,
    strategy: str = "structure_aware",
    n_results: int = 5,
    where_filter: dict | None = None,
) -> list[dict]:
    """
    Perform vector search against a collection.

    Args:
        query:         The search query string.
        strategy:      "naive" | "structure_aware"
        n_results:     Number of results to return.
        where_filter:  Optional ChromaDB 'where' metadata filter dict.

    Returns:
        List of result dicts with keys: chunk_id, score, text, metadata.
    """
    client = chromadb.PersistentClient(path=CHROMA_DB_PATH)
    emb_fn = get_embedding_fn()
    col_name = COLLECTION_SA if strategy == "structure_aware" else COLLECTION_NAIVE
    col = client.get_collection(col_name, embedding_function=emb_fn)

    kwargs = {
        "query_texts": [query],
        "n_results": n_results,
        "include": ["documents", "metadatas", "distances"],
    }
    if where_filter:
        kwargs["where"] = where_filter

    result = col.query(**kwargs)

    hits = []
    for i, (doc_id, doc, meta, dist) in enumerate(zip(
        result["ids"][0],
        result["documents"][0],
        result["metadatas"][0],
        result["distances"][0],
    )):
        hits.append({
            "rank": i + 1,
            "chunk_id": doc_id,
            "score": round(1 - dist, 4),   # cosine similarity (higher = better)
            "distance": round(dist, 4),
            "text": doc,
            "metadata": meta,
        })
    return hits


def search_both_strategies(query: str, n_results: int = 5) -> dict:
    """Run the same query against both collections and return both result sets."""
    return {
        "naive": search(query, strategy="naive", n_results=n_results),
        "structure_aware": search(query, strategy="structure_aware", n_results=n_results),
    }


# ---------------------------------------------------------------------------
# Metadata filter demo
# ---------------------------------------------------------------------------

def metadata_filter_demo(
    query: str,
    policy_line: str,
    strategy: str = "structure_aware",
    n_results: int = 5,
) -> dict:
    """
    Run the same query twice:
      1. Unfiltered — all policy lines
      2. Filtered   — only chunks where policy_line == policy_line

    Returns a dict with 'unfiltered' and 'filtered' result lists.
    """
    unfiltered = search(query, strategy=strategy, n_results=n_results)
    filtered = search(
        query,
        strategy=strategy,
        n_results=n_results,
        where_filter={"policy_line": {"$eq": policy_line}},
    )
    return {"unfiltered": unfiltered, "filtered": filtered}


# ---------------------------------------------------------------------------
# Hit-in-top-5 evaluator
# ---------------------------------------------------------------------------

def hit_in_top5(
    query: str,
    expected_form: str,
    expected_clause_fragment: str,
    strategy: str,
    n_results: int = 5,
) -> dict:
    """
    Check whether the correct answer (identified by form_number + clause text)
    appears in the top-N results.

    A hit is counted if ANY top-N result has:
      - metadata['form_number'] == expected_form  AND
      - expected_clause_fragment in result['text'] (case-insensitive)

    Returns dict with 'hit' (bool), 'rank' (int|None), and the result list.
    """
    results = search(query, strategy=strategy, n_results=n_results)
    hit = False
    rank = None
    for r in results:
        form_match = r["metadata"].get("form_number", "") == expected_form
        text_match = expected_clause_fragment.lower() in r["text"].lower()
        if form_match and text_match:
            hit = True
            rank = r["rank"]
            break
    return {"hit": hit, "rank": rank, "results": results}


# ---------------------------------------------------------------------------
# Pretty-print helpers
# ---------------------------------------------------------------------------

def format_results(results: list[dict], max_text_chars: int = 200) -> str:
    lines = []
    for r in results:
        meta = r["metadata"]
        snippet = r["text"][:max_text_chars].replace("\n", " ")
        lines.append(
            f"  Rank {r['rank']} | score={r['score']:.4f} | "
            f"chunk_id={r['chunk_id']}\n"
            f"           form={meta.get('form_number','?')} | "
            f"clause={meta.get('clause_id','?')} | "
            f"file={meta.get('source_file','?')}\n"
            f"           snippet: {snippet}..."
        )
    return "\n".join(lines)
