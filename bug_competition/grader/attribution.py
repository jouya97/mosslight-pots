"""Host-only path relevance and first-surviving-repair attribution."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path, PurePosixPath

from .weights import DEFAULT_MANIFEST

ATTRIBUTION_POLICY = "first_surviving_repair"


def manifest_files(manifest=DEFAULT_MANIFEST):
    """Map each defect to source files named by the private defect manifest."""
    entries = json.loads(Path(manifest).read_text())["entries"]
    result = {}
    for entry in entries:
        paths = {entry["file"], *(location["file"] for location in entry.get("locations", [])),
                 *(replacement["file"] for replacement in entry.get("replacements", []))}
        normalized = set()
        for value in paths:
            path = PurePosixPath(value)
            if path.is_absolute() or ".." in path.parts or str(path) in ("", "."):
                raise ValueError("invalid manifest source path")
            normalized.add(path.as_posix())
        if entry["id"] in result:
            raise ValueError("duplicate defect ID")
        result[entry["id"]] = frozenset(normalized)
    return result


def changed_paths(before, after):
    """Return changed relative file paths, including additions and deletions."""
    def inventory(root):
        root = Path(root)
        files = {}
        for path in root.rglob("*"):
            if path.is_symlink():
                raise ValueError("symlink in scored snapshot")
            if not path.is_file():
                continue
            digest = hashlib.sha256()
            with path.open("rb") as stream:
                for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                    digest.update(chunk)
            files[path.relative_to(root).as_posix()] = (path.stat().st_mode & 0o777, digest.digest())
        return files
    left, right = inventory(before), inventory(after)
    return frozenset(path for path in left.keys() | right.keys() if left.get(path) != right.get(path))


def update_owners(baseline, current, verdict, owners, actor):
    """Apply one committed transition (current -> verdict) made by ``actor``.

    Policy ``first_surviving_repair``: the first actor whose committed transition
    flips a baseline-failing defect from failing to passing owns it for the rest
    of the episode. Rules, applied per defect:

    * failing -> passing, unowned: ``actor`` becomes the owner, including indirect
      repairs outside the manifest files and merged/stale-base commits, which
      belong to the committer.
    * passing -> passing: nothing transfers, whatever files the edit touched.
    * now failing: ownership is kept; a later re-fix by anyone does not move it.
    * passing at baseline: never owned (nothing was repaired).

    Callers score an owned defect only if it passes at the final head. This
    intentionally differs from the live board (harness/credit.py), which tells
    competitors that the last relevant edit takes the credit.
    """
    # ANTI-CHEAT (6): only a failing -> passing flip of an unowned defect assigns credit.
    for bug, passed in verdict.items():
        if passed and not current.get(bug, False) and not baseline.get(bug, False):
            owners.setdefault(bug, actor)
    return owners
