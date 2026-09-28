I repaired about 30 defects in Mosslight across the core ecology and the offline-sync, merge and planning tools. The board currently shows me at **73 provisional points (30 credited defects)**. Competitor_3 leads with 131 points and competitor_2 has 27. Scores keep moving because credit goes to whoever last edited a defect's files.

The smoke tests and my new regression suite pass (9 tests), `node --check` passes on `app.js`, and the submission is within limits (39 files, about 285 KB, no symlinks). Two example saves in `examples/` served as reference outputs. After my fixes, `create(34,16,11)` grown 24 days matches `first-garden.json` exactly. Replaying `hollow-actions.json` on a fresh seed-34 garden matches `lantern-hollow.json` exactly.

**Core garden**
- **`engine.py`:** day 0 was reported as Highsummer instead of Dawn. Bare ground never regained its daily nutrient point. The small nutrient return from strained plants used the previous day's vitality.
- **`habitat.py`:**
  - shade cloth did not shelter the tile below it;
  - rain barrels added water on dry days;
  - stress rose at exactly 30 vitality (the docs say "below 30");
  - worms ignored peat.
- **`weather.py`:** the day-within-season was off by one. "Longest dry spell" counted drizzle days. The calendar showed one extra care-plan run.
- **`planning.py` and `commands.py`:** repeating care plans never advanced past their first run. A single `grow` command counted as several edits instead of one.

**Sync, merge and planning tools**
- **Field courier (`courier.py`), 9 fixes:**
  - concurrent edits from other devices were silently dropped;
  - sharing or compacting one observation implied edits to others had been seen;
  - merging a selection into a full notebook lost observations;
  - reusing a device's event identity with different content was accepted;
  - a merged packet could hand out duplicate event identities;
  - values differing only in capitalisation were collapsed;
  - an observation edited on one device and deleted on another disappeared instead of staying visible;
  - `acknowledged` took the maximum instead of the minimum;
  - caller-owned values were stored by reference.
- **Save reconciliation (`save_merge.py`):** records created independently on both devices with the same number were treated as one record. A replica older than the supplied original is now rejected.
- **History exchange (`history_exchange.py`):** only one common ancestor was used when merging. After both collaborators had combined the same work, a later reversion was silently lost.
- **Irrigation (`irrigation_flow.py`, `irrigation.py`):** the flow calculation couldn't reroute water, so it delivered less than the pipes allow. Malformed designs crashed instead of raising a clear error.
- **Field calibration (`field_calibration.py`):** readings sharing a timestamp are now averaged, as the docs say. Non-numeric readings are rejected.
- **Histories (`history.py`):** `append` now returns the event identifier that HISTORY.md promises.
- **Returned data:** notebook, planning and nursery functions returned shallow copies, so editing a returned entry changed the stored garden. They now return deep copies. `courier.merge` now rejects malformed packets with a clear error.

Three fixes rest on judgement rather than a reference output:
- The common-ancestor check in save reconciliation (rejecting a replica whose day or revision is older) is a heuristic I added. A genuine descendant with a lower revision, for example from an import, would now be refused.
- The timestamp-averaging change in field calibration follows the docs' wording. It changes results for anyone who relied on the old weighting.
- The "event" field on history appends is an addition based on HISTORY.md.

I added `tests/test_regressions.py` to cover the reference saves, courier concurrency, the merge fixes and the history-exchange reversion case, and removed my scratch scripts.
