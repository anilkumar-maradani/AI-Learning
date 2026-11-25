# Architecture (one page)

```
 FNOL ──► policylens.py triage CLM-…            (one entry point; trace id tr_xxxxxxxxxxxx minted here)
            │
            ▼
 ┌──────────────────────── HOST: src/triage_agent.py ─────────────────────────────────────────┐
 │ intake (code, not the model):                                                              │
 │   claims_system__get_adjuster_notes ──MCP──► mcp_servers/claims_system (third party)       │
 │      reads data/claims_at_triage (snapshot: decision notes withheld)                       │
 │   redact names / addresses / injuries  (redaction.PERSONAL_KINDS) ──► FNOL message         │
 │                                                                                            │
 │ agent loop (Week 7 loop, 4 budgets), tools discovered at runtime from mcp_config.w12.json  │
 │   lap 1  check_coverage_in_force(policy, loss_date) ──MCP + _meta{trace_id, span_id}──┐    │
 │   lap 2  search_policy_wording(forms, loss_date)    ──MCP + _meta───────────────────┐ │    │
 │   lap 3  refer_to_adjuster (local) ──► referral guard (code): no decision words,     │ │    │
 │          cited chunk must have been read, clause must exist in that edition,         │ │    │
 │          edition must be in force on the loss date ─► referral with three numbers    │ │    │
 │   ★ every lap = one model call to Groq (gpt-oss) ◄── THE ONLY PLACE MONEY IS SPENT   │ │    │
 │ request line (redacted on write): spans with tokens/cost/latency ─► traces/w12/      │ │    │
 └──────────────────────────────────────────────────────────────────────────────────────┼─┼────┘
                                                                                        ▼ ▼
 ┌──────────────── OUR MCP SERVER: mcp_servers/coverage (northgate-coverage 1.0.0) ─────────────┐
 │ lookup_policy · check_coverage_in_force ──► policy_register.py ─► data/policies/policies.jsonl│
 │ search_policy_wording ──► hybrid_search(loss_date=, product=)                                  │
 │     vector leg: Chroma where effective_from ≤ loss_date ≤ effective_to ┐ filtered BEFORE     │
 │     BM25 leg:   same predicate                                          ┘ ranking            │
 │     whole-form read: editions.edition_in_force(form, loss_date), uncut                       │
 │ call log: trace_id + parent span + latency + exact result (redacted) ─► traces/w12/          │
 │ also served to other squads: python policylens.py serve-mcp                                  │
 └──────────────────────────────────────────────────────────────────────────────────────────────┘
        ▲ data/policy/*_07-23.txt + *_01-26/02-26/03-26.txt, both editions, chunk ids carry the edition
```

**Where the model calls happen:** inside the agent loop only. There are 3 model
calls on the normal path, plus one more for each guard rejection. The judge (eval
only) is a separate model call per case. These parts make no model call:

- MCP servers, retrieval and the date filter;
- the in-force check, citations and the referral guard;
- redaction and logging.

**Where the money goes:** every lap re-sends the system prompt, the tool
definitions, the FNOL with its notes, and every earlier tool result. Groq does no
prompt caching (checked: two identical 1,479-token calls were both billed in
full). So the referral lap costs the most: it carries the full in-force wording
of every form on the policy. A rejected referral costs that lap again. Per-claim
tokens and cost are in [README.md](README.md).
