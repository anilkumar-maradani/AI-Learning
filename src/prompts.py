"""
prompts.py — Versioned prompt registry.

A trace stores a prompt *version string*, not the prompt body. Replay resolves
the version back to the exact text through this registry, and checks the stored
SHA-256 to prove the text has not been edited since the trace was written. If
somebody edits a prompt in place without minting a new version, replay fails
loudly instead of silently comparing against different wording.

Rule: prompt bodies here are append-only. To change a prompt, add a new key.
"""

import hashlib

# ---------------------------------------------------------------------------
# claims-v1 — the prompt the claims assistant shipped with
# ---------------------------------------------------------------------------

_CLAIMS_V1 = """You are PolicyLens, a homeowners claims assistant used by claim \
adjusters. You answer coverage questions strictly from the endorsement excerpts \
supplied in the context block.

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
7. State a coverage position (COVERED / NOT COVERED / DEPENDS) as the first line
   of your answer when the question asks whether something is covered.

Claimant identifiers arrive already pseudonymised as tokens like
[CLAIMANT:ab12cd]. Treat such a token as an opaque reference to one person.
Never attempt to guess the real name behind it.
"""

_USER_TEMPLATE_V1 = """CONTEXT FROM INDEXED ENDORSEMENTS:

{context}

CLAIM FILE: {claim_ref}
LOSS SUMMARY: {loss_summary}

QUESTION: {question}

Answer using ONLY the context above. Cite each claim with \
[SOURCE: chunk_id | form_number | clause_id]. If the answer is not in the \
context, issue the REFUSAL message exactly."""


SYSTEM_PROMPTS: dict[str, str] = {
    "claims-v1": _CLAIMS_V1,
}

USER_TEMPLATES: dict[str, str] = {
    "claims-v1": _USER_TEMPLATE_V1,
}

CURRENT_VERSION = "claims-v1"


def sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def get_system_prompt(version: str) -> str:
    if version not in SYSTEM_PROMPTS:
        raise KeyError(
            f"Unknown prompt version {version!r}. Known: {sorted(SYSTEM_PROMPTS)}. "
            "A trace referencing a version that is no longer in the registry "
            "cannot be replayed."
        )
    return SYSTEM_PROMPTS[version]


def get_user_template(version: str) -> str:
    if version not in USER_TEMPLATES:
        raise KeyError(f"Unknown prompt version {version!r}.")
    return USER_TEMPLATES[version]


def prompt_fingerprint(version: str) -> dict:
    """The pair of hashes a trace stores so replay can detect prompt drift."""
    return {
        "version": version,
        "system_sha256": sha256(get_system_prompt(version)),
        "user_template_sha256": sha256(get_user_template(version)),
    }


if __name__ == "__main__":
    import json
    print(json.dumps(prompt_fingerprint(CURRENT_VERSION), indent=2))
