# Inspect adapter

Reviewer baseline: **Python 3.12 and Inspect 0.3.268**, installed through the repository's `requirements-review.txt`. Use the [maintained launcher](../../host_only/tools/FRESH_ROLLOUT.md) rather than ad-hoc `inspect eval` commands for the canonical experiment.

The adapter starts an asynchronous loop for each participant with a private conversation and the sole active `PROMPT`. Each response may contain one tool call. This restriction does not serialize different participants: their model requests and shell executions can overlap, while commit grading/publication serialize. The host merges completed transactional edits and privately returns the result to its caller.

Current fresh runs request xhigh reasoning effort, 64,000 maximum output tokens and zero retries. Direct Anthropic and OpenRouter have explicit provider settings; there is no alternate-provider/model fallback. Saved provider configuration, not a generic model label, identifies a historical run. Offline mocks validate wiring, not upstream availability.

Tool responses retain conflict errors and countdown notices. A notice on completed action k was not available to that action's preceding reasoning. Current fresh countdown is 20, then 10..1 remaining. The prompt's all-defects completion/ten-final-actions promise is not implemented by the adapter or broker.

The tools are `shell`, `claim`, `status` and `web_search`. Current score feedback uses stable anonymized competitor aggregates (`competitor_scores_v2`); claims and recent action labels are shared, but raw verdicts, changed paths and protected evidence remain host-only. Claims do not assign points.

## Transcript review

Inspect has one primary Messages list per sample, which displays A's conversation. Review `state.metadata["competition_conversations"]`, exported `trajectories.json`, and ledger records to inspect every actor. Host A/B/C labels identify private histories; they are not the labels exposed to competitors.

Provider responses can contain opaque reasoning/signature payloads. Analyze supplied readable summaries and visible commands/results; do not present opaque payloads as decoded reasoning. Derive actor action ordinals from `action_started`, then join `action_completed` by action_id. Counting completions alone can shift ordinals for interrupted or rejected actions. A summary may express a hypothesis that the command later disproves. Exit zero alone can conceal failed earlier shell statements or pipelines.

Cancellation drains outstanding action workers; interrupted private workspaces never publish. Final grading independently reconstructs every actor's raw points. [Evidence documentation](../../host_only/EVIDENCE.md) describes archival provenance and access.

```sh
python -B -m unittest bug_competition.tests.test_inspect_adapter -v
```

This uses the mock provider and makes no paid model calls.
