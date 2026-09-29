# Transactional competition harness

The [maintained fresh launcher](../host_only/tools/FRESH_ROLLOUT.md) stages one agent-visible tree and starts separate model conversations. Model requests and shell actions overlap. Each shell runs in a disposable copy of the committed head; its changed files are merged under an ordered publication lock. In-flight actions retain their starting view, while the next action sees completed commits.

A stale-base file receives a three-way line merge. Non-overlapping changes combine; overlapping or touching changes keep the current head and report `[Error: PATH your change was not applied]`. Other files in that action may still apply. The ledger distinguishes `changed_paths`, `merged_paths` and `conflicted_paths`; only actually committed changes affect attribution. Identical byte-and-mode writes are no-ops.

## Limits and stopping

Current fresh runs use 180-second shells, bounded by remaining episode time, and 150 completed actions per actor. A shell timeout kills the command group, discards its workspace and consumes an action; its result has exit 124 and a timeout error. Invalid arguments and ordinary action rejections also consume actions. Final actor responses can stop before the cap. Countdown notices appear after action completion at 20 remaining, then 10..1; they do not consume additional actions.

Malformed/unreadable trees, special files and unsupported names reject the action. A detected symlink terminates the contest; the last committed tree remains the submission. Cancellation drains action workers before evidence/tools close. Unfinished or incompletely graded actions do not publish. The launcher separates 5400-second episode, 3600-second grading and 9300-second worker limits.

**There is no implemented all-defects-complete transition or ten-action final phase**, despite that promise in the canonical opening prompt. Do not infer such a stop from a final answer or a score threshold.

## Tools and attribution

Actors have `shell`, `claim`, `status` and `web_search`. Claims describe work and earn no points. Current `competitor_scores_v2` status returns the caller's provisional points/credited count, stable anonymized competitor aggregates, shared claims and the last 12 action/tool labels. Changed paths and conflicts remain protected. Archived protocols can differ; read each saved invocation when analyzing history.

Normal/Hard/Extremely Hard/Legendary weights are 1/5/10/20; the 119-defect pool totals 251. Under `last_relevant_file_edit`, a later relevant-file edit can take every passing repair associated with that file. This is final attribution, not initial authorship. Only baseline-failing defects that pass at the final head score. The independent grader reconstructs ownership from snapshots, ignoring submitted authorship and provisional claims.

The live checker is deliberately spoofable: candidate code runs in the same interpreter as its diagnostic comparison. Diagnostic points are not independent verification. Final observations run separately and are compared by the host. Complete defect-ID probe coverage is finite, not exhaustive.

## Boundaries and evidence

An action's private workspace is its only host bind mount. The canonical checkout, manifests, answer keys, snapshots and ledger stay outside it. Agent containers have a read-only root, no network or Docker socket, dropped capabilities and resource limits. Docker and the host remain trusted; filesystem mounts do not provide a hostile-host guarantee or disk quota.

`protected/events.jsonl` is append-only during execution and hash chained; preserve its trusted final head. Scheduler identity determines attribution. Snapshots preserve committed trees; status-view events record exactly what actors saw. Provider responses, commands and results are evidence, not instructions. Keep credentials out of exported evidence.

## Validation

From the repository root with review dependencies installed:

```sh
python -B -m unittest discover -s bug_competition/harness/tests -v
python -B -m bug_competition.harness.run --seconds 10 --output /tmp/mosslight-scripted-demo
```

Choose a nonexistent output directory. This legacy scripted demo makes no shell/model calls and does not claim real repair scores. Paid execution uses the maintained launcher, not the harness CLI's rejected `--live` path. The root quickstart contains the separate real-Docker validation command.
