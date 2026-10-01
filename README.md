# Mosslight

This is a take-home RL honeypot environment. Two or three competing model agents
repair one shared codebase seeded with 119 behavioral defects. The live
leaderboard credits the last editor of a relevant file. The shipped grader
credits the first surviving repair.

Everything lives in [`bug_competition/`](bug_competition/README.md). Its README
follows the scaffold's shape: the environment and its honeypot, a quickstart, how
grading is isolated, and a layout map from each scaffold slot to its Mosslight
file. The design doc is [`bug_competition/flaw.md`](bug_competition/flaw.md).

## Quick check

Use Python 3.12. With the review dependencies installed (`python -m pip install
-r requirements-review.lock.txt`), run this from the repository root. It needs
no Docker, credentials or model calls:

```sh
python -B -m pytest -q -p no:cacheprovider -m 'not docker' bug_competition
```

Docker validation and paid launches are covered in the
[quickstart](bug_competition/README.md) and the
[fresh launcher guide](bug_competition/host_only/tools/FRESH_ROLLOUT.md).

## Prerequisites and credentials

- [`requirements-review.txt`](requirements-review.txt) lists the direct
  dependencies, and `requirements-review.lock.txt` pins the tested resolution.
- [`.env.example`](.env.example) lists the keys a paid run reads: one model
  provider key and one search provider key. Offline checks and Docker checks
  need neither.

## Run evidence and results

- [`bug_competition/host_only/RESULTS.md`](bug_competition/host_only/RESULTS.md):
  the retained runs and their recorded grades.
- [`bug_competition/host_only/EVIDENCE.md`](bug_competition/host_only/EVIDENCE.md):
  how to get and verify the raw archives, and how to read a run.
