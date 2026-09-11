"""
summariser.py — Generate structured claim summaries from adjuster notes.

Uses the same Groq API client as the main app (src/generation.py).
This is the module whose output the LLM judge evaluates.
"""

import json
import os
import sys
import time

# Add parent src/ to path for generation.py imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from generation import get_client, get_model          # noqa: E402


SUMMARISER_PROMPT = """\
You are a claims summary writer for a homeowners insurance company.

Given adjuster field notes and claim metadata, produce a concise, structured
claim summary suitable for the claims operations file.

The summary MUST include ALL of the following when applicable:
  • The claim number exactly as provided (in CLM-YYYY-NNNNN format)
  • The date of loss exactly as provided
  • A brief factual description of the loss event
  • The coverage decision: COVERED / NOT COVERED / DENIED / PENDING
  • If denied: cite the specific exclusion clause ID (e.g., E-17, E-26)
  • If an excess or deductible applies: state the numeric dollar amount
  • Reference to the applicable policy form and clause where known

Rules:
  – Keep the summary under 150 words.
  – Be strictly factual — do NOT invent information absent from the notes.
  – Do NOT add general insurance advice or policy interpretation.
  – Write in professional claims-operations register.
"""


def generate_summary(case: dict) -> str:
    """Generate a claim summary for one eval case."""
    client = get_client()
    model = get_model()

    user_msg = (
        f"ADJUSTER NOTES:\n{case['adjuster_notes']}\n\n"
        f"CLAIM METADATA:\n"
        f"  Claim Number : {case['claim_number']}\n"
        f"  Date of Loss : {case['date_of_loss']}\n"
        f"  Excess Amount: {case.get('excess_amount') or 'N/A'}\n"
        f"  Denial Reason: {case.get('denial_reason') or 'None'}\n"
        f"  Exclusion ID : {case.get('exclusion_id') or 'None'}\n\n"
        f"Write the claim summary now."
    )

    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": SUMMARISER_PROMPT},
            {"role": "user",   "content": user_msg},
        ],
        temperature=0.0,
        max_tokens=400,
    )
    return response.choices[0].message.content.strip()


def generate_all_summaries(
    cases_path: str,
    output_path: str,
    sleep: float = 1.0,
) -> list[dict]:
    """Generate summaries for all cases and save to JSON."""
    cases: list[dict] = []
    with open(cases_path) as fh:
        for line in fh:
            line = line.strip()
            if line:
                cases.append(json.loads(line))

    summaries: list[dict] = []
    for case in cases:
        print(f"  [{case['id']:>2}/{len(cases)}] Generating summary "
              f"(mode={case['mode']})…")
        try:
            summary_text = generate_summary(case)
        except Exception as exc:
            summary_text = f"ERROR: {type(exc).__name__}: {exc}"
            print(f"         ⚠ {summary_text}")

        summaries.append({
            "id":           case["id"],
            "mode":         case["mode"],
            "claim_number": case["claim_number"],
            "summary":      summary_text,
        })
        time.sleep(sleep)

    with open(output_path, "w", encoding="utf-8") as fh:
        json.dump(summaries, fh, indent=2, ensure_ascii=False)

    print(f"\n  ✓ Wrote {len(summaries)} summaries → {output_path}")
    return summaries


# ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    week6_dir = os.path.dirname(os.path.abspath(__file__))
    generate_all_summaries(
        os.path.join(week6_dir, "eval_cases_25.jsonl"),
        os.path.join(week6_dir, "summaries_25.json"),
    )
