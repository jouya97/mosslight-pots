# Canonical fresh-rollout probes

These live and independent-grading inputs are tracked host-only fixtures. The
maintained fresh launcher validates both SHA-256 hashes before preparation.
No historical run directory is required to start a fresh competition.

The live fixture remains the all-bugs, competitor-scores-v2 experiment's input.
On October 5, 2026, the current grading fixture adopted the probe fairness fixes
from the bundled grader: public command and HTTP behavior, executable CLI exit
status, public campaign/ensemble results, optional history caches, and tolerance
for correct nursery, courier, chart and identifier-allocation implementations.
The 119 bug IDs and 251 available points are unchanged. Saved historical runs
and their pinned grading fixtures have not been rewritten.

- `live_probes.json`: `277166d239f0b41799c2fb69869d016201bf417f94c65c2bfdbec35f163ba6b4`
- `grading_probes.json`: `0323b641ca5988cb0f2ccc0a06feff9966960e318a4c10f8960402cd482ffc03`

Keep these files outside the participant workspace. Live checks are provisional;
independent grading uses the separate grading inputs and host comparison.

Validation: all 119 probes accept the clean fixture, reject their seeded bugs,
and accept individual repairs in the otherwise seeded tree. Twelve regression
tests cover alternative valid implementations. Docker checks of P13, P14, P15,
P21, V04 and R03 independently repeated the clean/seeded/individual-repair checks,
including real loopback HTTP under the grader's network-disabled container.

```sh
python3 -m unittest bug_competition.grader.tests.test_independent_probes \
    bug_competition.grader.tests.test_probe_fairness
```
