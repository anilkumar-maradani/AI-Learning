# Verdict — agent vs fixed workflow

**Rule:** use an agent only if the right path changes with the input in a way
fixed steps cannot anticipate.

The agent's path did vary (one to four policy searches; on CLM-2026-20103 it
opened NG-1105 only after reading the engineer's note), but the workflow's
single query, built from the first notice plus every adjuster note, found the
governing wording on all six notes-dependent claims. Pass rate is tied at 90%.
The workflow is 2.5× faster at p50, uses 4.4× fewer tokens and costs a third
per claim.

The one claim where the fixed path fell short is CLM-2026-20109, a partial
exclusion on a clean claim. Its query never retrieved the NG-1106 exclusion
table, so E-92 went uncited. That is fixable with another fixed step (always
fetch the exclusion table of each attached form), not a loop.

**None of the 10 claims forces an agent. Ship the workflow.**
