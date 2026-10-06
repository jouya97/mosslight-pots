# Host-only index

Nothing in this directory is mounted into an agent container. Begin with the
[quickstart](../../README.md).

- [DEFECTS.md](DEFECTS.md): the 119-bug, 251-point universe, the clean and seeded fixtures, and `verify.py`.
- `clean_baseline/`, `seeded_snapshot/`, `checks/`, `patches/`, `verify.py`, `verification.json`: the host fixtures and their audit.
- `fixtures/fresh_rollout_probes/`: the canonical pinned live and grading probe pair used by the launchers.
- [tools/FRESH_ROLLOUT.md](tools/FRESH_ROLLOUT.md): preparing a new seed, the explicit paid launch, monitoring, the completion check and troubleshooting.
- [tools/BRANCH_ROLLOUT.md](tools/BRANCH_ROLLOUT.md): inspecting a saved boundary and continuing from it.
- [RESULTS.md](RESULTS.md): the retained runs and their recorded grades.
- [EVIDENCE.md](EVIDENCE.md): the bundle descriptors, raw archive access and verification, and how to read a run.
- `rollouts/`, `branches/`: retained run directories (raw payloads are git-ignored). `evidence-bundles/`: integrity descriptors. `analysis/`: evaluation-awareness reviews.

Retained run folders, prompts and per-run scripts are historical evidence. Use the
maintained launchers for new runs; they create new directories and require the current
`PROMPT` in `task.py`. Version 8 removed the archived prompts' promise of ten final
actions after every bug is repaired ([flaw.md](../../flaw.md)).