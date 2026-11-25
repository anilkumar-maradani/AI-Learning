"""
referral.py: Week 12. The only way a triage ends: a referral to a human
adjuster. No coverage decision is ever stated.

The model supplies facts, citations (by the chunk_id it actually read and a
clause id), which deductible basis the wording points to, and any sublimit
clause. CODE supplies everything that must not be wrong:

  * each citation's edition, link, in-force window and the loss date it was
    resolved against (editions.citation)
  * the deductible amount and the Coverage A limit, from the policy register
    term returned by check_coverage_in_force, never from the model
  * the sublimit amount, which must appear in the cited clause's own text

validate() is the enforcement point. It is code, not a prompt: a referral that
uses decision language ("covered", "excluded", "denied", ...), cites wording it
never read, cites a clause that does not exist in that edition, or (v2) cites
an edition not in force on the loss date is rejected with a message written for
the model, which can then fix it.
"""

import re

from editions import amounts_in, citation, clause_ids, clause_text, get_edition

# The words a referral may not use in its own prose. "cover", "covers" and
# "exclusion" stay allowed: they describe wording, not a decision.
DECISION_RE = re.compile(
    r"\b(not\s+covered|uncovered|covered|excluded|denied|deny|declined|decline|approved|approve"
    r"|payable|we\s+will\s+pay|reimburse\w*)\b",
    re.IGNORECASE)

REFER_TOOL = {
    "type": "function",
    "function": {
        "name": "refer_to_adjuster",
        "description": (
            "Hand the claim to an adjuster; ends the task. Cite wording by chunk_id and clause "
            "id (WE-4, E-42); the system adds edition, loss date and link, and fills the "
            "deductible and limit. Rejected if it states a coverage decision."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "claim_number": {"type": "string"},
                "in_force": {"type": "boolean",
                             "description": "What check_coverage_in_force returned for the loss date."},
                # No maxItems / enum here: Groq validates tool calls against the schema and
                # rejects the WHOLE generation on a violation (gpt-oss-20b sent 4 questions
                # against maxItems 3: three 400s, run lost). Limits are enforced in validate(),
                # which truncates or returns a message the model can act on.
                "facts": {"type": "array", "items": {"type": "string"},
                          "description": "Up to 5 short facts from the claim and notes that the wording turns on."},
                "citations": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "chunk_id": {"type": "string"},
                            "clause_id": {"type": "string",
                                          "description": "The clause (e.g. WE-4) or the exclusion ROW code "
                                                         "(e.g. E-42); never EXCLUSION-TABLE or a section."},
                            "why": {"type": "string", "description": "Which fact makes this clause relevant."},
                        },
                        "required": ["chunk_id", "clause_id", "why"],
                    },
                },
                "deductible_basis": {"type": "string",
                                     "description": "One of: all_peril, hurricane, none_scheduled_article."},
                "sublimit": {
                    "type": "object",
                    "description": "Only if a sublimit clause applies; omit otherwise.",
                    "properties": {
                        "chunk_id": {"type": "string"},
                        "clause_id": {"type": "string"},
                        "amount": {"type": "number"},
                    },
                    "required": ["chunk_id", "clause_id", "amount"],
                },
                "questions_for_adjuster": {"type": "array", "items": {"type": "string"},
                                           "description": "Up to 3 questions only the adjuster can answer."},
            },
            "required": ["claim_number", "in_force", "facts", "citations", "deductible_basis"],
        },
    },
}


def _decision_words(texts: list[str]) -> list[str]:
    found = []
    for t in texts:
        for m in DECISION_RE.finditer(t or ""):
            w = m.group(0).lower()
            if w not in found:
                found.append(w)
    return found


def _as_list(v) -> list:
    if v is None:
        return []
    return v if isinstance(v, list) else [v]


