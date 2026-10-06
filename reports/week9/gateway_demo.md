# Week 9 bonus — one front door, scoped token

Agent config: `mcp_config.gateway.json` (one server: the gateway). The gateway fans out to `policy_docs` and `claims_system` from `mcp_servers/gateway/gateway_config.json`.

## Direct tools/call through the gateway (token `triage-agent`, notes denied)

- `gateway__claims_system__get_claim_status` → isError=False: `{"claim_number": "CLM-2026-20106", "status": "open", "policy_number": "HOP-5510206", "claimant_name": "[CLAIMANT:1bcc6e]", "date_of_loss": "2026-05-19", "reported_date": "2026-05-20", "forms": ["NG-1101"], "adjuster_note_cou`
- `gateway__claims_system__get_adjuster_notes` → isError=True: `permission denied: caller 'triage-agent' is not scoped for claims_system__get_adjuster_notes. This is a permission decision, not an outage or a bad argument, so retrying will not help. Answer from the tools you can use, `

### Model run through the gateway

Config: `mcp_config.gateway.json` · stop: `final_answer` · laps 3 · 5168 tokens · $0.00092

Discovered: `gateway__policy_docs__search_policy`, `gateway__claims_system__get_claim_status`, `gateway__claims_system__get_adjuster_notes`

**Adjuster:** For claim CLM-2026-20106, what is its status and what do the adjuster notes say about where the water came from?

- lap 1: **`gateway__claims_system__get_claim_status`** (server `gateway`, MCP tool `claims_system__get_claim_status`) `{"claim_number": "CLM-2026-20106"}`
  - `{"claim_number": "CLM-2026-20106", "status": "open", "policy_number": "HOP-5510206", "claimant_name": "[CLAIMANT:1bcc6e]", "date_of_loss": "2026-05-19", "reported_date": "2026-05-20", "forms": ["NG-1101"], "adjuster_note_count": 1, "latest_note_date": "2026-05-21"}`
- lap 2: **`gateway__claims_system__get_adjuster_notes`** (server `gateway`, MCP tool `claims_system__get_adjuster_notes`) `{"claim_number": "CLM-2026-20106"}`
  - **isError: true** — `permission denied: caller 'triage-agent' is not scoped for claims_system__get_adjuster_notes. This is a permission decision, not an outage or a bad argument, so retrying will not help. Answer from the tools you can use, and tell the adjuster this part needs someone with access to it.`

**Final answer:**

> The claim CLM‑2026‑20106 is **open** (see claim‑status record). I don’t have permission to view the adjuster‑note text, so I can’t tell you what the adjuster recorded about the source of the water. Someone with access to the adjuster‑note history will need to retrieve that information.

## Audit log (`logs/gateway_audit.jsonl`, one line per tools/call)

```
{"ts": "2026-10-06T12:44:58+00:00", "caller": "triage-agent", "tool": "claims_system__get_claim_status", "claim_number": "CLM-2026-20106", "outcome": "ok"}
{"ts": "2026-10-06T12:44:58+00:00", "caller": "triage-agent", "tool": "claims_system__get_adjuster_notes", "claim_number": "CLM-2026-20106", "outcome": "denied"}
{"ts": "2026-10-06T12:44:59+00:00", "caller": "triage-agent", "tool": "claims_system__get_claim_status", "claim_number": "CLM-2026-20106", "outcome": "ok"}
{"ts": "2026-10-06T12:45:06+00:00", "caller": "triage-agent", "tool": "claims_system__get_adjuster_notes", "claim_number": "CLM-2026-20106", "outcome": "denied"}
```

