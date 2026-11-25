"""
coverage: PolicyLens' Week 12 MCP server. Policy lookup, coverage in force on
the loss date, and endorsement wording scoped by product and date.

  lookup_policy            policy record (product, terms, forms) by claim or policy number
  check_coverage_in_force  was cover in force on the loss date; deductible, Coverage A
                           limit, and (v2) the wording edition in force per attached form
  search_policy_wording    wording of the edition in force on the loss date (v2)

Nothing it returns carries a claimant name, address or injury: the policy
register holds none, and wording is wording. Every tools/call is logged, redacted
on write, with the caller's trace id from params._meta, to POLICYLENS_CALL_LOG
(default traces/w12/coverage_calls.jsonl).

Environment (from mcp_config.w12.json; an unset ${VAR} arrives as ""):
  POLICYLENS_WORDING_VERSION  v2 (default): the loss date is a filter the code enforces.
                              v1: the date-blind BEFORE, kept so the fix can be measured:
                              whole-form reads return the newest edition, searches rank
                              every edition and the date is only a hint in the query.
  POLICYLENS_CALL_LOG         where the per-call log goes.
The claims_system entry in the same config needs CLAIMS_DATA_DIR set by the
host to the triage snapshot (claim_store.write_triage_snapshot), or that
server reads nothing.

Run directly only to debug; normally the host starts it from mcp_config.w12.json:
    python mcp_servers/coverage/server.py      (JSON-RPC on stdin/stdout)
"""

import os
import re
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "src"))

from mcp_server import Server, ToolError  # noqa: E402

VERSION = (os.environ.get("POLICYLENS_WORDING_VERSION") or "v2").strip().lower()
if VERSION not in ("v1", "v2"):
    VERSION = "v2"
CALL_LOG = os.environ.get("POLICYLENS_CALL_LOG") or os.path.join(ROOT, "traces", "w12", "coverage_calls.jsonl")

server = Server("northgate-coverage", "1.0.0", call_log=CALL_LOG)

FORM_RE = re.compile(r"^NG-\d{4}$")


def _check(out: dict) -> dict:
    if out.get("error"):
        raise ToolError(out["error"])
    return out


@server.tool({
    "type": "object",
    "properties": {
        "claim_number": {"type": "string", "description": "e.g. CLM-2025-30001"},
        "policy_number": {"type": "string", "description": "e.g. HOP-6610301"},
    },
})
def lookup_policy(claim_number: str | None = None, policy_number: str | None = None) -> dict:
    """
    The policy behind a claim (give claim_number OR policy_number): product, plan
    and every term with its dates, status and forms. Not an in-force check, no
    wording. "not found" means the number is wrong; do not guess.
    """
    if not (claim_number or policy_number):
        raise ToolError("give claim_number or policy_number")
    from policy_register import lookup_policy as _lookup
    return _check(_lookup(policy_number=policy_number, claim_number=claim_number))


@server.tool({
    "type": "object",
    "properties": {
        "policy_number": {"type": "string", "description": "HOP-NNNNNNN"},
        "loss_date": {"type": "string", "description": "date of loss, YYYY-MM-DD"},
    },
    "required": ["policy_number", "loss_date"],
})
def check_coverage_in_force(policy_number: str, loss_date: str) -> dict:
    """
    Was the policy in force on the loss date? Returns in_force with the reason,
    the term, forms, all-peril deductible, Coverage A limit, and the edition of
    each form in force ON THE LOSS DATE. Does not decide coverage.
    """
    from policy_register import coverage_in_force
    return _check(coverage_in_force(policy_number, loss_date, with_editions=(VERSION == "v2")))


def _passage(meta: dict, text: str, chunk_id: str) -> dict:
    from editions import get_edition, window
    p = {"chunk_id": chunk_id, "form_number": meta.get("form_number"),
         "edition": meta.get("edition_date"), "clause_id": meta.get("clause_id"),
         "text": text.split("\n", 1)[-1] if text.startswith("[") else text}
    return p   # w12-5: no per-passage window (the in-force check reports it once)