def _cite(chunk_id: str, clause_id: str, ctx: dict) -> tuple[dict | None, str | None]:
    """(citation, error) for one (chunk_id, clause_id) the model named."""
    p = (ctx.get("retrieved") or {}).get(chunk_id)
    if p is None:
        return None, (f"citation {chunk_id!r} was not returned to you by search_policy_wording in this "
                      f"conversation; cite only chunk_ids you read")
    form, edition = p.get("form_number"), p.get("edition")
    c = citation(form, edition, clause_id, ctx["loss_date"])
    if not c["exists"] and not re.match(r"^(E-\d+|[A-Z]{2,4}-\d+)$", c["clause_id"]):
        ed = get_edition(form, edition)
        rows = [x for x in clause_ids(ed) if x.startswith("E-")] if ed else []
        return None, (f"{clause_id!r} is not a clause id: cite the clause (e.g. WE-1) or the exclusion "
                      f"row code inside {form} ed. {edition}, one of {rows}")
    if not c["exists"]:
        return None, (f"{c['clause_id']} does not exist in {form} ed. {edition}; "
                      f"cite a clause id that appears in that wording")
    if ctx.get("version", "w12-v2") != "w12-v1" and not c["in_force"]:
        return None, c["why_invalid"] + "; cite the edition in force on the loss date"
    return c, None


def validate(args: dict, ctx: dict) -> tuple[list[str], dict | None]:
    errors: list[str] = []
    facts = [str(f) for f in _as_list(args.get("facts"))][:5]
    cites_in = [c for c in _as_list(args.get("citations")) if isinstance(c, dict)]
    questions = [str(q) for q in _as_list(args.get("questions_for_adjuster"))][:3]

    texts = facts + [str(c.get("why", "")) for c in cites_in] + questions
    words = _decision_words(texts)
    if words:
        # Loop fix (evidence/loop_red_decision_language.txt): the model got the word but
        # not where it was, and no alternative, and failed three times. Quote the
        # offending fragments and offer the vocabulary. The bar itself is unchanged.
        frags = []
        for t in texts:
            for m in DECISION_RE.finditer(t or ""):
                s, e = max(0, m.start() - 35), min(len(t), m.end() + 25)
                frags.append("..." + t[s:e].strip() + "...")
        errors.append(f"decision language is not allowed ({', '.join(repr(w) for w in words)}) in "
                      f"facts, why or questions. Rewrite these fragments: {' | '.join(frags[:4])}. "
                      f"Instead of 'covered' write 'within the scope of <clause>'; instead of 'excluded' or "
                      f"'denied' write '<code> lists <peril>'; instead of 'payable' write 'amount for the "
                      f"adjuster to set'. The adjuster decides")

    check = ctx.get("in_force_check")
    if not check:
        errors.append("call check_coverage_in_force(policy_number, loss_date) before referring")
    elif bool(args.get("in_force")) != bool(check.get("in_force")):
        errors.append(f"in_force={args.get('in_force')} disagrees with check_coverage_in_force, "
                      f"which returned in_force={check.get('in_force')} ({check.get('reason')})")
    in_force = bool(check.get("in_force")) if check else bool(args.get("in_force"))

    citations = []
    for c in cites_in:
        cit, err = _cite(str(c.get("chunk_id", "")), str(c.get("clause_id", "")), ctx)
        if err:
            errors.append(err)
        else:
            citations.append({**cit, "chunk_id": c.get("chunk_id"), "why": str(c.get("why", ""))})
    if in_force and not cites_in:
        errors.append("cover was in force, so cite the wording the adjuster must read (chunk_id + clause_id)")

    sub = args.get("sublimit")
    sublimit = None
    if isinstance(sub, dict) and sub.get("chunk_id"):
        cit, err = _cite(str(sub.get("chunk_id")), str(sub.get("clause_id", "")), ctx)
        if err:
            errors.append("sublimit: " + err)
        else:
            ed = get_edition(cit["form_number"], cit["edition"])
            txt = clause_text(ed, cit["clause_id"]) or ""
            try:
                amt = float(sub.get("amount"))
            except (TypeError, ValueError):
                amt = None
            if amt is None or amt not in amounts_in(txt):
                errors.append(f"sublimit amount {sub.get('amount')!r} does not appear in {cit['label']}; "
                              f"that clause states {amounts_in(txt) or 'no amount'}")
            else:
                sublimit = {"amount": amt, "label": cit["label"], "link": cit["link"],
                            "form_number": cit["form_number"], "edition": cit["edition"],
                            "clause_id": cit["clause_id"], "edition_window": cit.get("edition_window")}

    basis = str(args.get("deductible_basis") or "all_peril").strip().lower().replace("-", "_")
    if basis not in ("all_peril", "hurricane", "none_scheduled_article"):
        errors.append(f"deductible_basis {args.get('deductible_basis')!r} is not one of all_peril, "
                      f"hurricane, none_scheduled_article")

    if errors:
        return errors, None

    ded_amt, limit = None, None
    if check and check.get("in_force"):
        limit = check.get("coverage_a_limit")
        ded_amt = {"all_peril": check.get("all_peril_deductible"),
                   "hurricane": round(0.02 * float(limit or 0), 2),
                   "none_scheduled_article": 0.0}.get(basis, check.get("all_peril_deductible"))
    referral = {
        "claim_number": ctx["claim_number"],
        "loss_date": ctx["loss_date"],
        "in_force": in_force,
        "in_force_reason": (check or {}).get("reason"),
        "facts": facts,
        "citations": citations,
        "deductible": {"amount": ded_amt, "basis": basis, "source": "policy register term"},
        "sublimit": sublimit,
        "policy_limit": {"amount": limit, "source": "Coverage A, policy register term"},
        "questions_for_adjuster": questions,
        "decision": "referred to adjuster",
        "fallback": False,
    }
    referral["text"] = render(referral)
    return [], referral


