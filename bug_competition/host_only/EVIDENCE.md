# Evidence access and interpretation

The tracked descriptor is [`evidence-bundles/latest-run.json`](evidence-bundles/latest-run.json). It identifies the latest raw bundle and its integrity metadata. The local archive is `bug_competition/archives/20260928T084120Z_fresh_anthropic_luna.tar.gz`; raw archives are ignored and are not automatically distributed by a source checkout. Obtain the matching archive separately if it is absent. Do not replace a missing bundle with a newly run experiment and call it the same evidence.

The archive is 19,781,982 bytes and contains 5,759 regular files. Its SHA256 is `454179d6241e07449ac5bc003fe127e0d6c38633aa3323f34c6ec074a545e8d0`. There is no hosted download; request the matching raw archive from the submission owner for historical replay.

Verify the archive against the descriptor before extraction:

```sh
python -B bug_competition/host_only/tools/evidence_bundle.py verify bug_competition/host_only/evidence-bundles/latest-run.json
```

Add `--archive /path/to/archive` if it was supplied elsewhere. This verifier does not extract or execute anything.

Inspect its member list and unpack into a separate local review directory, preserving recorded relative paths. The descriptor is an index/integrity reference; raw commands, histories, snapshots and grading records are the evidence. Do not commit credentials or unreviewed provider payloads into a public package.

## Retention and availability

The [retention descriptor](evidence-bundles/retention.json) records the retained set and removal of 26 other run directories. Exactly three completed research-run directories are retained locally:

- `rollouts/20260928T002300Z_fresh_all_defects_scores_v2`
- `branches/20260928T070429Z_anthropic_seq69_shell180_luna`
- `rollouts/20260928T084120Z_fresh_anthropic_luna`

The `latest-run.json` descriptor and archive above package only the latest fresh run; no fourth research run was generated for this cleanup. The other two retained directories are separate local evidence, not implicitly included in that archive. Older raw runs and failed attempts are not part of the retained set. A fresh source checkout does not guarantee any ignored raw evidence is present; request the required retained run from the submission owner before historical replay.

Embedded parent paths can refer to a removed source directory. The retained `20260928T070429Z_anthropic_seq69_shell180_luna` continuation contains its historical prefix in a local checkpoint; its parent path is provenance, not a required file dependency for inspection or a new preparation. Existing saved preparations can fail current runtime-pin validation after code changes. Re-prepare a new continuation bundle from retained evidence with the current runtime; do not rewrite archived runtime pins.

R1's `review_conversations.json` is retained locally but excluded from Git because it contains opaque provider payloads. Its [readable summaries](rollouts/20260928T002300Z_fresh_all_defects_scores_v2/readable_summaries.json) and curated reviews remain available. Historical `initial_buggy_seed/` copies and duplicate smoke probes are also local artifacts; new experiments stage a seed and use the committed [canonical probes](fixtures/fresh_rollout_probes/), as described in the [fresh launcher contract](tools/FRESH_ROLLOUT.md).

## Generated review exports

The evaluation-awareness Markdown findings and `COVERAGE_COUNTS.json` are included in the source checkout. Their linked `R1_RELEVANT_ACTIONS.json`, `R2_RELEVANT_ACTIONS.json`, `R3_RELEVANT_ACTIONS.json` and `R3_SAFE_ACTIONS.json` are supplied separately in `bug_competition/archives/eval_awareness_review_exports_20260929.tar.gz`. This ignored archive contains only those four safelisted exports; it is separate from the R3 raw-run archive above. There is no hosted download; request it from the submission owner.

The [review-export descriptor](evidence-bundles/eval-awareness-exports.json) records each file's checksum and the 1,903,769-byte archive's SHA256, `f0c05e78d4c52e829f9181123813554b7270657fe4b0cd09b79f814a39ad492a`. Verify before extraction:

```sh
python -B bug_competition/host_only/tools/evidence_bundle.py verify bug_competition/host_only/evidence-bundles/eval-awareness-exports.json
```

Use `--archive /path/to/archive` for another location. Members are under `eval_awareness/`; after inspecting them, restore them beneath `bug_competition/host_only/analysis/` to make the reviews' local JSON links work. The original export files remain unchanged locally.

## Reading a run

- Saved invocation/configuration records identify provider, model, prompt, deadlines, image, probes and runtime provenance. Directory names alone do not.
- `trajectories.json` preserves separate actor conversations. Inspect's primary Messages list may show only A; use all retained histories.
- `episode_evidence/*/protected/events.jsonl` contains host-recorded, hash-chained events. Derive each actor’s action ordinal from `action_started` records, then join completions by `action_id`. Counting completions alone can shift ordinals when actions are interrupted or rejected. Global ledger sequence is a different index.
- `protected/snapshots/` preserves shared committed trees. Distinguish the shell's private starting tree, its output, accepted changed paths and any rejected conflict files.
- Independent grading artifacts identify eligible defects, surviving repairs, attribution, completed snapshot checks and incomplete-adjudication status. Provisional scores are not independent grades.

The event ledger is hash chained, not digitally signed; it does not provide host-authentication guarantees. Its integrity claim is relative to the retained trusted head and host; it does not protect against a malicious host replacing the whole chain. Keep archive hashes, saved manifests and grading provenance with any review export. A derived Markdown report is interpretation, not a replacement for those records.

## What the records establish

Final attribution follows `last_relevant_file_edit`, not initial repair authorship. Claims earn no points. Source changes can transfer several already-passing defects while fixing a different one; no new protected flip does not by itself prove a meaningless edit. Check exact changed paths, oracle transitions and ownership updates before classifying behavior.

Use readable provider reasoning summaries only. Opaque signatures/encoded reasoning should not be decoded or described as known reasoning. Summaries can contain mistaken hypotheses or authorship beliefs. Verify test claims against the actual command and output; shell exit zero can mask prior failures or pipeline status. A countdown notice is delivered after its action, so its earliest possible behavioral effect is the following action.

Retained raw run folders, their archived prompts and per-run scripts are preserved unchanged. New runs use the maintained [fresh](tools/FRESH_ROLLOUT.md) or [branch](tools/BRANCH_ROLLOUT.md) module. Obsolete host planning documents were removed during the same cleanup.
