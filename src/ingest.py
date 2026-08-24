"""
ingest.py — Ingest the 6 endorsements into TWO separate ChromaDB collections:
  • 'endorsements_naive'          — Strategy A chunks
  • 'endorsements_structure_aware' — Strategy B chunks

Each chunk carries metadata: source_file, form_number, policy_line,
edition_date, chunk_id, clause_id, strategy, chunk_index.

NOTE: Only the 6 new endorsements are indexed. The base wording library
is NOT re-indexed (per the assignment constraint — see results.md).
"""

import os
import sys
import chromadb
from chromadb.utils import embedding_functions

# Add parent dir to path so src imports work when run from project root
sys.path.insert(0, os.path.dirname(__file__))
from chunkers import naive_chunker, structure_aware_chunker

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

ENDORSEMENTS_DIR = os.path.join(os.path.dirname(__file__), "..", "endorsements")
CHROMA_DB_PATH = os.path.join(os.path.dirname(__file__), "..", "chroma_db")

COLLECTION_NAIVE = "endorsements_naive"
COLLECTION_SA = "endorsements_structure_aware"

# Metadata extracted from filenames like "HO-0304_03-24.txt"
ENDORSEMENT_META = {
    "HO-0304_03-24.txt": {
        "form_number": "HO-0304",
        "edition_date": "03-24",
        "policy_line": "homeowners",
    },
    "HO-0305_03-24.txt": {
        "form_number": "HO-0305",
        "edition_date": "03-24",
        "policy_line": "homeowners",
    },
    "HO-0306_04-24.txt": {
        "form_number": "HO-0306",
        "edition_date": "04-24",
        "policy_line": "homeowners",
    },
    "HO-0307_04-24.txt": {
        "form_number": "HO-0307",
        "edition_date": "04-24",
        "policy_line": "homeowners",
    },
    "HO-0308_05-24.txt": {
        "form_number": "HO-0308",
        "edition_date": "05-24",
        "policy_line": "homeowners",
    },
    "HO-0309_05-24.txt": {
        "form_number": "HO-0309",
        "edition_date": "05-24",
        "policy_line": "homeowners",
    },
}


# ---------------------------------------------------------------------------
# Embedding function — local sentence-transformers (no extra API needed)
# ---------------------------------------------------------------------------

def get_embedding_fn():
    return embedding_functions.SentenceTransformerEmbeddingFunction(
        model_name="all-MiniLM-L6-v2"
    )


# ---------------------------------------------------------------------------
# Core ingest function
# ---------------------------------------------------------------------------

def ingest_all(reset: bool = True) -> dict:
    """
    Ingest all 6 endorsements into both ChromaDB collections.

    Args:
        reset: If True, drop and recreate collections (clean run).

    Returns:
        dict with ingest summary stats.
    """
    client = chromadb.PersistentClient(path=CHROMA_DB_PATH)
    emb_fn = get_embedding_fn()

    # Create or reset collections
    for name in [COLLECTION_NAIVE, COLLECTION_SA]:
        if reset:
            try:
                client.delete_collection(name)
                print(f"  Dropped existing collection: {name}")
            except Exception:
                pass
        client.get_or_create_collection(
            name=name,
            embedding_function=emb_fn,
            metadata={"hnsw:space": "cosine"},
        )

    col_naive = client.get_collection(COLLECTION_NAIVE, embedding_function=emb_fn)
    col_sa = client.get_collection(COLLECTION_SA, embedding_function=emb_fn)

    stats = {
        "files_processed": 0,
        "naive_chunks": 0,
        "sa_chunks": 0,
        "failed_files": [],
    }

    endorsement_files = sorted(
        [f for f in os.listdir(ENDORSEMENTS_DIR) if f.endswith(".txt")]
    )

    for filename in endorsement_files:
        if filename not in ENDORSEMENT_META:
            print(f"  WARNING: No metadata mapping for {filename}, skipping.")
            stats["failed_files"].append(filename)
            continue

        filepath = os.path.join(ENDORSEMENTS_DIR, filename)
        with open(filepath, "r", encoding="utf-8") as fh:
            text = fh.read()

        base_meta = {
            "source_file": filename,
            **ENDORSEMENT_META[filename],
        }

        # --- Naive chunks ---
        naive_chunks = naive_chunker(text, base_meta)
        _upsert_chunks(col_naive, naive_chunks)
        stats["naive_chunks"] += len(naive_chunks)

        # --- Structure-aware chunks ---
        sa_chunks = structure_aware_chunker(text, base_meta)
        _upsert_chunks(col_sa, sa_chunks)
        stats["sa_chunks"] += len(sa_chunks)

        stats["files_processed"] += 1
        print(
            f"  [{filename}] naive={len(naive_chunks)} chunks, "
            f"structure_aware={len(sa_chunks)} chunks"
        )

    print(
        f"\nIngest complete: {stats['files_processed']} files, "
        f"{stats['naive_chunks']} naive chunks, "
        f"{stats['sa_chunks']} SA chunks"
    )
    return stats


def _upsert_chunks(collection, chunks: list[dict]) -> None:
    """Batch-upsert chunks into a ChromaDB collection."""
    if not chunks:
        return
    ids = [c["metadata"]["chunk_id"] for c in chunks]
    texts = [c["text"] for c in chunks]
    metadatas = [c["metadata"] for c in chunks]

    # ChromaDB upsert in batches of 100
    batch_size = 100
    for i in range(0, len(chunks), batch_size):
        collection.upsert(
            ids=ids[i : i + batch_size],
            documents=texts[i : i + batch_size],
            metadatas=metadatas[i : i + batch_size],
        )


# ---------------------------------------------------------------------------
# Convenience: verify a chunk_id resolves to real content
# ---------------------------------------------------------------------------

def resolve_chunk(chunk_id: str, strategy: str = "structure_aware") -> dict | None:
    """
    Retrieve a chunk by its chunk_id from the appropriate collection.
    Returns the chunk dict or None if not found.
    """
    client = chromadb.PersistentClient(path=CHROMA_DB_PATH)
    emb_fn = get_embedding_fn()
    col_name = COLLECTION_SA if strategy == "structure_aware" else COLLECTION_NAIVE
    col = client.get_collection(col_name, embedding_function=emb_fn)
    result = col.get(ids=[chunk_id], include=["documents", "metadatas"])
    if result["ids"]:
        return {
            "chunk_id": chunk_id,
            "text": result["documents"][0],
            "metadata": result["metadatas"][0],
        }
    return None


if __name__ == "__main__":
    print("Starting ingest of 6 endorsements (base wording NOT re-indexed)...")
    stats = ingest_all(reset=True)
    print(f"\nFinal stats: {stats}")
