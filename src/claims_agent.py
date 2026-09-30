"""
claims_agent.py — The claims assistant, instrumented.

One call per adjuster question:

    retrieve (hybrid BM25 + vector + RRF)  ->  generate (Groq)  ->  write trace

The function returns the trace record rather than a pretty answer, because for
this week the trace *is* the product. Every parameter that influences the output
is captured on the way past: retrieval mode and candidate counts, each chunk's
id / rank / score / form / edition, the prompt version, the model and its
sampling parameters, and the untouched raw completion.

Failure is traced too. A provider error produces a trace with ``error`` set and
an empty output rather than no trace at all — a log that only records successes
would understate exactly the failure modes error analysis is looking for.
"""

import os
import re
import sys
import time

sys.path.insert(0, os.path.dirname(__file__))
import prompts
from tracing import TraceRecord, TraceWriter

DEFAULT_RETRIEVAL = {
    "mode": "hybrid_rrf",
    "strategy": "structure_aware",
    "n_results": 5,
    "bm25_candidates": 25,
    "vector_candidates": 25,
    "rrf_k": 60,
}

DEFAULT_MODEL_PARAMS = {
    "temperature": 0.0,
    "max_tokens": 800,
    "top_p": 1.0,
    "seed": None,
}


def build_user_message(
    prompt_version: str,
    context: str,
    claim_ref: str,
    loss_summary: str,
    question: str,
) -> str:
    """Single source of truth for the user turn — used live AND by replay."""
    return prompts.get_user_template(prompt_version).format(
        context=context,
        claim_ref=claim_ref,
        loss_summary=loss_summary,
        question=question,
    )


def retrieve(question: str, retrieval_cfg: dict) -> list[dict]:
    from hybrid_retrieval import hybrid_search
    from retrieval import search as vector_search

    if retrieval_cfg["mode"] == "hybrid_rrf":
        return hybrid_search(
            question,
            n_results=retrieval_cfg["n_results"],
            bm25_candidates=retrieval_cfg["bm25_candidates"],
            vector_candidates=retrieval_cfg["vector_candidates"],
        )
    return vector_search(
        question,
        strategy=retrieval_cfg["strategy"],
        n_results=retrieval_cfg["n_results"],
    )


_WAIT_RE = re.compile(r"try again in\s+(?:(\d+)m)?([\d.]+)s", re.IGNORECASE)


def _suggested_wait(message: str) -> float | None:
    """Seconds the provider asked us to wait, parsed out of a 429 body."""
    m = _WAIT_RE.search(message)
    if not m:
        return None
    minutes = float(m.group(1) or 0)
    seconds = float(m.group(2))
    return minutes * 60 + seconds + 2  # small cushion


def call_model(
    system_prompt: str,
    user_message: str,
    model_params: dict,
    max_wait_s: float = 300.0,
) -> dict:
    """Returns raw text plus provider metadata. Retries transient 429/5xx."""
    from generation import get_client, get_model

    client = get_client()
    model_name = model_params.get("name") or get_model()
    kwargs = {
        "model": model_name,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ],
        "temperature": model_params["temperature"],
        "max_tokens": model_params["max_tokens"],
        "top_p": model_params["top_p"],
    }
    if model_params.get("seed") is not None:
        kwargs["seed"] = model_params["seed"]

    last_exc = None
    for attempt in range(4):
        try:
            resp = client.chat.completions.create(**kwargs)
            choice = resp.choices[0]
            usage = getattr(resp, "usage", None)
            return {
                "raw": (choice.message.content or "").strip(),
                "finish_reason": choice.finish_reason,
                "usage": {
                    "prompt_tokens": getattr(usage, "prompt_tokens", None),
                    "completion_tokens": getattr(usage, "completion_tokens", None),
                } if usage else None,
                "system_fingerprint": getattr(resp, "system_fingerprint", None),
                "error": None,
            }
        except Exception as exc:
            last_exc = exc
            msg = str(exc)
            transient = any(s in msg for s in ("429", "500", "502", "503", "timeout", "Timeout"))
            if attempt < 3 and transient:
                # Groq states the wait explicitly on a quota 429
                # ("Please try again in 3m56.736s"). Honour it rather than
                # burning the remaining attempts on a fixed short backoff.
                time.sleep(min(_suggested_wait(msg) or 3 * (attempt + 1), max_wait_s))
                continue
            break

    return {
        "raw": "",
        "finish_reason": "error",
        "usage": None,
        "system_fingerprint": None,
        "error": {"type": type(last_exc).__name__, "message": str(last_exc)[:400]},
    }


def answer_claim_question(
    claim: dict,
    writer: TraceWriter | None = None,
    prompt_version: str = prompts.CURRENT_VERSION,
    retrieval_cfg: dict | None = None,
    model_params: dict | None = None,
    verbose: bool = False,
) -> TraceRecord:
    """
    ``claim`` keys: question, loss_summary, claimant_name, claim_number,
    and optionally channel / tags.
    """
    from generation import format_context, get_model

    retrieval_cfg = {**DEFAULT_RETRIEVAL, **(retrieval_cfg or {})}
    model_params = {**DEFAULT_MODEL_PARAMS, **(model_params or {})}
    writer = writer or TraceWriter()

    question = claim["question"]
    loss_summary = claim.get("loss_summary", "")
    claimant_name = claim.get("claimant_name", "")
    claim_number = claim.get("claim_number", "")

    t0 = time.perf_counter()
    hits = retrieve(question, retrieval_cfg)
    t1 = time.perf_counter()

    # The claim reference sent to the model is already pseudonymised: the raw
    # claim number never leaves the process, not even to the provider.
    from redaction import redact_text
    claim_ref_for_prompt, _ = redact_text(claim_number, [claimant_name])
    loss_for_prompt, _ = redact_text(loss_summary, [claimant_name])
    question_for_prompt, _ = redact_text(question, [claimant_name])

    user_message = build_user_message(
        prompt_version,
        format_context(hits),
        claim_ref_for_prompt,
        loss_for_prompt,
        question_for_prompt,
    )
    result = call_model(
        prompts.get_system_prompt(prompt_version), user_message, model_params
    )
    t2 = time.perf_counter()

    record = TraceRecord.build(
        question=question,
        loss_summary=loss_summary,
        claimant_name=claimant_name,
        claim_number=claim_number,
        prompt_version=prompt_version,
        retrieval_meta={k: v for k, v in retrieval_cfg.items()},
        hits=hits,
        model_meta={
            "provider": "groq",
            "name": model_params.get("name") or get_model(),
            "temperature": model_params["temperature"],
            "max_tokens": model_params["max_tokens"],
            "top_p": model_params["top_p"],
            "seed": model_params.get("seed"),
            "finish_reason": result["finish_reason"],
            "usage": result["usage"],
            "system_fingerprint": result["system_fingerprint"],
        },
        raw_output=result["raw"],
        timing={
            "retrieval_ms": round((t1 - t0) * 1000, 1),
            "generation_ms": round((t2 - t1) * 1000, 1),
            "total_ms": round((t2 - t0) * 1000, 1),
        },
        error=result["error"],
        tags=claim.get("tags", []),
        channel=claim.get("channel", "adjuster_console"),
    )
    writer.write(record, known_names=[claimant_name] if claimant_name else None)

    if verbose:
        print(f"[{record.trace_id}] {record.input['question'][:80]}")
        print(f"    -> {record.output['raw'][:160]}\n")

    return record
