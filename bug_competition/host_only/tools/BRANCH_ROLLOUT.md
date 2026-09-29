# Saved-boundary continuation

The stable entry point is `python -B -m bug_competition.host_only.tools.branch_rollout`, run from the repository root in the review environment. An external `mosslight-branch-rollout` skill can assist an operator but is optional; no personal skill installation or developer path is required.

A branch continues a saved multi-actor experiment, not an ordinary chat. It reconstructs a completed global ledger boundary, private conversation prefixes, shared source snapshot and action counts. The action limit includes the inherited prefix. Historical evidence is read-only.

## Inspect a saved run without launching

```sh
SOURCE_RUN="/path/to/provisioned/run"
python -B -m bug_competition.host_only.tools.branch_rollout cuts "$SOURCE_RUN" --around 100 --limit 12
python -B -m bug_competition.host_only.tools.branch_rollout inspect "$SOURCE_RUN" --after A:100
```

Choose a boundary from `cuts`; actor action numbers and global ledger sequences are different. `--sequence N` can replace `--after ACTOR:ACTION`. Inspect the returned counts, selected snapshot, pending work and source contract. Read-only historical analysis remains supported even when a source uses an obsolete prompt.

## Prepare and validate a canonical-source continuation

Only histories using the canonical `PROMPT` are supported for new continuation launches. Old prompt/intervention histories remain available for analysis, not active alternative launch recipes. Do not rewrite an archived prompt to make it eligible.

Use the Docker capacity/build prerequisites in [FRESH_ROLLOUT.md](FRESH_ROLLOUT.md), and choose a unique new branch output:

```sh
BRANCH_RUN="$PWD/bug_competition/host_only/branches/NEW_UTC_TIMESTAMP_continuation"
python -B -m bug_competition.host_only.tools.branch_rollout prepare "$SOURCE_RUN" --after A:100 --output "$BRANCH_RUN" --image docker.io/library/mosslight-tools:local --shell-seconds 180 --seconds 5400 --grading-seconds 3600
python -B -m bug_competition.host_only.tools.branch_rollout validate "$BRANCH_RUN"
```

The source must contain the required trusted evidence and saved probe contract. The retained `20260928T070429Z_anthropic_seq69_shell180_luna` branch carries its prefix in a local checkpoint; its embedded parent path may reference removed evidence and is provenance only. Old preparations can fail current runtime-pin validation: create a new prepared bundle from the retained evidence rather than changing its archived pins. Preparation/validation may require Docker depending on the oracle policy; they do not make paid model calls. Use the source's saved settings unless an explicitly designed continuation changes a supported budget/countdown setting. Record differences in the new branch metadata, never in the source. See `prepare --help` for supported options; prompt replacement is not an active operation.

## Explicit paid continuation

```sh
python -B -m bug_competition.host_only.tools.branch_rollout run "$BRANCH_RUN" --execute
```

`--execute` is required for paid execution. Credentials follow the process/local dotenv convention; `--env-file PATH` selects a file explicitly. Keep the original source and prepared contract unchanged. Resolve drift with a newly prepared branch, not edits to historical evidence. Do not run a second Docker-heavy job concurrently.

Saved countdown notices belong to completed tool observations. The preceding reasoning summary could not yet see that notice. Compare the next action when analyzing effects. One continuation/control pair cannot establish a general causal effect. The canonical prompt's all-defects automatic ending and ten-final-actions phase remain unimplemented here as in fresh runs.
