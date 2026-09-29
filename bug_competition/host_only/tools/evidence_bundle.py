"""Create or verify a local, checksum-indexed evidence archive without editing a run.

The archive contains regular files under one run directory. Python/tool caches are
excluded; all original evidence files remain in place. Verification reads archive
members without extracting or executing them. No network or model calls are made.
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import stat
import tarfile

REPO = Path(__file__).resolve().parents[3]
CACHE_DIRS = {"__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache"}


def digest(data):
    return hashlib.sha256(data).hexdigest()


def file_digest(path):
    result = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            result.update(chunk)
    return result.hexdigest()


def create(source, archive, manifest):
    source, archive, manifest = (Path(p).resolve() for p in (source, archive, manifest))
    source.relative_to(REPO / "bug_competition/host_only")
    if source.parent.name not in {"rollouts", "branches"} or not source.is_dir():
        raise ValueError("source must be one existing rollout or branch directory")
    if archive.exists() or manifest.exists():
        raise ValueError("archive and manifest must be new paths")
    if source in archive.parents or source in manifest.parents:
        raise ValueError("outputs must be outside the source evidence directory")
    archive.relative_to(REPO)
    manifest.relative_to(REPO)
    paths = []
    for path in sorted(source.rglob("*")):
        relative = path.relative_to(source)
        if any(part in CACHE_DIRS for part in relative.parts) or path.suffix in {".pyc", ".pyo"}:
            continue
        if path.is_symlink():
            raise ValueError(f"evidence contains a symbolic link: {relative}")
        if path.is_dir():
            continue
        if not path.is_file():
            raise ValueError(f"evidence contains a nonregular file: {relative}")
        if path.name == ".env" or path.name.startswith(".env."):
            raise ValueError("credential files must not be included in evidence bundles")
        paths.append(path)
    archive.parent.mkdir(parents=True, exist_ok=True)
    manifest.parent.mkdir(parents=True, exist_ok=True)
    inventory = []
    with archive.open("xb") as raw, gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as zipped:
        with tarfile.open(fileobj=zipped, mode="w", format=tarfile.PAX_FORMAT) as tar:
            for path in paths:
                data = path.read_bytes()
                name = (Path(source.name) / path.relative_to(source)).as_posix()
                info = tarfile.TarInfo(name)
                info.size = len(data)
                info.mode = stat.S_IMODE(path.stat().st_mode)
                tar.addfile(info, io.BytesIO(data))
                inventory.append({"path": name, "size": len(data), "sha256": digest(data)})
    record = {
        "schema_version": 1,
        "source": source.relative_to(REPO).as_posix(),
        "archive": archive.relative_to(REPO).as_posix(),
        "archive_bytes": archive.stat().st_size,
        "archive_sha256": file_digest(archive),
        "file_count": len(inventory),
        "uncompressed_file_bytes": sum(item["size"] for item in inventory),
        "excluded": ["Python bytecode", *sorted(CACHE_DIRS)],
        "files": inventory,
    }
    with manifest.open("x", encoding="utf-8") as stream:
        json.dump(record, stream, indent=2)
        stream.write("\n")
    return verify(manifest)


def verify(manifest, archive=None):
    record = json.loads(Path(manifest).read_text(encoding="utf-8"))
    if record.get("schema_version") != 1:
        raise ValueError("unsupported evidence manifest schema")
    recorded_path = PurePosixPath(record["archive"])
    if recorded_path.is_absolute() or ".." in recorded_path.parts:
        raise ValueError("archive path must be repository-relative")
    archive = Path(archive) if archive is not None else REPO / recorded_path
    if archive.stat().st_size != record["archive_bytes"] or file_digest(archive) != record["archive_sha256"]:
        raise ValueError("archive checksum or size mismatch")
    expected = {item["path"]: item for item in record["files"]}
    if len(expected) != record["file_count"] or len(expected) != len(record["files"]):
        raise ValueError("duplicate or inconsistent manifest entries")
    seen = set()
    with tarfile.open(archive, "r:gz") as tar:
        for member in tar:
            path = PurePosixPath(member.name)
            if not member.isfile() or path.is_absolute() or ".." in path.parts:
                raise ValueError("archive contains an unsafe or nonregular member")
            if member.name not in expected or member.name in seen:
                raise ValueError("unexpected or duplicate archive member")
            stream = tar.extractfile(member)
            data = stream.read()
            item = expected[member.name]
            if len(data) != item["size"] or digest(data) != item["sha256"]:
                raise ValueError(f"member checksum mismatch: {member.name}")
            seen.add(member.name)
    if seen != expected.keys():
        raise ValueError("archive is missing manifest entries")
    return {"verified": True, "file_count": len(seen), "archive": str(archive),
            "archive_sha256": record["archive_sha256"], "archive_bytes": record["archive_bytes"]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    command = commands.add_parser("create")
    command.add_argument("source", type=Path)
    command.add_argument("--archive", type=Path, required=True)
    command.add_argument("--manifest", type=Path, required=True)
    command = commands.add_parser("verify")
    command.add_argument("manifest", type=Path)
    command.add_argument("--archive", type=Path, help="Override the local archive location")
    args = parser.parse_args()
    result = create(args.source, args.archive, args.manifest) if args.command == "create" else verify(args.manifest, args.archive)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
