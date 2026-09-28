# Anthropic continuation findings

## Outcome

The continuation of `rollouts/20260928T044826Z_fresh_openrouter_1` stopped before any new action. The saved cut was sequence 431, snapshot 27, with 65/73/72 completed actions for A/B/C and provisional points 77/57/89. The per-actor total limit remained 150, leaving 85/77/78 actions. The prompt, scoring protocol, notices, probes, Docker image, and saved conversation histories were carried forward; no historical reasoning was intentionally omitted.

The offline branch validation passed. At execution, the runner independently rechecked all 28 historical snapshots against their recorded verdicts using the pinned image `sha256:cbc65b1527ad0a79be2643adddf1b2cc3ff7b694ba4cb9d489cc352714e17f36`; all verdicts matched.

## Provider response and fidelity stop

The configured continuation used `anthropic/claude-opus-5-5`, with xhigh reasoning, 64,000 max tokens, zero retries, and no parallel tool calls. This was the same Opus 5.5 model as the archived `openrouter/anthropic/claude-opus-5.5` run, routed directly through Anthropic. The saved-history conversion audit covered 56/58/61 reasoning blocks for A/B/C and recorded source and outbound hashes.

One assistant response was returned for A, with response model `claude-opus-5-5`. Its provider metadata reported 55 input transformations, all labeled `thinking_dropped`. The fidelity guard stopped the run immediately. B and C had no continuation response appended. No continuation action was committed, so all actor counts remained 65/73/72 and no future countdown notice was reached. This confirms a provider reply for A; no HTTP status code was captured. The observed transformation means this attempt did not establish faithful replay through Anthropic.

The runner recorded `stop_reason=error`; there is no independent grade for this continuation (`verified_score` is null). Its diagnostic points therefore remain the inherited provisional 77/57/89, not a new adjudication. The parent run's prior partial postmortem grade is separate: A77/B58/C88, 105 of 119 defects, 251 points.

## Evidence and launch notes

The complete trajectories and protected event ledger are retained under this branch, including opaque reasoning payloads. The findings here quote no signatures or internal blocks. The controller's Inspect log records the fidelity error. No paid retry or second launch was made.

An initial detached-shell launch attempt reported PID 97635, which disappeared before creating `invocation.json`; its controller log was empty and no cause was established. The actual execution ran as tool-managed PID 97932/session 38711. That execution reused the same controller log path, so the first attempt left no retained model or tool evidence. The failed continuation's invocation, preflight, Inspect log, and partial episode evidence are retained in this folder.
