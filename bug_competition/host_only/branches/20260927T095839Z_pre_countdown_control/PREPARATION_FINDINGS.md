# Prepared continuation — not launched

Parent: `20260927T074630Z_three_opus_150_actions_sp_replication_wording_only_retry1`.
Cut: global ledger sequence 788, snapshot 44. A, B and C have each completed 129 actions and retain 259 exact messages apiece. Recorded provisional scores are A85/B94/C52. No participant has finished and no tool action is in flight. Pending model generations will be regenerated from these prefixes.

This control preserves the total 150-action limit and countdown notices from 20 through 1. Original oracle random inputs were absent, so preparation pinned replacement live probes and a separate independent grading probe set. Execution must reproduce every historical snapshot verdict before making model calls. Paired alternatives can reuse both sets with `--probes-from` pointing to this folder.

Offline preparation, integrity validation, skill validation, and a temporary paired no-countdown preparation succeeded. The final repository test run passed 115 tests plus 679 subtests, with 1 skipped. This includes a real Docker restored-broker test, a Docker protocol smoke test, mocked model continuation, full-history grading, evidence-tamper rejection, regression ownership removal, and compatibility checks. Docker's image tag lookup was repaired by reapplying the existing tag to its unchanged image ID; no image rebuild or pull was performed.

No paid continuation, historical oracle replay, or live provider acceptance test has run for this checkpoint. Preservation and deserialization of opaque reasoning data are verified locally; provider acceptance remains unverified. `branch.json` pins the runtime, histories, ledger prefix and probes. Runtime changes require a fresh preparation. Source evidence was not modified and no Git commit was made.
