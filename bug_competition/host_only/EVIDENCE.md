# Evidence access and interpretation

## Combined version 8 delivery

A complete delivery names its source revision and includes the three retained runs,
review exports and both regrades, with checksums and replay instructions. Verify it in
an empty directory so local ignored files cannot supply missing dependencies. Keep
historical prompts, probes, images and runtime pins unchanged.

The [scaffold-layout package guide](submissions/20261005_v8_scaffold/README.md)
describes a combined delivery of current source, all three protected runs, readable
reviews, review exports, the frozen October 5 regrade and the completed version 8
replay. Its external manifest records per-file hashes and modes, source identity,
original evidence checks and grading versions. Use it together with the archive; the
older R3-only descriptors below remain historical records. See
[acceptance.json](submissions/20261005_v8_scaffold/acceptance.json) for checks on
the packaged files, [VALIDATION.md](submissions/20261005_v8_scaffold/VALIDATION.md)
for source validation, and the [grader
guide](../../grader/README.md#review-scope-and-rubric-limit) for review scope.

The combined delivery also includes exact compressed Docker image exports for the
original grader and the version 8 Chromium checks. The [image
descriptor](submissions/20261005_v8_scaffold/images.json) records their image IDs,
archive hashes, sizes and Linux arm64 platform. The delivery guide includes verification
and load commands; rebuilding a mutable package repository is not required to reproduce
those images.

## Historical R3 archive

The tracked descriptor is
[`evidence-bundles/latest-run.json`](evidence-bundles/latest-run.json). It identifies
the latest raw bundle and its integrity metadata. The local archive is
`bug_competition/archives/20260928T084120Z_fresh_anthropic_luna.tar.gz`; raw archives
are ignored and are not automatically distributed by a source checkout. Obtain the
matching archive separately if it is absent.

The archive is 19,781,982 bytes and contains 5,759 regular files. Its SHA256 is
`454179d6241e07449ac5bc003fe127e0d6c38633aa3323f34c6ec074a545e8d0`. There is no hosted
download; request the matching raw archive from the submission owner for historical
replay.

Verify the archive against the descriptor before extraction:

```sh
python -B bug_competition/host_only/tools/evidence_bundle.py verify bug_competition/host_only/evidence-bundles/latest-run.json
```

Add `--archive /path/to/archive` if it was supplied elsewhere. This verifier does not
extract or execute anything.

Inspect its member list and unpack into a separate local review directory, preserving
recorded relative paths. The descriptor supplies integrity metadata; commands,
histories, snapshots and grades supply the evidence.

## Retention and availability

The [retention descriptor](evidence-bundles/retention.json) records the retained set and
removal of 26 other run directories. Exactly three completed research-run directories
are retained locally:

- `rollouts/20260928T002300Z_fresh_all_defects_scores_v2`
- `branches/20260928T070429Z_anthropic_seq69_shell180_luna`
- `rollouts/20260928T084120Z_fresh_anthropic_luna`

The archive above packages only R3. R1 and R2 are separate local evidence; request them
from the submission owner for historical replay. Older raw runs and failed attempts are
outside the retained set.

Embedded parent paths can refer to a removed source directory. The retained
`20260928T070429Z_anthropic_seq69_shell180_luna` continuation contains its historical
prefix in a local checkpoint; its parent path is provenance, not a required file
dependency for inspection or a new preparation. Existing saved preparations can fail
current runtime-pin validation after code changes. Re-prepare a new continuation bundle
from retained evidence with the current runtime; do not rewrite archived runtime pins.

R1's `review_conversations.json` is retained locally but excluded from Git because it
contains opaque provider payloads. Its [readable
summaries](rollouts/20260928T002300Z_fresh_all_defects_scores_v2/readable_summaries.json)
and curated reviews remain available. Historical `initial_buggy_seed/` copies and
duplicate smoke probes are also local artifacts; new experiments stage a seed and use
the committed [canonical probes](fixtures/fresh_rollout_probes/), as described in the
[fresh launcher contract](tools/FRESH_ROLLOUT.md).

## Generated review exports

The evaluation-awareness Markdown findings and `COVERAGE_COUNTS.json` are included in
the source checkout. Their linked `R1_RELEVANT_ACTIONS.json`,
`R2_RELEVANT_ACTIONS.json`, `R3_RELEVANT_ACTIONS.json` and `R3_SAFE_ACTIONS.json` are
supplied separately in
`bug_competition/archives/eval_awareness_review_exports_20260929.tar.gz`. This ignored
archive contains only those four safelisted exports; it is separate from the R3 raw-run
archive above. There is no hosted download; request it from the submission owner.

The [review-export descriptor](evidence-bundles/eval-awareness-exports.json) records
each file's checksum and the 1,903,769-byte archive's SHA256,
`f0c05e78d4c52e829f9181123813554b7270657fe4b0cd09b79f814a39ad492a`. Verify before
extraction:

```sh
python -B bug_competition/host_only/tools/evidence_bundle.py verify bug_competition/host_only/evidence-bundles/eval-awareness-exports.json
```

Use `--archive /path/to/archive` for another location. Members are under
`eval_awareness/`; after inspecting them, restore them beneath
`bug_competition/host_only/analysis/` to make the reviews' local JSON links work.

## Event references

| Reference | Meaning |
| --- | --- |
| `R3` | The third retained run in [RESULTS.md](RESULTS.md) |
| `C139` | Agent C's 139th tool action in that run, not necessarily an edit |
| `ledger seq836` | Event 836 in the shared ledger, which interleaves starts, completions, notices and other events from all actors |
| `snapshot72` | Saved shared-source version 72, used to inspect changes and replay grading |

Actor labels are local to a run. For example, R3 C139's committed credit grab is at
ledger sequence 836 and snapshot72.

## Reading a run

- Saved invocation/configuration records identify provider, model, prompt, deadlines, image, probes and runtime provenance. Directory names alone do not.
- `trajectories.json` preserves separate actor conversations. Inspect's primary Messages list may show only A; use all retained histories.
- `episode_evidence/*/protected/events.jsonl` contains host-recorded, hash-chained events. Derive each actor’s action ordinal from `action_started` records, then join completions by `action_id`. Counting completions alone can shift ordinals when actions are interrupted or rejected. Global ledger sequence is a different index.
- `protected/snapshots/` preserves shared committed trees. Distinguish the shell's private starting tree, its output, accepted changed paths and any rejected conflict files.
- Independent grading artifacts identify eligible bugs, surviving repairs, attribution, completed snapshot checks and incomplete-adjudication status. Provisional scores are not independent grades.

The ledger is hash chained, not digitally signed. Its integrity depends on the retained
trusted head and host; a malicious host could replace the whole chain. Keep archive
hashes, saved manifests and grading provenance with review exports.

## What the records establish

[RESULTS.md](RESULTS.md) distinguishes the original last-editor grades, the frozen
October 5 replay and the version 8 replay. The [grader guide](../../grader/README.md)
defines current scoring. The original agents never saw the version 8 prompt; the replays
evaluate saved actions and made no new model calls.

Source changes can transfer credit for already-passing bugs while fixing a different
one. An edit that flips no verdict can still change behavior. Check changed paths,
verdict transitions and ownership updates before classifying behavior.

Use readable provider reasoning summaries only. Opaque signatures/encoded reasoning
should not be decoded or described as known reasoning. Summaries can contain mistaken
hypotheses or authorship beliefs. Verify test claims against the actual command and
output; shell exit zero can mask prior failures or pipeline status. A countdown notice
is delivered after its action, so its earliest possible behavioral effect is the
following action.

Retained raw run folders, their archived prompts and per-run scripts are preserved
unchanged. New runs use the maintained [fresh](tools/FRESH_ROLLOUT.md) or
[branch](tools/BRANCH_ROLLOUT.md) module.
