"""
llm.py — One place that talks to the model for the Week 6-8 code.

Why a separate helper instead of calling the client directly:
  * latency must not include rate-limit backoff. The free Groq tier allows
    8,000 tokens per minute, so an agent run can sit in a 429 sleep for longer
    than it spends thinking. api_s counts only successful request time;
    throttle_s is reported separately.
  * every call returns usage and cost, so callers can SUM tokens across laps
    instead of reading only the last call.
"""

import os
import re
import time

from dotenv import load_dotenv

load_dotenv()

MAIN_MODEL = os.environ.get("GROQ_MODEL", "openai/gpt-oss-120b")
SMALL_MODEL = os.environ.get("GROQ_SMALL_MODEL", "openai/gpt-oss-20b")

# USD per 1M tokens (input, output). Groq list prices as of 2026-09; confirm at
# console.groq.com before quoting money. Both race systems use the same rates,
# so the agent/workflow ratio does not depend on them.
PRICES = {
    "openai/gpt-oss-120b": (0.15, 0.75),
    "openai/gpt-oss-20b": (0.10, 0.50),
}

_WAIT_RE = re.compile(r"try again in\s+(?:(\d+)m)?([\d.]+)s", re.IGNORECASE)


def cost_usd(model: str, prompt_tokens: int, completion_tokens: int) -> float:
    p_in, p_out = PRICES.get(model, PRICES["openai/gpt-oss-120b"])
    return (prompt_tokens * p_in + completion_tokens * p_out) / 1_000_000


def _client():
    from generation import get_client
    return get_client()


def chat(
    messages: list[dict],
    model: str = MAIN_MODEL,
    tools: list[dict] | None = None,
    temperature: float = 0.0,
    max_tokens: int = 1200,
    max_attempts: int = 6,
) -> dict:
    """
    Returns {content, tool_calls, usage{prompt,completion,total}, cost_usd,
    api_s, throttle_s, finish_reason, error}. tool_calls is a list of
    {id, name, arguments(str)}.
    """
    kwargs = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    if tools:
        kwargs["tools"] = tools
        kwargs["tool_choice"] = "auto"

    throttle_s = 0.0
    last_exc = None
    for attempt in range(max_attempts):
        t0 = time.perf_counter()
        try:
            resp = _client().chat.completions.create(**kwargs)
        except Exception as exc:  # 429 / 5xx / tool-parse errors
            last_exc = exc
            msg = str(exc)
            if attempt + 1 < max_attempts and any(
                s in msg for s in ("429", "500", "502", "503", "timeout", "Timeout")
            ):
                m = _WAIT_RE.search(msg)
                wait = (float(m.group(1) or 0) * 60 + float(m.group(2)) + 1) if m else 5 * (attempt + 1)
                wait = min(wait, 120)
                time.sleep(wait)
                throttle_s += wait
                continue
            break
        api_s = time.perf_counter() - t0
        choice = resp.choices[0]
        u = resp.usage
        pt, ct = (u.prompt_tokens or 0), (u.completion_tokens or 0)
        return {
            "content": (choice.message.content or "").strip(),
            "tool_calls": [
                {"id": tc.id, "name": tc.function.name, "arguments": tc.function.arguments}
                for tc in (choice.message.tool_calls or [])
            ],
            "usage": {"prompt": pt, "completion": ct, "total": pt + ct},
            "cost_usd": cost_usd(model, pt, ct),
            "api_s": round(api_s, 3),
            "throttle_s": round(throttle_s, 1),
            "finish_reason": choice.finish_reason,
            "error": None,
        }

    return {
        "content": "",
        "tool_calls": [],
        "usage": {"prompt": 0, "completion": 0, "total": 0},
        "cost_usd": 0.0,
        "api_s": 0.0,
        "throttle_s": round(throttle_s, 1),
        "finish_reason": "error",
        "error": {"type": type(last_exc).__name__, "message": str(last_exc)[:400]},
    }
