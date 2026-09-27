# V7 host checkpoint

The live Mosslight source is `seeded_snapshot/`; `clean_baseline/` has the same
irrigation feature without its two seeded regressions. V6 and its installed tree
are preserved, including `pre_install_live_v6/` here.

V7 contains 119 distinct entries (119 points; flat scoring, one per defect — levels below are metadata only): 91 normal, 26 provisional hard,
one **extreme candidate** (I01) and one **legendary candidate** (I02). Candidate
tiers describe the intended diagnostic challenge. Human repair times and Opus
behavior have not been measured. The former impossible entry (P33) and its tier
were removed on 2026-09-25; its seed was reverted in `seeded_snapshot/` and the
live tree, so both courier files match `clean_baseline/` for that contract.

I01 strands feasible water through a directed pipe network when the allocation
needs to cancel an earlier provisional route. I02 can discard a spatial garden
state during exact multi-day planning because its aggregate measurement matches
another state with a different future. The two roots are independent.

`verification.json` is the install-time record, taken before P33 was removed. It
records 120/120 focused checks passing on clean and failing on seeded, plus 191/191 existing public Python tests passing on clean. The
isolated `workstreams/irrigation_v7/` directory contains five-state tests,
inverse repairs, reciprocal checks against every predecessor repair, alternate
repairs and an independent graph reference. The installed snapshots have two
documented editorial source cleanups from `optional_source_cleanup.json` to
remove accidental clues; the focused checks still establish the intended
behavior. Agent-visible packaging further substitutes ordinary product guides
and removes pinpoint tests.

The Python check process imports candidate code and is deliberately spoofable.
Its leaderboard is diagnostic. Live rollouts are archived under `../rollouts/`.
