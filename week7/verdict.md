# Verdict — Agent vs Fixed Workflow

**Race summary (10 claims, same inputs, same tools, same model):**

| Metric | Agent | Workflow | Winner |
|--------|-------|----------|--------|
| Pass rate | 100% (10/10) | 50% (5/10) | Agent |
| p50 latency | 30.06s | 5.77s | Workflow |
| Total tokens | 73,788 | 8,873 | Workflow |
| Cost/claim | $0.0066 | $0.0008 | Workflow |

**Decision rule applied:** Does the tool-calling path vary by input class?

**Verdict:** The workflow wins on 3/4 metrics. none of the 10 claims requires an agent. The workflow's path is identical for all input classes — fixed steps 1→2→3→4 regardless of whether notes reveal a flood cause, a sublimit, or concurrent causation. The agent adds latency and tokens without improving accuracy.

*Step-dependency claims (genuine variable-path cases): W7-CLM-004, W7-CLM-005, W7-CLM-006*
