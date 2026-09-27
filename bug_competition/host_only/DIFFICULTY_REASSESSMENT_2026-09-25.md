# Difficulty interpretation addendum

This addendum corrects the interpretation of the frozen v5 report and manifest.
It does not change the seeded application, checks, patches, or recorded results.

The requested difficulty bands were **frames of reference for how long a human
senior engineer might need to debug a defect**. A minimal valid repair measures
implementation scope *after the root cause is known*. It does not measure time
to reproduce the failure, locate the cause, understand the violated invariant,
or gain confidence in a fix. A one-line repair can therefore still follow days
of debugging. The v5 report's statements that short repairs "defeat" or
"reject" extreme or legendary ratings overstate what the repair audits show.

The audits establish that compact valid repairs exist for X01, X02, L01, M01,
X03, Q01 and Q02, and that those repairs pass the recorded checks. They do not
establish a human debugging-time distribution for any of those defects. The
normal/hard values in the v5 manifest are provisional estimates; the extreme
and legendary human-time categories are **unvalidated**, not disproven by patch
size. Keep the frozen v5 distribution as its original annotation rather than
retroactively assigning a higher label without timing evidence.

P33 is a different claim. Its stipulated legacy inputs are identical in two
creation histories that require different notebook-lineage decisions. The
original automatic-classification requirement cannot be guaranteed from those
inputs. Its tested writer-scope/namespace patch is a practical **relaxation**,
not a repair satisfying the original requirement. The proof, workaround check,
and original-contract outcome must remain separate.

The 116 five-state checks and 116-by-116 recorded repair matrix establish
reproducible symptoms and independence for the recorded repairs. They do not
calibrate human difficulty. A future calibration should time independent
engineers on the task from the agent-visible starting state, measuring diagnosis
and a passing repair together; patch size alone is insufficient.
