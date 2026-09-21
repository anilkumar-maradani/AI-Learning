"""
generation.py — Grounded answer generation with a hard refusal gate.

Talks to Groq's OpenAI-compatible endpoint (default model: openai/gpt-oss-120b,
override with the GROQ_MODEL env var). The system prompt forbids answering
from general knowledge: when the retrieved chunks do not contain the answer
the model must emit a fixed "REFUSAL:" message, which callers detect via
``is_refusal``.
"""

import os
from openai import OpenAI
from dotenv import load_dotenv

# ---------------------------------------------------------------------------
# Groq client (OpenAI-compatible)
# ---------------------------------------------------------------------------

GROQ_BASE_URL = "https://api.groq.com/openai/v1"
DEFAULT_MODEL = "openai/gpt-oss-120b"


def _api_key() -> str:
    """Resolve the Groq key lazily so a .env file works for every entry point."""
    load_dotenv()
    return os.environ.get("GROQ_API_KEY", "").strip()


def get_model() -> str:
    return os.environ.get("GROQ_MODEL", DEFAULT_MODEL)


def get_client() -> OpenAI:
    key = _api_key()
    if not key:
        raise ValueError(
            "GROQ_API_KEY is not set. Put it in .env (see .env.example) or set it "
            "in your shell: PowerShell `$env:GROQ_API_KEY=\"gsk_...\"`, "
            "bash `export GROQ_API_KEY=gsk_...`."
        )
    return OpenAI(api_key=key, base_url=GROQ_BASE_URL)


# ---------------------------------------------------------------------------
# Grounding system prompt — HARD refusal, no hallucination escape hatch
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """You are PolicyLens, a policy-endorsement assistant. You answer
questions strictly from the endorsement excerpts supplied in the context block.

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
        model=get_model(),
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


# ---------------------------------------------------------------------------
# Tool-calling model call (Week 7 agent loop)
# ---------------------------------------------------------------------------

# Groq pricing estimate for openai/gpt-oss-120b (as of 2026-09).
# Confirm at console.groq.com/settings/billing if pricing changes.
_COST_PER_1K_PROMPT_TOKENS = 0.0009     # USD
_COST_PER_1K_COMPLETION_TOKENS = 0.0009 # USD


def estimate_cost(usage: dict | None) -> float:
    """Return estimated USD cost for one model call given a usage dict."""
    if not usage:
        return 0.0
    prompt_tok = usage.get("prompt_tokens") or 0
    completion_tok = usage.get("completion_tokens") or 0
    return (
        prompt_tok / 1000 * _COST_PER_1K_PROMPT_TOKENS
        + completion_tok / 1000 * _COST_PER_1K_COMPLETION_TOKENS
    )


def call_model_with_tools(
    messages: list[dict],
    tools: list[dict],
    model_params: dict | None = None,
    max_wait_s: float = 300.0,
) -> dict:
    """
    One model call with tool definitions attached.

    Returns a dict with:
        "content"    : str | None   — final answer text (when no tool calls)
        "tool_calls" : list | None  — raw tool_call objects from the API
        "usage"      : dict | None  — {"prompt_tokens": int, "completion_tokens": int}
        "finish_reason": str
        "error"      : dict | None

    Retries transient 429/5xx up to 3 times, honouring Groq's stated wait.
    """
    import time
    import re

    client = get_client()
    mp = model_params or {}
    model_name = mp.get("name") or get_model()

    _WAIT_RE = re.compile(r"try again in\s+(?:(\d+)m)?([\d.]+)s", re.IGNORECASE)

    def _suggested_wait(msg: str) -> float | None:
        m = _WAIT_RE.search(msg)
        if not m:
            return None
        return float(m.group(1) or 0) * 60 + float(m.group(2)) + 2

    kwargs = {
        "model": model_name,
        "messages": messages,
        "tools": tools,
        "tool_choice": "auto",
        "temperature": mp.get("temperature", 0.0),
        "max_tokens": mp.get("max_tokens", 1200),
    }

    last_exc = None
    for attempt in range(4):
        try:
            resp = client.chat.completions.create(**kwargs)
            choice = resp.choices[0]
            usage = getattr(resp, "usage", None)
            usage_dict = {
                "prompt_tokens": getattr(usage, "prompt_tokens", 0),
                "completion_tokens": getattr(usage, "completion_tokens", 0),
            } if usage else None

            # Normalise tool_calls — may be None or an empty list
            raw_tool_calls = getattr(choice.message, "tool_calls", None) or []
            tool_calls_out = []
            for tc in raw_tool_calls:
                tool_calls_out.append({
                    "id": tc.id,
                    "name": tc.function.name,
                    "arguments": tc.function.arguments,  # raw JSON string
                })

            return {
                "content": (choice.message.content or "").strip() or None,
                "tool_calls": tool_calls_out if tool_calls_out else None,
                "usage": usage_dict,
                "finish_reason": choice.finish_reason,
                "error": None,
            }
        except Exception as exc:
            last_exc = exc
            msg = str(exc)
            transient = any(s in msg for s in ("429", "500", "502", "503", "timeout", "Timeout"))
            if attempt < 3 and transient:
                time.sleep(min(_suggested_wait(msg) or 3 * (attempt + 1), max_wait_s))
                continue
            break

    return {
        "content": None,
        "tool_calls": None,
        "usage": None,
        "finish_reason": "error",
        "error": {"type": type(last_exc).__name__, "message": str(last_exc)[:400]},
    }
