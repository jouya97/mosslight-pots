# Host-only high-difficulty expansion proposal

This is design and clean feature groundwork, not new seed metadata. Do not copy
this file, the prototype origin record, verification logs, or any host artifacts
into a competitor workspace. No new bug has been seeded or relabeled. The live
application still has 88 normal, 7 hard, 0 extreme, 0 legendary and 1 impossible
entry. No human repair timings or model rollouts were performed.

## Finding and concrete next step

The previous courier assessment withstands independent critique. Its clean
implementation is 219 lines, the current seeded one is 222 lines, and its hardest
causal-context mistakes have bounded repairs. Public documentation already
states the allocation-clock versus per-record-coverage distinction. Complexity
terminology, long traces, many tests and rare failure schedules do not establish
multi-day repair difficulty.

The constructive route is to grow an independently useful **durable experiment
workspace**. Mosslight already offers repeatable experiments, treatment branches,
historical observations, scheduled care and a notebook. Saving/resuming campaigns,
reproducing old published runs, and correcting historical interventions naturally
extend those workflows. They justify new state and provenance concerns without
adding an unrelated algorithm just to hide defects.

The current codebase cannot credibly support extreme or legendary labels under
the requested definitions. The prototype below also does not establish either
tier. Two concrete extreme candidates and one separately rooted legendary
research candidate are specified here. Each remains conditional on completed
features, a minimal-repair audit, and human calibration. A correct smaller repair
is evidence to lower the tier, not a reason to forbid that repair.

## Implemented, clean, isolated groundwork

`high_difficulty_prototype/` is a separate copy of `expanded_baseline/`. The
original clean archive, live defective application, existing manifests, checks
and seed patches were not edited. `PROTOTYPE_ORIGIN.json` records the copied
baseline's file hashes. The only application addition is `mosslight/campaigns.py`,
with documentation in `CAMPAIGNS.md` and eight tests in `tests/test_campaigns.py`.

The feature is usable through `python3 -B -m mosslight.campaigns`:

- A full source save, ordered treatment events, sampling policy and installed
  engine fingerprint identify a campaign. Identical creation is idempotent.
- A local SQLite database retains each branch's full world, samples and next
  event offset in one checkpoint. A run can resume after the process exits.
- Workers compute outside short database transactions and claim separate
  branches. Reclaimed claims receive a new generation; stale workers cannot
  overwrite their replacement or publish after cancellation.
- A failed command leaves the previous checkpoint intact and marks the branch
  failed. Cancellation is terminal in this version.
- Both further computation and result interpretation require the original
  installed engine and Python version. Cross-version replay is explicitly not
  implemented. This is a conservative coherent first release.
- Results agree with the existing ordinary experiment function; campaigns do
  not change the source garden.

Validation: 8/8 new campaign tests passed. They include real process termination
immediately before and after publication, concurrent claims, lease reclamation,
cancellation during computation, failed-command rollback, input ownership and
full-input identity. The complete isolated suite passed **115/115**, including
the preexisting HTTP tests after an approved local-loopback sandbox escalation.
JavaScript syntax and the studio DOM contract test also passed.
`high_difficulty_prototype/PROTOTYPE_TESTS.txt` contains the complete Python log.

These tests establish bounded clean behavior, not crash safety for defective
hardware, distributed SQLite, every operating-system failure, or absence of all
latent bugs. This prototype deliberately uses complete snapshots and a simple
database transaction. A bug confined to its offset, lease, or publication logic
would generally be normal or hard, not automatically extreme.

## Candidate X1: historical runs acquire mixed engine semantics

**Provisional tier:** extreme candidate; unmeasured and low confidence. It is
hard or lower if retaining an old engine plus one dispatch point satisfies the
final public contract with a small repair.

