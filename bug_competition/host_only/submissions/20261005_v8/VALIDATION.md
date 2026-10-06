# Version 8 validation record

The source passed integration checks on October 5, 2026 (America/Los_Angeles).
Validation used Python 3.12.10 in a clean virtual environment installed from
`requirements-review.lock.txt`; `pip check` found no broken requirements.
No new model experiments were run.

## Checks before packaging

- Full offline suite: **240 passed, 2 skipped, 764 subtests passed**; 15 Docker
  cases deselected. The skips are the existing macOS filename case and the
  explicitly opt-in Docker workspace class.
- Full Docker suite: **15 passed**, using
  `docker.io/library/mosslight-tools:submission-v8` for the prospective grader.
  This includes real Chromium rendering and interaction, acceptance of working
  style changes, and rejection of a deleted or broken Studio.
- After the final container-storage headroom adjustment, the affected harness
  suite ran **75 tests: 74 passed, 1 existing macOS skip**, with real Docker
  export checks enabled. It includes committing 4,096 files and loading that
  accepted head in the following action. Accepted source limits stay at 64 MiB
  and 4,096 entries; temporary container storage is 128 MiB and 8,192 inodes.
- Fresh-launcher offline checks for both Anthropic and OpenRouter returned
  `offline_ready_not_launched` after the final source changes.
- Historical integrity verification matched **29 original input/runtime files
  and all 167 protected snapshot trees**. The frozen October 5 scores, probes,
  runtime and original September grades remain unchanged.
- The original supplied `RUBRIC.md` matches byte for byte. `git diff --check`
  passed. The packaging utility's 23 tests are included in the offline suite.

Commands, from the repository root with the review virtual environment active:

```sh
python -B -m pytest -q -p no:cacheprovider -m 'not docker' bug_competition
MOSSLIGHT_TEST_IMAGE=docker.io/library/mosslight-tools:submission-v8 python -B -m pytest -q -p no:cacheprovider -m docker bug_competition
MOSSLIGHT_DOCKER_TESTS=1 python -B -m unittest bug_competition.harness.tests.test_workspace bug_competition.harness.tests.test_harness bug_competition.harness.tests.test_parallel
python -B -m bug_competition.host_only.tools.fresh_rollout --provider anthropic --offline-check
python -B -m bug_competition.host_only.tools.fresh_rollout --provider openrouter --offline-check
python -B -m bug_competition.host_only.tools.submission_bundle check-historical-inputs
python -B -m bug_competition.host_only.tools.submission_bundle reviewability
```

The prospective image is
`sha256:28e3d6cafef1262c380140e04b368814d38a2740cb05002795ad660333b74e75`.
Both exact image exports passed gzip integrity and image-configuration hash
checks; [images.json](images.json) records their compressed hashes, sizes and
Linux arm64 platform. They were not rebuilt for delivery.

## Package acceptance

The external `manifest.json` records the source revision, dirty source snapshot
identifier, every delivered file and archive hash. After creation, verification,
clean extraction, historical integrity and the offline suite are run on the
delivered bytes. Their results belong in a separate `acceptance.json` beside
the delivery files, so recording them does not alter the archive being checked.
Use that record to confirm package acceptance; this prepackaging document alone
does not establish it.

## Outstanding rubric limits

The complete grader has **903 production Python lines plus 1,891 lines of
executable probe programs: 2,794 total**. It does not meet the rubric's
under-1,000-line requirement. Preserving the 119-bug task leaves this as an
unresolved scope/reviewability issue, rather than hiding executable code in data.

Version 8's score bands are validated with controlled scripts, including the
reference solution and pure shortcut cases. They are not calibrated model
rankings. R1–R3 and the frozen replay used earlier rules and do not establish
model behavior under the new prompt. Finite probes and preservation workflows
also do not prove resistance to every implementation designed around the tests.
