# Week 11 (Set D): find the coverage answer that ignored an exclusion

Run date 2026-11-03 · model `openai/gpt-oss-120b` on Groq · production service: the
**workflow Week 7 shipped** (`src/workflow.py`, prompt version `workflow-v2`), behind the new
front door `src/triage_service.py`.

| Deliverable | File | Headline |
|---|---|---|
| drill (mm:ss + slice) | [drill.md](drill.md) | **00:21**, sliced by **time + output decision**; bonus re-run **00:09** after adding `adjuster_exclusion_ids` |
| the found trace | [trace.json](trace.json) | `tr_03c4501f8140`: 4 spans with latency, tokens and cost, `workflow-v2` + SHA-256s, 4 context ids, **no exclusion table among them** |
| new eval case | [`evals/cases/week11_regressions.jsonl`](../../evals/cases/week11_regressions.jsonl) | W11-1 (E-93), plus W11-2 (E-46) from the bonus drill |
| suite RED then GREEN | [suite.md](suite.md) | **7/11 → 10/11** (W11-1 RED → GREEN, 0 regressions); re-run with W11-2 **7/12 → 12/12** |
| version bump + canary | [canary.md](canary.md) | workflow-v2 → **workflow-v3**: a retrieval fix, system prompt unchanged; sticky 10% canary, rollback = `POLICYLENS_CANARY_PERCENT=0` |
| cost by stage | [cost_by_stage.md](cost_by_stage.md) | $0.000584 for the query: retrieval $0 direct / 12% attributed, generation $0.000584, tools $0; after the fix +11% per query, all of it in retrieval |
| 10x | [tenx.md](tenx.md) | **a rate limit (tokens per day) breaks first: 366,026 tokens/day vs a 200,000 TPD cap**; cost only $0.11/day |

## Commands

| Command | What it does |
|---|---|
| `python evals/week11.py traffic` | replays three desk days (Fri 10-30, Mon 11-02 = yesterday, Tue 11-03 morning; 44 requests, every claim in the store at least once) through production on `workflow-v2` → `traces/week11/requests.jsonl` |
| `python evals/week11.py plant --n N` | the squadmate's step: plants one real bad coverage answer at a random time yesterday and seals a salted hash of its trace id |
| `python evals/week11.py drill start --n N` → `find …` / `show ID` → `drill found --n N ID` | the timed find; every query is timestamped in `drillN_session.jsonl` |
| `python evals/week11.py trace ID` · `case ID --mode … --payable … --why …` | export the trace; turn it into a regression case pinned to the trace id and the hash of the notes |
| `python evals/week11.py suite --version V --label L` · `diff A B` | 10 Week-6 cases + the regression cases, code-graded; case by case diff |
| `python evals/week11.py cost ID` · `tenx` | [cost_by_stage.md](cost_by_stage.md), [tenx.md](tenx.md) |
| `python evals/week11.py outcomes` · `find … --uncited-outcome` | bonus: the claims system's decisions as a PII-free stream joined on `claim_ref` |
| `python tests/test_week11_request_log.py` | the log holds no claim number, policy number, claimant name or note text; every answered line has a prompt version, context ids and a span for each stage |

## What Week 11 built: one line per request

The task builds on "the app you already built in Week 11", but the repo had no Week 11 layer,
so it was built here, on the production path:

- **`src/observability.py`.** It writes one JSON line per request with:
  - `ts_utc`, `user` (adjuster id), `channel`;
  - `input.type` (the peril family of each attached form), `input.claim_ref`
    (pseudonymised) and the redacted one-line `fnol`;
  - the adjuster notes as **SHA-256 + count only**, never the text;
  - `prompt.version` with the system and user-template SHA-256s;
  - `retrieval.context_ids`;
  - `output.decision / exclusion_ids / payable / reason`;
  - `spans[]`: one per call, staged `retrieval`, `generation` or `tools`, each with
    `latency_ms`, `tokens` and `cost_usd`; the generation span also splits its prompt tokens
    by block, so cost can be attributed to a stage;
  - `totals.by_stage`.

  Lines are redacted on write through the Week 5 `EventWriter`, which refuses to append a line
  that still holds an identifier. Rate-limit sleeps are recorded as `throttle_ms`, never as
  latency.
