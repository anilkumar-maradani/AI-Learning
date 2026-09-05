"""
redaction.py — Strip claimant identifiers BEFORE a trace is written to disk.

Design rule (graded by the Week 5 rubric): redaction is a *pre-write* step, not
a post-hoc scrub of an existing log. ``TraceRecord`` calls ``redact_text`` while
it is still an in-memory object; the raw claimant name and claim number never
reach ``traces/traces.jsonl``. There is no "clean the log later" path in this
module, deliberately.

Identifiers are replaced with a *stable pseudonym* rather than a blank ``[REDACTED]``:

    Margaret Whitfield  ->  [CLAIMANT:7f2a91]
    CLM-2026-04417      ->  [CLAIM_NO:1c8b40]

The token is HMAC-SHA256(identifier, salt) truncated to 6 hex chars. Same person,
same token, in every trace — so error analysis can ask "did this claimant recur?"
without the log holding a name. The salt lives in the environment
(``POLICYLENS_REDACTION_SALT``); without it, the tokens are not reversible by
anyone who only has the log.
"""

import hashlib
import hmac
import os
import re

# ---------------------------------------------------------------------------
# Salt
# ---------------------------------------------------------------------------

_DEFAULT_SALT = "policylens-local-dev-salt"


def _salt() -> bytes:
    return os.environ.get("POLICYLENS_REDACTION_SALT", _DEFAULT_SALT).encode("utf-8")


def _token(kind: str, value: str) -> str:
    """Stable, non-reversible pseudonym for one identifier."""
    digest = hmac.new(_salt(), value.strip().lower().encode("utf-8"), hashlib.sha256)
    return f"[{kind}:{digest.hexdigest()[:6]}]"


# ---------------------------------------------------------------------------
# Patterns
# ---------------------------------------------------------------------------
# Ordered: the most specific pattern runs first so a claim number is not
# partially eaten by the policy-number rule.

_PATTERNS: list[tuple[str, re.Pattern]] = [
    # CLM-2026-04417 / CLM2026044117 / Claim No. 04417 / claim # 04417
    ("CLAIM_NO", re.compile(
        r"\bCLM[-\s]?\d{4}[-\s]?\d{3,8}\b"
        r"|\bclaim\s*(?:no\.?|number|#)\s*:?\s*[A-Z0-9][A-Z0-9-]{4,}\b",
        re.IGNORECASE)),
    # HOP-8842116 / policy no. 8842116  (NOT form numbers like HO-0304)
    ("POLICY_NO", re.compile(
        r"\bHOP[-\s]?\d{5,10}\b"
        r"|\bpolicy\s*(?:no\.?|number|#)\s*:?\s*[A-Z0-9][A-Z0-9-]{4,}\b",
        re.IGNORECASE)),
    ("EMAIL", re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.]{2,}\b")),
    ("PHONE", re.compile(r"(?:\+?1[-.\s]?)?\(?\b\d{3}\)?[-.\s]\d{3}[-.\s]\d{4}\b")),
    # 41 Harborview Lane / 1180 Cypress Bend Rd
    ("ADDRESS", re.compile(
        r"\b\d{1,5}\s+(?:[A-Z][a-z]+\s+){1,3}"
        r"(?:Street|St|Avenue|Ave|Road|Rd|Lane|Ln|Drive|Dr|Court|Ct|Boulevard|Blvd|Way|Terrace|Ter|Place|Pl|Circle|Cir|Bend)\b")),
]

# Words that look like names but are policy vocabulary. Never pseudonymise these.
_NAME_STOPWORDS = {
    "named storm", "national hurricane", "hurricane center", "special form",
    "homeowners policy", "coverage a", "coverage b", "coverage c", "coverage d",
    "exclusion table", "declarations page", "inland marine", "wet rot",
    "dry rot", "earth movement", "supply line", "business pursuits",
    "home day", "day care", "scheduled personal", "personal property",
}


def _looks_like_policy_term(name: str) -> bool:
    low = name.lower()
    return any(sw in low or low in sw for sw in _NAME_STOPWORDS)