**Organic feature.** Researchers keep named, published experiment results and
fork a new experiment from a historical checkpoint after an ecology upgrade.
They can reproduce the original run under its original rules and explicitly
start a new branch under the newer rules. Saving storage with checkpoint
compaction and migrating a workspace must preserve those meanings. Old raw
inputs, command events and engine provenance remain retained or recoverable.

**Ordinary symptom.** Opening an old trial after an upgrade shows its first few
samples unchanged, but resuming it or regenerating its report changes a later
plant count or nursery readiness. A fork started at the same visible checkpoint
disagrees with a freshly reproduced historical run. No unusual identifier,
timestamp or artificial trigger is needed.

**Plausible maintenance mistake.** A schema migration normalizes every stored
checkpoint into the current `World` shape, and the scheduler/report service then
treats that shape as proof that current execution rules apply. The migration
has conflated save representation version with simulation semantics version.
For example, a genuine later release may change a nursery hydration rule; a
resumed historical run must continue with its recorded earlier rule unless the
user explicitly forks into the new rules. This example is a future release
scenario, not a claim that a second released engine currently exists.

**Exact failure mode.** The first part of a branch was executed by engine A.
Its checkpoint is migrated to schema B. The remaining commands, derived census
or comparison are interpreted by engine B without a recorded semantic boundary.
The state passes validation while its samples and final report belong to no
single permitted execution. Interruption and restart during migration can make
different descendants select different semantics.

**Minimal realistic repair scope.** Separate representation migrations from
execution semantics; preserve an immutable engine identifier on every execution
segment; provide compatible engine execution or a correct historical adapter;
record an explicit fork boundary when the user opts into newer rules; bind
published reports to their inputs and interpreter. Repair/reindex affected
retained histories using their original inputs and provenance. Likely touched
components are workspace schema, checkpoint loader, command/engine dispatch,
fork workflow, report materialization and resumable migration. It is one
semantic-version invariant even when it has several manifestations. Restoring
a single lost version field may be enough in a better-designed system and must
then be accepted and downgraded.

**Deterministic host oracle.** Archive two actual clean engine releases and
their public change contract. Use ordinary garden/treatment fixtures that cause
their documented behavior to differ. Record full reference executions under
each release. Check: uninterrupted versus resumed engine-A execution; old report
reproduction after upgrade; an explicit A-checkpoint-to-B fork; descendants
created before/after migration; process termination at each migration write and
restart. Compare full states and report provenance as well as samples. Repeat
with different garden seeds and treatment names. The reference engines and
trace scheduler stay host-only; the version/fork promises and release change
remain public. Do not make a hidden historical behavior a grading requirement.

**Nonoverlap.** This does not alter daily ecology formulas (E01–E30), sampling
or treatment ordering (F09/F21–F25), command revision rules, server persistence
(P13/P14), or courier clocks/identity (P24–P34). Build it in new workspace
versioning modules using a clean, pinned engine. Its isolated oracle must still
fail with every existing seed repaired. Its repair must leave all existing
focused outcomes unchanged. As the scientific engine is a dependency, isolate
the oracle with known valid snapshots and archived clean engine execution rather
than letting E/F failures become an X1 reproduction prerequisite.

**Why multiple days could be credible.** Correctly recovering already published
mixed-version descendants and implementing resumable schema/execution boundaries
across an established history may require tracing several persistent formats,
designing compatibility behavior and rebuilding history. This is a plausible
multi-day maintenance job in a mature workspace, not established difficulty in
the present prototype.

**Cheap-repair audit.** Pin old runs and fork new ones; retain both engines;
rebuild reports from retained raw inputs; remove unnecessary migration. All are
legitimate. Never demand that historical runs silently adopt new numerical rules
while also matching old outcomes. Rejecting all explicit upgrade/fork requests
violates the proposed useful feature, but pin-old-and-fork-new is an acceptable
implementation of it. If that is a small patch, X1 is not extreme.

## Candidate X2: correcting a historical intervention retargets later commands

**Provisional tier:** extreme candidate; unmeasured and low confidence. The
hard part must be repair of an established history model, not changing one ID
allocator or adding a UUID field.

