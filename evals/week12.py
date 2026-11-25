#!/usr/bin/env python3
"""
Week 12: the eval suite for the integrated system.

Retrieval and register (no model calls):
    python evals/week12.py            # retrieval + hitrate + inforce, in order
    python evals/week12.py retrieval  # the 5 edition-boundary cases (+1 control): red before, green after
    python evals/week12.py hitrate    # what the filter cost on cases that do NOT straddle a boundary
    python evals/week12.py inforce    # coverage-in-force against the loss date, all 48 claims

before = hybrid_search with no date filter (what ranks best wins: the brief's bug)
after  = hybrid_search(loss_date=...): the filter src/hybrid_retrieval.chunk_filter
         enforces on both retrieval legs before ranking

The integrated agent (25 cases in evals/cases/week12_cases.jsonl):
    python evals/week12.py run --version w12-v2 --label after [--ids W12-B1,W12-B2] [--model M]
    python evals/week12.py score --label after         # assertions, all code, before any judge
    python evals/week12.py trajectory --label after    # tool-choice accuracy, outcome-vs-trajectory gap
    python evals/week12.py label-sheet --label after   # blind sheet for hand labels (labels first)
    python evals/week12.py judge --label after         # one binary criterion; refuses without labels
    python evals/week12.py agreement --label after     # judge vs hand labels
    python evals/week12.py report --label after [--before before]

`run` is resumable: cases already in reports/week12/runs_<label>.jsonl are
skipped, so a run stopped by the provider's daily token cap continues where it
stopped when re-run.
"""

import json
import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(ROOT, "src"))

from console import enable_utf8  # noqa: E402

enable_utf8()

from editions import edition_in_force, normalise_clause_id  # noqa: E402

# The clause each W12 claim turns on, from the adjuster's decision note
# (data/claims/w12_claims.jsonl). straddle = the loss falls in the OLD edition's
# window while a newer edition exists that a date-blind search can rank first.
CASES = [
    {"id": "W12-B1", "claim": "CLM-2025-30001", "form": "NG-1101", "clause": "WE-4", "straddle": True,
     "why": "Aug 2025 runoff loss: 07-23 WE-4 gives runoff cover; 01-26 E-42 excludes runoff"},
    {"id": "W12-B2", "claim": "CLM-2025-30002", "form": "NG-1101", "clause": "WE-4", "straddle": True,
     "why": "loss on 2025-12-31, the day before NG-1101 ed. 01-26 took effect"},
    {"id": "W12-B4", "claim": "CLM-2026-30004", "form": "NG-1103", "clause": "MR-2", "straddle": True,
     "why": "mold sublimit: $5,000 in 07-23 (in force to 2026-01-31) vs $7,500 in 02-26"},
    {"id": "W12-B5", "claim": "CLM-2026-30005", "form": "NG-1105", "clause": "GM-3", "straddle": True,
     "why": "GM-3 gives water damage back in 07-23; GM-3 in 03-26 says the opposite and E-83 excludes it"},
    {"id": "W12-B6", "claim": "CLM-2025-30006", "form": "NG-1101", "clause": "E-44", "straddle": True,
     "why": "unoccupied 45 days: E-44 needs >60 days in 07-23, >30 days in 01-26"},
    {"id": "W12-B3", "claim": "CLM-2026-30003", "form": "NG-1101", "clause": "E-42", "straddle": False,
     "why": "control: loss on 2026-01-01, the day the new wording took effect"},
]


def _claims() -> dict:
    from claim_store import load_claims
    return load_claims()


def fixed_query(claim: dict) -> str:
    """The Week 11 workflow's one fixed query: FNOL + every note except the decision."""
    notes = " ".join(n["text"] for n in claim["adjuster_notes"] if not n["text"].startswith("Decision:"))
    return (claim["fnol_description"] + " " + notes)[:1500]


def wrong_editions(hits: list[dict], loss_date: str) -> list[str]:
    out = []
    for h in hits:
        m = h["metadata"]
        ed = edition_in_force(m["form_number"], loss_date)
        if ed is None or ed["edition_date"] != m["edition_date"]:
            out.append(f"{m['form_number']} ed. {m['edition_date']} {m['clause_id']}")
    return out


def key_clause_hit(hits: list[dict], case: dict, loss_date: str) -> bool:
    """The deciding clause, from the edition in force, is in the top 3."""
    ed = edition_in_force(case["form"], loss_date)
    for h in hits:
        m = h["metadata"]
        if m["form_number"] == case["form"] and ed and m["edition_date"] == ed["edition_date"]:
            text = h["text"].upper()
            cid = case["clause"]
            if f"CLAUSE {cid}" in text or f"| {cid} |" in text:
                return True
    return False


