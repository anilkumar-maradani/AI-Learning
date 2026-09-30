"""
summariser.py — Writes the claim summary that goes on a closed claim file.

Input is the claim file (policy, estimate, dated adjuster notes ending in the
decision). The claimant's name is never sent; the claim number is, because the
summary has to carry it. Runs on the small model: this is a high-volume,
low-stakes-per-call job, which is exactly why its output needs checking.
"""

import hashlib

from claim_store import render_claim_file
from llm import SMALL_MODEL, chat

SUMMARY_PROMPT_VERSION = "summary-v1"

SUMMARY_SYSTEM = """You write the closing summary for a homeowners claim file at \
Northgate Mutual. Claims operations reads only your summary, so it must carry \
the adjuster's final decision exactly.

Write at most 120 words of plain text covering:
- the claim number and the date of loss
- what happened
- the coverage decision and, for anything denied, the exclusion code relied on
- the deductible (excess) that applies, as a dollar amount
- the amount payable

Use only what is in the claim file. Do not add policy interpretation of your own."""


def build_user_message(claim: dict) -> str:
    return f"CLAIM FILE\n{render_claim_file(claim)}\n\nWrite the closing summary."


def input_sha256(claim: dict) -> str:
    """Hash of the exact model input; lets a regression case prove it is verbatim."""
    payload = SUMMARY_SYSTEM + "\x00" + build_user_message(claim)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def summarise(claim: dict) -> dict:
    res = chat(
        [
            {"role": "system", "content": SUMMARY_SYSTEM},
            {"role": "user", "content": build_user_message(claim)},
        ],
        model=SMALL_MODEL,
        max_tokens=1500,
    )
    return {
        "summary": res["content"],
        "model": SMALL_MODEL,
        "prompt_version": SUMMARY_PROMPT_VERSION,
        "input_sha256": input_sha256(claim),
        "usage": res["usage"],
        "api_s": res["api_s"],
        "error": res["error"],
    }
