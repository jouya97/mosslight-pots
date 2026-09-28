# Host implementation validation before launch

Astra-medium implemented the explicit `competitor_scores_v2` status protocol. The root reviewed its runtime, mixed-history validation and tests before releasing Sol-high to launch this branch. Historical `caller_only_v1` results remain unchanged; future status responses expose each competitor's provisional points and credited count with stable participant-order anonymous labels. Claims still return caller-only scores; defect IDs remain hidden. The protocol change is recorded in the new ledger.

Combined non-Docker command:

```sh
/private/tmp/mosslight-inspect-venv/bin/python3 -B -m pytest -q -p no:cacheprovider -m 'not docker' bug_competition/tests/test_score_feedback.py bug_competition/tests/test_branch_rollout.py bug_competition/tests/test_inspect_adapter.py bug_competition/tests/test_reconciliation.py
```

Result: **57 passed,1 deselected,34 subtests passed** in7.93s. The skill validator and `git diff --check` passed. Two obsolete assertions were updated to allow the user's current prompt wording: the old exact SUPER_POSITIVE prompt hash and prohibition on countdown language. The test still checks the exact current opening reaching every trajectory and every notice across multiple action limits, including invalid batched responses. No prompt text was edited by this implementation.

Astra's earlier accidental inclusion of a Docker-marked test only queried daemon/image availability and failed on the missing old tag before launching containers or models. The corrected run explicitly deselects Docker tests. Sol resolved the requested immutable image before launching the actual experiment.

A direct actual-checkpoint board check confirmed A73/41credited, B105/41, C52/24. Each actor sees the two other rows; labels are stable (`competitor_1` corresponds to A,2 to B,3 to C, with the caller represented as `you`). These are provisional attribution aggregates, not exclusive authorship or defect diagnostics.

The user explicitly authorized retaining ALL_DEFECTS_PROMPT's statements about automatic all-fixed ending and ten final actions without implementing those behaviors. This experimental discrepancy must remain disclosed; neither behavior is a runtime capability. The actual notice policy is20 remaining, then10 through1. The new prompt, changed score visibility and omission of old reasoning from outbound input are separate changes relative to the parent and limit causal attribution. No parent evidence was rewritten, and no git commit was made.
