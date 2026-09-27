# Independent final checks

`FinalOracle` loads one behavioral probe for each of the 119 v7 contracts
(119 raw points; flat scoring, one point per defect). Startup rejects missing, duplicate, or unknown IDs. The four
`grader_data/probes_*.json` files contain 117 static probe definitions; N01 and
I01 are constructed by the host.
E01's calendar inputs and I01's capacities vary between adjudications and remain
fixed while the recorded snapshots are replayed.

Candidate programs receive fixture inputs and return observations. Expected
values, comparison code, coverage policy, audit evidence, and scoring stay on the
host. Every probe runs in its own network-disabled, read-only Docker container.
Early exits, malformed/extra output, nonfinite values, excessive output, and a
probe's own 30-second timeout fail that probe. No provisional check script or
candidate-authored verdict contributes to a final verdict.

The probes use contract-specific fixtures, boundary cases, exception types,
persisted state, event dispatch, and concurrent-worker schedules. Controlled
dependencies isolate seeded defects whose normal downstream simulation also
contains other seeded bugs. In particular:

* R01 returns paired cohort measurements; the host computes the pairing formula.
* R02 returns original, current, and reopened historical report observations;
  the host checks historical immutability.
* N01 uses positive, negative, and zero-slope measurements at four timestamp origins.
* I01 checks integral capacities, conservation, outlet delivery, and a host-computed
  minimum cut across six varied-capacity residual-routing fixtures.
* I02 runs the actual candidate solver with a deterministic spatial-growth
  dependency. The host independently enumerates all 117 schedules in five small
  problems, including refill and remaining-supply ties. A reported schedule must
  reach the optimum and its reported world must match the host's reference for
  that schedule. Rebuild that table with
  `python3 -B bug_competition/grader/tests/build_irrigation_reference.py`.

The old `grader_data/probes.json` is retained historical data and is not loaded.

Attribution uses `last_relevant_file_edit`, shared with both live harnesses.
Every passing defect that failed at baseline transfers to the latest actor whose
commit changed any of its manifest `file`, `locations[].file`, or
`replacements[].file` paths, including edits that fix nothing. False-to-true
repairs also earn credit when indirect. Final replay recomputes changed paths
from authenticated snapshots and counts only repairs surviving at the final head.
Claims and diagnostic ownership records do not determine final credit.

## Replay budget

The default final-adjudication budget is 3600 seconds. Four probes run
concurrently. Authenticated repeated full-tree hashes reuse verdicts from the
same adjudication; each snapshot is still hash-verified and participates in
ownership attribution. Distinct source trees receive fresh observations.

Exhausting the overall budget sets `adjudication_complete=false` and
`adjudication_timed_out=true`, reports how many snapshots finished, and withholds
all credit. Rerun the immutable evidence with a larger budget. An unexecuted
check is never interpreted as a repair regression.

## Offline evidence

Run `python3 -B -m unittest bug_competition.grader.tests.test_independent_probes`.
The suite checks every probe against the trusted clean fixture, the complete
seeded fixture, and that fixture with only the target repair applied. It also
checks host comparator rejection, exhaustive solver validation, authenticated
verdict caching, and incomplete adjudication. Its subprocess runner is for these
bundled trusted fixtures only; production uses `CandidateRunner`.

Every seeded defect is discriminated, but finite fixtures cannot prove
all possible behavior or resistance to deliberate hardcoding. The
`adversarially_verified` flag remains false. No model rollout or score calibration
is claimed by these tests.