def cmd_retrieval(_args=None) -> dict:
    from hybrid_retrieval import hybrid_search
    claims = _claims()
    print("\n## Edition-boundary cases: top-3 retrieval, before (no date filter) vs after (filter)\n")
    print("| Case | Claim | Loss date | Deciding clause | Wrong-edition passages in top 3: before | after | "
          "Deciding clause (right edition) in top 3: before | after | Verdict |")
    print("|---|---|---|---|---|---|---|---|---|")
    res = []
    for case in CASES:
        c = claims[case["claim"]]
        q, d = fixed_query(c), c["date_of_loss"]
        before = hybrid_search(q, n_results=3)
        after = hybrid_search(q, n_results=3, loss_date=d)
        wb, wa = wrong_editions(before, d), wrong_editions(after, d)
        hb, ha = key_clause_hit(before, case, d), key_clause_hit(after, case, d)
        red_before = bool(wb) or not hb
        green_after = not wa and ha
        verdict = ("RED -> GREEN" if red_before and green_after else
                   "GREEN -> GREEN" if not red_before and green_after else
                   "RED -> RED" if not green_after and red_before else "GREEN -> RED")
        res.append({**case, "loss_date": d, "wrong_before": wb, "wrong_after": wa,
                    "hit_before": hb, "hit_after": ha, "verdict": verdict})
        ed = edition_in_force(case["form"], d)
        print(f"| {case['id']} | {case['claim']} | {d} | {case['form']} ed. {ed['edition_date']} {case['clause']} | "
              f"{len(wb)} {('(' + '; '.join(wb) + ')') if wb else ''} | {len(wa)} | "
              f"{'yes' if hb else 'no'} | {'yes' if ha else 'no'} | {verdict} |")
    s = [r for r in res if r["straddle"]]
    print(f"\nStraddle cases red before: {sum(r['verdict'].startswith('RED') for r in s)}/{len(s)}; "
          f"green after: {sum(r['verdict'].endswith('GREEN') for r in s)}/{len(s)}")
    print(f"Cases with >=1 wrong-edition passage in top 3: before "
          f"{sum(bool(r['wrong_before']) for r in res)}/{len(res)}, after {sum(bool(r['wrong_after']) for r in res)}/{len(res)}")
    return {"cases": res}


def cmd_hitrate(_args=None) -> dict:
    """Week 4 golden set: 12 questions about the 2026 wording, none straddles a boundary.
    lenient hit = right form + expected fragment in a top-3 passage (Week 4's rule)
    strict hit  = the same, from the edition in force on the assumed loss date"""
    from hybrid_retrieval import hybrid_search
    loss_date = "2026-06-01"
    with open(os.path.join(ROOT, "golden_set.jsonl"), encoding="utf-8") as fh:
        golden = [json.loads(l) for l in fh if l.strip()]
    rows = []
    for g in golden:
        out = {"id": g["id"]}
        for arm, kw in (("before", {}), ("after", {"loss_date": loss_date})):
            hits = hybrid_search(g["question"], n_results=3, **kw)
            frag = g["expected_clause_fragment"].lower()
            lenient = [h for h in hits if h["metadata"]["form_number"] == g["expected_form"]
                       and frag in h["text"].lower()]
            ed = edition_in_force(g["expected_form"], loss_date)
            strict = [h for h in lenient if h["metadata"]["edition_date"] == ed["edition_date"]]
            out[arm] = {"lenient": bool(lenient), "strict": bool(strict),
                        "wrong_edition_in_top3": len(wrong_editions(hits, loss_date))}
        rows.append(out)
    n = len(rows)
    print(f"\n## Non-straddling cases: Week 4 golden set, n={n}, loss date assumed {loss_date}\n")
    print("| Metric | Before (no filter) | After (date filter) |")
    print("|---|---:|---:|")
    for k, lbl in (("lenient", "hit-rate@3, Week 4 rule (form + fragment, any edition)"),
                   ("strict", "hit-rate@3, right edition only")):
        b = sum(r["before"][k] for r in rows)
        a = sum(r["after"][k] for r in rows)
        print(f"| {lbl} | {b}/{n} = {b / n:.0%} | {a}/{n} = {a / n:.0%} |")
    wb = sum(r["before"]["wrong_edition_in_top3"] for r in rows)
    wa = sum(r["after"]["wrong_edition_in_top3"] for r in rows)
    print(f"| wrong-edition passages among the {3 * n} top-3 slots | {wb} | {wa} |")
    lost = [r["id"] for r in rows if r["before"]["lenient"] and not r["after"]["lenient"]]
    gained = [r["id"] for r in rows if not r["before"]["lenient"] and r["after"]["lenient"]]
    print(f"\nQuestions the filter lost (lenient): {lost or 'none'}; gained: {gained or 'none'}")
    return {"rows": rows}


