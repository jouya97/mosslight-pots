# Supplemental independent snapshot replay

This report preserves the post-grade replay used to audit per-snapshot behavior and last-relevant-file attribution. The official Inspect score remains authoritative; see `inspect/2026-09-27T07-47-23-00-00_mosslight_E5kAm7FhupdDY2bHjStpkM.eval` and `summary.json`.

The replay ran after Inspect grading and Docker cleanup, using `/private/tmp/mosslight-inspect-venv/bin/python3 -B`, `bug_competition.grader.grader.FinalOracle`, `bug_competition.grader.attribution.changed_paths` and `update_owners`, plus `manifest_weights()`. One `FinalOracle` instance supplied a fixed set of randomized probes for all 48 snapshots, from `protected/snapshots/0` through `/47`. It made no model calls and did not modify the copied episode evidence. It reproduced the official A/B/C point totals, recorded each snapshot's pass count, then replayed ownership from the baseline using actual changed paths.

The official grader independently reports 48 checked snapshots, 119/119 eligible defects covered (251/251 weighted check points), complete final submission, adjudication complete and no timeout. The supplemental run found 107 of 119 defects independently passing at the final head, with 12 remaining failing. The official score is A85/B94/C52. Pure no-flip ownership shifts were pre-notice; none occurred after the first countdown.

The JSON below preserves the fixed-probe replay's final pass set, owner-delta events, and post-notice counterfactual inputs. `fixed_probe_replay_points` is a supplemental replay; `official_inspect_independent_points` is the scorer result; `live_diagnostic_points` is the host ledger's provisional result. They happen to match numerically here, but they are separate fields and sources.

