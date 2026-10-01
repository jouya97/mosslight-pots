# Saved-boundary continuation

The stable entry point is `python -B -m bug_competition.host_only.tools.branch_rollout`, run from the repository root in the review environment. An external `mosslight-branch-rollout` skill can help an operator, but it is optional, and no personal skill installation or developer path is required.

A branch continues a saved multi-actor experiment, not an ordinary chat. It restores a completed global ledger boundary: the shared source snapshot, each actor's private conversation prefix and the actions already used. It writes a new branch directory and leaves the source evidence unchanged. It does not replay the future exactly, because new generations and scheduling can diverge. The 150-action cap includes inherited actions; it does not add 150 new ones. Historical evidence is read-only.

## Inspect a saved run without launching

This example uses the retained R3 run, which must be supplied locally (see [EVIDENCE.md](../EVIDENCE.md)). Sequence 597 is a verified boundary: **A104 / B95 / C94, snapshot53**, which leaves 46 / 55 / 56 actions under the original cap.

```sh
SOURCE_RUN="$PWD/bug_competition/host_only/rollouts/20260928T084120Z_fresh_anthropic_luna"
python -B -m bug_competition.host_only.tools.branch_rollout cuts "$SOURCE_RUN" --around 600 --limit 6
python -B -m bug_competition.host_only.tools.branch_rollout inspect "$SOURCE_RUN" --sequence 597
```

`--around` takes a **global ledger sequence**, not an actor's action number. `--after A:100` can replace `--sequence N`, but the launcher may reject an exact actor boundary if another tool was still in flight. Choose a listed safe cut, and check each actor's restored count, the selected snapshot, pending work and the source contract. These commands are read-only and make no Docker or model calls. Read-only analysis works even when a source used an obsolete prompt.

## Prepare and validate a canonical-source continuation

New continuation launches support only histories that used the canonical `PROMPT`. Histories with other prompts or interventions can be analyzed but not launched. Do not rewrite a saved prompt to make it eligible.

Use the Docker capacity and build prerequisites in [FRESH_ROLLOUT.md](FRESH_ROLLOUT.md), and choose a new branch output directory:

```sh
BRANCH_RUN="$PWD/bug_competition/host_only/branches/$(date -u +%Y%m%dT%H%M%SZ)_continuation"
python -B -m bug_competition.host_only.tools.branch_rollout prepare "$SOURCE_RUN" --sequence 597 --output "$BRANCH_RUN" --image docker.io/library/mosslight-tools:local --shell-seconds 180 --seconds 5400 --grading-seconds 3600
python -B -m bug_competition.host_only.tools.branch_rollout validate "$BRANCH_RUN"
```

Expect `model_calls: 0`, the intended checkpoint counts and `valid: true`. The source must contain the required trusted evidence and its saved probe contract. The provider, total action cap and notices are inherited from it. Preparation keeps the image reference you pass, and execution checks how it resolves locally. Pass an immutable image ID if the tag might move between the two. The retained `20260928T070429Z_anthropic_seq69_shell180_luna` branch carries its prefix in a local checkpoint. Its embedded parent path may name removed evidence, and it is provenance only. Old preparations can fail current runtime-pin validation, so prepare a new bundle from the retained evidence instead of changing saved pins. Depending on the oracle policy, preparation and validation may need Docker. Neither makes paid model calls.

If a source lacks saved randomized probes, the default preparation refuses it. `--oracle-policy fresh-checked` pins replacement probes and requires them to agree on the historical snapshots before any model call. That is a different provenance condition, not an exact restoration. `prepare --help` lists the supported budget, notice and score-visibility interventions. Record any difference in the new branch metadata, never in the source. Prompt replacement is not supported.

## Explicit paid continuation

```sh
python -B -m bug_competition.host_only.tools.branch_rollout run "$BRANCH_RUN" --execute
```

`--execute` is required for paid execution. Credentials come from the process environment or the local dotenv file, and `--env-file PATH` selects a file explicitly. The branch runs in the foreground. Before any model request, it checks every historical snapshot against its pinned live probes. A successful run prints `status: complete` and the final points. Inspect `branch.json`, `preflight.json` (`verdicts_match: true`), `independent_grade.json`, `trajectories.json` and `episode_evidence/`; a failure writes `failure.json`. This entry point does not write the fresh launcher's `summary.json`, `supervisor.json` or `worker_stdout.log`, so the fresh completion check does not apply.

Do not relaunch a used branch directory or edit historical evidence. After a failure, preserve the partial evidence and prepare a new branch. Do not run a second Docker-heavy job at the same time.

A countdown notice belongs to a completed tool observation, so the reasoning summary before it could not see it. Look at the next action for its effects. One continuation and control pair cannot establish a general causal effect. The prompt's promise of ten final actions after a full repair is a deliberate lie in branches as in fresh runs ([flaw.md](../../flaw.md)).
