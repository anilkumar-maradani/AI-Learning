**Sunk-cost bias, named first:** I built the squad this week and I want it to win. That is sunk-cost bias, so the effort counts for nothing here. Only the race counts.
**Verdict: KEEP the squad, narrowly and on probation, not as a settled win.**
**Pass rate 60% vs 40%** (judge v2, the same 10 Week-6 cases). The two extra passes are case 7, where the single agent called a non-existent `json` tool and gave no answer, and case 8, where it added E-81 to E-83.
**Tokens 65,154 vs 106,306 (0.6×), cost $0.00193 vs $0.00213 per claim:** no multi-agent tax here. 91% of the single agent's tokens are its own conversation re-sent, and it looped into the 8-lap budget on cases 9 and 10.
**Latency:** p99 is 27.67 s for the squad vs 91.25 s; p50 is worse, 7.85 s vs 4.61 s, because five sequential calls add about 3 s to a typical claim.
**Not proven:** two cases out of ten is within noise, and the judge's validated agreement is 64%. The single agent's case 3 was right ($1,800, E-63) and failed only on how it was rendered for the judge.
**Much of the win is constraint, not "more agents":** the exclusions worker has one tool and a 4-lap cap. Give the single agent the same cap and the gap may close. That is the next race, on all 25 cases.
**Don't ship it as it is:** on a worker 500 it first crashed, and after the fix it answers `needs_info` instead of pausing for the adjuster ([failure_case.md](failure_case.md)).
