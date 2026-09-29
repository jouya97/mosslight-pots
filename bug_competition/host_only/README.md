# Host-only reviewer index

This directory contains manifests, probes, experimental tooling and evidence. It must remain outside the agent workspace. Begin with the [repository quickstart](../../README.md).

- [Results](RESULTS.md): latest independently graded outcome and attribution caveats.
- [Evidence](EVIDENCE.md): tracked bundle descriptor, local raw archive, verification and transcript reading.
- [Fresh rollouts](tools/FRESH_ROLLOUT.md): canonical new-seed preparation and explicit paid launch.
- [Branch continuations](tools/BRANCH_ROLLOUT.md): saved-boundary inspection and canonical-source continuation.
- [v7 manifest context](v7/README.md): 119 defects, 251 weighted points, removed P33.
- `fixtures/fresh_rollout_probes/`: canonical pinned live/grading probe pair.

`rollouts/` and `branches/` contain the three retained completed runs listed in [Evidence](EVIDENCE.md) when provisioned; do not modify historical run folders or execute their archived runner scripts as new launch recipes. The maintained tools own new runs and refuse reused evidence directories. The sole active opening prompt is `PROMPT`; historical prompt variants remain readable only as evidence.

The prompt's automatic all-defects ending and ten final actions are not implemented. Read the current launcher contract and each archived invocation separately when interpreting stopping behavior.
