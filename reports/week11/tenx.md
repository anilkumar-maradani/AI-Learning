# What breaks first at 10x

**Rate limit, the tokens-per-day cap: 10x today's 19 claims is 366,026 tokens/day against Groq's 200,000 TPD for gpt-oss-120b (1.8x the cap, reached at 5.5x today's volume), while cost is only $0.11/day.**

## The numbers

- Today's volume: **19 triage requests on 2026-11-02** (the last full desk day in `traces/week11/requests.jsonl`), 19 of them with a model call.
- Per answered request: **1,926 tokens** and **$0.000597** (from suite_after, i.e. after the workflow-v3 fix, which is what would ship).
- Latency today: p50 1.51 s, p99 2.95 s (model + tool time; nearest-rank p99 = slowest).
- Limits, read from Groq's response headers on 2026-11-03: `x-ratelimit-limit-tokens: 8000` (per minute), `x-ratelimit-limit-requests: 1000` (per day). Tokens per day: 200,000 for gpt-oss-120b (the free-tier cap that stopped Week 10's first squad run; see `reports/week10/README.md`).

| At 10x | Value | Limit | Headroom |
|---|---:|---:|---:|
| tokens / day | 366,026 | 200,000 TPD | **0.55x (breaks)** |
| tokens / minute, busiest hour (3 requests) | 963 | 8,000 TPM | 8.3x |
| requests / day | 190 | 1,000 RPD | 5.3x |
| cost / day | $0.11 | none set | n/a |
| latency | p99 2.95 s per request | n/a | does not depend on volume until a limit throttles |

Why the token-per-day cap and not the per-minute one: requests arrive spread over a ten-hour desk day, so even the busiest hour at 10x stays under the 8,000-token minute. The daily total does not: the quota runs out after about 5.5 hours of a 10-hour day. `src/llm.py` fails fast on the daily cap, so every claim after that point gets no answer at all, not a slow one. Cost is the last thing to break: 10x is still cents a day.
