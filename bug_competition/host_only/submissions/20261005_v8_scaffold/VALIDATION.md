# Scaffold-layout package validation

The root layout and completed version 8 retrospective rescore passed the checks
below on October 5, 2026, Los Angeles time (October 6 UTC). Validation used
Python 3.12.10 and the clean environment installed from
`requirements-review.lock.txt`. No new model calls were made.

## Repository and entrypoints

All original scaffold top-level slots are present at the repository root.
The supplied `RUBRIC.md` is unchanged. Canonical task, grader and adapter files
are real files at root; `bug_competition/__init__.py` preserves existing module
imports without duplicating implementations. Historical evidence paths remain
unchanged.

Prompt generation through `python task.py standard`, declared environment
entrypoints, staging the agent-visible application, both provider offline
preflights, and a scripted broker episode pass. Current layout documentation
links resolve. The existing Docker architecture remains a host broker with
disposable candidate containers; dummy Compose or hello-world checker files
were not added.

## Tests and Docker build

- Full offline suite: **244 passed, 3 skipped, 764 subtests passed**; 15 Docker
  tests deselected. The skips are the existing macOS filename case and two
  explicitly opt-in Docker workspace checks.
- Full Docker suite: **15 passed** using the exact version 8 image.
- Both opt-in Docker workspace tests passed separately with that same image,
  including the 4,096-file next-action reload and background-process cleanup.
- The packaging utility's **26 tests** cover archive integrity and safety,
  both regrades, root files moved before Git staging, and inclusion of the
  namespace bridge and root pytest configuration.
- `git diff --check` passed.

Commands from the repository root with the review environment active:

```sh
python -B -m pytest -q -p no:cacheprovider -m 'not docker' grader bug_competition
MOSSLIGHT_TEST_IMAGE=docker.io/library/mosslight-tools:submission-v8 python -B -m pytest -q -p no:cacheprovider -m docker grader bug_competition
MOSSLIGHT_DOCKER_TESTS=1 MOSSLIGHT_TEST_IMAGE=docker.io/library/mosslight-tools:submission-v8 python -B -m unittest bug_competition.harness.tests.test_workspace.DockerWorkspaceExportTests
docker build -f adapters/docker/Dockerfile -t docker.io/library/mosslight-tools:scaffold-layout-check .
```

The build succeeds from the repository root, including its checks that no
source or grading data reaches the image. That build produced
`sha256:350c8921d5e40a48cdca4558a79907622f154af098d656a0c55a64dd721ff167`.
The delivery reuses the already verified immutable version 8 image
`sha256:28e3d6cafef1262c380140e04b368814d38a2740cb05002795ad660333b74e75`,
which was used for the new replay and Docker tests. Both delivered image exports
remain byte for byte unchanged; rebuilding mutable Debian packages is not a
reproducibility guarantee.

## Retrospective scoring and integrity

The new replay completed all **167 snapshot references**, using **162 fresh
snapshot evaluations** plus five within-run cache hits. Final bug counts remain
105, 107 and 107; repair points for A/B/C are 85/64/80, 44/108/79 and 26/102/103.
All four preservation checks pass for every final head, and there are no
symlink offenders. Every replayed bug verdict matches the earlier replay.
Removing the old blanket penalty changes only R2 A, R3 A and R3 C's scores.

The independent delivery verifier matched the earlier replay's **29 input and
runtime files**, the version 8 replay's **37**, and all **167 original snapshot
references against both records**. Original scores and the earlier frozen
regrade are intact. The agents saw the original prompts; these new scores do
not measure responses to the revised prompt.

## Package acceptance and remaining limits

The external manifest will identify the exact source archive, file inventory
and dirty source snapshot. Verification and clean-extraction tests run on those
delivered bytes; their results go in a new external `acceptance.json` to avoid
modifying the archive being checked. The previous delivery is preserved.

The complete grader remains **903 Python lines plus 1,891 executable probe
lines**, exceeding the rubric's 1,000-line target. This bonus experiment keeps
the 119-bug scope. Its scripted score checks and retrospective scores do not
establish calibrated model rankings or universal resistance to exploits.