- **`src/triage_service.py`.** The front door, with canary routing (stable, canary and a
  percentage, from the environment; the bucket is sticky per claim).
- **Slices in `find`:** time (`--day`, `--since`, `--until`), `--user`, `--prompt-version`,
  `--input-type`, `--cost-outlier` (Tukey fence), plus output-side `--decision` and `--grep`.
  The complaint describes an *output*, so the output has to be indexed as well as the inputs.

## What the drill found, and the fix

`tr_03c4501f8140` (CLM-2026-10011, NG-1101 + NG-1106): production paid an **employer's
laptop as the insured's business property**, `partially_covered` $2,500, with no exclusion
cited. The adjuster denied the laptop under **E-93** (property of others) and paid $800.

The context ids gave the diagnosis in one hop: **retrieval missed the exclusions schedule**.
The workflow's one fixed query returned four clause passages and neither form's exclusion
table, so the model never saw E-93; it did not see the row and ignore it. Two more facts make
this systemic rather than one bad request:

- `search_policy` cuts every passage at **900 characters**. NG-1101's table is 1,609
  characters, so **E-44, E-45 and E-46 never reach the model** even when the table is
  "retrieved". The bonus drill's find, `tr_5d0758c1e3af` (groundwater E-46 called covered),
  is exactly this.
- Of yesterday's 10 covered or partially covered answers, **7 were made without the complete
  exclusion table of every attached form in context.**

The fix, **workflow-v3**, is a retrieval step: attach the complete, uncut exclusion table of
every attached form. The system prompt is byte-identical, so the change can be attributed. It
costs +11% per query ($0.000538 → $0.000597), all of it retrieval-attributed prompt tokens.
Week 7's verdict had already named this fix ("always fetch the exclusion table of each
attached form") after CLM-2026-20109. It was not done then, and this week's complaint is the
price.

## How these numbers were produced (please read)

- **Replay clock.** The three desk days were replayed today. Each line's `ts_utc` is its
  scheduled arrival time on the replay clock (seeded with the run date, no re-rolls), not the
  moment it executed. Nothing else about a line is simulated: every answer is a real model
  call.
- **Squadmate and finder.** A script planted the bad answers; it is blind to the finder and
  sealed. The finder was Claude, who had read the claim files while building this, so treat
  00:21 as a lower bound. **Re-run the drill with a named squadmate** (`plant --n 3 --by
  "<name>"`); [drill.md](drill.md) gives the steps.
- **Non-determinism.** At temperature 0 the same input still gave different answers: W11-1
  paid $2,500 in production and $800 in the first suite run. Case 4 (hurricane deductible)
  failed in 3 of 4 runs and passed once, so it is flaky; v3 did not fix it. The regression
  cases do not depend on luck: on v2 the exclusion row is deterministically absent from the
  context.
- **Budget.** About 155K tokens today on the free tier (200K/day): 71K for the request log
  (the traffic plus two plants), 81K for four suite runs, about 5K for discarded plant
  candidates and one smoke test.

## Follow-ups not done here

- The 900-character cut in `tools.search_policy` still applies to the single agent, the
  Week 10 squad and the Week 9 MCP `policy_docs` server. Only the production workflow
  bypasses it (step 2b).
- v3 sends NG-1101's table twice when the fixed query also ranks it (once cut, once whole).
  De-duplicating saves about 200 prompt tokens on those requests; measure it as its own
  version.
- Log `chars_sent` per context entry, so a truncated passage cannot pass for a retrieved one.
- Case 4 (hurricane deductible → `needs_info`) is a separate, flaky failure. It needs its own
  regression case and fix.
