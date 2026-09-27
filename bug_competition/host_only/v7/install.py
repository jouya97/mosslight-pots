"""Install the two irrigation candidates after host-only cross-checks."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys

HERE = Path(__file__).resolve().parent
HOST = HERE.parent
ROOT = HOST.parent
V6 = HOST / "v6"
WORK = HOST / "workstreams" / "irrigation_v7"
IGNORE = shutil.ignore_patterns("__pycache__", "*.pyc")


def inventory(root: Path) -> dict[str, str]:
    return {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in root.rglob("*") if p.is_file() and "__pycache__" not in p.parts and p.suffix != ".pyc"}


def replace_once(path: Path, old: str, new: str) -> None:
    value = path.read_text()
    assert value.count(old) == 1, path
    path.write_text(value.replace(old, new))


def check(root: Path, code: str) -> bool:
    program = "import sys\nsys.path.insert(0, " + repr(str(root)) + ")\n" + code
    completed = subprocess.run([sys.executable, "-B", "-c", program], cwd=root,
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=60)
    return completed.returncode == 0


def main() -> None:
    live = ROOT / "mosslight"
    assert inventory(live) == inventory(V6 / "seeded_snapshot"), "live tree changed since v6"
    delivery = json.loads((WORK / "DELIVERY.json").read_text())
    assert delivery["candidate_ids"] == ["I01", "I02"]
    assert delivery["candidate_tiers"] == {"extreme": ["I01"], "legendary": ["I02"]}
    assert all(delivery["predecessor_files_preserved"].values())
    assert json.loads((WORK / "verification.json").read_text())["all_verified"]
    assert json.loads((WORK / "overlap_matrix.json").read_text())["all_preserved"]
    assert json.loads((WORK / "repair_alternatives.json").read_text())["all_passed"]
    cleanup = json.loads((WORK / "optional_source_cleanup.json").read_text())
    assert cleanup["verified"]

    for name in ("clean_baseline", "seeded_snapshot"):
        source, target = WORK / name, HERE / name
        assert not target.exists(), f"refusing to overwrite {target}"
        shutil.copytree(source, target, ignore=IGNORE)
        assert inventory(target) == inventory(source)
        prior, added = inventory(V6 / name), inventory(target)
        assert all(added.get(path) == digest for path, digest in prior.items())
        assert set(added) - set(prior) == set(delivery["integration_files"])
        edit = cleanup["N02_both_trees_editorial_replacement"]
        replace_once(target / edit["file"], edit["old"], edit["new"])
        if name == "seeded_snapshot":
            edit = cleanup["N01_seeded_only_extra_replacement"]
            replace_once(target / edit["file"], edit["old"], edit["new"])

    for name in ("checks", "patches"):
        target = HERE / name
        assert not target.exists()
        shutil.copytree(V6 / name, target, ignore=IGNORE)
        for ident in delivery["candidate_ids"]:
            suffix = "py" if name == "checks" else "patch"
            shutil.copy2(WORK / name / f"{ident}.{suffix}", target / f"{ident}.{suffix}")

    prior = json.loads((V6 / "manifest.json").read_text())
    additions = json.loads((WORK / "mutations.json").read_text())
    assert [entry["id"] for entry in additions] == delivery["candidate_ids"]
    entries = prior["entries"] + additions
    assert len(entries) == len({entry["id"] for entry in entries}) == 120
    n01 = next(entry for entry in entries if entry["id"] == "N01")
    n01["seeded_editorial_cleanup"] = cleanup["N01_seeded_only_extra_replacement"]
    manifest = {**prior, "schema_version": 7,
                "purpose": "Host-only v7 ground truth; v6 and earlier evidence retained",
                "count": len(entries), "entries": entries,
                "distribution": {**prior["distribution"], "extreme": 1, "legendary": 1},
                "candidate_distribution": {"extreme": 1, "legendary": 1},
                "tier_calibration": "I01/I02 are target-tier candidates; human debugging time unmeasured",
                "parent_manifest": "../v6/manifest.json",
                "integration_workstream": "../workstreams/irrigation_v7/DELIVERY.json"}
    (HERE / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    for entry in entries:
        assert (HERE / "checks" / f"{entry['id']}.py").read_text().rstrip("\n") == entry["check"].rstrip("\n")

    def verify(entry: dict) -> dict:
        code = (HERE / "checks" / f"{entry['id']}.py").read_text()
        return {"id": entry["id"], "clean": check(HERE / "clean_baseline", code),
                "seeded": check(HERE / "seeded_snapshot", code)}

    with ThreadPoolExecutor(max_workers=6) as pool:
        outcomes = list(pool.map(verify, entries))
    assert all(row["clean"] and not row["seeded"] for row in outcomes)
    public = subprocess.run([sys.executable, "-B", "-m", "unittest", "discover", "-s", "tests", "-q"],
                            cwd=HERE / "clean_baseline", capture_output=True, text=True, timeout=120)
    assert public.returncode == 0, public.stderr[-2000:]
    report = {"count": len(outcomes), "clean_passed": sum(row["clean"] for row in outcomes),
              "seeded_failed": sum(not row["seeded"] for row in outcomes),
              "clean_public_tests": public.stderr.strip().splitlines()[-3:],
              "clean_tree_sha256": hashlib.sha256(json.dumps(inventory(HERE / "clean_baseline"), sort_keys=True).encode()).hexdigest(),
              "seeded_tree_sha256": hashlib.sha256(json.dumps(inventory(HERE / "seeded_snapshot"), sort_keys=True).encode()).hexdigest(),
              "manifest_sha256": hashlib.sha256((HERE / "manifest.json").read_bytes()).hexdigest(),
              "source_cleanup_applied": True}
    (HERE / "verification.json").write_text(json.dumps(report, indent=2) + "\n")

    staged, backup = HERE / "install_candidate", HERE / "pre_install_live_v6"
    assert not staged.exists() and not backup.exists()
    shutil.copytree(HERE / "seeded_snapshot", staged, ignore=IGNORE)
    assert inventory(staged) == inventory(HERE / "seeded_snapshot")
    live.rename(backup)
    try:
        staged.rename(live)
    except BaseException:
        backup.rename(live)
        raise
    assert inventory(live) == inventory(HERE / "seeded_snapshot")
    (HOST / "CURRENT.json").write_text(json.dumps({
        "current_version": 7, "manifest": "v7/manifest.json", "verification": "v7/verification.json",
        "note": "I01/I02 are extreme/legendary candidates; human-time calibration unmeasured."
    }, indent=2) + "\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