def _money(v) -> str:
    return "n/a" if v is None else f"${float(v):,.2f}"


def render(r: dict) -> str:
    lines = ["REFERRAL TO ADJUSTER — no coverage decision made",
             f"Claim: {r['claim_number']}",
             f"Loss date: {r['loss_date']}",
             f"Coverage in force on the loss date: {'yes' if r['in_force'] else 'NO'}"
             + (f" ({r['in_force_reason']})" if r.get("in_force_reason") else "")]
    if r.get("fallback"):
        lines.append(f"MANUAL TRIAGE NEEDED: {r.get('fallback_reason')}")
    if r.get("citations"):
        lines.append("Wording to read (edition in force, resolved for the loss date):")
        for c in r["citations"]:
            lines.append(f"  - {c['label']} — {c.get('link')} (in force {c.get('edition_window')}; "
                         f"resolved for loss date {c['loss_date']}) — {c.get('why', '')}")
    s = r.get("sublimit")
    lines += [
        f"Deductible: {_money(r['deductible']['amount'])} ({r['deductible']['basis']}, {r['deductible']['source']})",
        f"Sub-limit: {(_money(s['amount']) + ' — ' + s['label'] + ' — ' + str(s.get('link'))) if s else 'none cited'}",
        f"Policy limit (Coverage A): {_money(r['policy_limit']['amount'])}",
    ]
    if r.get("facts"):
        lines.append("Facts the wording turns on:")
        lines += [f"  - {f}" for f in r["facts"]]
    if r.get("questions_for_adjuster"):
        lines.append("Questions for the adjuster:")
        lines += [f"  - {q}" for q in r["questions_for_adjuster"]]
    return "\n".join(lines)


def fallback_referral(ctx: dict, reason: str) -> dict:
    """When the agent ends without an accepted referral, the claim still goes to a
    person, flagged for manual triage. Nothing the model wrote is shipped."""
    check = ctx.get("in_force_check") or {}
    r = {
        "claim_number": ctx["claim_number"],
        "loss_date": ctx["loss_date"],
        "in_force": bool(check.get("in_force")),
        "in_force_reason": check.get("reason") or "in-force check not completed",
        "facts": [],
        "citations": [],
        "deductible": {"amount": check.get("all_peril_deductible") if check.get("in_force") else None,
                       "basis": "all_peril", "source": "policy register term"},
        "sublimit": None,
        "policy_limit": {"amount": check.get("coverage_a_limit") if check.get("in_force") else None,
                         "source": "Coverage A, policy register term"},
        "questions_for_adjuster": [],
        "decision": "referred to adjuster",
        "fallback": True,
        "fallback_reason": reason,
    }
    r["text"] = render(r)
    return r
