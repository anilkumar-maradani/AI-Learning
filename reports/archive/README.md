# Archive — Weeks 3 to 5, produced against the retired corpus

Everything in this folder was produced against the original endorsement
corpus (forms HO-0304 to HO-0309). That corpus was copied from another
repository, not written for this project, so it was removed on 2026-09-30 and
replaced by the six Northgate forms in `data/policy/`.

These files are kept as the historical record of what those weeks measured.
They are **not** reproducible against the current index: re-running the Week 5
traffic or replaying these traces would retrieve different chunks, and
`replay.py` will report an index fingerprint mismatch.

| Path | Week | What it was |
|---|---|---|
| `week3_results.md` | 3 | chunker comparison, cited answers, refusals |
| `week5_traffic/` | 5 | the 130-question traffic generator and its driver |
| `week5_traces/` | 5 | the week of traces and the demo-set traces |
| `week5_error_analysis/` | 5 | seeded sample, open-coding notes, **failure taxonomy**, prediction |

The Week 5 taxonomy (`week5_error_analysis/taxonomy.md`) is still used: its
five failure modes are the tags on the Week 6 eval cases. The tooling from
those weeks (`src/tracing.py`, `src/redaction.py`, `src/replay.py`,
`src/sample_traces.py`, `src/render_traces.py`) is still part of the app.
