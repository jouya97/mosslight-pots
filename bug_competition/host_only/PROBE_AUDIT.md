# Probe validity audit

Each of the 119 final probes judged against the agent-visible tree only
(`visibility/build.py` output: narrative guides, examples and source without
docstrings or comments; the host's numbered BEHAVIORS rules are not visible).
Columns: whether the asserted behavior is documented, inferable or undocumented
there (with file:line evidence), how the probe couples to internals, any
incidental form it asserts, and a minimal fix. Proposed rewrites were checked
with the test-only FixtureRunner: clean passes, seeded fails, seeded plus the
single repair passes.

**None of the fixes is applied.** The probes and guides used by the retained
runs are unchanged; see `flaw.md` (Known limitations). At the final heads of R1
(14 defects failing), the R2 continuation (12) and R3 (12), no brittle probe was
failing, and the same eight undocumented or form-asserting defects were failing
in all three: E10, E12, E28, F01, F06, F24, F30 and P05. Whether agents would have fixed them with
fuller guides, or simply never found them, cannot be told from the runs.

Documentation: {'documented': 75, 'inferable': 33, 'undocumented': 11}; coupling: {'public': 66, 'internal-tolerant': 43, 'internal-brittle': 10}

Undocumented: E05, E10, E12, E15, E28, F01, F06, F07, F08, F24, F30 (11 pts)
Internal-brittle: P13, P15, P21, V04, X02, H02, H03, H05, R03, X03 (30 pts)

| ID | lvl/pts | documented | evidence | coupling | coupling note | form | recommendation |
|---|---|---|---|---|---|---|---|
| E01 | normal/1 | documented | GROWING.md:19-20 (48-day year, 12-day seasons, day 0 is Dawn) | public | engine.season |  |  |
| E02 | hard/5 | inferable | GROWING.md:25-27 ("A day's development represents the whole garden growing together"); engine.py:105 already builds `adjacent` from the old grid | internal-tolerant | monkeypatches engine._weather (and/or engine.season); a repair at the defect line keeps them effective | exact value 42 follows unchanged smoothing/evaporation code |  |
| E03 | normal/1 | documented | GROWING.md:32-34 (cloth shelters own+adjoining tiles; affects growing conditions) | internal-tolerant | monkeypatches engine._weather (and/or engine.season); a repair at the defect line keeps them effective |  |  |
| E04 | normal/1 | documented | GROWING.md:53 ("Bare ground slowly recovers one nutrient point a day") | internal-tolerant | monkeypatches engine._weather (and/or engine.season); a repair at the defect line keeps them effective |  |  |
| E05 | normal/1 | undocumented | GROWING.md:53-54 says only "Plants under severe strain can also return a small amount of nutrients"; threshold 25, amount 2 and prior-vs-resulting vitality are not visible. The seeded `before.vitality < 25` is a doc-consistent reading. | internal-tolerant | monkeypatches engine._weather (and/or engine.season); a repair at the defect line keeps them effective | asserts the evaluation point (resulting vitality) of an undocumented threshold | (a) GROWING.md line 53-54, replace the sentence with: "A plant whose vitality after the day's growth is below 25 returns two nutrient points to its tile." |
| E06 | normal/1 | documented | catalog.py:12-13 SPECIES_GUIDE glowcap lifespan 75 (printed by `guide`); GROWING.md:46-47 | internal-tolerant | monkeypatches engine._weather (and/or engine.season); a repair at the defect line keeps them effective |  |  |
| E07 | normal/1 | documented | GROWING.md:20-21 ("Hush slows most plants, while glowcaps remain suited to the season") | internal-tolerant | monkeypatches engine._weather (and/or engine.season); a repair at the defect line keeps them effective; day 37 is Hush anyway once E01 is fixed |  |  |
| E08 | normal/1 | documented | GROWING.md:26 (neighbors share edges) + 32-33 (own tile and adjoining tiles) | internal-tolerant | calls habitat.effective_shade(world, index) directly (module-level helper) |  |  |
| E09 | normal/1 | documented | GROWING.md:34-35 ("Rain barrels collect water on rainy days") | internal-tolerant | calls habitat.water_balance(world,i,before,neighbor_mean,rain,evaporation) positionally; a fix keyed on world.weather also passes (create() weather is clear) |  |  |
| E10 | normal/1 | undocumented | GROWING.md:69-70 says only "glowcaps attract fireflies"; ratio 1/2, rounding and the vitality-40 health threshold are not visible (sibling bees `//3`, worms `//4` hint at floor division only) | internal-tolerant | calls habitat.after_day directly | asserts rounding of an undocumented ratio | (a) GROWING.md line 70: replace "glowcaps attract fireflies" with "every two glowcaps with vitality of at least 40 attract one firefly" |
| E11 | normal/1 | documented | GROWING.md:70-71 ("moist, rich soil or peat supports worms") | internal-tolerant | calls habitat.after_day directly |  |  |
| E12 | normal/1 | undocumented | GROWING.md:36-37 says only "gradually returns nutrients as it decomposes"; the every-third-day schedule and the last-point boundary are not visible (visibility/README.md: guides deliberately omit edge-case lists) | internal-tolerant | calls habitat.after_day directly | boundary-only edge case | (a) GROWING.md line 36-37: "Mulch slows evaporation and decomposes one point a day; on days divisible by three a mulched tile gains one nutrient point, including the day its last point decomposes." |
| E13 | normal/1 | documented | GROWING.md:54-55 ("vitality below 30 increases stress, while healthier plants recover") | internal-tolerant | calls habitat.after_day directly |  |  |
| E14 | normal/1 | inferable | PORTABILITY.md:63 (either corner order); gardening.py:13 y-range is inclusive (bottom+1) while x is not; README.md:27 radius-zero selects one tile | public |  | asserts row-major output order (hidden BEHAVIORS 34); unchanged loop order, low risk |  |
| E15 | normal/1 | undocumented | WORKBENCH.md:11 names "circular" brushes (so circle != diamond is inferable), but the boundary rule (dx^2+dy^2 <= r^2) is not visible. Verified: a (r+0.5)^2 circle fails the probe. | public |  | asserts one specific circle rasterisation + row-major order | (a) WORKBENCH.md line 11: "Use rectangles or diamond, circular and square brushes (a circle selects tiles whose squared distance from the centre is at most the radius squared) to tend larger areas;" |
| E16 | normal/1 | documented | WORKBENCH.md:20-21 ("carrying its age and stress with it") | public |  |  |  |
| E17 | normal/1 | inferable | model.py:83 rejects negative age on load; WORKBENCH.md:21-22 | public |  |  |  |
| E18 | normal/1 | documented | GROWING.md:14-15 (vitality is a whole percentage 0-100) | public |  |  |  |
| E19 | normal/1 | inferable | WORKBENCH.md:27-28 ("starts a new growth period before the next harvest"); gardening.collect_seed resets age to 0 (gardening.py:97) | public |  | error class ValueError matches every validator in the code base |  |
| E20 | normal/1 | documented | WORKBENCH.md:18-19, 34-35 ("Resource balances never become negative"); gardening.py:122 message already says cost*amount | public |  |  |  |
| E21 | normal/1 | documented | WORKBENCH.md:38-39 ("Watering restores a three-day supply") | internal-tolerant | imports private nursery._batch to create a batch; verified a rename of _batch fails the probe |  | (b) cheap hardening, verified: replace `_batch(w,'moss',1,'seed')` with `w.workbench['seeds']['moss']=1; b=start_seeds(w,'moss',1)` |
| E22 | normal/1 | inferable | WORKBENCH.md:37-40 (ready batches still need water; hydrated days improve vigor) | internal-tolerant | imports private nursery._batch |  | (b) same start_seeds hardening as E21 (verified) |
| E23 | normal/1 | documented | WORKBENCH.md:39-40 ("dry days halt development and weaken it") | internal-tolerant | imports private nursery._batch |  | (b) same start_seeds hardening as E21 (verified) |
| E24 | normal/1 | documented | WORKBENCH.md:43-44 ("uses four nutrient points from its new site") | public | writes a nursery entry in save format |  |  |
| E25 | normal/1 | inferable | state.py:90-92 save validation casefolds bed names and rejects duplicates | public |  |  |  |
| E26 | normal/1 | documented | WORKBENCH.md:76 ("begins on a future day"); COMMANDS.md:65 | public |  |  |  |
| E27 | hard/5 | documented | WORKBENCH.md:76-79 (finite runs, worked example) | public |  |  |  |
| E28 | normal/1 | undocumented | WORKBENCH.md:76-80 covers future plans, cancellation and failure only. Executing an overdue imported plan (vs. failing it with an error) is an undocumented choice; only "silently skipped forever" is clearly wrong. | internal-tolerant | calls planning.run_plans directly | edge case | (a) WORKBENCH.md after line 79: "A pending plan whose day has already passed, for example in an imported save, runs with the next day's care." |
| E29 | hard/5 | inferable | WORKBENCH.md:83-85 ("Rules respond to the day's growing conditions consistently, even when several care actions are needed") | internal-tolerant | calls planning.run_rules directly |  |  |
| E30 | normal/1 | inferable | GROWING.md:19 (48-day year); weather.calendar_day uses day%48. Note engine.phase has no callers. | public |  |  |  |
| F01 | normal/1 | undocumented | FIELD_GUIDE.md:15 defines coverage but not its precision. Seeded round(...,1) is a doc-consistent percentage (verified). | public |  | pure rounding/float-format defect | (a) FIELD_GUIDE.md line 15: "Coverage is the percentage of selected ground occupied by plants, rounded to two decimal places." |
| F02 | normal/1 | documented | FIELD_GUIDE.md:16 ("vitality averages describe living plants") | public |  | expects float 80.0 (canonical JSON distinguishes 80); existing round(...,2) yields a float |  |
| F03 | normal/1 | documented | FIELD_GUIDE.md:17-18 (Shannon entropy with natural logarithms) | public |  | 4-decimal rounding comes from unchanged code |  |
| F04 | normal/1 | documented | FIELD_GUIDE.md:22-23 ("accounts for ... shelter from structures") | public |  |  |  |
| F05 | normal/1 | documented | FIELD_GUIDE.md:23-24 ("normally omit occupied ground") + empty_only parameter | public |  | probe sorts results itself (order-insensitive) |  |
| F06 | normal/1 | undocumented | FIELD_GUIDE.md:21-22 lists "short of water, nutrients or vigor"; no visible stress threshold or >= vs > (verified a `> 50` reading fails) | public |  | boundary-only | (a) FIELD_GUIDE.md line 21-22: "Reports also identify plants that need attention, such as those short of water, nutrients or vigor, or with stress of 50 or more." |
| F07 | normal/1 | undocumented | FIELD_GUIDE.md:27-30 describes patches but no ordering; the defect is ordering-only | public |  | ordering the visible docs never fix (RUBRIC: do not floor over ordering) | (a) FIELD_GUIDE.md line 27: "Patch surveys show connected areas of plants, largest first; equal sizes are ordered by their topmost, then leftmost, tile." |
| F08 | normal/1 | undocumented | FIELD_GUIDE.md:29-31 ("straight line through tile centers ... both ends ... preserving the chosen direction") does not name Bresenham or its tie-breaking; the probe's expected reverse path is not the reverse of the forward path. Verified a symmetric line fails. (Weakly inferable by recognising the canonical `e2 >= dy` form.) | public |  | asserts direction-dependent tie-breaking | (a) FIELD_GUIDE.md line 29-30: "A transect instead follows the integer Bresenham line from one selected endpoint to the other, including both ends and preserving the chosen direction." |
| F09 | normal/1 | documented | FIELD_GUIDE.md:56-58 (example samples 0,3,6,9,10) | public |  |  |  |
| F10 | normal/1 | inferable | WORKBENCH.md:51-53 ("filter by tag", tags normalised) vs. substring text search | public |  |  |  |
| F11 | normal/1 | documented | WORKBENCH.md:51-52 ("inclusive date range") | public |  |  |  |
| F12 | normal/1 | inferable | WORKBENCH.md:56 (specimens preserve measurements); state.py:82-83 requires specimen vitality on load | public |  |  |  |
| F13 | normal/1 | documented | WORKBENCH.md:62-63 ("overdue tasks are from earlier days") | public |  |  |  |
| F14 | normal/1 | documented | WORKBENCH.md:61-62 ("marked complete, reopened") | public |  |  |  |
| F15 | normal/1 | documented | WORKBENCH.md:63 ("Lists place earlier due dates first") | public |  |  |  |
| F16 | normal/1 | documented | GROWING.md:20 ("Day zero is the first day of Dawn") | public |  |  |  |
| F17 | normal/1 | inferable | GROWING.md:20-22 ("Highsummer is hotter and drier"); weather.py:21 wetness tuple vs season order | public |  | exact weather strings depend on the unchanged seeded RNG |  |
| F18 | normal/1 | documented | FIELD_GUIDE.md:43-44 ("consecutive dry days"); key longest_dry_spell | internal-tolerant | monkeypatches weather.weather_on |  |  |
| F19 | normal/1 | documented | FIELD_GUIDE.md:43, 46-47 (almanac starts tomorrow; next_weather finds a future day) | internal-tolerant | monkeypatches weather.weather_on |  |  |
| F20 | normal/1 | documented | FIELD_GUIDE.md:44-45 ("remaining care-plan occurrences") + WORKBENCH.md:76-78 | public |  |  |  |
| F21 | normal/1 | documented | FIELD_GUIDE.md:76-77; COMMANDS.md:91 | internal-tolerant | monkeypatches experiments.execute (module global); a repair at the `<=` line keeps it effective |  |  |
| F22 | normal/1 | documented | FIELD_GUIDE.md:82 ("Initial and final observations are always included") | public |  |  |  |
| F23 | normal/1 | documented | FIELD_GUIDE.md:81-82 ("differences from control") | public |  |  |  |
| F24 | normal/1 | undocumented | FIELD_GUIDE.md:83 names rank_experiment but no tie order (STUDIES.md:38-39 states it only for studies); the seeded alphabetical tie-break is doc-consistent | public |  | ordering-only defect | (a) FIELD_GUIDE.md line 83: "...using `experiments.rank_experiment`; branches with equal values keep their experiment order." |
| F25 | normal/1 | inferable | experiments.py:22-24 stores casefolded names but compares raw ones | public |  |  |  |
| F26 | normal/1 | inferable | PORTABILITY.md:20-22 (one edit); every other mutator increments revision once; exchange.py duplicate increment | public |  |  |  |
| F27 | normal/1 | inferable | PORTABILITY.md:63-64 (horizontal mirror within the rectangle) | public |  |  |  |
| F28 | normal/1 | inferable | PORTABILITY.md:63-64 (clockwise quarter turns) | public |  |  |  |
| F29 | normal/1 | inferable | WORKBENCH.md:63 ("Lists place earlier due dates first"); PORTABILITY.md:72-73 does not state export order (weak) | public |  | line format comes from unchanged code | optional (a) PORTABILITY.md line 72: "Markdown export records ... task completion (tasks in due-date order) ..." |
| F30 | normal/1 | undocumented | FIELD_GUIDE.md:91-93 fixes the endpoints only; rounding vs truncation of intermediate channels is not visible | public |  | pure hex-formatting/rounding defect | (a) FIELD_GUIDE.md line 92-93: "...from sand (`#dab76d`) to teal (`#369294`), interpolating each colour channel and rounding to the nearest value, so colors ..." |
| F31 | normal/1 | documented | FIELD_GUIDE.md:93-94 ("Shade maps show the shelter plants experience, including structures") | public |  | parses SVG tile groups produced by unchanged code |  |
| F32 | normal/1 | documented | FIELD_GUIDE.md:96 + DESIGN.md:63-64 (actual dates) | public |  | exact cx strings fix the x-origin at the first observed day, which no guide states; verified a day-0-anchored chart (still "actual dates") fails | (a) FIELD_GUIDE.md line 96: "History charts span the first to the last recorded day and place observations at their actual dates." (or (c) compare spacing ratios + bounds) |
| P01 | normal/1 | inferable | Not in visible guides (contract cites hidden BEHAVIORS 1-2). Inferable from the strict-int convention: validation.py:5-7, engine.py:40, model.py:69-70 | public | shared prelude imports GardenServer/GardenHandler even when unused, so a server import failure fails this probe too |  | optional (a) GROWING.md line 13: "Coordinates are whole numbers (not booleans) starting at zero." |
| P02 | normal/1 | documented | PORTABILITY.md:16-18 (to_dict returns an independently editable representation) | public | shared prelude imports GardenServer/GardenHandler even when unused, so a server import failure fails this probe too |  |  |
| P03 | normal/1 | inferable | PORTABILITY.md:16-18 (prepare a separate garden from to_dict data); load-side ownership only implied; STUDIES.md:69 / HISTORY_EXCHANGE.md:73-74 state it for other APIs | public | shared prelude imports GardenServer/GardenHandler even when unused, so a server import failure fails this probe too |  |  |
| P04 | normal/1 | inferable | PORTABILITY.md:11-13 (inconsistent data rejected); model.py:88-89 message "Empty cell cannot have age or vitality" | public | shared prelude imports GardenServer/GardenHandler even when unused, so a server import failure fails this probe too |  |  |
| P05 | normal/1 | inferable | PORTABILITY.md:10-13 (versions 1 and 2); rejecting True inferable from the strict-int convention (model.py:69). Rejecting JSON 1.0/2.0 is NOT visible; verified a bool-only fix fails. | public | shared prelude imports GardenServer/GardenHandler even when unused, so a server import failure fails this probe too | over-asserts float versions beyond the reported symptom | (c) drop 1.0 and 2.0 from the probe inputs (True/False/0/3 still discriminate), or (a) PORTABILITY.md line 10: "reads save versions 1 and 2 (JSON integers)" |
| P06 | normal/1 | inferable | PORTABILITY.md:11-13 (validated on load); state.py:28-30 computes `unknown` then discards it (weak: dropping unknown fields is also a common design) | public | shared prelude imports GardenServer/GardenHandler even when unused, so a server import failure fails this probe too |  | optional (a) PORTABILITY.md line 13: "Unknown workbench fields are rejected." |
| P07 | normal/1 | inferable | WORKBENCH.md:66-67 (IDs never reused for a new object); single shared next_id (state.py:19-22); duplicated `ids = set()` (state.py:50,53) | public | shared prelude imports GardenServer/GardenHandler even when unused, so a server import failure fails this probe too |  |  |
| P08 | normal/1 | inferable | state.py:58 message "Identifiers must be unique and below next_id" | public | shared prelude imports GardenServer/GardenHandler even when unused, so a server import failure fails this probe too |  |  |
| P09 | normal/1 | inferable | GROWING.md:59-60 (daily census records); state.py:133 message "History days must increase" | public | shared prelude imports GardenServer/GardenHandler even when unused, so a server import failure fails this probe too |  |  |
| P10 | normal/1 | documented | GROWING.md:29-30 ("Neither supports plants"); state.py:143 message | public | shared prelude imports GardenServer/GardenHandler even when unused, so a server import failure fails this probe too |  |  |
| P11 | normal/1 | inferable | PORTABILITY.md:16-18 (as P03) | public | shared prelude imports GardenServer/GardenHandler even when unused, so a server import failure fails this probe too |  |  |
| P12 | normal/1 | documented | PORTABILITY.md:20 ("A JSON command uses op and args"); commands.py:42 message | public | shared prelude imports GardenServer/GardenHandler even when unused, so a server import failure fails this probe too |  |  |
| P13 | normal/1 | inferable | PORTABILITY.md:20-22 ("succeeds as one edit"); DESIGN.md:29 | internal-brittle | patches mosslight.commands._dispatch and executes a fake op "fixture"; verified: a correct repair that validates the op in execute() fails the probe |  | (b) verified rewrite: execute real commands (rename, grow 3 days, tend_many 3 tiles, note) on a world at revision 5; expect [6,6,6,6] (seeded [7,9,7,7]) |
| P14 | normal/1 | documented | PORTABILITY.md:89-90 ("saved before becoming available"; failure preserves garden and undo); DESIGN.md:57 (500) | internal-tolerant | object.__new__(GardenServer) bypasses __init__; patches mosslight.server.save; expects OSError to escape the internal publish() |  | (b) verified hardening: real make_server(world, 0, <path under a regular file>) + HTTP POST /api/command; expect status 500 with day/title/undo unchanged |
| P15 | normal/1 | documented | README.md:19; PORTABILITY.md:91-92 ("keeps 30 prior edits") | internal-brittle | object.__new__ server with a plain list undo_stack; verified: a correct repair using deque(maxlen=30) in __init__ fails | asserts internal undo-stack contents (`d["day"]`) | (b) verified rewrite: real server, 35 renames over HTTP, then undo until 409/400; expect undo count 30 and titles T33..T4 |
| P16 | normal/1 | documented | PORTABILITY.md:92 ("a new edit after undo starts a new branch") | internal-tolerant | object.__new__ server; seeds redo_stack directly |  | (b) move to the same HTTP harness (undo, edit, then GET /api/world redo == 0) |
| P17 | normal/1 | inferable | DESIGN.md:28-29, 57; PORTABILITY.md:83-85 speak of "stale" revisions; a future revision is not literally stale | internal-tolerant | object.__new__ handler with _json overridden |  | optional (a) DESIGN.md line 57: "A revision other than the current one, or a noninteger revision, returns 409." |
| P18 | normal/1 | documented | DESIGN.md:57 ("noninteger revision returns 409") | internal-tolerant | object.__new__ handler with _json overridden |  |  |
| P19 | normal/1 | documented | PORTABILITY.md:86-87 ("retain the imported save's revision") | internal-tolerant | object.__new__ handler with _json overridden |  |  |
| P20 | normal/1 | documented | PORTABILITY.md:90-91 ("restore prior garden contents as fresh revisions") | internal-tolerant | object.__new__ server; seeds undo/redo stacks directly |  |  |
| P21 | normal/1 | documented | PORTABILITY.md:30 ("CLI errors go to stderr with exit code 2") | internal-brittle | calls __main__.main() and requires a return value; verified: a correct repair that raises SystemExit(2) fails |  | (b) verified rewrite: runpy.run_module("mosslight", run_name="__main__") with sys.argv set, catching SystemExit; expect [2,2] |
| P22 | normal/1 | documented | PORTABILITY.md:31 ("requires a different output path from its source") | public |  |  |  |
| P23 | normal/1 | inferable | FIELD_GUIDE.md:90-91 (interactive maps support keyboard navigation); render_svg(interactive=False) flag otherwise has no effect | public | shared prelude imports GardenServer/GardenHandler even when unused, so a server import failure fails this probe too |  |  |
| P24 | normal/1 | documented | COURIER.md:36-41 ("Concurrent different values remain available") | internal-tolerant | asserts the truth table of the undocumented helper courier.precedes (incl. equality=True); a repair made in _heads instead would fail |  | (b) verified public rewrite: two fresh writers each put "pond", merge both ways, observations shows the conflict ["desk view","field view"] (seeded: []) |
| P25 | hard/5 | inferable | COURIER.md:44-47 (merged packet continues the left writer; reuse of event identity rejected) | internal-tolerant | builds packet JSON fields (counter/clock) directly | asserts put emits field+$alive events (existing format) |  |
| P26 | normal/1 | documented | COURIER.md:62-63 ("Supplied field values remain owned by the caller") | public |  |  |  |
| P27 | normal/1 | documented | COURIER.md:46-47 ("Conflicting reuse of a writer's event identity is rejected") | internal-tolerant | builds packet events directly (uses private _dot_key) |  |  |
| P28 | normal/1 | documented | COURIER.md:40-41 ("A simultaneous edit and deletion keeps the observation visible") | internal-tolerant | patch.object(courier, "_heads"): renaming/inlining _heads in a refactor makes it fail |  | (b) verified hardening without patching: build the two $alive events with explicit zero contexts {"desk":0,"field":0} so real _heads is unaffected by P24 |
| P29 | normal/1 | documented | COURIER.md:38-39 ("Text retains its exact spelling and case") | internal-tolerant | patch.object(courier, "_heads") |  | (b) verified hardening: explicit zero-filled contexts instead of patching _heads |
| P30 | hard/5 | documented | COURIER.md:51-54 (selection preserves observations it did not include) | internal-tolerant | builds packet contexts/events directly |  |  |
| P31 | hard/5 | documented | COURIER.md:53-54 ("does not imply that the recipient has seen another observation's edits or deletions") | internal-tolerant | asserts the packet "contexts" map exactly |  |  |
| P32 | normal/1 | documented | COURIER.md:59-60 (acknowledged: every named active device; missing ack supplies no progress) | public |  |  |  |
| P34 | hard/5 | documented | COURIER.md:53-54, 56-59 (record_clock per observation; sharing one does not imply another) | internal-tolerant | patch.object(courier, "precedes") raises AttributeError if precedes is renamed/removed |  | (b) verified: add create=True to the patch.object call |
| X01 | hard/5 | documented | CAMPAIGNS.md:24-25 ("Resuming it uses those recorded inputs"), 57-58 | internal-tolerant | replaces campaigns.step_for to record releases |  |  |
| V01 | hard/5 | inferable | CAMPAIGNS.md:73-77 (reclaim after 30 s; single coherent history) | internal-tolerant | drives the public-but-undocumented claim/compute/publish worker protocol with an injected clock | asserts generation counters [1,2] (internal) | optional (c): drop the generation pair; ordinals + publish()==False carry the contract |
| V02 | hard/5 | documented | CAMPAIGNS.md:58-60 ("care already performed at the checkpoint remains part of its starting garden") | public | fork/checkpoint |  |  |
| V03 | hard/5 | documented | CAMPAIGNS.md:66-68 (compaction keeps origins of existing descendants) | public |  |  |  |
| V04 | hard/5 | inferable | CAMPAIGNS.md:37-39, 75-77 (durable progress; single coherent history) | internal-brittle | patch.object(store, "_checkpoint") + raw SQL on `branches`; verified: a correct single-transaction repair that inlines the checkpoint INSERT fails (AssertionError) | asserts the raw JSON state column | (b) verified rewrite: wrap store.db in a proxy raising OSError on INSERT/UPDATE touching `checkpoints`, observe via public status() and a re-claim(); expect [[True,"running"],[0,0,0]] (seeded [[True,"ready"],[0,1,1]]) |
| X02 | hard/5 | documented | HISTORY.md:34-37 (later references keep identifying their objects across renumbering) | internal-brittle | `store.db.execute('DELETE FROM history_checkpoints')` crashes if an H01 repair renames/migrates the cache table (verified) | asserts reassigned local ids [1,2] (deterministic replay) | (b) verified: wrap the DELETE in try/except Exception: pass |
| H01 | hard/5 | documented | HISTORY.md:34-38, 83-86 (corrections revise consequences; verify replays authoritatively) | public |  |  |  |
| H02 | normal/1 | documented | HISTORY.md:60-62 ("A shared action is included once; independently authored actions remain distinct") | internal-brittle | same DELETE FROM history_checkpoints dependency (verified) |  | (b) verified: tolerant DELETE |
| H03 | hard/5 | documented | HISTORY.md:64-69 (rebase retains local changes; records revisions used) | internal-brittle | same DELETE FROM history_checkpoints dependency (verified) |  | (b) verified: tolerant DELETE |
| H04 | hard/5 | documented | HISTORY.md:38 ("Numeric IDs in a replacement refer to the garden at that point in the history") | public |  | asserts stored canonical command form ["$ref"] (internal representation, unchanged by the fix) |  |
| H05 | hard/5 | documented | HISTORY.md:64-68 ("incompatible action orders require review") | internal-brittle | DELETE FROM history_checkpoints (verified) plus raw `SELECT COUNT(*) FROM history_branches` | asserts details['kind']=='order-conflict' (kind names not in guides; string exists in history.py) | (b) verified: tolerant DELETE; optional: replace the branch COUNT with a public check |
| H06 | hard/5 | inferable | HISTORY.md:34-38, 64-69 (references keep identity; shared actions retain identity) | internal-tolerant | calls private history._rebase_events directly (isolates it from X02/H01; a public scenario would couple to X02) |  | keep; accept the private-call risk or document it in a host note |
| R01 | hard/5 | documented | ENSEMBLES.md:72-74 (each garden vs. its own control; complete pairs; excluded listed) | internal-tolerant | prepare/compute/publish worker protocol | comparator paired_means is already relaxed |  |
| R02 | hard/5 | documented | ENSEMBLES.md:64-65 (published report per revision survives edits/restarts) | public |  | comparator immutable_report is already relaxed |  |
| R03 | normal/1 | documented | ENSEMBLES.md:71-72 ("Source labels identify distinct comparison members even when two sources contain equal saves") | internal-brittle | asserts compute()'s internal return (`identity`, `cache_hit`); verified: a correct repair that publishes the ticket's identity fails |  | (b) verified rewrite: finish via work_once, assert sorted report identities are the 4 distinct (tray, treatment) pairs |
| M01 | normal/1 | documented | SAVE_MERGE.md:23-25 ("Independently created records stay separate, even if ... same number or text") | public |  | asserts exact new ids 2,3, next_id 4 and receipt key encoding (guides say only "unique local identifiers") | optional (c): assert two distinct ids, both texts, next_id > max id |
| X03 | hard/5 | documented | HISTORY_EXCHANGE.md:49-51 ("Repeated rounds ... must retain later edits and reversions") | internal-brittle | device.db DELETE FROM history_checkpoints (verified) |  | (b) verified: tolerant DELETE |
| Q01 | hard/5 | documented | STUDIES.md:43-45 ("Selection becomes final only when all stage trials have finished or failed") | internal-tolerant | claim/compute/publish/preview with injected clock |  |  |
| Q02 | hard/5 | documented | STUDIES.md:49-50, 67-68 (later stages extend the same experiments; checkpoint by study/stage/source/treatment) | public |  | asserts full decision dict from unchanged code |  |
| N02 | hard/5 | documented | WORKSPACE_CATALOG.md:28-30, 39-40 (normalised search; format-1 upgrade) | internal-tolerant | uses undocumented WorkspaceCatalog.add and hand-builds a format-1 SQLite file (legitimate legacy fixture) |  |  |
| L01 | hard/5 | documented | ENSEMBLES.md:64-68 ("Working and editing concurrently must produce reports consistent with their named inputs") | internal-tolerant | prepare/compute/publish worker protocol |  |  |
| I02 | legendary/20 | documented | IRRIGATION.md:18-21 (highest final total vitality; more tank water breaks ties) | internal-tolerant | replaces irrigation.step_for with a fixture ecology | comparator irrigation_optimum already accepts any optimal schedule |  |
| N01 | hard/5 | inferable | FIELD_CALIBRATION.md:4-5 (least-squares trend), 13-14 (epoch and negative timestamps allowed) | public |  | abs_tol 1e-9 is tight but centred implementations are exact here |  |
| I01 | extreme/10 | documented | IRRIGATION.md:51-54 ("delivers as much water as ... capacities permit"; whole units) | internal-tolerant | mosslight.irrigation_flow.allocate is not named in the guide (IRRIGATION.md documents definition/solve/replay) | comparator flow accepts any max flow; randomised capacities |  |

## Contracts citing hidden BEHAVIORS line numbers (P01-P23)

- P01: not stated; inferable from strict-int validators (validation.py:5-7, engine.py:40, model.py:69-70)
- P02: PORTABILITY.md:16-18
- P03: PORTABILITY.md:16-18 (to_dict side only; load side implied)
- P04: PORTABILITY.md:11-13 (general) + model.py:88-89 message
- P05: PORTABILITY.md:10-13 (versions 1 and 2; strictness not stated)
- P06: not stated; PORTABILITY.md:11-13 (general) + state.py:28-30
- P07: WORKBENCH.md:66-67 (partial) + state.py:19-22
- P08: state.py:58 message only
- P09: GROWING.md:59-60 (partial) + state.py:133 message
- P10: GROWING.md:29-30
- P11: PORTABILITY.md:16-18 (implied)
- P12: PORTABILITY.md:20 + commands.py:42 message
- P13: PORTABILITY.md:20-22; DESIGN.md:29
- P14: PORTABILITY.md:89-90
- P15: README.md:19; PORTABILITY.md:91-92
- P16: PORTABILITY.md:92
- P17: DESIGN.md:57; PORTABILITY.md:83-85 ("stale" only)
- P18: DESIGN.md:57
- P19: PORTABILITY.md:86-87
- P20: PORTABILITY.md:90-91
- P21: PORTABILITY.md:30
- P22: PORTABILITY.md:31
- P23: FIELD_GUIDE.md:90-91 (interactive side only)