EXPECTED_NOT_IN_FORCE = {"CLM-2025-30007": "cancelled", "CLM-2025-30008": "pre-inception"}


def cmd_inforce(_args=None) -> dict:
    from policy_register import coverage_in_force
    claims = _claims()
    ok, rows = 0, []
    for cn, c in sorted(claims.items()):
        r = coverage_in_force(c["policy_number"], c["date_of_loss"])
        want = cn not in EXPECTED_NOT_IN_FORCE
        good = r.get("in_force") == want
        ok += good
        mixed = len({w["edition"] for w in r.get("wording_in_force") or []}) > 1
        old = [f"{w['form_number']} ed. {w['edition']}" for w in r.get("wording_in_force") or []
               if w["edition"] == "07-23"]
        rows.append((cn, c["date_of_loss"], r.get("in_force"), good, r.get("reason"), old, mixed))
    print(f"\n## Coverage in force on the loss date: {ok}/{len(rows)} claims match the register's expected answer\n")
    print("| Claim | Loss date | In force | Correct | Wording in force that is NOT the newest edition | Reason |")
    print("|---|---|---|---|---|---|")
    for cn, d, inf, good, why, old, mixed in rows:
        if not inf or old:
            print(f"| {cn} | {d} | {inf} | {'yes' if good else 'NO'} | {', '.join(old) or '-'}"
                  f"{' (mixed editions on one claim)' if mixed else ''} | {why} |")
    print(f"\n(The other {sum(1 for r in rows if r[2] and not r[5])} claims are in force and every attached form "
          f"is on its newest edition.)")
    return {"ok": ok, "n": len(rows)}


# ===========================================================================
# The integrated agent: run / score / trajectory / judge / labels / report
# ===========================================================================

import hashlib  # noqa: E402
import re  # noqa: E402
import statistics  # noqa: E402

REPORT_DIR = os.path.join(ROOT, "reports", "week12")
CASES_PATH = os.path.join(ROOT, "evals", "cases", "week12_cases.jsonl")
JUDGE_PROMPT = os.path.join(REPORT_DIR, "judge_w12.txt")
DEFAULT_JUDGE_MODEL = "openai/gpt-oss-20b"
OPTIONAL_LOOKUPS = {"lookup_policy", "get_claim_status", "get_adjuster_notes"}

# Same rule as the runtime guard in src/referral.py; a local copy is used only
# if that module is missing, so `score` still runs on saved runs.
_FALLBACK_DECISION_RE = re.compile(
    r"\b(covered|uncovered|not\s+covered|excluded|denied|deny|declined?|approved?|payable|"
    r"we\s+will\s+pay|is\s+owed)\b", re.IGNORECASE)


def decision_re():
    try:
        from referral import DECISION_RE
        return DECISION_RE
    except Exception:
        return _FALLBACK_DECISION_RE


def _path(kind: str, label: str, ext: str = "json") -> str:
    return os.path.join(REPORT_DIR, f"{kind}_{label}.{ext}")


def load_cases(ids: str | None = None) -> list[dict]:
    with open(CASES_PATH, encoding="utf-8") as fh:
        cases = [json.loads(l) for l in fh if l.strip()]
    if ids:
        want = [i.strip() for i in ids.split(",") if i.strip()]
        cases = [c for c in cases if c["id"] in want]
    return cases


def load_runs(label: str) -> dict[str, dict]:
    p = _path("runs", label, "jsonl")
    if not os.path.exists(p):
        return {}
    out = {}
    with open(p, encoding="utf-8") as fh:
        for l in fh:
            if l.strip():
                r = json.loads(l)
                out[r["case_id"]] = r["run"]
    return out


