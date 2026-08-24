#!/usr/bin/env python3
"""
chat.py — Interactive CLI chat for the Insurance Claims RAG app.

Type any question about the endorsements and get a grounded answer.
The app searches your indexed endorsements and generates a cited response.
Type 'quit' or 'exit' to stop.

Usage:
    source venv/bin/activate
    python3 chat.py
"""

import os
import sys
from dotenv import load_dotenv

# Load .env from the project root (if present) before anything else
load_dotenv()

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

from retrieval import search, format_results
from generation import generate_answer

# ── ANSI colours ────────────────────────────────────────────────────────────
CYAN   = "\033[96m"
GREEN  = "\033[92m"
YELLOW = "\033[93m"
RED    = "\033[91m"
BOLD   = "\033[1m"
RESET  = "\033[0m"
DIM    = "\033[2m"

BANNER = f"""
{BOLD}{CYAN}╔══════════════════════════════════════════════════════════════╗
║       🏠  Insurance Claims RAG — Endorsement Assistant       ║
║              Week 3 Practical · Task Set D                   ║
╚══════════════════════════════════════════════════════════════╝{RESET}

{DIM}Indexed endorsements: HO-0304, HO-0305, HO-0306, HO-0307, HO-0308, HO-0309{RESET}
{DIM}Type your question below. Type {BOLD}quit{RESET}{DIM} to exit.{RESET}

{YELLOW}Example questions you can ask:{RESET}
  • Does E-17 cover water damage from a burst supply line?
  • What is the named storm deductible under HO-0305?
  • Does HO-0306 exclude mold damage?
  • What does "sudden and accidental" mean under HO-0304?
  • Does HO-0308 cover earthquake damage?
  • Is there a business pursuits exclusion in HO-0309?
"""

SEPARATOR = f"{DIM}{'─' * 64}{RESET}"


def chat_loop():
    print(BANNER)

    # Check API key
    api_key = os.environ.get("GROQ_API_KEY", "")
    if not api_key:
        print(f"{RED}⚠  GROQ_API_KEY is not set!{RESET}")
        print(f"   Copy .env.example → .env and fill in your key, then run:")
        print(f"   {BOLD}export GROQ_API_KEY=<your-key>{RESET}")
        print(f"   Then run: {BOLD}python3 chat.py{RESET}\n")
        sys.exit(1)

    turn = 0
    while True:
        turn += 1
        print(SEPARATOR)
        try:
            question = input(f"\n{BOLD}{CYAN}You:{RESET} ").strip()
        except (EOFError, KeyboardInterrupt):
            print(f"\n\n{DIM}Goodbye!{RESET}\n")
            break

        if not question:
            print(f"{DIM}  (empty input — please type a question){RESET}")
            continue

        if question.lower() in ("quit", "exit", "q", "bye"):
            print(f"\n{DIM}Goodbye!{RESET}\n")
            break

        # ── Retrieval ──────────────────────────────────────────────────
        print(f"\n{DIM}🔍 Searching endorsements...{RESET}", end="", flush=True)
        try:
            hits = search(question, strategy="structure_aware", n_results=5)
        except Exception as e:
            print(f"\n{RED}Retrieval error: {e}{RESET}")
            continue

        # Show which chunks were found
        print(f"\r{DIM}🔍 Found {len(hits)} relevant chunks:{RESET}")
        for h in hits[:3]:
            meta = h["metadata"]
            print(
                f"   {DIM}#{h['rank']} score={h['score']:.3f} │ "
                f"{meta.get('form_number','?')} │ "
                f"{meta.get('clause_id','?')}{RESET}"
            )
        if len(hits) > 3:
            print(f"   {DIM}... and {len(hits)-3} more{RESET}")

        # ── Generation ─────────────────────────────────────────────────
        print(f"\n{DIM}💬 Generating answer...{RESET}", end="", flush=True)
        try:
            result = generate_answer(question, hits, verbose=False)
        except Exception as e:
            print(f"\n{RED}Generation error: {e}{RESET}")
            continue

        answer = result["answer"]
        is_refusal = result["is_refusal"]

        # ── Print answer ───────────────────────────────────────────────
        print(f"\r", end="")  # clear the "Generating..." line
        if is_refusal:
            print(f"\n{BOLD}{RED}🚫 Assistant (REFUSAL):{RESET}")
            print(f"{RED}{answer}{RESET}")
        else:
            print(f"\n{BOLD}{GREEN}🤖 Assistant:{RESET}")
            print(f"{answer}")

        # ── Source hint ────────────────────────────────────────────────
        top_hit = hits[0] if hits else None
        if top_hit and not is_refusal:
            meta = top_hit["metadata"]
            print(
                f"\n{DIM}📄 Primary source: {meta.get('source_file','?')} │ "
                f"form={meta.get('form_number','?')} │ "
                f"clause={meta.get('clause_id','?')}{RESET}"
            )

    print(f"{BOLD}{CYAN}Session ended.{RESET}\n")


if __name__ == "__main__":
    chat_loop()