**Organic feature.** A gardener corrects an incorrectly recorded intervention
in a historical experiment, obtains a new descendant branch, and compares it
with the original. Existing published branch/checkpoint handles stay valid.
Subsequent commands refer to the logical observation, nursery batch, task or
plan originally selected. A correction that removes a referenced object creates
an explicit unresolved conflict; it must never silently target its replacement.
Original historical branches remain reproducible.

**Ordinary symptom.** Correcting an early notebook entry unexpectedly edits a
later, unrelated note; watering a nursery batch after replay changes another
batch. Everything is valid JSON and local IDs remain unique. A user sees the
wrong object changed only several interventions after the correction.

**Plausible development mistake.** The first replay implementation serialized
commands with branch-local integer IDs and later reused those commands after
rewriting earlier history. Developers assumed snapshot identity and authored
object identity were equivalent. Shared `next_id` allocation across collections
makes this especially easy to miss in Mosslight.

**Exact failure mode and ordinary trace.** Events create note A as local ID 1,
note B as ID 2, and note C as ID 3. A later event edits B using ID 2. A correction
removes A's creation. Replay now allocates B as ID 1 and C as ID 2; blindly replaying
the edit changes C. Reusing a deleted object's ID in another branch or restoring
a named historical checkpoint creates related manifestations of the same
reference-binding mistake. The original event ledger must retain each event's
result bindings, original branch and parent context. That retained provenance
makes the original referent recoverable; without it, ambiguous histories could
be impossible and must not be mislabeled extreme.

**Minimal realistic repair scope.** Introduce durable logical event/entity
identity and explicit references to command results; resolve a command's original
references before rewriting history; map those references to each materialized
branch's local IDs; preserve generation identity across deletion/recreation;
surface missing-target conflicts. Migrate known histories from retained creation
results and parent contexts, keep published branch handles stable, and replay
descendants against the corrected bindings. Scope includes the event schema,
result-reference representation, replay/rebase interpreter, command adapters,
history migration, and conflict presentation. One namespace invariant is counted
once even when notes, plans and nursery expose it.

**Deterministic host oracle.** Build a small independent interpreter whose
entities are named by `(creation_event, result_slot)` and whose commands contain
logical references; it should use full replay and no production rebasing code.
Test the A/B/C trace, cross-collection allocation, independent equal-valued notes,
deletion/recreation, historical fork/correction, correction that actually deletes
a required referent, and branches with colliding local IDs. Check logical targets,
full resulting worlds, stable published handles and explicit conflict reports.
Include permutations of event labels and changes to incidental local ID offsets.
Retain ordinary public examples showing the intended correction behavior.

**Nonoverlap.** Existing P07/P08 check uniqueness and the local allocator's bound
inside a save; those can pass while this cross-history identity bug occurs.
P33 lacks origin information in old files, whereas X2 intentionally retains
enough event provenance to recover the answer. P25/P27 concern courier writer
sequences; P30/P31/P34 concern causal coverage. None defines command-result
references across rewritten experiment histories. F12 concerns specimen capture,
not referential identity. Implement X2 in a separate event/rebase subsystem and
exercise it with clean command/model dependencies. No change to the existing
courier identity policy is required.

**Why multiple days could be credible.** A correct repair must recover meaning
for existing histories, transport references across branches, and handle missing
targets without corrupting published results. If those behaviors already exist
across many command types, a representation redesign and migration could be
substantial. Adding UUIDs only for future events is insufficient for retained
histories. A compact event-to-object mapping might nevertheless solve the actual
implementation; in that case lower the tier.

**Cheap-repair audit.** Replaying from the start with correct binding maps is
valid. Stable logical IDs alone may solve a well-designed implementation. A
snapshot-only diff is insufficient when equal-valued independently authored
objects differ in identity. Rejecting every correction is not the proposed
product, but reporting a real unresolved reference conflict is required and is
not a failed repair. Never insist on automatic resolution of ambiguous intent.

