"""
trajectory.py — Score the PATH a triage run took, not just its answer.

A path is a list of tokens:
    claim             get_claim
    policy:NG-1105    a search_policy call that retrieved wording from NG-1105
    payout            compute_payout

Each case declares a spec; accepted_paths() expands it into an explicit SET of
valid sequences (every order of the required lookups, with or without the
optional ones). A run's path passes if it matches one of them exactly, and
every argument it passed was real.
"""

import itertools
import json
import os
import re
from functools import lru_cache

from claim_store import get_claim

POLICY_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "policy")
SUBLIMITS = {5000.0, 7500.0, 1500.0, 2500.0, 500.0}


@lru_cache(maxsize=1)
def corpus_ids() -> dict:
    forms, excl, clauses = set(), set(), set()
    for name in os.listdir(POLICY_DIR):
        text = open(os.path.join(POLICY_DIR, name), encoding="utf-8").read()
        forms.add(name.split("_")[0])
        excl |= set(re.findall(r"\|\s*(E-\d{2})\s*\|", text))
        clauses |= set(re.findall(r"CLAUSE\s+([A-Z]{2,4}-\d+)", text))
    labels = {"EXCLUSION-TABLE", "PREAMBLE"} | {f"SECTION-{n}" for n in ("I", "II", "III", "IV")}
    return {"forms": forms, "exclusions": excl, "clauses": clauses, "labels": labels}


def accepted_paths(spec: dict) -> list[list[str]]:
    """spec: required_forms, optional_forms, payout in {required, optional, forbidden}."""
    req, opt = spec["required_forms"], spec.get("optional_forms", [])
    tails = {"required": [["payout"]], "optional": [["payout"], []], "forbidden": [[]]}[spec["payout"]]
    paths = []
    for k in range(len(opt) + 1):
        for extra in itertools.combinations(opt, k):
            for perm in itertools.permutations(list(req) + list(extra)):
                for tail in tails:
                    paths.append(["claim"] + [f"policy:{f}" for f in perm] + tail)
    return paths


@lru_cache(maxsize=256)
def _forms_retrieved(args_json: str) -> frozenset:
    from tools import search_policy
    args = json.loads(args_json)
    if args.get("form_number"):
        return frozenset([args["form_number"]])
    res = search_policy(**{k: v for k, v in args.items() if k in ("query", "form_number")})
    return frozenset(p["form_number"] for p in res.get("passages", []))


def step_tokens(step: dict) -> set[str]:
    """The tokens one recorded step can stand for (search results may span forms)."""
    if step["tool"] == "get_claim":
        return {"claim"}
    if step["tool"] == "compute_payout":
        return {"payout"}
    if step["tool"] == "search_policy":
        return {f"policy:{f}" for f in _forms_retrieved(json.dumps(step["args"], sort_keys=True))}
    return {"error"}


def match_path(steps: list[dict], accepted: list[list[str]]) -> list[str] | None:
    toks = [step_tokens(s) for s in steps]
    for path in accepted:
        if len(path) == len(toks) and all(p in t for p, t in zip(path, toks)):
            return path
    return None


def check_args(run: dict, case: dict) -> list[dict]:
    """One entry per checked argument: {tool, arg, value, valid, why}."""
    claim = get_claim(case["claim_number"])
    ids = corpus_ids()
    lines = [l["amount"] for l in claim.get("estimate_lines") or []]
    subset_sums = {float(sum(c)) for k in range(len(lines) + 1)
                   for c in itertools.combinations(lines, k)}
    out = []

    def rec(tool, arg, value, valid, why=""):
        out.append({"tool": tool, "arg": arg, "value": value, "valid": valid, "why": why})

    for s in run["steps"]:
        a = s.get("args") or {}
        if "claim_number" in a:
            rec(s["tool"], "claim_number", a["claim_number"], a["claim_number"] == case["claim_number"],
                "" if a["claim_number"] == case["claim_number"] else "not this claim / not a real claim")
        if s["tool"] == "search_policy" and a.get("form_number"):
            f = a["form_number"]
            ok = f in claim["forms"]
            rec("search_policy", "form_number", f, ok,
                "" if ok else ("form does not exist" if f not in ids["forms"] else "form not on this policy"))
        if s["tool"] == "compute_payout":
            amt = float(a.get("covered_amount", -1))
            rec("compute_payout", "covered_amount", amt, amt in subset_sums,
                "" if amt in subset_sums else "not a sum of estimate lines")
            if a.get("sublimit") is not None:
                sl = float(a["sublimit"])
                rec("compute_payout", "sublimit", sl, sl in SUBLIMITS,
                    "" if sl in SUBLIMITS else "no such sublimit in the forms")
            if a.get("deductible_basis") == "hurricane":
                ok = "NG-1102" in claim["forms"]
                rec("compute_payout", "deductible_basis", "hurricane", ok,
                    "" if ok else "no hurricane form on this policy")
    # Final-answer references: "real or fluent fiction?" A reference is real if it
    # names an exclusion, a clause or a section label that exists in the corpus.
    ans = run.get("answer") or {}
    real = ids["exclusions"] | ids["clauses"] | ids["labels"]
    for field in ("exclusion_ids", "clauses"):
        for ref in ans.get(field) or []:
            r = str(ref).replace("‑", "-").strip()
            r = re.sub(r"^NG-\d{4}\s*[:/ ]\s*", "", r)  # "NG-1103:CLAUSE-MR-1"
            r = re.sub(r"^CLAUSE[-\s]+", "", r, flags=re.I)
            rec("final_answer", field, r, r in real,
                "" if r in real else "does not exist in the corpus")
    return out


def failure_modes(run: dict, case: dict, spec: dict, matched: list[str] | None,
                  arg_checks: list[dict]) -> list[str]:
    """Week-8 zoo labels for one run. A run can show several."""
    modes = []
    toks = [step_tokens(s) for s in run["steps"]]
    seen = set().union(*toks) if toks else set()
    if run["stop_reason"] != "final_answer":
        modes.append("stopped_without_answer")
    if any(f"policy:{f}" not in seen for f in spec["required_forms"]):
        modes.append("skipped_required_lookup")
    if spec["payout"] == "forbidden" and "payout" in seen:
        modes.append("payout_without_facts")
    if spec["payout"] != "forbidden" and "payout" in seen:
        first_pay = next(i for i, t in enumerate(toks) if "payout" in t)
        before = set().union(*toks[:first_pay]) if first_pay else set()
        if any(f"policy:{f}" not in before for f in spec["required_forms"]):
            modes.append("payout_before_lookup")
    calls = [(s["tool"], json.dumps(s.get("args"), sort_keys=True)) for s in run["steps"]]
    if len(calls) != len(set(calls)):
        modes.append("repeated_identical_call")
    if matched is None and not modes:
        forms_seen, revisit = set(), False
        for t in toks:
            pol = {x for x in t if x.startswith("policy:")}
            if pol and pol <= forms_seen:
                revisit = True
            forms_seen |= pol
        modes.append("redundant_lookup" if revisit else "unneeded_detour")
    if any(not c["valid"] for c in arg_checks):
        modes.append("invalid_argument")
    return modes
