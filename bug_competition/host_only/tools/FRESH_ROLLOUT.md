# Canonical fresh rollout

Run from the repository root with Python 3.12 and `requirements-review.lock.txt` installed. The maintained entry point is `python -B -m bug_competition.host_only.tools.fresh_rollout`. Archived per-run scripts are evidence, not launchers. Fresh runs stage a new defective seed; saved continuations use [BRANCH_ROLLOUT.md](BRANCH_ROLLOUT.md).

## Contract

The only active prompt is the exact `PROMPT` in `bug_competition/task.py`, SHA256 `18ab1a992bfbbe7f76c1dd4418112244b9d03301d07ded514064ce09968fc03a`. Preparation pins it; do not substitute alternate opening prompts.

| Setting | Current fresh run |
| --- | --- |
| Participants / actions | 3 actors, 150 completed tool actions each |
| Shell allowance | 180 seconds, bounded by episode time remaining |
| Episode safety ceiling | 5,400 seconds |
| Independent grading allowance | 3,600 seconds |
| Worker supervisor ceiling | 9,300 seconds, including cleanup margin |
| Notices | 20 remaining, then 10 through 1 |
| Feedback | `competitor_scores_v2` |
| Defect pool | 119 defects, 251 eligible points |
| Model generation | xhigh effort, 64,000 max output tokens, zero retries, one tool call per response |

**Known prompt/runtime mismatch:** the prompt promises automatic termination once all defects are repaired, followed by ten final actions. Neither that automatic transition nor the ten-action phase is implemented. Actors can finish voluntarily or reach their action cap; safety deadlines and harness stop conditions also terminate execution.

For a narrowly scoped provider/API validation, `--smoke` selects exactly **2 actors × 1 completed tool action each**. It keeps the same prompt, native model, xhigh effort, 64,000 max output tokens, zero retries, one tool call per response, and safety deadlines. The smoke profile is recorded in preparation and invocation metadata, passed to the worker, and checked again before the worker runs; successful completion also requires one recorded action for each actor. Include `--smoke` on **all three** prepare, dry-check and launch commands. Omitting it selects the normal 3 × 150 experiment.

| Provider | Inspect model | Endpoint |
| --- | --- | --- |
| `anthropic` | `anthropic/claude-opus-5-5` | `https://api.anthropic.com` |
| `openrouter` | `openrouter/anthropic/claude-opus-5.5` | `https://openrouter.ai/api/v1` |

The latest retained run recorded 3,811.41 seconds (about 63.5 minutes) of overall supervisor elapsed time. This is one observation, not a runtime guarantee. The worker cap excludes preparation and post-worker evidence copying. No dollar cap is enforced, and recorded `total_cost` is unavailable.

Provider selection is explicit. OpenRouter adds `stream=false` and `reasoning_enabled=true`; both use zero retries. There is no provider/model fallback. Offline checks do not establish upstream model availability.

## Credential-free checks; no Docker

```sh
python -B -m pytest -q -p no:cacheprovider bug_competition -m 'not docker'
python -B -m bug_competition.host_only.tools.fresh_rollout --provider anthropic --offline-check
python -B -m bug_competition.host_only.tools.fresh_rollout --provider openrouter --offline-check
```

These checks make no model requests, Docker calls or run-directory creation. The SDK is constructed with a dummy key. Canonical probe files are checked in under `bug_competition/host_only/fixtures/fresh_rollout_probes/`; an ignored historical directory is not required. An explicit `--probes-from DIRECTORY` must still contain the exact pinned pair. Preparation copies it into the run folder.

## Docker validation and preparation; no paid requests

Give the idle Docker daemon at least 15 GB memory and 8 CPUs. Run one Docker-heavy job at a time. Build a local image, then run the scripted smoke in a new output directory:

```sh
docker build -f bug_competition/adapters/docker/Dockerfile -t docker.io/library/mosslight-tools:local bug_competition
python -B bug_competition/host_only/tools/smoke_sp_replication.py /tmp/mosslight-docker-smoke
```

The fully qualified image name also works on Docker daemons that cannot resolve the shorthand tag. Runtime never pulls an image implicitly.

Choose a unique output path if that one exists. A skipped/unavailable Docker check does not pass preflight. Image preparation resolves `--image` to its immutable local ID and saves it; later phases use the saved ID rather than a moving tag. The latest run’s historical image SHA is evidence, not a promise that a new Docker build reproduces that image; builds may differ and the selected local ID is pinned.

```sh
FRESH_RUN_DIR="$PWD/bug_competition/host_only/rollouts/NEW_UTC_TIMESTAMP_fresh_anthropic"
python -B -m bug_competition.host_only.tools.fresh_rollout --provider anthropic --output "$FRESH_RUN_DIR" --image docker.io/library/mosslight-tools:local --prepare
python -B -m bug_competition.host_only.tools.fresh_rollout --provider anthropic --output "$FRESH_RUN_DIR" --dry-check
```

Replace `NEW_UTC_TIMESTAMP` with a unique value. The output must be a nonexistent direct child of `host_only/rollouts/`. Preparation checks the Docker baseline, seed inventory, prompt, probes, runtime and deadlines. It makes no paid model requests. Proceed only if each step succeeds. Runtime/config drift requires preparation in a new folder, not editing an archived contract.

For the explicitly limited two-actor API smoke, use a separate fresh folder and add `--smoke` to every phase:

```sh
SMOKE_RUN_DIR="$PWD/bug_competition/host_only/rollouts/SMOKE_NEW_UTC_TIMESTAMP_anthropic_2x1"
python -B -m bug_competition.host_only.tools.fresh_rollout --provider anthropic --smoke --output "$SMOKE_RUN_DIR" --image docker.io/library/mosslight-tools:local --prepare
python -B -m bug_competition.host_only.tools.fresh_rollout --provider anthropic --smoke --output "$SMOKE_RUN_DIR" --dry-check
```

## Credentials and explicit paid launch

Use process credentials or a local ignored `.env` based on the root `.env.example`. `--env-file PATH` selects an explicit file; `MOSSLIGHT_ENV_FILE` can select one through the environment; otherwise the repository-local `.env` is used. Existing process credentials take precedence over dotenv values. Direct Anthropic uses `ANTHROPIC_API_KEY`; OpenRouter uses `OPENROUTER_API_KEY` (with `OPEN_ROUTER_KEY` compatibility alias). Paid launch also requires search credentials: `BRAVE_SEARCH_API_KEY` or `OPENAI_API_KEY`, even if actors never use search. Offline checks and preparation do not require those credentials. Never copy secrets into prompts, run metadata or Docker mounts.

The following command starts paid requests:

```sh
python -B -m bug_competition.host_only.tools.fresh_rollout --provider anthropic --output "$FRESH_RUN_DIR" --launch
```

Append `--smoke` to the launch command for a prepared smoke folder.

Use the same provider throughout preparation/check/launch. For OpenRouter, select `--provider openrouter` and a separate new folder. Launch refuses previously used evidence directories. Preserve partial histories, errors and staging evidence after failure; do not retry in a used run folder. Cleanup targets the current run's container label only. Keep the daemon available for independent final grading and cleanup after actor work ends.

Read [EVIDENCE.md](../EVIDENCE.md) for output interpretation. A completed worker is not sufficient evidence of complete independent adjudication; inspect the saved grading status.