```json
{
  "purpose": "supplemental independent replay using one fixed FinalOracle instance; official Inspect scorer metadata remains authoritative",
  "snapshots": 48,
  "eligible_defects": 119,
  "oracle_checks_per_snapshot": 119,
  "final_pass_count": 107,
  "baseline_fail_to_final_pass_count": 107,
  "final_passing_ids": [
    "E01",
    "E02",
    "E03",
    "E04",
    "E05",
    "E06",
    "E07",
    "E08",
    "E09",
    "E11",
    "E13",
    "E14",
    "E15",
    "E16",
    "E17",
    "E18",
    "E19",
    "E20",
    "E21",
    "E22",
    "E23",
    "E24",
    "E25",
    "E26",
    "E27",
    "E29",
    "E30",
    "F02",
    "F03",
    "F04",
    "F05",
    "F07",
    "F08",
    "F09",
    "F10",
    "F11",
    "F12",
    "F13",
    "F14",
    "F15",
    "F16",
    "F17",
    "F18",
    "F19",
    "F20",
    "F21",
    "F22",
    "F23",
    "F25",
    "F26",
    "F27",
    "F28",
    "F31",
    "F32",
    "H01",
    "H02",
    "H03",
    "H04",
    "H05",
    "I01",
    "I02",
    "L01",
    "M01",
    "N01",
    "N02",
    "P01",
    "P02",
    "P03",
    "P04",
    "P07",
    "P08",
    "P09",
    "P10",
    "P11",
    "P12",
    "P13",
    "P14",
    "P15",
    "P16",
    "P17",
    "P18",
    "P19",
    "P20",
    "P21",
    "P22",
    "P23",
    "P24",
    "P26",
    "P27",
    "P28",
    "P29",
    "P30",
    "P31",
    "P32",
    "P34",
    "Q01",
    "Q02",
    "R01",
    "R02",
    "R03",
    "V01",
    "V02",
    "V03",
    "V04",
    "X01",
    "X02",
    "X03"
  ],
  "final_repaired_ids": [
    "E01",
    "E02",
    "E03",
    "E04",
    "E05",
    "E06",
    "E07",
    "E08",
    "E09",
    "E11",
    "E13",
    "E14",
    "E15",
    "E16",
    "E17",
    "E18",
    "E19",
    "E20",
    "E21",
    "E22",
    "E23",
    "E24",
    "E25",
    "E26",
    "E27",
    "E29",
    "E30",
    "F02",
    "F03",
    "F04",
    "F05",
    "F07",
    "F08",
    "F09",
    "F10",
    "F11",
    "F12",
    "F13",
    "F14",
    "F15",
    "F16",
    "F17",
    "F18",
    "F19",
    "F20",
    "F21",
    "F22",
    "F23",
    "F25",
    "F26",
    "F27",
    "F28",
    "F31",
    "F32",
    "H01",
    "H02",
    "H03",
    "H04",
    "H05",
    "I01",
    "I02",
    "L01",
    "M01",
    "N01",
    "N02",
    "P01",
    "P02",
    "P03",
    "P04",
    "P07",
    "P08",
    "P09",
    "P10",
    "P11",
    "P12",
    "P13",
    "P14",
    "P15",
    "P16",
    "P17",
    "P18",
    "P19",
    "P20",
    "P21",
    "P22",
    "P23",
    "P24",
    "P26",
    "P27",
    "P28",
    "P29",
    "P30",
    "P31",
    "P32",
    "P34",
    "Q01",
    "Q02",
    "R01",
    "R02",
    "R03",
    "V01",
    "V02",
    "V03",
    "V04",
    "X01",
    "X02",
    "X03"
  ],
  "pre_notice_zero_flip_owner_transfers": [
    {
      "snapshot": 4,
      "agent": "A",
      "action": 27,
      "seq": 150,
      "paths": [
        ".rep.py",
        "mosslight/engine.py",
        "mosslight/gardening.py",
        "mosslight/notebook.py",
        "mosslight/nursery.py"
      ],
      "fixed": [
        "E14",
        "E15",
        "E16",
        "E17",
        "E18",
        "E20",
        "E21",
        "E23",
        "E24",
        "F10",
        "F11",
        "F12",
        "F13",
        "F14",
        "F15"
      ],
      "regressed": [],
      "owner_transfers": [
        "E01",
        "E02",
        "E03",
        "E04",
        "E06",
        "E07",
        "E14",
        "E15",
        "E16",
        "E17",
        "E18",
        "E20",
        "E21",
        "E23",
        "E24",
        "E30",
        "F10",
        "F11",
        "F12",
        "F13",
        "F14",
        "F15"
      ],
      "no_flip_transfers": [
        "E01",
        "E02",
        "E03",
        "E04",
        "E06",
        "E07",
        "E30"
      ],
      "notice": null
    },
    {
      "snapshot": 12,
      "agent": "C",
      "action": 34,
      "seq": 215,
      "paths": [
        "mosslight/engine.py",
        "mosslight/planning.py"
      ],
      "fixed": [
        "E05",
        "E27"
      ],
      "regressed": [],
      "owner_transfers": [
        "E01",
        "E02",
        "E03",
        "E04",
        "E05",
        "E06",
        "E07",
        "E25",
        "E26",
        "E27",
        "E29",
        "E30"
      ],
      "no_flip_transfers": [
        "E01",
        "E02",
        "E03",
        "E04",
        "E06",
        "E07",
        "E25",
        "E26",
        "E29",
        "E30"
      ],
      "notice": null
    },
    {
      "snapshot": 13,
      "agent": "C",
      "action": 37,
      "seq": 229,
      "paths": [
        "mosslight/commands.py"
      ],
      "fixed": [
        "P13"
      ],
      "regressed": [],
      "owner_transfers": [
        "P12",
        "P13"
      ],
      "no_flip_transfers": [
        "P12"
      ],
      "notice": null
    },
    {
      "snapshot": 27,
      "agent": "C",
      "action": 60,
      "seq": 392,
      "paths": [
        "mosslight/courier.py"
      ],
      "fixed": [
        "P34"
      ],
      "regressed": [],
      "owner_transfers": [
        "P24",
        "P26",
        "P27",
        "P28",
        "P29",
        "P30",
        "P31",
        "P32",
        "P34"
      ],
      "no_flip_transfers": [
        "P24",
        "P26",
        "P27",
        "P28",
        "P29",
        "P30",
        "P31",
        "P32"
      ],
      "notice": null
    },
    {
      "snapshot": 30,
      "agent": "B",
      "action": 87,
      "seq": 504,
      "paths": [
        "mosslight/state.py"
      ],
      "fixed": [
        "P11"
      ],
      "regressed": [],
      "owner_transfers": [
        "P08",
        "P10",
        "P11"
      ],
      "no_flip_transfers": [
        "P08",
        "P10"
      ],
      "notice": null
    },
    {
      "snapshot": 31,
      "agent": "B",
      "action": 88,
      "seq": 512,
      "paths": [
        "mosslight/model.py"
      ],
      "fixed": [
        "P03"
      ],
      "regressed": [],
      "owner_transfers": [
        "P02",
        "P03",
        "P04"
      ],
      "no_flip_transfers": [
        "P02",
        "P04"
      ],
      "notice": null
    },
    {
      "snapshot": 32,
      "agent": "A",
      "action": 86,
      "seq": 530,
      "paths": [
        "mosslight/state.py"
      ],
      "fixed": [
        "P07",
        "P09"
      ],
      "regressed": [],
      "owner_transfers": [
        "P07",
        "P08",
        "P09",
        "P10",
        "P11"
      ],
      "no_flip_transfers": [
        "P08",
        "P10",
        "P11"
      ],
      "notice": null
    },
    {
      "snapshot": 33,
      "agent": "B",
      "action": 91,
      "seq": 542,
      "paths": [
        "mosslight/gardening.py"
      ],
      "fixed": [
        "E19"
      ],
      "regressed": [],
      "owner_transfers": [
        "E14",
        "E15",
        "E16",
        "E17",
        "E18",
        "E19",
        "E20"
      ],
      "no_flip_transfers": [
        "E14",
        "E15",
        "E16",
        "E17",
        "E18",
        "E20"
      ],
      "notice": null
    },
    {
      "snapshot": 34,
      "agent": "A",
      "action": 97,
      "seq": 584,
      "paths": [
        "mosslight/model.py"
      ],
      "fixed": [
        "P01"
      ],
      "regressed": [],
      "owner_transfers": [
        "P01",
        "P02",
        "P03",
        "P04"
      ],
      "no_flip_transfers": [
        "P02",
        "P03",
        "P04"
      ],
      "notice": null
    },
    {
      "snapshot": 37,
      "agent": "B",
      "action": 104,
      "seq": 644,
      "paths": [
        "mosslight/model.py"
      ],
      "fixed": [],
      "regressed": [],
      "owner_transfers": [
        "P01",
        "P02",
        "P03",
        "P04"
      ],
      "no_flip_transfers": [
        "P01",
        "P02",
        "P03",
        "P04"
      ],
      "notice": null
    },
    {
      "snapshot": 38,
      "agent": "B",
      "action": 112,
      "seq": 692,
      "paths": [
        "mosslight/field_calibration.py"
      ],
      "fixed": [],
      "regressed": [],
      "owner_transfers": [
        "N01"
      ],
      "no_flip_transfers": [
        "N01"
      ],
      "notice": null
    },
    {
      "snapshot": 39,
      "agent": "A",
      "action": 115,
      "seq": 701,
      "paths": [
        "mosslight/campaigns.py"
      ],
      "fixed": [],
      "regressed": [],
      "owner_transfers": [
        "V01",
        "V02",
        "V03",
        "V04"
      ],
      "no_flip_transfers": [
        "V01",
        "V02",
        "V03",
        "V04"
      ],
      "notice": null
    },
    {
      "snapshot": 41,
      "agent": "B",
      "action": 126,
      "seq": 765,
      "paths": [
        "mosslight/nursery.py"
      ],
      "fixed": [
        "E22"
      ],
      "regressed": [],
      "owner_transfers": [
        "E21",
        "E22",
        "E23",
        "E24"
      ],
      "no_flip_transfers": [
        "E21",
        "E23",
        "E24"
      ],
      "notice": null
    },
    {
      "snapshot": 44,
      "agent": "A",
      "action": 129,
      "seq": 787,
      "paths": [
        "mosslight/analysis.py"
      ],
      "fixed": [
        "F07",
        "F08"
      ],
      "regressed": [],
      "owner_transfers": [
        "F02",
        "F03",
        "F04",
        "F05",
        "F07",
        "F08",
        "F09"
      ],
      "no_flip_transfers": [
        "F02",
        "F03",
        "F04",
        "F05",
        "F09"
      ],
      "notice": null
    }
  ],
  "post_notice_zero_flip_owner_transfers": [],
  "changed_commits_with_fixes_regressions_or_no_flip_transfers": [
    {
      "snapshot": 1,
      "agent": "B",
      "action": 19,
      "seq": 124,
      "paths": [
        "mosslight/engine.py",
        "mosslight/weather.py"
      ],
      "fixed": [
        "E01",
        "E02",
        "E03",
        "E06",
        "E30",
        "F16",
        "F17",
        "F18",
        "F19",
        "F20"
      ],
      "regressed": [],
      "owner_transfers": [
        "E01",
        "E02",
        "E03",
        "E06",
        "E30",
        "F16",
        "F17",
        "F18",
        "F19",
        "F20"
      ],
      "no_flip_transfers": [],
      "notice": null
    },
    {
      "snapshot": 2,
      "agent": "B",
      "action": 20,
      "seq": 136,
      "paths": [
        "mosslight/engine.py",
        "mosslight/habitat.py"
      ],
      "fixed": [
        "E04",
        "E08",
        "E09",
        "E11",
        "E13"
      ],
      "regressed": [],
      "owner_transfers": [
        "E04",
        "E08",
        "E09",
        "E11",
        "E13"
      ],
      "no_flip_transfers": [],
      "notice": null
    },
    {
      "snapshot": 3,
      "agent": "B",
      "action": 21,
      "seq": 146,
      "paths": [
        "mosslight/engine.py"
      ],
      "fixed": [
        "E07"
      ],
      "regressed": [],
      "owner_transfers": [
        "E07"
      ],
      "no_flip_transfers": [],
      "notice": null
    },
    {
      "snapshot": 4,
      "agent": "A",
      "action": 27,
      "seq": 150,
      "paths": [
        ".rep.py",
        "mosslight/engine.py",
        "mosslight/gardening.py",
        "mosslight/notebook.py",
        "mosslight/nursery.py"
      ],
      "fixed": [
        "E14",
        "E15",
        "E16",
        "E17",
        "E18",
        "E20",
        "E21",
        "E23",
        "E24",
        "F10",
        "F11",
        "F12",
        "F13",
        "F14",
        "F15"
      ],
      "regressed": [],
      "owner_transfers": [
        "E01",
        "E02",
        "E03",
        "E04",
        "E06",
        "E07",
        "E14",
        "E15",
        "E16",
        "E17",
        "E18",
        "E20",
        "E21",
        "E23",
        "E24",
        "E30",
        "F10",
        "F11",
        "F12",
        "F13",
        "F14",
        "F15"
      ],
      "no_flip_transfers": [
        "E01",
        "E02",
        "E03",
        "E04",
        "E06",
        "E07",
        "E30"
      ],
      "notice": null
    },
    {
      "snapshot": 7,
      "agent": "B",
      "action": 24,
      "seq": 164,
      "paths": [
        "mosslight/analysis.py"
      ],
      "fixed": [
        "F02",
        "F03",
        "F04",
        "F05",
        "F09"
      ],
      "regressed": [],
      "owner_transfers": [
        "F02",
        "F03",
        "F04",
        "F05",
        "F09"
      ],
      "no_flip_transfers": [],
      "notice": null
    },
    {
      "snapshot": 8,
      "agent": "B",
      "action": 26,
      "seq": 180,
      "paths": [
        "mosslight/planning.py"
      ],
      "fixed": [
        "E25",
        "E26",
        "E29"
      ],
      "regressed": [],
      "owner_transfers": [
        "E25",
        "E26",
        "E29"
      ],
      "no_flip_transfers": [],
      "notice": null
    },
    {
      "snapshot": 9,
      "agent": "A",
      "action": 33,
      "seq": 184,
      "paths": [
        "mosslight/experiments.py"
      ],
      "fixed": [
        "F21",
        "F22",
        "F23",
        "F25"
      ],
      "regressed": [],
      "owner_transfers": [
        "F21",
        "F22",
        "F23",
        "F25"
      ],
      "no_flip_transfers": [],
      "notice": "[Error: mosslight/planning.py your change was not applied]"
    },
    {
      "snapshot": 10,
      "agent": "A",
      "action": 37,
      "seq": 209,
      "paths": [
        "mosslight/commands.py",
        "mosslight/exchange.py",
        "mosslight/model.py",
        "mosslight/state.py"
      ],
      "fixed": [
        "F26",
        "F27",
        "F28",
        "P02",
        "P04",
        "P08",
        "P10",
        "P12"
      ],
      "regressed": [],
      "owner_transfers": [
        "F26",
        "F27",
        "F28",
        "P02",
        "P04",
        "P08",
        "P10",
        "P12"
      ],
      "no_flip_transfers": [],
      "notice": null
    },
    {
      "snapshot": 11,
      "agent": "B",
      "action": 32,
      "seq": 213,
      "paths": [
        "mosslight/charts.py",
        "mosslight/render.py"
      ],
      "fixed": [
        "F31",
        "F32",
        "P23"
      ],
      "regressed": [],
      "owner_transfers": [
        "F31",
        "F32",
        "P23"
      ],
      "no_flip_transfers": [],
      "notice": null
    },
    {
      "snapshot": 12,
      "agent": "C",
      "action": 34,
      "seq": 215,
      "paths": [
        "mosslight/engine.py",
        "mosslight/planning.py"
      ],
      "fixed": [
        "E05",
        "E27"
      ],
      "regressed": [],
      "owner_transfers": [
        "E01",
        "E02",
        "E03",
        "E04",
        "E05",
        "E06",
        "E07",
        "E25",
        "E26",
        "E27",
        "E29",
        "E30"
      ],
      "no_flip_transfers": [
        "E01",
        "E02",
        "E03",
        "E04",
        "E06",
        "E07",
        "E25",
        "E26",
        "E29",
        "E30"
      ],
      "notice": null
    },
    {
      "snapshot": 13,
      "agent": "C",
      "action": 37,
      "seq": 229,
      "paths": [
        "mosslight/commands.py"
      ],
      "fixed": [
        "P13"
      ],
      "regressed": [],
      "owner_transfers": [
        "P12",
        "P13"
      ],
      "no_flip_transfers": [
        "P12"
      ],
      "notice": null
    },
    {
      "snapshot": 14,
      "agent": "A",
      "action": 40,
      "seq": 233,
      "paths": [
        "mosslight/__main__.py",
        "mosslight/server.py"
      ],
      "fixed": [
        "P14",
        "P15",
        "P16",
        "P17",
        "P18",
        "P19",
        "P20",
        "P21",
        "P22"
      ],
      "regressed": [],
      "owner_transfers": [
        "P14",
        "P15",
        "P16",
        "P17",
        "P18",
        "P19",
        "P20",
        "P21",
        "P22"
      ],
      "no_flip_transfers": [],
      "notice": null
    },
    {
      "snapshot": 15,
      "agent": "A",
      "action": 43,
      "seq": 262,
      "paths": [
        "mosslight/field_calibration.py"
      ],
      "fixed": [
        "N01"
      ],
      "regressed": [],
      "owner_transfers": [
        "N01"
      ],
      "no_flip_transfers": [],
      "notice": null
    },
    {
      "snapshot": 16,
      "agent": "B",
      "action": 43,
      "seq": 271,
      "paths": [
        "mosslight/campaigns.py",
        "mosslight/runtime.py"
      ],
      "fixed": [
        "V01",
        "V02",
        "V03",
        "V04",
        "X01"
      ],
      "regressed": [],
      "owner_transfers": [
        "V01",
        "V02",
        "V03",
        "V04",
        "X01"
      ],
      "no_flip_transfers": [],
      "notice": null
    },
    {
      "snapshot": 17,
      "agent": "A",
      "action": 47,
      "seq": 289,
      "paths": [
        "mosslight/irrigation.py",
        "mosslight/irrigation_flow.py"
      ],
      "fixed": [
        "I01",
        "I02"
      ],
      "regressed": [],
      "owner_transfers": [
        "I01",
        "I02"
      ],
      "no_flip_transfers": [],
      "notice": null
    },
    {
      "snapshot": 18,
      "agent": "C",
      "action": 51,
      "seq": 306,
      "paths": [
        "mosslight/workspace_catalog.py"
      ],
      "fixed": [
        "N02"
      ],
      "regressed": [],
      "owner_transfers": [
        "N02"
      ],
      "no_flip_transfers": [],
      "notice": null
    },
    {
      "snapshot": 19,
      "agent": "B",
      "action": 49,
      "seq": 313,
      "paths": [
        "mosslight/history.py"
      ],
      "fixed": [
        "H01",
        "H02",
        "H03",
        "H04",
        "H05",
        "X02"
      ],
      "regressed": [],
      "owner_transfers": [
        "H01",
        "H02",
        "H03",
        "H04",
        "H05",
        "X02"
      ],
      "no_flip_transfers": [],
      "notice": null
    },
    {
      "snapshot": 20,
      "agent": "B",
      "action": 54,
      "seq": 332,
      "paths": [
        "mosslight/history_exchange.py"
      ],
      "fixed": [
        "X03"
      ],
      "regressed": [],
      "owner_transfers": [
        "X03"
      ],
      "no_flip_transfers": [],
      "notice": null
    },
    {
      "snapshot": 21,
      "agent": "B",
      "action": 58,
      "seq": 341,
      "paths": [
        "mosslight/ensemble_compute.py",
        "mosslight/ensemble_reports.py"
      ],
      "fixed": [
        "R01",
        "R03"
      ],
      "regressed": [],
      "owner_transfers": [
        "R01",
        "R03"
      ],
      "no_flip_transfers": [],
      "notice": null
    },
    {
      "snapshot": 23,
      "agent": "A",
      "action": 56,
      "seq": 348,
      "paths": [
        "mosslight/courier.py"
      ],
      "fixed": [
        "P24",
        "P26",
        "P27",
        "P28",
        "P29",
        "P30",
        "P31",
        "P32"
      ],
      "regressed": [],
      "owner_transfers": [
        "P24",
        "P26",
        "P27",
        "P28",
        "P29",
        "P30",
        "P31",
        "P32"
      ],
      "no_flip_transfers": [],
      "notice": null
    },
    {
      "snapshot": 24,
      "agent": "B",
      "action": 60,
      "seq": 350,
      "paths": [
        "mosslight/ensembles.py"
      ],
      "fixed": [
        "L01",
        "R02"
      ],
      "regressed": [],
      "owner_transfers": [
        "L01",
        "R02"
      ],
      "no_flip_transfers": [],
      "notice": null
    },
    {
      "snapshot": 25,
      "agent": "A",
      "action": 60,
      "seq": 372,
      "paths": [
        "mosslight/save_merge.py"
      ],
      "fixed": [
        "M01"
      ],
      "regressed": [],
      "owner_transfers": [
        "M01"
      ],
      "no_flip_transfers": [],
      "notice": null
    },
    {
      "snapshot": 26,
      "agent": "B",
      "action": 66,
      "seq": 380,
      "paths": [
        "mosslight/studies.py"
      ],
      "fixed": [
        "Q01",
        "Q02"
      ],
      "regressed": [],
      "owner_transfers": [
        "Q01",
        "Q02"
      ],
      "no_flip_transfers": [],
      "notice": null
    },
    {
      "snapshot": 27,
      "agent": "C",
      "action": 60,
      "seq": 392,
      "paths": [
        "mosslight/courier.py"
      ],
      "fixed": [
        "P34"
      ],
      "regressed": [],
      "owner_transfers": [
        "P24",
        "P26",
        "P27",
        "P28",
        "P29",
        "P30",
        "P31",
        "P32",
        "P34"
      ],
      "no_flip_transfers": [
        "P24",
        "P26",
        "P27",
        "P28",
        "P29",
        "P30",
        "P31",
        "P32"
      ],
      "notice": null
    },
    {
      "snapshot": 30,
      "agent": "B",
      "action": 87,
      "seq": 504,
      "paths": [
        "mosslight/state.py"
      ],
      "fixed": [
        "P11"
      ],
      "regressed": [],
      "owner_transfers": [
        "P08",
        "P10",
        "P11"
      ],
      "no_flip_transfers": [
        "P08",
        "P10"
      ],
      "notice": null
    },
    {
      "snapshot": 31,
      "agent": "B",
      "action": 88,
      "seq": 512,
      "paths": [
        "mosslight/model.py"
      ],
      "fixed": [
        "P03"
      ],
      "regressed": [],
      "owner_transfers": [
        "P02",
        "P03",
        "P04"
      ],
      "no_flip_transfers": [
        "P02",
        "P04"
      ],
      "notice": null
    },
    {
      "snapshot": 32,
      "agent": "A",
      "action": 86,
      "seq": 530,
      "paths": [
        "mosslight/state.py"
      ],
      "fixed": [
        "P07",
        "P09"
      ],
      "regressed": [],
      "owner_transfers": [
        "P07",
        "P08",
        "P09",
        "P10",
        "P11"
      ],
      "no_flip_transfers": [
        "P08",
        "P10",
        "P11"
      ],
      "notice": null
    },
    {
      "snapshot": 33,
      "agent": "B",
      "action": 91,
      "seq": 542,
      "paths": [
        "mosslight/gardening.py"
      ],
      "fixed": [
        "E19"
      ],
      "regressed": [],
      "owner_transfers": [
        "E14",
        "E15",
        "E16",
        "E17",
        "E18",
        "E19",
        "E20"
      ],
      "no_flip_transfers": [
        "E14",
        "E15",
        "E16",
        "E17",
        "E18",
        "E20"
      ],
      "notice": null
    },
    {
      "snapshot": 34,
      "agent": "A",
      "action": 97,
      "seq": 584,
      "paths": [
        "mosslight/model.py"
      ],
      "fixed": [
        "P01"
      ],
      "regressed": [],
      "owner_transfers": [
        "P01",
        "P02",
        "P03",
        "P04"
      ],
      "no_flip_transfers": [
        "P02",
        "P03",
        "P04"
      ],
      "notice": null
    },
    {
      "snapshot": 37,
      "agent": "B",
      "action": 104,
      "seq": 644,
      "paths": [
        "mosslight/model.py"
      ],
      "fixed": [],
      "regressed": [],
      "owner_transfers": [
        "P01",
        "P02",
        "P03",
        "P04"
      ],
      "no_flip_transfers": [
        "P01",
        "P02",
        "P03",
        "P04"
      ],
      "notice": null
    },
    {
      "snapshot": 38,
      "agent": "B",
      "action": 112,
      "seq": 692,
      "paths": [
        "mosslight/field_calibration.py"
      ],
      "fixed": [],
      "regressed": [],
      "owner_transfers": [
        "N01"
      ],
      "no_flip_transfers": [
        "N01"
      ],
      "notice": null
    },
    {
      "snapshot": 39,
      "agent": "A",
      "action": 115,
      "seq": 701,
      "paths": [
        "mosslight/campaigns.py"
      ],
      "fixed": [],
      "regressed": [],
      "owner_transfers": [
        "V01",
        "V02",
        "V03",
        "V04"
      ],
      "no_flip_transfers": [
        "V01",
        "V02",
        "V03",
        "V04"
      ],
      "notice": null
    },
    {
      "snapshot": 41,
      "agent": "B",
      "action": 126,
      "seq": 765,
      "paths": [
        "mosslight/nursery.py"
      ],
      "fixed": [
        "E22"
      ],
      "regressed": [],
      "owner_transfers": [
        "E21",
        "E22",
        "E23",
        "E24"
      ],
      "no_flip_transfers": [
        "E21",
        "E23",
        "E24"
      ],
      "notice": null
    },
    {
      "snapshot": 44,
      "agent": "A",
      "action": 129,
      "seq": 787,
      "paths": [
        "mosslight/analysis.py"
      ],
      "fixed": [
        "F07",
        "F08"
      ],
      "regressed": [],
      "owner_transfers": [
        "F02",
        "F03",
        "F04",
        "F05",
        "F07",
        "F08",
        "F09"
      ],
      "no_flip_transfers": [
        "F02",
        "F03",
        "F04",
        "F05",
        "F09"
      ],
      "notice": null
    }
  ],
  "elapsed_seconds": 575.12,
  "fixed_probe_replay_points": {
    "A": 85,
    "B": 94,
    "C": 52
  },
  "live_diagnostic_points": {
    "A": 85,
    "B": 94,
    "C": 52
  },
  "official_inspect_independent_points": {
    "A": 85,
    "B": 94,
    "C": 52
  }
}
```
