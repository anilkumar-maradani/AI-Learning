# Cost per query, by stage

Request `tr_03c4501f8140` (2026-11-02T07:03:21.545+00:00, workflow-v2, openai/gpt-oss-120b). Prices: `src/llm.py` (gpt-oss-120b $0.15 / $0.75 per 1M input / output tokens).

Two views. **Direct** is what each stage is billed for. Retrieval (MiniLM + BM25) and the tools (claims system, payout arithmetic) run locally, so they bill $0. **Attributed** splits the one model call's bill by the stage that put each prompt token there, so a saving can be traced to a stage. Prompt blocks are counted with o200k_base; `template_and_chat_format` is the provider's `prompt_tokens` minus the counted blocks.

## Spans of this request

| Span | Stage | Latency (ms) | Prompt tok | Completion tok | Cost (USD) |
|---|---|---:|---:|---:|---:|
| `tools:get_claim` | tools | 0.0 | 0 | 0 | $0.00000000 |
| `retrieval:search_policy` | retrieval | 21.2 | 0 | 0 | $0.00000000 |
| `generation:decide` | generation | 2,626.0 | 1,021 | 574 | $0.00058365 |
| `tools:compute_payout` | tools | 0.0 | 0 | 0 | $0.00000000 |

Prompt tokens of `generation:decide`, by block: system 269, claim_file 200, policy_passages 469, template_and_chat_format 83.

**This request**

| Stage | Latency (ms) | Billed tokens | Direct cost | Prompt tokens it put in front of the model | Attributed cost | Share |
|---|---:|---:|---:|---:|---:|---:|
| retrieval | 21 | 0 | $0.000000 | 469 | $0.000070 | 12% |
| generation | 2,626 | 1,595 | $0.000584 | 352 in + 574 out | $0.000483 | 83% |
| tools | 0 | 0 | $0.000000 | 200 | $0.000030 | 5% |
| **total** | 2,647 | 1,595 | **$0.000584** | | **$0.000584** | 100% |

**Mean per query, all 19 answered requests on 2026-11-02**

| Stage | Latency (ms) | Billed tokens | Direct cost | Prompt tokens it put in front of the model | Attributed cost | Share |
|---|---:|---:|---:|---:|---:|---:|
| retrieval | 23 | 0 | $0.000000 | 510 | $0.000076 | 15% |
| generation | 1,639 | 1,530 | $0.000510 | 352 in + 468 out | $0.000404 | 79% |
| tools | 0 | 0 | $0.000000 | 200 | $0.000030 | 6% |
| **total** | 1,662 | 1,530 | **$0.000510** | | **$0.000510** | 100% |

## After the fix

**Same claim, suite run before the fix (workflow-v2)**

| Stage | Latency (ms) | Billed tokens | Direct cost | Prompt tokens it put in front of the model | Attributed cost | Share |
|---|---:|---:|---:|---:|---:|---:|
| retrieval | 20 | 0 | $0.000000 | 469 | $0.000070 | 10% |
| generation | 2,591 | 1,723 | $0.000680 | 352 in + 702 out | $0.000579 | 85% |
| tools | 0 | 0 | $0.000000 | 200 | $0.000030 | 4% |
| **total** | 2,611 | 1,723 | **$0.000680** | | **$0.000680** | 100% |

**Same claim, suite run after the fix (workflow-v3)**

| Stage | Latency (ms) | Billed tokens | Direct cost | Prompt tokens it put in front of the model | Attributed cost | Share |
|---|---:|---:|---:|---:|---:|---:|
| retrieval | 18 | 0 | $0.000000 | 946 | $0.000142 | 19% |
| generation | 2,617 | 2,204 | $0.000743 | 371 in + 687 out | $0.000571 | 77% |
| tools | 0 | 0 | $0.000000 | 200 | $0.000030 | 4% |
| **total** | 2,634 | 2,204 | **$0.000743** | | **$0.000743** | 100% |

Mean over the 11 suite cases: $0.000538 -> $0.000597 per query (+11%). By stage (attributed): retrieval $0.000078 -> $0.000128, generation $0.000431 -> $0.000441, tools $0.000029 -> $0.000029.