def _dump(obj, path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(obj, fh, indent=2, ensure_ascii=False)
        fh.write("\n")


def _load(path):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


_DROP_KEYS = {"raw", "content", "result_full", "messages", "final_text_raw"}


def _scrub(obj, roster):
    """Drop raw-text fields and redact personal data (names, addresses, injuries)
    from a run before it is saved under reports/. Claim and policy numbers stay:
    scoring needs them."""
    from redaction import PERSONAL_KINDS, redact_text
    if isinstance(obj, str):
        return redact_text(obj, roster, kinds=PERSONAL_KINDS)[0]
    if isinstance(obj, list):
        return [_scrub(v, roster) for v in obj]
    if isinstance(obj, dict):
        return {k: _scrub(v, roster) for k, v in obj.items() if k not in _DROP_KEYS}
    return obj


def _hit_daily_cap(run: dict) -> bool:
    blob = json.dumps({k: run.get(k) for k in ("steps", "error", "stop_reason", "spans")}, ensure_ascii=False)
    return "tokens per day" in blob


def cmd_run(args):
    from claim_store import get_claim
    from triage_agent import run_triage
    done = load_runs(args.label)
    path = _path("runs", args.label, "jsonl")
    os.makedirs(REPORT_DIR, exist_ok=True)
    todo = [c for c in load_cases(args.ids) if c["id"] not in done]
    print(f"run {args.label}: version {args.version}, {len(todo)} to run, {len(done)} already saved")
    for case in todo:
        res = run_triage(case["claim_number"], version=args.version, model=args.model,
                         log=(lambda m: print(m)) if args.verbose else None, write=True)
        claim = get_claim(case["claim_number"]) or {}
        rec = {"case_id": case["id"], "run": _scrub(res, [claim.get("claimant_name") or ""])}
        if _hit_daily_cap(res):
            print(f"  {case['id']}: daily token cap reached; re-run the same command to resume")
            return
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
        print(f"  {case['id']:8} {case['claim_number']}  {res.get('stop_reason'):14} "
              f"{res.get('tokens', 0):>6} tok  ${res.get('cost_usd', 0):.5f}  laps {res.get('laps')}  "
              f"guard rejections {len(res.get('guard_rejections') or [])}  trace {res.get('trace_id')}")
    print(f"-> {path}")


# --- assertions ------------------------------------------------------------

def _num_eq(a, b) -> bool:
    if a is None or b is None:
        return a is None and b is None
    try:
        return abs(float(a) - float(b)) < 0.5
    except (TypeError, ValueError):
        return False


def _model_text(ref: dict) -> str:
    parts = list(ref.get("facts") or []) + list(ref.get("questions_for_adjuster") or [])
    parts += [c.get("why") or "" for c in ref.get("citations") or []]
    return "\n".join(str(p) for p in parts)


def _decision_attempts(run: dict) -> int:
    return sum(1 for g in run.get("guard_rejections") or []
               if re.search(r"decision", json.dumps(g.get("errors"), ensure_ascii=False), re.I))


def assert_case(case: dict, run: dict) -> dict:
    ref = run.get("referral") or {}
    cits = ref.get("citations") or []
    res = {}

    res["referral_made"] = run.get("stop_reason") == "referred" and not ref.get("fallback")

    hits = sorted(set(m.group(0).lower() for m in decision_re().finditer(_model_text(ref))))
    res["no_decision_language"] = not hits

    res["in_force_correct"] = ref.get("in_force") is case["expected_in_force"]

    wrong = [c.get("label") or f"{c.get('form_number')} ed. {c.get('edition')}" for c in cits
             if not c.get("in_force") or case["expected_editions"].get(c.get("form_number")) != c.get("edition")]
    res["edition_in_force"] = not wrong

    res["loss_date_stated"] = all(c.get("loss_date") == case["loss_date"] for c in cits)
    res["citations_resolve"] = all(c.get("exists") and c.get("link") for c in cits)

    if case["expected_in_force"]:
        ded = (ref.get("deductible") or {}).get("amount")
        sub = (ref.get("sublimit") or {}).get("amount") if ref.get("sublimit") else None
        lim = (ref.get("policy_limit") or {}).get("amount")
        three = {"deductible": _num_eq(ded, case["expected_deductible"]),
                 "sublimit": _num_eq(sub, case["expected_sublimit"]),
                 "policy_limit": _num_eq(lim, case["expected_policy_limit"])}
        res["three_numbers"] = all(three.values())
    else:
        three = {"n/a": True}
        res["three_numbers"] = ref.get("in_force") is False

    cited = {normalise_clause_id(c.get("clause_id")) for c in cits}
    if ref.get("sublimit"):
        cited.add(normalise_clause_id(ref["sublimit"].get("clause_id")))
    groups = case["expected_clauses_any_of"]
    res["decisive_clause_surfaced"] = (not groups) or any(cited & set(g) for g in groups)

    return {"case_id": case["id"], "claim_number": case["claim_number"], "mode": case["mode"],
            "group": case["group"], "pass": all(res.values()), "assertions": res,
            "detail": {"decision_words": hits, "wrong_edition_citations": wrong,
                       "three_numbers": three, "cited_clauses": sorted(c for c in cited if c),
                       "decision_attempts_caught_by_guard": _decision_attempts(run),
                       "guard_rejections": len(run.get("guard_rejections") or []),
                       "stop_reason": run.get("stop_reason"), "trace_id": run.get("trace_id")},
            "has_citations": bool(cits)}


def score_label(label: str, ids: set | None = None) -> dict:
    runs = load_runs(label)
    rows = [assert_case(c, runs[c["id"]]) for c in load_cases() if c["id"] in runs
            and (ids is None or c["id"] in ids)]
    n = len(rows)
    with_cits = [r for r in rows if r["has_citations"]]
    wrong_ed = [r for r in with_cits if r["detail"]["wrong_edition_citations"]]
    attempts = [r for r in rows if r["detail"]["decision_attempts_caught_by_guard"]]
    by_mode = {}
    for r in rows:
        m = by_mode.setdefault(r["mode"], {"n": 0, "pass": 0})
        m["n"] += 1
        m["pass"] += r["pass"]
    per_assert = {}
    for r in rows:
        for k, v in r["assertions"].items():
            a = per_assert.setdefault(k, {"n": 0, "pass": 0})
            a["n"] += 1
            a["pass"] += bool(v)
    return {"label": label, "n": n, "passed": sum(r["pass"] for r in rows),
            "by_mode": by_mode, "by_assertion": per_assert,
            "wrong_edition_citation_rate": {"cases": len(wrong_ed), "of_cases_with_citations": len(with_cits)},
            "decision_language_attempts": {"cases": len(attempts), "of": n},
            "decision_language_shipped": {"cases": sum(not r["assertions"]["no_decision_language"] for r in rows),
                                          "of": n},
            "rows": rows}


def _pct(a, b):
    return f"{a}/{b} = {a / b:.0%}" if b else f"{a}/{b}"


def cmd_score(args):
    s = score_label(args.label)
    _dump(s, _path("score", args.label))
    print(f"\n## Assertions on the integrated system: {args.label}, n={s['n']}\n")
    print("| Case | Claim | Mode | " + " | ".join(next(iter(s["rows"]))["assertions"]) + " | Pass |" if s["rows"] else "")
    if s["rows"]:
        print("|---|---|---|" + "---|" * (len(s["rows"][0]["assertions"]) + 1))
    for r in s["rows"]:
        print(f"| {r['case_id']} | {r['claim_number']} | {r['mode']} | "
              + " | ".join("ok" if v else "**FAIL**" for v in r["assertions"].values())
              + f" | {'PASS' if r['pass'] else 'FAIL'} |")
    print("\n| Mode | n | Pass rate |\n|---|---:|---:|")
    for m, v in sorted(s["by_mode"].items()):
        print(f"| {m} | {v['n']} | {_pct(v['pass'], v['n'])} |")
    print(f"| **all** | {s['n']} | **{_pct(s['passed'], s['n'])}** |")
    print("\n| Assertion | Pass rate |\n|---|---:|")
    for k, v in s["by_assertion"].items():
        print(f"| {k} | {_pct(v['pass'], v['n'])} |")
    w = s["wrong_edition_citation_rate"]
    print(f"\nWrong-endorsement-version citation rate: {_pct(w['cases'], w['of_cases_with_citations'])} "
          f"of cases with citations")
    a = s["decision_language_attempts"]
    print(f"Decision language attempted and caught by the runtime guard: {_pct(a['cases'], a['of'])} of cases; "
          f"shipped in a referral: {_pct(s['decision_language_shipped']['cases'], s['n'])}")
    print(f"-> {_path('score', args.label)}")


# --- trajectory --------------------------------------------------------------

def _short(tool: str) -> str:
    return (tool or "").split("__")[-1]


def trajectory_case(case: dict, run: dict) -> dict:
    steps = run.get("steps") or []
    labels, correct = [], 0
    seen_calls, seen_optional = set(), set()
    inforce_done, refer_seen = False, False
    searched = set()
    need = set(case["required_forms"])
    # Calls made in the same model turn are concurrent: a wording read issued in the
    # same lap as the in-force check is not "before" it (prompt w12-5 asks for both).
    inforce_lap = next((s.get("lap") for s in steps if _short(s.get("tool")) == "check_coverage_in_force"), None)
    for s in steps:
        checked_by_now = inforce_lap is not None and (s.get("lap") or 0) >= inforce_lap
        t = _short(s.get("tool"))
        args = s.get("args") or {}
        key = (t, json.dumps(args, sort_keys=True))
        repeated = key in seen_calls
        seen_calls.add(key)
        if repeated and "repeated_identical_call" not in labels:
            labels.append("repeated_identical_call")
        ok = False
        if t == "check_coverage_in_force":
            ok = not inforce_done and not repeated
            inforce_done = True
        elif t == "search_policy_wording":
            ld = args.get("loss_date")
            if not ld:
                labels.append("search_without_loss_date")
            elif ld != case["loss_date"]:
                labels.append("search_wrong_loss_date")
            if not checked_by_now and "search_before_inforce_check" not in labels:
                labels.append("search_before_inforce_check")
            f = args.get("form_number")
            covers = ({x.strip().upper() for x in str(f).replace(";", ",").split(",") if x.strip()} if f
                      else {x for x in need if x in json.dumps(s.get("result_preview") or "")})
            new = (covers & need) - searched
            ok = bool(checked_by_now and ld == case["loss_date"] and not repeated and (new or not f))
            searched |= covers
        elif t in OPTIONAL_LOOKUPS:
            ok = t not in seen_optional
            seen_optional.add(t)
        elif t == "refer_to_adjuster":
            refer_seen = True
            if not inforce_done and "refer_before_inforce_check" not in labels:
                labels.append("refer_before_inforce_check")
            ok = inforce_done
        else:
            labels.append(f"unknown_tool:{t}")
        correct += ok
    if not inforce_done:
        labels.append("skipped_inforce_check")
    missing = need - searched
    if missing:
        labels.append("skipped_required_form:" + ",".join(sorted(missing)))
    if not steps or _short(steps[-1].get("tool")) != "refer_to_adjuster":
        labels.append("did_not_end_in_referral" if refer_seen else "no_referral")
    labels = list(dict.fromkeys(labels))
    return {"case_id": case["id"], "claim_number": case["claim_number"], "calls": len(steps),
            "correct_calls": correct, "path": [_short(s.get("tool")) for s in steps],
            "trajectory_pass": not labels, "failures": labels}


def trajectory_label(label: str) -> dict:
    runs = load_runs(label)
    rows = [trajectory_case(c, runs[c["id"]]) for c in load_cases() if c["id"] in runs]
    calls = sum(r["calls"] for r in rows)
    correct = sum(r["correct_calls"] for r in rows)
    tpass = sum(r["trajectory_pass"] for r in rows)
    score = score_label(label)
    outcome = score["passed"]
    n = len(rows)
    gap = (outcome / n - tpass / n) * 100 if n else 0.0
    return {"label": label, "n": n, "tool_calls": calls, "correct_tool_calls": correct,
            "tool_choice_accuracy": correct / calls if calls else None,
            "trajectory_pass": tpass, "outcome_pass": outcome,
            "outcome_minus_trajectory_points": round(gap, 1), "rows": rows}


def cmd_trajectory(args):
    t = trajectory_label(args.label)
    _dump(t, _path("trajectory", args.label))
    n = t["n"]
    print(f"\n## Trajectory eval: {args.label}, n={n}\n")
    print("| Case | Path | Correct calls | Trajectory | Failure labels |\n|---|---|---:|---|---|")
    for r in t["rows"]:
        print(f"| {r['case_id']} | {' → '.join(r['path'])} | {r['correct_calls']}/{r['calls']} | "
              f"{'pass' if r['trajectory_pass'] else 'FAIL'} | {', '.join(r['failures']) or '-'} |")
    acc = t["tool_choice_accuracy"]
    print(f"\nTool-choice accuracy: {t['correct_tool_calls']}/{t['tool_calls']} = "
          f"{acc:.0%}" if acc is not None else "\nTool-choice accuracy: n/a")
    print(f"Outcome pass (all assertions): {_pct(t['outcome_pass'], n)}")
    print(f"Trajectory pass: {_pct(t['trajectory_pass'], n)}")
    print(f"Outcome-vs-trajectory gap: {t['outcome_minus_trajectory_points']:+.1f} points")
    print(f"-> {_path('trajectory', args.label)}")


# --- labels, judge, agreement ------------------------------------------------

def _sha(text: str) -> str:
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()


def _judge_view(claim: dict) -> str:
    """The full claim file, the adjuster's decision note included, with personal
    data redacted before it goes to the judge model."""
    from claim_store import render_claim_file
    from redaction import PERSONAL_KINDS, redact_text
    return redact_text(render_claim_file(claim), [claim.get("claimant_name") or ""], kinds=PERSONAL_KINDS)[0]


def cmd_label_sheet(args):
    from claim_store import get_claim
    runs = load_runs(args.label)
    lines = [f"# Label sheet: {args.label}", "",
             "Criterion (BASIS): " + _load_text(JUDGE_PROMPT).split("CRITERION (BASIS):", 1)[-1].split("\n\n", 1)[0].strip(), "",
             f"Write labels to `reports/week12/labels_{args.label}.json` as "
             '`{"labels": {"W12-B1": "PASS", ...}, "sha256": {...}}`; the sha256 block is pre-filled in '
             f"`labels_{args.label}.template.json`. Do not open any judge output first.", ""]
    shas = {}
    for c in load_cases():
        if c["id"] not in runs:
            continue
        text = (runs[c["id"]].get("referral") or {}).get("text") or "(no referral)"
        shas[c["id"]] = _sha(text)
        lines += [f"## {c['id']} · {c['claim_number']}", "", "**Claim file**", "", "```",
                  _judge_view(get_claim(c["claim_number"])), "```", "", "**Referral**", "", "```", text, "```",
                  "", "Label: PASS / FAIL", ""]
    with open(_path("label_sheet", args.label, "md"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")
    _dump({"labels": {k: None for k in shas}, "sha256": shas}, _path("labels", args.label, "template.json"))
    print(f"-> {_path('label_sheet', args.label, 'md')} ({len(shas)} cases)")


def _load_text(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def _labels(label: str) -> tuple[dict, dict]:
    raw = _load(_path("labels", label))
    if "labels" in raw:
        return raw["labels"], raw.get("sha256") or {}
    return {k: v for k, v in raw.items() if k != "sha256"}, raw.get("sha256") or {}


def cmd_judge(args):
    import llm
    from claim_store import get_claim
    if not os.path.exists(_path("labels", args.label)):
        sys.exit(f"refusing to judge: hand labels first (reports/week12/labels_{args.label}.json, "
                 f"from `label-sheet --label {args.label}`)")
    labels, shas = _labels(args.label)
    prompt = _load_text(args.prompt)
    runs = load_runs(args.label)
    out = {"label": args.label, "model": args.model, "prompt_file": os.path.basename(args.prompt),
           "prompt_sha256": _sha(prompt), "results": {}}
    for c in load_cases(args.ids):
        if c["id"] not in runs:
            continue
        text = (runs[c["id"]].get("referral") or {}).get("text") or "(no referral)"
        if c["id"] in shas and shas[c["id"]] != _sha(text):
            sys.exit(f"refusing to judge: referral of {c['id']} changed after it was labelled")
        user = (f"CLAIM FILE\n{_judge_view(get_claim(c['claim_number']))}\n\nREFERRAL TO JUDGE\n{text}\n\n"
                'Reply with JSON only: {"verdict": "PASS" or "FAIL", "reason": "<one sentence>"}')
        res = llm.chat([{"role": "system", "content": prompt}, {"role": "user", "content": user}],
                       model=args.model, max_tokens=1200)
        verdict, reason = None, res["content"]
        m = re.search(r"\{.*\}", res["content"] or "", re.S)
        if m:
            try:
                obj = json.loads(m.group(0))
                verdict = str(obj.get("verdict", "")).upper() or None
                reason = obj.get("reason", reason)
            except json.JSONDecodeError:
                pass
        if verdict not in ("PASS", "FAIL"):
            verdict = "FAIL"
        out["results"][c["id"]] = {"verdict": verdict, "reason": reason, "tokens": res["usage"]["total"],
                                   "error": res["error"], "referral_sha256": _sha(text)}
        print(f"  {c['id']:8} {verdict}  {str(reason)[:110]}")
        if res["error"] and res["error"].get("quota"):
            print("  daily token cap reached; re-run to resume")
            break
    prev = _path("judge", args.label)
    if os.path.exists(prev) and args.ids:
        old = _load(prev)
        old["results"].update(out["results"])
        out = old
    _dump(out, prev)
    print(f"-> {prev}")


def agreement_label(label: str) -> dict | None:
    if not (os.path.exists(_path("labels", label)) and os.path.exists(_path("judge", label))):
        return None
    labels, _ = _labels(label)
    judged = _load(_path("judge", label))["results"]
    both = [k for k in judged if labels.get(k) in ("PASS", "FAIL")]
    cm = {"PASS/PASS": 0, "PASS/FAIL": 0, "FAIL/PASS": 0, "FAIL/FAIL": 0}   # judge/label
    for k in both:
        cm[f"{judged[k]['verdict']}/{labels[k]}"] += 1
    agree = cm["PASS/PASS"] + cm["FAIL/FAIL"]
    return {"n": len(both), "agree": agree, "agreement": agree / len(both) if both else None,
            "confusion_judge_slash_label": cm,
            "disagreements": [k for k in both if judged[k]["verdict"] != labels[k]]}


def cmd_agreement(args):
    a = agreement_label(args.label)
    if a is None:
        sys.exit("need both labels_<label>.json and judge_<label>.json")
    print(f"Judge agreement with hand labels: {a['agree']}/{a['n']} = {a['agreement']:.0%}")
    print(f"Confusion (judge/label): {a['confusion_judge_slash_label']}")
    print(f"Disagreements: {a['disagreements'] or 'none'}")


# --- report ----------------------------------------------------------------

def _pctl(xs, p):
    """Nearest-rank percentile."""
    import math
    xs = sorted(xs)
    if not xs:
        return None
    return xs[max(0, min(len(xs) - 1, math.ceil(p / 100 * len(xs)) - 1))]


def cmd_report(args):
    s = score_label(args.label)
    t = trajectory_label(args.label)
    runs = load_runs(args.label)
    lines = [f"# Eval report: {args.label}", "",
             f"Integrated system, {s['n']} cases (`evals/cases/week12_cases.jsonl`). Assertions run first, "
             "all in code; the judge scores one criterion code cannot.", "",
             "| Mode | n | Pass rate |", "|---|---:|---:|"]
    for m, v in sorted(s["by_mode"].items()):
        lines.append(f"| {m} | {v['n']} | {_pct(v['pass'], v['n'])} |")
    lines.append(f"| **all** | {s['n']} | **{_pct(s['passed'], s['n'])}** |")
    lines += ["", "| Assertion | Pass rate |", "|---|---:|"]
    lines += [f"| {k} | {_pct(v['pass'], v['n'])} |" for k, v in s["by_assertion"].items()]
    w = s["wrong_edition_citation_rate"]
    lines += ["", f"- Wrong-endorsement-version citation rate: **{_pct(w['cases'], w['of_cases_with_citations'])}** "
              "of cases with citations"]
    if args.before:
        shared = set(load_runs(args.before)) & set(runs)
        sb = score_label(args.before, shared)
        sa = score_label(args.label, shared)
        wb, wa = sb["wrong_edition_citation_rate"], sa["wrong_edition_citation_rate"]
        lines.append(f"- Before → after on the same {len(shared)} cases: wrong-edition citations "
                     f"**{_pct(wb['cases'], wb['of_cases_with_citations'])} → "
                     f"{_pct(wa['cases'], wa['of_cases_with_citations'])}**; all assertions "
                     f"{_pct(sb['passed'], sb['n'])} → {_pct(sa['passed'], sa['n'])}")
    a = s["decision_language_attempts"]
    lines.append(f"- Decision language attempted and caught by the guard: {_pct(a['cases'], a['of'])}; "
                 f"shipped: {_pct(s['decision_language_shipped']['cases'], s['n'])}")
    ag = agreement_label(args.label)
    if ag:
        lines.append(f"- Judge agreement with hand labels: **{ag['agree']}/{ag['n']} = {ag['agreement']:.0%}**")
    acc = t["tool_choice_accuracy"]
    lines += [f"- Tool-choice accuracy: {t['correct_tool_calls']}/{t['tool_calls']}"
              + (f" = {acc:.0%}" if acc is not None else ""),
              f"- Outcome pass {_pct(t['outcome_pass'], t['n'])}, trajectory pass {_pct(t['trajectory_pass'], t['n'])}, "
              f"gap {t['outcome_minus_trajectory_points']:+.1f} points"]
    costs = [r.get("cost_usd") or 0 for r in runs.values()]
    toks = [r.get("tokens") or 0 for r in runs.values()]
    lats = [r.get("latency_s") or 0 for r in runs.values()]
    if runs:
        lines += [f"- Cost per claim triaged: mean ${statistics.mean(costs):.5f}; tokens per claim: mean "
                  f"{statistics.mean(toks):,.0f}; latency p50 {_pctl(lats, 50):.2f} s, p95 {_pctl(lats, 95):.2f} s "
                  "(model + tool time, rate-limit waits excluded)"]
    with open(_path("eval_report", args.label, "md"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")
    print("\n".join(lines))
    print(f"-> {_path('eval_report', args.label, 'md')}")


LEGACY = {"retrieval": cmd_retrieval, "hitrate": cmd_hitrate, "inforce": cmd_inforce}


def main():
    argv = sys.argv[1:]
    if not argv or all(a in LEGACY for a in argv):
        for name in argv or list(LEGACY):
            LEGACY[name]()
        return
    import argparse
    p = argparse.ArgumentParser(prog="week12.py")
    sub = p.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--version", default="w12-v2", choices=["w12-v1", "w12-v2"])
    r.add_argument("--label", required=True)
    r.add_argument("--ids")
    r.add_argument("--model")
    r.add_argument("--verbose", action="store_true")
    for name in ("score", "trajectory", "label-sheet", "agreement"):
        sp = sub.add_parser(name)
        sp.add_argument("--label", required=True)
    j = sub.add_parser("judge")
    j.add_argument("--label", required=True)
    j.add_argument("--ids")
    j.add_argument("--model", default=DEFAULT_JUDGE_MODEL)
    j.add_argument("--prompt", default=JUDGE_PROMPT, help="judge prompt file (versions: judge_w12.txt = v1, judge_w12_v2.txt = v2)")
    rp = sub.add_parser("report")
    rp.add_argument("--label", required=True)
    rp.add_argument("--before")
    a = p.parse_args(argv)
    {"run": cmd_run, "score": cmd_score, "trajectory": cmd_trajectory, "label-sheet": cmd_label_sheet,
     "judge": cmd_judge, "agreement": cmd_agreement, "report": cmd_report}[a.cmd](a)


if __name__ == "__main__":
    main()
