"""
generation.py — RAG generation and hard refusal logic.

Uses Groq API (OpenAI-compatible) with model openai/gpt-oss-120b.
The grounding prompt FORCES refusal when the answer cannot be sourced
from retrieved chunks. No "use your best judgment" loophole.
"""

import os
from openai import OpenAI

# ---------------------------------------------------------------------------
# Groq client (OpenAI-compatible)
# ---------------------------------------------------------------------------

GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")
GROQ_BASE_URL = "https://api.groq.com/openai/v1"
MODEL = "openai/gpt-oss-120b"

def get_client() -> OpenAI:
    if not GROQ_API_KEY:
        raise ValueError(
            "GROQ_API_KEY environment variable is not set. "
            "Export it before running: export GROQ_API_KEY=gsk_..."
        )
    return OpenAI(api_key=GROQ_API_KEY, base_url=GROQ_BASE_URL)


# ---------------------------------------------------------------------------
# Grounding system prompt — HARD refusal, no hallucination escape hatch
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """You are an insurance claims assistant that answers questions
ONLY from the provided policy endorsement context.

RULES (non-negotiable):
1. Answer ONLY using information explicitly stated in the provided context chunks.
2. Every factual claim in your answer MUST be supported by a chunk_id citation,
   formatted as: [SOURCE: chunk_id | form_number | clause_id]
3. If the answer to the question is NOT present in the provided context, you MUST
   respond with EXACTLY this refusal message and nothing else:
   "REFUSAL: The requested information (e.g. [brief topic]) is not present in
   the indexed endorsement corpus. This question cannot be answered from the
   available policy documents."
4. Do NOT use your general knowledge, assumptions, or reasoning beyond what
   the context states. Do NOT say "typically" or "generally" or "based on
   standard practice."
5. Do NOT attempt to answer partially if the key information is missing.
   Partial answers that fill gaps with inference are treated as hallucinations.
6. If in doubt, refuse. An invented coverage answer given to a policyholder
   is a bad-faith exposure; refusal is always safer than invention.
"""

# ---------------------------------------------------------------------------
# Context formatter
# ---------------------------------------------------------------------------

def format_context(hits: list[dict]) -> str:
    """Format retrieved chunks into a numbered context block for the prompt."""
    parts = []
    for h in hits:
        meta = h["metadata"]
        parts.append(
            f"--- CHUNK ---\n"
            f"chunk_id: {h['chunk_id']}\n"
            f"form_number: {meta.get('form_number', 'UNKNOWN')}\n"
            f"clause_id: {meta.get('clause_id', 'N/A')}\n"
            f"source_file: {meta.get('source_file', 'UNKNOWN')}\n"
            f"score: {h['score']:.4f}\n"
            f"text:\n{h['text']}\n"
        )
    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Main generation function
# ---------------------------------------------------------------------------

def generate_answer(
    question: str,
    hits: list[dict],
    verbose: bool = True,
) -> dict:
    """
    Generate a grounded answer (or hard refusal) from retrieved chunks.

    Args:
        question: The user's question.
        hits:     List of retrieved chunk dicts from retrieval.search().
        verbose:  If True, print the question and answer.

    Returns:
        dict with keys: question, answer, used_hits (chunk_ids in answer).
    """
    client = get_client()
    context = format_context(hits)

    user_message = (
        f"CONTEXT FROM INDEXED ENDORSEMENTS:\n\n{context}\n\n"
        f"QUESTION: {question}\n\n"
        f"Answer using ONLY the context above. Cite each claim with "
        f"[SOURCE: chunk_id | form_number | clause_id]. "
        f"If the answer is not in the context, issue the REFUSAL message exactly."
    )

    response = client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_message},
        ],
        temperature=0.0,
        max_tokens=800,
    )

    answer = response.choices[0].message.content.strip()

    if verbose:
        print(f"\nQ: {question}")
        print(f"A: {answer}\n")

    return {
        "question": question,
        "answer": answer,
        "is_refusal": answer.startswith("REFUSAL:"),
        "hits_used": [h["chunk_id"] for h in hits],
    }


# ---------------------------------------------------------------------------
# Batch: run answerable + unanswerable questions
# ---------------------------------------------------------------------------

def run_answerable_questions(
    questions: list[dict],
    search_fn,
    n_results: int = 5,
    verbose: bool = True,
) -> list[dict]:
    """
    Run a list of answerable questions through generation.
    Each question dict: {question, expected_form, expected_clause}
    """
    results = []
    for q in questions:
        hits = search_fn(q["question"], strategy="structure_aware", n_results=n_results)
        gen = generate_answer(q["question"], hits, verbose=verbose)
        gen["expected_form"] = q.get("expected_form", "")
        gen["expected_clause"] = q.get("expected_clause", "")
        results.append(gen)
    return results


def run_unanswerable_questions(
    questions: list[str],
    search_fn,
    n_results: int = 5,
    verbose: bool = True,
) -> list[dict]:
    """
    Run a list of out-of-corpus questions through generation.
    These MUST trigger refusal.
    """
    results = []
    for question in questions:
        hits = search_fn(question, strategy="structure_aware", n_results=n_results)
        gen = generate_answer(question, hits, verbose=verbose)
        gen["expected_refusal"] = True
        gen["correctly_refused"] = gen["is_refusal"]
        results.append(gen)
    return results
