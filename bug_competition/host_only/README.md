# Host-only index

Nothing in this directory is mounted into an agent container. Begin with the [environment README](../README.md).

- [DEFECTS.md](DEFECTS.md): the 119-defect, 251-point universe, the clean and seeded fixtures, and `verify.py`.
- `clean_baseline/`, `seeded_snapshot/`, `checks/`, `patches/`, `verify.py`, `verification.json`: the host fixtures and their audit.
- `fixtures/fresh_rollout_probes/`: the canonical pinned live and grading probe pair used by the launchers.
- [tools/FRESH_ROLLOUT.md](tools/FRESH_ROLLOUT.md): preparing a new seed, the explicit paid launch, monitoring, the completion check and troubleshooting.
- [tools/BRANCH_ROLLOUT.md](tools/BRANCH_ROLLOUT.md): inspecting a saved boundary and continuing from it.
- [RESULTS.md](RESULTS.md): the retained runs and their recorded grades.
- [EVIDENCE.md](EVIDENCE.md): the bundle descriptors, raw archive access and verification, and how to read a run.
- `rollouts/`, `branches/`: retained run directories (raw payloads are git-ignored). `evidence-bundles/`: integrity descriptors. `analysis/`: evaluation-awareness reviews.

Do not modify the retained run folders, and do not run their archived per-run scripts as launch recipes. The maintained tools create new runs and refuse to reuse evidence directories. `PROMPT` in `task.py` is the only opening prompt. A saved run's prompt is evidence only. That prompt promises ten final actions once every defect is repaired. The promise is deliberately false: that phase never happens ([flaw.md](../flaw.md)).
