# Bug universe

The ground truth is
[`grader/grader_data/manifest.json`](../../grader/grader_data/manifest.json). It lists
**119 seeded behavioral bugs worth 251 points** across 31 source files.

| Tier | Weight | Bugs | Points |
| --- | ---: | ---: | ---: |
| normal | 1 | 91 | 91 |
| hard | 5 | 26 | 130 |
| extreme | 10 | 1 (I01) | 10 |
| legendary | 20 | 1 (I02) | 20 |
| **total** | | **119** | **251** |

The tiers estimate difficulty; they are not measured human repair times. N01/N02 are
provisionally hard. I01 (cancelling an earlier pipe allocation through reverse capacity)
and I02 (wrongly merging spatial garden states that share aggregate measurements) are
separate root causes. Each manifest entry gives the contract, symptom, root cause, file
and locations, seeded `old`/`new` text, a focused check, the expected fix, and
difficulty and realism rationales. The ID families are E 30, F 32, P 33, H 6, V 4, R 3,
X 3, I 2, N 2, Q 2, L 1 and M 1. P33 was dropped from the universe.

## Fixtures

| Path | Contents |
| --- | --- |
| `clean_baseline/` | The clean application and its public regression tests |
| `seeded_snapshot/` | The same tree with all 119 bugs seeded. Its code matches the agent-visible `mosslight/`; only docstrings, comments and guides differ |
| `checks/<ID>.py` | One focused host check per bug; passes on clean, fails on seeded |
| `patches/<ID>.patch` | The clean-to-seeded diff for each bug |
| `verification.json` | The last `verify.py` audit: 119/119 checks pass on clean, 119/119 fail on seeded, 191 clean public tests pass, plus tree and manifest hashes |

These checks import the tree under test, so they are for trusted host trees only. They
are not the final grader. The grader uses its own probes in
`grader/grader_data/probes_*.json`, runs them in isolated containers and compares the
results on the host ([grader/README.md](../../grader/README.md)). Nothing in this
directory enters an agent mount. The agent-visible tree is built from `mosslight/` by
`visibility/build.py`, which replaces the pinpoint public tests with two smoke tests.

## Verify

```sh
python3 -B bug_competition/host_only/verify.py --check E01 --tree bug_competition/host_only/seeded_snapshot   # one bug; exits nonzero on seeded
python3 -B bug_competition/host_only/verify.py                                                               # full audit; rewrites verification.json
```

The full audit exits 0 only when every check passes on clean, every check fails on
seeded, and the clean public suite passes. It makes no model calls, no network calls and
no Docker calls.