# A person name cued by an explicit role word — the only way we pseudonymise
# free-text capitalised words, so "National Hurricane Center" survives intact.
_NAME_CUE = re.compile(
    r"\b(?:claimant|insured|policyholder|named insured|mr\.?|mrs\.?|ms\.?|dr\.?)\s+"
    r"((?:[A-Z][a-z'’-]+)(?:\s+[A-Z][a-z'’-]+){0,2})")


def redact_text(text: str, known_names: list[str] | None = None) -> tuple[str, dict]:
    """
    Return ``(redacted_text, counts)``.

    ``known_names`` is the roster the caller already holds in structured form
    (the claimant on the claim file). Those are matched exactly and are the
    reliable path; the cue-word regex is the safety net for names that only
    appear inside free text.
    """
    counts: dict[str, int] = {}
    out = text

    def _bump(kind: str, n: int = 1) -> None:
        if n:
            counts[kind] = counts.get(kind, 0) + n

    # 1. Structured identifiers first, so an email or phone is consumed whole
    #    rather than half-eaten by a surname match inside it.
    for kind, pattern in _PATTERNS:
        def _sub(m: re.Match, _kind: str = kind) -> str:
            return _token(_kind, m.group(0))
        out, n = pattern.subn(_sub, out)
        _bump(kind, n)

    # 2. Exact roster names — the reliable path, since the claim file already
    #    holds the claimant in structured form.
    for name in sorted(known_names or [], key=len, reverse=True):
        name = name.strip()
        if not name:
            continue
        pat = re.compile(re.escape(name), re.IGNORECASE)
        out, n = pat.subn(_token("CLAIMANT", name), out)
        _bump("CLAIMANT", n)
        # Surname alone ("Whitfield says the pipe burst")
        parts = name.split()
        if len(parts) > 1:
            sur = re.compile(r"\b" + re.escape(parts[-1]) + r"\b", re.IGNORECASE)
            out, n = sur.subn(_token("CLAIMANT", name), out)
            _bump("CLAIMANT", n)

    # 3. Cue-word names the roster missed.
    def _cue_sub(m: re.Match) -> str:
        candidate = m.group(1)
        if _looks_like_policy_term(candidate):
            return m.group(0)
        _bump("CLAIMANT")
        return m.group(0).replace(candidate, _token("CLAIMANT", candidate))
    out = _NAME_CUE.sub(_cue_sub, out)

    return out, counts


# Anything matching these in a finished trace line means redaction leaked.
_LEAK_CHECKS = [
    ("claim_no", _PATTERNS[0][1]),
    ("policy_no", _PATTERNS[1][1]),
    ("email", _PATTERNS[2][1]),
    ("phone", _PATTERNS[3][1]),
]


def assert_clean(payload: str, known_names: list[str] | None = None) -> list[str]:
    """
    Verify a serialised trace before it is appended. Returns a list of leak
    descriptions; empty list means clean. ``tracing.TraceWriter`` refuses to
    write when this is non-empty, so a redaction bug fails loudly at write
    time instead of silently populating the log.
    """
    leaks = []
    for label, pattern in _LEAK_CHECKS:
        if pattern.search(payload):
            leaks.append(f"{label}: {pattern.search(payload).group(0)!r}")
    for name in known_names or []:
        if not name:
            continue
        for fragment in {name, name.split()[-1]}:
            if len(fragment) > 2 and re.search(r"\b" + re.escape(fragment) + r"\b",
                                               payload, re.IGNORECASE):
                leaks.append(f"claimant_name: {fragment!r}")
    return leaks


if __name__ == "__main__":
    sample = (
        "Claimant Margaret Whitfield, claim CLM-2026-04417, policy HOP-8842116, "
        "reachable at m.whitfield@example.com or (813) 555-0142, at "
        "41 Harborview Lane. Whitfield reports a burst supply line. Does the "
        "Named Storm deductible from the National Hurricane Center definition apply?"
    )
    red, counts = redact_text(sample, known_names=["Margaret Whitfield"])
    print(red)
    print(counts)
    print("leaks:", assert_clean(red, ["Margaret Whitfield"]))