## Candidate L1: concurrent publication misses a newly discovered dependency

**Provisional tier:** legendary research candidate only. No current evidence
establishes borderline-impossible repair burden. It may warrant extreme or hard
even after expansion, and may never be appropriate for Mosslight.

**Organic feature.** Larger experiment ensembles reuse unchanged calculations
and update affected descendants while a gardener adjusts treatments, watches
results, and continues editing. Conditional care can discover dependencies only
during evaluation. Each visible result identifies one immutable requested input
snapshot; a result must never mix versions. Caching is justified only after real
interactive workloads show a benefit.

**Ordinary symptom.** After a treatment edit, an apparently finished forecast
briefly or permanently displays an old population under the new treatment label.
Reopening or running the same trial afresh produces another answer. It tends to
occur when a changed care condition starts reading data it previously ignored,
while another worker completes an older calculation.

**Plausible optimization mistake.** Invalidation uses the last published
dependency graph, while evaluation updates that graph only after calculating
its output. Publication validates previously known dependencies rather than
every input actually read by that evaluation.

**Exact controlled schedule.** Worker T evaluates node N from snapshot v and
discovers a new read of M. A correction U commits a new M while the published
graph still lacks edge N-to-M. U's invalidation misses N. T validates the old
dependency set and publishes its stale output under the new visible head. A
late completion can also clear a newer dirty generation. These manifestations
share the invariant that dependency discovery, invalidation and publication must
agree on a single input snapshot and generation.

**Minimal realistic repair scope.** Capture actual input reads and their
versions, validate newly discovered dependencies, and publish output, read-set
and dependency edges with a coherent snapshot/generation decision. Coordinate
concurrent invalidation with publication and preserve newer dirty generations
when older work finishes. Rebuild or safely invalidate previously inconsistent
cached outputs. Likely components are the dependency evaluator, immutable
snapshot store, scheduler, invalidation engine, persistent graph and result
projection. It is a dependency-publication defect, not three separate seeds.

**Deterministic host oracle.** A slow independent implementation fully replays
each requested immutable snapshot. Pause workers at real evaluation boundaries:
before discovering an edge, after reading the new input, before recording that
edge, before invalidation, and before committing output. Enumerate small bounded
schedules, restart at persistence boundaries, and compare every visible result
and its cited input versions with full replay. Use conditional dependencies
that turn on and off, concurrent corrections to separate branches, delayed
completions and cancellation. An allowed stale-but-explicitly-versioned old
result must not be falsely treated as a violation; the public UI contract must
define whether it stays visible while a new result is pending.

**Nonoverlap.** X1 selects historical engine semantics; hold that fixed here.
X2 preserves logical object references; use stable preexisting entities here.
E02 concerns traversal-order moisture calculations inside a single daily step;
L1 compares complete, otherwise correct immutable computations. P14 concerns
publishing a save after a filesystem error; L1 arises without any I/O failure.
Courier causality is unused. Separate reference executions must show all these
other invariants hold while the dependency-publication schedule fails.

**What could justify the tier.** An established dynamically dependent graph with
persistent compaction, overlapping branches, cancellation and sustained editing
may require a difficult consistency redesign and broad compatibility work.
Severe diagnostic ambiguity plus a demonstrably difficult smallest repair might
justify legendary after specialist review. Algorithm names, many workers and
one subtle race are insufficient evidence.

**Decisive falsifiers.** A global workspace-revision check/retry, compute lock,
per-branch full replay, whole-input cache key, or disabled cache are legitimate
repairs if they meet the product needs. The present maximum of eight treatments,
120 experiment days and 1,200 cells provides no measured reason to exclude them.
Only a useful measured workload and a public latency/throughput contract can
justify more sophisticated behavior. Establish that workload before introducing
the defect. Do not invent a complexity bound, ban SQLite, ban full replay, or
require a particular algorithm just to make the task harder. If simple correct
fallbacks remain acceptable, abandon the legendary label.

