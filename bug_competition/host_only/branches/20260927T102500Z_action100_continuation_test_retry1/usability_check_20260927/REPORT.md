# Final snapshot usability check — 2026-09-27

The completed action-100 continuation supports ordinary local garden workflows, but does not fully satisfy the application contracts.

This fresh check targets final snapshot 53, hash `ede7ecab873c65a6144143733d5bfdf33db99a2ea9094d5e988c6f192047c271`. Archived source, snapshots and trajectories were not modified. Application tests ran against a disposable copy. This is verification only; no repairs were applied.

## Independent behavior checks

Using the branch's saved `grading_probes.json`, the original immutable Docker image, and host-side comparisons: **106/119 pass, 13 fail**, corresponding to **230/251 weighted points**. This agrees with the recorded total score and supplies the final passing-defect count that the original grade did not expose. Finite probe success is not proof of all possible application behavior.

## Application checks

- All 7 retained rollout smoke/regression tests pass, including CLI create/grow/inspect/render and save/load.
- The broader repository Python suite, copied from `bug_competition/mosslight/tests`, runs 191 tests: **187 pass; 2 tests fail assertions and 2 raise errors**. The failures are coverage precision (6.2 rather than 6.25), silently accepted unknown workbench fields, and two history rebase/cherry-pick cases involving audit metadata. These correspond to still-failing seeded contracts F01, P06 and H06; this check alone does not establish when a failure was introduced.
- Studio DOM contract tests pass (initialization, selection, brush, mutation, error feedback, notes and text safety). These use a simulated DOM, not an interactive browser session.

## Remaining independently failing contracts

- **E10**: An odd number of glowcaps reports one extra firefly.
- **E12**: The last point of mulch decays before its scheduled nutrient benefit is counted.
- **E28**: A late plan is silently skipped forever.
- **F01**: Coverage loses its hundredths precision.
- **F06**: A plant at exactly 50 stress is not alerted.
- **F08**: Some diagonal samples drift from the canonical Bresenham path.
- **F24**: Equal treatments are reordered alphabetically.
- **F29**: Exported reminders follow insertion order.
- **F30**: Midpoint colors truncate fractional channel values.
- **H06**: A metadata-only reauthoring after ID reallocation conflicts with an actual correction on the other branch. Repeated selection of the same logical command can likewise be rejected as divergent content.
- **P05**: A boolean true is accepted as a version-one save.
- **P06**: A misspelled workbench field is silently discarded during load.
- **P25**: An older writer overwrites event identifiers after merging newer work from the same writer.

## Additional review concern

C124 reduced the accepted journal length from 200 to 100. A retained test proves the new rejection boundary, but does not establish the compatibility policy: otherwise accepted saves containing 101–200 journal entries are now rejected. This is an additional specification/compatibility concern, not one of the 13 failed graded probes.

Normal single-user gardening is supported by the evidence. Before treating this as a fully repaired release, the remaining contracts—especially courier writer counter reuse, false history conflicts, and overdue imported plans—need attention. Credit totals describe attribution and are not substitutes for this usability assessment.
