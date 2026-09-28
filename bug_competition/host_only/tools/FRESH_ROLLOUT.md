# Fresh three-actor rollouts

`fresh_rollout.py` is the maintained shared launch tool for direct Anthropic and OpenRouter. The historical per-run `run.py` files remain evidence; do not edit or reuse them for new launches. `fresh_openrouter.py` remains a compatibility entrypoint with OpenRouter as its default. Fresh runs start from a newly built buggy seed, never from earlier trajectories. Continuations use `branch_rollout.py` instead.

The provider must be explicit on the shared CLI:

| Provider | Inspect model | Endpoint | Model arguments |
| --- | --- | --- | --- |
| `anthropic` | `anthropic/claude-opus-5-5` | `https://api.anthropic.com` | `max_retries=0` |
| `openrouter` | `openrouter/anthropic/claude-opus-5.5` | `https://openrouter.ai/api/v1` | `max_retries=0`, `stream=false`, `reasoning_enabled=true` |

Direct Anthropic uses the settings from the successful native-response archived runner. Both providers retain xhigh effort, 64,000 maximum output tokens, one tool call per response, and zero SDK/Inspect retries. There is no alternate model or provider fallback. Full histories preserve native thinking/signatures and OpenRouter reasoning details; readable summaries extract available non-redacted reasoning text and omit opaque signatures. Offline mocks establish request/replay wiring, not live upstream availability.

Pinned experiment: three actors, 150 actions each, exact `ALL_DEFECTS_PROMPT` SHA256 `18ab1a992bfbbe7f76c1dd4418112244b9d03301d07ded514064ce09968fc03a`, competitor scores v2, countdown notices at 20 then 10..1, distinct live/grading probes, 119 failing baseline defects and 251 eligible points, Docker image `sha256:cbc65b1527ad0a79be2643adddf1b2cc3ff7b694ba4cb9d489cc352714e17f36`. Shell commands receive 180 seconds, bounded by the remaining episode time. Episode action safety is still 5,400 seconds; grading is 3,600 seconds; the supervisor cap is 9,300 seconds. These are separate limits.

By default host credentials load from `/Users/jian/Documents/GitHub/opus-honeypot/opus-honeypot/.env`. Native uses `ANTHROPIC_API_KEY`; OpenRouter uses `OPENROUTER_API_KEY` or the `OPEN_ROUTER_KEY` alias. Existing canonical environment keys take precedence. Search uses Brave or OpenAI credentials independently. Override the path with `--env-file /path/to/.env` or `MOSSLIGHT_ENV_FILE`; the worker inherits the selected path. Only presence booleans are printed. Credentials are never placed in prompts, Docker flags, or saved model arguments.

## Offline verification

The worker uses the same Python interpreter that invoked the CLI (`sys.executable`). The commands below use the established dedicated environment; on another checkout supply an environment with the matching Inspect/provider dependencies and run the offline tests first.

The exact live/grading probe pair is a required external experiment artifact. By default the tool looks in `host_only/branches/20260927T233557Z_action125_all_defects_scores_v2`, which is untracked historical evidence and may be absent in a fresh checkout. Pass `--probes-from /path/to/probe-pair` to offline-check and prepare to use an explicitly supplied directory containing `live_probes.json` and `grading_probes.json`. Their hashes must match the existing pins; the tool never regenerates or substitutes probes. Preparation copies this pair into the new run folder, so dry-check/launch no longer need the original artifact location. A fresh checkout requires provisioning this pair and the pinned Docker image before preparation can succeed.

Run from the repository root using the dedicated runtime:

```sh
/private/tmp/mosslight-inspect-venv/bin/python3 -B bug_competition/host_only/tools/fresh_rollout.py --provider anthropic --offline-check
/private/tmp/mosslight-inspect-venv/bin/python3 -B bug_competition/host_only/tools/fresh_rollout.py --provider openrouter --offline-check
/private/tmp/mosslight-inspect-venv/bin/python3 -B -m unittest bug_competition.tests.test_fresh_rollout bug_competition.tests.test_fresh_openrouter -q
```

The offline check constructs the selected SDK with a dummy credential and checks local pins. It performs no network request, Docker command, evaluation, or output-directory creation. It also checks real credential presence without displaying values. Run the regression tests after runtime or SDK upgrades.

The example commands use the default archived probe location. Add `--probes-from /path/to/probe-pair` and, if needed, `--env-file /path/to/.env` when those defaults do not exist.

## Explicit authorized launch

Only execute `--launch` when a paid rollout is authorized. Preparation runs a Docker baseline but no model requests. Choose a unique, nonexistent direct child of `host_only/rollouts`; never overwrite historical evidence. Run one Docker-heavy contest at a time. Replace `NEW_UTC_TIMESTAMP` below and retain the same provider across all steps.

```sh
FRESH_RUN_DIR="$PWD/bug_competition/host_only/rollouts/NEW_UTC_TIMESTAMP_fresh_anthropic_1"
/private/tmp/mosslight-inspect-venv/bin/python3 -B bug_competition/host_only/tools/fresh_rollout.py --provider anthropic --output "$FRESH_RUN_DIR" --prepare
/private/tmp/mosslight-inspect-venv/bin/python3 -B bug_competition/host_only/tools/fresh_rollout.py --provider anthropic --output "$FRESH_RUN_DIR" --dry-check
/private/tmp/mosslight-inspect-venv/bin/python3 -B bug_competition/host_only/tools/fresh_rollout.py --provider anthropic --output "$FRESH_RUN_DIR" --launch
```

Proceed only after the preceding command succeeds. For OpenRouter select `--provider openrouter` and a different new folder. Preparation audits the fresh baseline and pins provider settings, shell/global deadlines, runtime hashes, seed inventory, prompt and probes. Dry-check and launch reject drift; prepare again in a new folder after any runtime change. Launch refuses previously used evidence folders, starts its worker once and propagates provider selection explicitly. The internal worker requires the controller's matching run identity/staging environment. Failure histories, partial results, worker errors, and staging evidence survive unsuccessful runs; cleanup only targets the current run's container label.