## Impossible P33: retain it, distinguish proof from repair

P33 is preferable to an artificial bounded-string or hidden-input puzzle. Legacy
saves contain local observation IDs and garden state, but no persistent origin
identifier. The public requirement asks a fresh offline installation to join
copies from one original garden while separating independently created gardens,
using unchanged legacy bytes and without a registry or identity question.

The supplied witness gives two histories with the same two received saves,
filenames and writer names. One is a copied garden; the other consists of two
independent gardens created with the same deterministic seed and authored note.
All available inputs are identical. One history requires one lineage; the other
requires two. Therefore any algorithm over the allowed input has the same output
distribution in both histories and cannot guarantee both required answers.
Hashes, fresh UUIDs, larger models, more compute and current timestamps cannot
reconstruct a historical bit the input never contained.

This looks initially fixable as a deduplication or migration bug, but the failure
is observable with ordinary saves and a finite indistinguishable-history witness.
The honest outcome is diagnosis plus an explicit product relaxation: ask for
notebook provenance, use a known mapping, require manual namespaces, or document
an ambiguity policy. Persist origin IDs for future saves. Do not claim they
retroactively solve ambiguous old files.

**Oracle/adjudication correction for future reporting.** `checks/P33.py` checks
that independent default exports are distinct and that explicit namespaces can
join. It does not require automatic joining for copied legacy files. The inverse
writer-scoped default passes that check while returning two lineages for both
histories; the independent reviewer reproduced this in memory. Existing host
documentation already calls this a relaxation. Future reports should make the
distinction machine-visible: `impossibility_witness_valid`,
`explicit_relaxation_works`, and `original_contract_satisfied: false`. Do not
include P33 among repairable defects when reporting all repairs passing their
original contracts. The full original conjunction intentionally has no passing
implementation. No existing metadata was changed for this proposal.

For an impossible task, the host evaluates the submitted explanation/witness and
any explicitly declared relaxation. It must not demand one different hidden
answer for the same available input or fail an honest diagnosis because code
cannot satisfy the conjunction. The contradictory product promises need to stay
visible; only the prepared witness and adjudication rubric are host-only.

## Implementation sequence and gates before any seeding

1. **Preserve provenance.** Keep the immutable original archive and 96-seed
   snapshot. Continue only in the isolated clean prototype. Hash copied inputs
   and distinguish new feature code from preexisting code. Do not change the
   competition counts merely because a candidate exists.
2. **Finish the useful workspace baseline.** Integrate durable campaigns into
   ordinary CLI/studio workflows; add persistent branch names and historical
   checkpoint navigation. First specify visible semantics, cancellation,
   failure handling, supported concurrency and storage limits. The implemented
   command is initial groundwork, not this full product.
3. **Build versioned replay cleanly.** Introduce real engine release identities,
   an explicit historical fork flow and immutable published reports. Retain the
   raw events/provenance required for repair. Gate on dual-engine reference
   execution, checkpoint equivalence, interrupted migration and restart. No
   candidate X1 injection until the clean product satisfies these promises.
4. **Build correction and reference semantics cleanly.** Define event/result
   identity and missing-reference conflicts before adding historical correction.
   Implement the independent logical-reference interpreter first or in parallel.
   Gate on colliding-ID histories, deleted/recreated entities, cross-collection
   allocation and preservation of published branches. Build an explainable UI
   for a correction that cannot be applied automatically. No X2 injection yet.
5. **Measure real workloads before incremental expansion.** Exercise useful
   experiment ensembles on disclosed hardware with full replay and a simple
   scheduler. If their responsiveness is adequate, stop at that architecture.
   If not, establish public latency targets and add selective recomputation.
   Gate on equivalence to full replay under controlled schedules and process
   restart. A performance optimization alone is not a new defect or a tier.
