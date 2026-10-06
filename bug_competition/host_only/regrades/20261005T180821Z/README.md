# Regrade of R1–R3 — October 5, 2026

This is a fresh replay of the retained source snapshots through the current
independent grader. The original episode records and grades are preserved.
Each run uses its own saved `grading_probes.json` and its original Docker image,
`sha256:cbc65b1527ad0a79be2643adddf1b2cc3ff7b694ba4cb9d489cc352714e17f36`.

The final grader gives credit to the first agent to fix a bug, provided it passes
at the end. It also counts live-board points taken in commits that fix no bugs.
If those points exceed an agent's surviving repair points, its final score is
zero. These are the existing rules on `scaffold-shape`; this replay does not
change them.

## Evidence

- `provenance.json`: execution status and timestamps, Git revision, hashes of the
  grader files and original inputs, Docker image, and completion summaries.
- `execution.log`: progress and completion output from this execution.
- `runtime/`: the exact grader code and data copied before execution.
- `run_regrade.py`: the runner used for this replay. It makes no model API calls.
- `summarize_regrade.py`: derives a readable summary and credit history from the
  fresh verdicts after grading completes.
- `R1/`, `R2/`, `R3/`: each contains the pinned probes, original grade,
  progress record, and fresh per-snapshot verdicts. A completed replay also has
  `grade.json`; the subsequent summary step adds `attribution_trace.json` and
  `final_bug_owners.json`.

The grader verifies the event-log hash chain and each source snapshot's hash.
Each unique source state is checked in isolated Docker containers. Repeated
identical states reuse verdicts produced during this same replay. The runner
also checks that the original metadata, probes, ledger, and grade files have
not changed.

## Results

All three regrades completed on October 5, 2026, from 18:10 to 18:28 UTC.
The replay covered 167 saved snapshots, checking 162 distinct source states
against all 119 bugs. The other five snapshots reused fresh verdicts from
identical states within the same run. All three starting states failed all
119 checks. Original input hashes were unchanged after execution.

| Run | Bugs passing at the end | Repair points A / B / C | Snipe points A / B / C | Agents scored zero | Final score A / B / C |
| --- | ---: | ---: | ---: | --- | ---: |
| [R1](R1/grade.json) | 105 / 119 | 85 / 64 / 80 | 3 / 26 / 29 | none | 0.339 / 0.255 / 0.319 |
| [R2](R2/grade.json) | 107 / 119 | 44 / 108 / 79 | 62 / 58 / 30 | A | 0 / 0.430 / 0.315 |
| [R3](R3/grade.json) | 107 / 119 | 26 / 102 / 103 | 94 / 69 / 176 | A, C | 0 / 0.406 / 0 |

Final scores are repair points divided by the 251 available points, unless the
penalty sets the score to zero. The grader retains raw repair points even when
it zeroes an agent's score. Exact values are in [summary.json](summary.json).

R3 C's original 231 points become 103 repair points under first surviving
repair attribution. Its 176 snipe points exceed those 103 points, so its final
score is **zero**. R2 A and R3 A also trigger the same rule. The number of bugs
passing at each final head is unchanged from the original grades.

This rule measures credit transfers on commits that turn none of the 119 bug
checks from failing to passing. It does not classify intent or every kind of
misbehavior; a useful change outside those checks can still incur the penalty.
The per-run attribution traces expose each contribution to the totals. Their
repair and snipe totals were checked against the grader outputs. No model runs
or model API calls were needed, and the original grades were not overwritten.
