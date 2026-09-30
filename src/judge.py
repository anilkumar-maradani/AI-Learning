"""
judge.py — LLM judge for claim summaries, ONE binary criterion.

The judge prompt text lives in reports/week6/judge_v*.txt so each version is a
reviewable, diffable file. Everything a regex can check was moved to
assertions.py and deleted from the prompt.
"""

import json
import os
import re

from claim_store import render_claim_file
from llm import MAIN_MODEL, chat

JUDGE_DIR = os.path.join(os.path.dirname(__file__), "..", "reports", "week6")


def load_judge_prompt(version: str) -> str:
    with open(os.path.join(JUDGE_DIR, f"judge_{version}.txt"), encoding="utf-8") as fh:
        return fh.read()


def judge_summary(prompt: str, claim: dict, summary: str) -> dict:
    user = (
        f"CLAIM FILE\n{render_claim_file(claim)}\n\n"
        f"SUMMARY TO JUDGE\n{summary}\n\n"
        'Reply with JSON only: {"verdict": "PASS" or "FAIL", "reason": "<one sentence>"}'
    )
    res = chat([{"role": "system", "content": prompt}, {"role": "user", "content": user}],
               model=MAIN_MODEL, max_tokens=1500)
    verdict, reason = None, res["content"]
    m = re.search(r"\{.*\}", res["content"], re.S)
    if m:
        try:
            obj = json.loads(m.group(0))
            verdict = str(obj.get("verdict", "")).upper() or None
            reason = obj.get("reason", reason)
        except json.JSONDecodeError:
            pass
    if verdict not in ("PASS", "FAIL"):
        verdict = "PASS" if re.search(r"\bPASS\b", res["content"]) and not re.search(
            r"\bFAIL\b", res["content"]) else "FAIL"
    return {"verdict": verdict, "reason": reason, "usage": res["usage"],
            "error": res["error"]}