@server.tool({
    "type": "object",
    "properties": {
        "query": {"type": "string", "description": "the peril or rule to look up"},
        "loss_date": {"type": "string", "description": "date of loss, YYYY-MM-DD"},
        "form_number": {"type": "string", "description": "optional, NG-NNNN: returns that form's complete wording"},
        "product": {"type": "string", "description": "policy line; default homeowners"},
    },
    "required": ["query", "loss_date"],
})
def search_policy_wording(query: str, loss_date: str | None = None, form_number: str | None = None,
                          product: str = "homeowners") -> dict:
    """
    Endorsement wording IN FORCE ON loss_date. form_number "NG-1101" or several
    comma-separated ("NG-1101,NG-1103") returns each form's complete wording, every
    clause and exclusion row; without it, the best 4 passages for the query. Cite
    the chunk_id and clause. "no edition ... in force" -> refer the claim.
    """
    from editions import as_date, edition_in_force, editions, latest_edition, products
    from hybrid_retrieval import _get_bm25_index, hybrid_search
    # Fresh-eyes fix: a caller that leaves the date out used to get a Python
    # TypeError ("missing 1 required positional argument"). Wording depends on
    # the date, so there is no safe default; say so in words a caller can act on.
    if not loss_date:
        raise ToolError("loss_date is required (YYYY-MM-DD): the wording that applies depends on "
                        "the date of loss, because editions change. Pass the claim's date of loss.")
    try:
        as_date(loss_date)
    except ValueError:
        raise ToolError(f"'{loss_date}' is not a date: use YYYY-MM-DD")
    product = (product or "homeowners").strip().lower()
    if product not in products():
        raise ToolError(f"no {product} wording in this library: it holds homeowners endorsements only")
    if form_number:
        # Several forms in one call (one model lap per claim instead of one per form).
        forms = [f.strip().upper() for f in str(form_number).replace(";", ",").split(",") if f.strip()]
        passages = []
        for form in dict.fromkeys(forms):
            if not FORM_RE.match(form):
                raise ToolError(f"'{form}' is not a form number: form numbers look like NG-NNNN, e.g. NG-1101")
            if form not in editions():
                raise ToolError(f"form {form} not found: the library holds {', '.join(sorted(editions()))}")
            ed = edition_in_force(form, loss_date) if VERSION == "v2" else latest_edition(form)
            if ed is None:
                raise ToolError(f"no edition of {form} was in force on {loss_date}; refer the claim")
            chunks = sorted((c for c in _get_bm25_index().chunks
                             if c["metadata"].get("form_number") == form
                             and c["metadata"].get("edition_date") == ed["edition_date"]
                             and c["metadata"].get("clause_id") != "PREAMBLE"
                             # w12-5: a bare section heading carries no wording
                             and not (c["metadata"].get("clause_id", "").startswith("SECTION")
                                      and len(c["text"].strip().splitlines()) <= 2)),
                            key=lambda c: c["metadata"]["chunk_index"])
            passages += [_passage(c["metadata"], c["text"], c["chunk_id"]) for c in chunks]
    else:
        try:
            if VERSION == "v2":
                hits = hybrid_search(query, n_results=4, loss_date=loss_date, product=product)
            else:
                hits = hybrid_search(f"{query} (date of loss {loss_date})", n_results=4, product=product)
        except Exception as exc:  # noqa: BLE001
            raise ToolError(f"policy library unavailable ({type(exc).__name__}); a server fault, "
                            f"retrying will not help: refer the claim")
        passages = [_passage(h["metadata"], h["text"], h["chunk_id"]) for h in hits]
    return {"loss_date": loss_date,
            "rule": "edition in force on the loss date" if VERSION == "v2" else "best match",
            "passages": passages}


if __name__ == "__main__":
    server.run()
