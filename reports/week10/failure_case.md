# Week 10: injected worker failure

**What the orchestrator did: it DEGRADED.** It retried the exclusions worker once, then
returned `needs_info` and named the failed worker. It did not declare the claim covered.

## The injection

- **Case:** 2, `CLM-2026-10002`. The adjuster denied this claim under **E-41** (seepage:
  a drain-trap leak that ran about three weeks).
- **The fault:** the coverage/exclusions worker returns HTTP 500 on every attempt.
  ```
  python evals/week10.py fail --case 2
  ```
  (`squad.run_squad(..., inject="exclusions_worker")` raises
  `WorkerError(status=500)` at the hand-off.)
- **The same case without the fault:** the squad answered `excluded`, E-41, $0, and
  the judge passed it (`squad_runs.jsonl`).

## What happened, step by step (`failure_run.jsonl`)

| Step | Result |
|---|---|
| `orchestrator:plan` | 560 tokens; briefs written for both workers |
| `orchestrator -> notes_worker` | 1,007 tokens. The facts came back correct: "slow leak from the drain trap … ongoing for approximately three weeks … cabinet base rotted" |
| `orchestrator -> exclusions_worker`, attempt 1 | **HTTP 500** |
| `orchestrator -> exclusions_worker`, attempt 2 (the one retry) | **HTTP 500** |
| `compute_payout` | not run: there was no coverage decision to price |
| `workers -> orchestrator:synthesis` | 783 tokens. The synthesis input said `exclusions_worker: {"status": "FAILED", "error": "…HTTP 500…"}` |
| **Final answer** | `{"decision": "needs_info", "exclusion_ids": [], "payable": null, "reason": "Exclusions worker failed to return a result and compute_payout was not run because no coverage decision is available."}` |
| Judge (v2) | **FAIL**: "states needs_info … whereas the adjuster denied the claim based on exclusion E-41" |

The run used 2,350 tokens, $0.00102, and 5.0 s of latency.

**Retry, degrade or lie?** It **retried** (once, as designed) and then **degraded**.
It did **not lie**: it neither said "covered" nor invented an exclusion. The answer is
still wrong, and the judge failed it. It is a safe failure, not a correct one.

**Recorded honestly: the first run of this injection crashed.** The orchestrator's
retry helper (`squad._call_worker`) read the exception variable after its
`except` block had ended, and Python had already deleted it. So the first time both
attempts failed, the whole squad raised `UnboundLocalError` and gave **no answer at
all**. The code had never been exercised on the double-failure path; that is the
point of injecting the fault. Fixed in `src/squad.py` (the error text is now kept
in `last`); the run above is the re-run after the fix.

**One flaw remains even after the fix:** `needs_info` is the wrong status. In the
output contract, `needs_info` means "the claim file lacks the facts". Here the facts
were present, and the notes worker extracted the three-week leak; it was our own
service that failed. An adjuster reading `needs_info` would go and ask the insured
for information they already gave.

## Bonus: the A2A task lifecycle for this case

The orchestrator's AgentCard is in [agent_card.json](agent_card.json): skills
`triage-claim` and `summarise-adjuster-notes`, JSON and text input and output,
OAuth2 client credentials with the `claims.triage` scope.

Mapped onto `submitted → working → (input-required → working)* → completed | failed | canceled`:

- **The delegated exclusions sub-task** should end **`failed`**, with the 500 as the
  status message. It is a system fault, and only a retry or a person can fix it.
- **The claim triage task itself** should **pause at `input-required`**, not end
  `completed` with `needs_info` (what we did) and not end `failed` (which throws away
  the facts gathered). The status message: "The exclusions check is unavailable
  (HTTP 500 ×2). The notes show the leak ran ~3 weeks, which points to E-41 seepage.
  Confirm the denial, or ask me to retry." The adjuster's reply moves it back to
  `working` and on to `completed`.

**What A2A buys over a plain REST call to the worker:** a REST call gives you a
status code, and you invent the retry, pause and resume semantics yourself. A2A
gives the hand-off a standard, discoverable contract (the AgentCard: skills, modes,
auth) and a task with a lifecycle. `input-required` makes "stop and ask the
adjuster" a first-class state instead of a status the synthesis prompt has to
improvise.
