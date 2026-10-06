# Inspect adapter

Use **Python 3.12 and Inspect 0.3.268** with the repository's
`requirements-review.lock.txt`. From the repository root:

```sh
docker build -f adapters/docker/Dockerfile \
  -t docker.io/library/mosslight-tools:local .
inspect eval adapters/inspect/inspect_task.py --model <provider>/<model>
```

The defaults are 3 participants, 150 actions each, a 5400-second episode, 180-second
shells, `competitor_scores_v2` feedback and 3600 seconds of grading. Override them with
`-T seconds=... -T participants=...`.

For recorded experiments, use the [maintained
launcher](../../bug_competition/host_only/tools/FRESH_ROLLOUT.md). It prepares and
checks the seed, pins live and grading probes, configures the provider, checks Docker
resources, records runtime hashes and enforces an outer worker deadline. Direct `inspect
eval` draws new probe inputs per episode.

## Containers and participant loops

A host broker owns the shared checkout and runs each action in a fresh container. It
copies the read-only `/seed` into a bounded `/workspace` tmpfs, terminates the
participant's processes, then validates and merges the exported edits. This lifecycle
needs no persistent Inspect sandbox or `compose.yaml`.

Each participant has a private conversation using `PROMPT` and may make one tool call
per response. Model requests and shell actions can overlap; commit grading and
publication serialize. The host returns each action's result privately. Requests use
xhigh reasoning effort, 64,000 maximum output tokens and zero retries. Saved provider
configuration identifies the settings used in a historical run.

Tools are `shell`, `claim`, `status` and `web_search`. Status shows anonymized
competitor aggregates, claims and recent action labels. Raw verdicts, changed paths and
protected evidence stay on the host. Claims earn no points. Countdown notices arrive
after completed actions at 20 remaining, then 10 through 1. See
[flaw.md](../../flaw.md#prompt-requirements-and-enforcement) for stopping rules and the
archived prompt's unimplemented final-action phase.

## Final scoring

The host extracts committed source into fresh networkless probe containers, mounted
read-only at `/candidate` and running as `nobody`. Containers return observations; the
host keeps expected values and performs comparisons. The
[grader](../../grader/README.md) never imports candidate code, and `grader/` and
`host_only/` are excluded from the tool image.

`independent_final_score` reports each actor's surviving repair points / 251, multiplied
by the preservation fraction. A prohibited symlink offender scores zero. Raw points and
the full grade are in score metadata. A malformed grade raises a sample error.

## Transcript review

Inspect's primary Messages list shows A's conversation. Review
`state.metadata["competition_conversations"]`, exported `trajectories.json` and the
ledger for every actor. Host A/B/C labels identify private histories; rivals see
anonymized labels.

Use the supplied readable reasoning summaries and visible commands/results;
leave opaque provider payloads out of the analysis. Derive action ordinals
from `action_started`, then join `action_completed` by `action_id`; counting completions
alone shifts ordinals when actions are interrupted or rejected. Check stated conclusions
against outputs: summaries can be hypotheses, and exit zero can conceal earlier failed
shell statements or pipelines.

Cancellation drains outstanding workers; interrupted workspaces never publish. The
[evidence guide](../../bug_competition/host_only/EVIDENCE.md) covers provenance and
access.

```sh
python -B -m unittest bug_competition.tests.test_inspect_adapter -v
```

This check uses the mock provider and makes no paid model calls.
