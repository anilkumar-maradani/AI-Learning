"""
policy_docs — PolicyLens' own MCP server: search over the Northgate Mutual
endorsement library (data/policy, indexed by src/ingest.py).

  tool      search_policy                  model-invoked: read endorsement wording
  resource  policy://exclusion-schedule    app-attached: every exclusion row of
                                           every form, one line each

The exclusion schedule is a resource, not a tool, because the model should
already have it in front of it; it should never have to decide to go and
fetch it.

Run it directly only to debug; normally the host starts it from mcp_config.json:
    python mcp_servers/policy_docs/server.py      (speaks JSON-RPC on stdin/stdout)
"""

import glob
import os
import re
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "src"))

from mcp_server import Server, ToolError  # noqa: E402

server = Server("policy-docs", "0.9.0")

POLICY_DIR = os.path.join(ROOT, "data", "policy")
FORM_RE = re.compile(r"^NG-\d{4}$")


def _forms() -> dict[str, str]:
    """{form_number: title}, read from the form headers so the error message never goes stale."""
    out = {}
    for path in sorted(glob.glob(os.path.join(POLICY_DIR, "*.txt"))):
        with open(path, encoding="utf-8") as fh:
            head = dict(l.split(":", 1) for l in fh.read().splitlines()[:10] if ":" in l)
        out[head["Form Number"].strip()] = head["Title"].strip()
    return out


@server.tool({
    "type": "object",
    "properties": {
        "query": {"type": "string"},
        "form_number": {"type": "string"},
    },
    "required": ["query"],
})
def search_policy(query: str, form_number: str | None = None) -> dict:
    """
    Read Northgate Mutual endorsement wording: coverage clauses, exclusion-table
    rows, deductible and sublimit rules. Use it whenever an answer depends on what
    a form actually says; quote the clause ids (e.g. GM-3) and exclusion codes
    (e.g. E-83) it returns.

    form_number (optional) restricts the search to one form and then returns that
    form's COMPLETE wording, so one call per form is enough. Form numbers look
    like NG-NNNN. The library holds NG-1101 to NG-1106 only. Without form_number,
    returns the best-matching passages across every form for the query.

    It knows nothing about any particular claim and does not decide coverage.

    Errors are written for you to act on:
      "form NG-xxxx not found"  -> the number is wrong; the message lists every
                                   form in the library, retry with the right one
                                   or drop form_number.
      "is not a form number"    -> fix the format (NG-NNNN) and retry.
      "policy library unavailable" -> a server fault; do not retry, tell the
                                   adjuster the wording could not be read.
    """
    from tools import search_policy as _search
    if form_number is not None:
        form_number = form_number.strip().upper()
        library = _forms()
        if not FORM_RE.match(form_number):
            raise ToolError(
                f"'{form_number}' is not a form number: form numbers look like NG-NNNN, "
                f"e.g. NG-1105. Retry with the corrected number, or omit form_number to "
                f"search every form.")
        if form_number not in library:
            listing = "; ".join(f"{n} {t}" for n, t in library.items())
            raise ToolError(
                f"form {form_number} not found: the policy library holds only {listing}. "
                f"If the adjuster quoted {form_number}, it is probably a typo for one of these; "
                f"retry with the form whose title matches the question, or omit form_number "
                f"to search every form.")
    try:
        out = _search(query, form_number=form_number)
    except Exception as exc:
        raise ToolError(
            f"policy library unavailable ({type(exc).__name__}): the search index could not be "
            f"read. This is a server fault, not a bad argument; retrying will not help. Tell "
            f"the adjuster the policy wording could not be retrieved.")
    if out.get("error"):
        raise ToolError(out["error"])
    return out


_ROW_RE = re.compile(r"^\|\s*(E-\d+)?\s*\|\s*(.*?)\s*\|\s*(.*?)\s*\|\s*$")


@server.resource("policy://exclusion-schedule", "Exclusion schedule",
                 "Every exclusion code in every Northgate Mutual endorsement, one line each.")
def exclusion_schedule() -> str:
    lines = []
    for path in sorted(glob.glob(os.path.join(POLICY_DIR, "*.txt"))):
        form = os.path.basename(path).split("_")[0]
        rows: list[list[str]] = []
        for line in open(path, encoding="utf-8"):
            m = _ROW_RE.match(line.strip())
            if not m:
                continue
            code, peril, scope = m.groups()
            if code:
                rows.append([code, peril, scope])
            elif rows and scope and not set(scope) <= {"-"}:
                rows[-1][1] = (rows[-1][1] + " " + peril).strip()
                rows[-1][2] += " " + scope
        lines += [f"{form} {c}: {p} — {s}" for c, p, s in rows]
    return "\n".join(lines)


if __name__ == "__main__":
    server.run()