6. **Minimal-repair review.** An independent engineer must actively try every
   simple repair listed above and propose a smaller valid implementation. Keep
   a candidate only if its required repair burden survives that review. Expose
   all product obligations in ordinary documentation; keep prepared traces and
   expected fixes host-only. Reclassify or discard candidates that collapse to
   a local change. Reproduction depth and patch size are separate evidence.
7. **Calibrate people before labels.** Run blind repair sessions with at least
   three senior engineers per candidate, ideally including one with the relevant
   specialization. Give everyone the same public repo, tooling, user symptom
   and requirements, with no host trace or intended repair. Record active time
   to reproduce, diagnose, implement and validate; also record unsuccessful or
   time-limited attempts, accepted alternative repairs and any additional hints.
   Report observations individually and as a range, not a false precise average.
   More people may be needed when results disagree. Define the working day in
   advance, and count neither waiting nor artificial environment setup as
   difficulty. Multiple independent multi-day repairs support extreme; a few
   timeouts alone do not prove legendary. Keep low confidence if evidence is
   sparse. No such human study has occurred yet.
8. **Only then authorize a seed.** For each approved root cause, capture a clean
   feature archive and introduce one plausible maintenance regression. Validate
   clean pass, isolated failure, isolated repair, integrated failure and repair.
   For X1/X2/L1, a conforming clean reference must exist; only P33 uses proof
   adjudication instead. Seeding is not part of the work performed here.
9. **Prove nonoverlap empirically.** Run every old and new focused oracle against
   each isolated mutation and inverse repair. Repairs must clear their own
   defect without clearing another. Validate dependencies on a clean reference
   so an E/F failure does not mask the new issue. Add pairwise interaction checks
   and end-to-end user workflows beyond the diagonal matrix, since one inverse
   repair per row does not prove independence for every possible broad rewrite.
10. **Integrate only with evidence.** Preserve public tests, archive the clean
    extension, record immutable feature/seed hashes and publish a truthful
    difficulty distribution. Keep the host directory entirely outside the
    eventual competitor tree. A healthy mix is selected from validated defects;
    filling a desired quota is never a reason to inflate labels.

## Independent critique and resolution

Exactly one child agent was used, explicitly `gpt-6-astra` with `ultra` reasoning,
for independent critique. It inspected the clean and seeded courier, public
contracts, manifest/audits and P33 witness, and performed the in-memory P33
comparison. It made no edits and spawned no agents.

- It rejected rebranding P34 or a spatial old-grid error as extreme. Resolution:
  retain existing ratings and use separate historical execution/reference
  invariants instead of another causal-coverage or E02 manifestation.
- It identified SQLite transactions, full snapshots, engine pinning and complete
  replay as valid simplifying repairs. Resolution: every candidate includes
  these attacks as downgrade/abandon gates; no arbitrary implementation ban.
- It cautioned that merging divergent biological futures is underspecified or
  impossible. Resolution: this proposal uses explicit fork/correction semantics
  and surfaced conflicts; it never promises to preserve incompatible outcomes
  in one automatic merge.
- It distinguished P33's rigorous impossibility from its partial behavior check.
  Resolution: retain the task and recommend separate proof/relaxation reporting.
- Its limited static prototype review noticed `result()` could reinterpret old
  samples under a changed engine and that cancellation had no restart semantics.
  Resolution: `result()` now enforces the fingerprint, the engine-change test
  covers it, and `CAMPAIGNS.md` explicitly defines cancellation as terminal.
- Its legendary candidate survives as a useful research direction, not an
  achieved tier. Resolution: no legendary label unless actual workloads defeat
  legitimate simple alternatives and independent repair evidence supports the
  unusually severe burden. It is acceptable to conclude that Mosslight cannot
  credibly offer this tier.

No external technical claims or online sources were needed; conclusions derive
from the inspected local application and host evidence. The work made no model
API calls, ran no model rollouts, and did not inspect credentials or unrelated
environment directories.
