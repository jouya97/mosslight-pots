"""Bounded export after participant processes are terminated; never extract candidate tar paths."""
from __future__ import annotations

import os
from pathlib import Path, PurePosixPath
import selectors
import subprocess
import tarfile
import tempfile
import time

WORKSPACE_BYTES = 64 * 1024 * 1024
WORKSPACE_ENTRIES = 4096
PATH_BYTES = 512
ARCHIVE_BYTES = WORKSPACE_BYTES + 16 * 1024 * 1024

# Executed as the participant's unprivileged UID in its PID namespace. Services
# cannot persist after a shell action. Termination prevents delayed SIGCONT from
# resuming an old writer; repeated scans account for children forked during kill.
# Uninterruptible processes or unreadable metadata reject export within 3 seconds.
FINISH_ACTION_PROGRAM = """import os, signal, time
from pathlib import Path
if os.getuid() != 65534:
    raise RuntimeError('action cleanup must run as the participant')
self_pid = str(os.getpid())
deadline, previous = time.monotonic() + 3, None
while True:
    try:
        os.kill(-1, signal.SIGKILL)
    except ProcessLookupError:
        pass
    states = {}
    for pid in os.listdir('/proc'):
        if not pid.isdigit() or pid == self_pid:
            continue
        try:
            directory = Path('/proc') / pid
            uids = next(row for row in (directory/'status').read_text().splitlines() if row.startswith('Uid:'))
            if 65534 not in map(int, uids.split()[1:]):
                continue
            states[pid] = (directory/'stat').read_text().rsplit(')', 1)[1].split()[0]
        except (FileNotFoundError, ProcessLookupError):
            continue
    finished = all(state in ('Z', 'X') for state in states.values())
    if finished and frozenset(states) == previous:
        break
    previous = frozenset(states) if finished else None
    if time.monotonic() >= deadline:
        raise TimeoutError('participant processes did not terminate')
    time.sleep(.01)
"""


class ExportRejected(ValueError):
    pass


def _download(name, target, seconds):
    """Bound time and bytes even for sparse files with enormous apparent sizes."""
    if seconds <= 0:
        raise TimeoutError('workspace export deadline')
    child = subprocess.Popen(['docker', 'exec', '--user', '65534:65534', name,
                              '/usr/bin/tar', '-C', '/workspace', '-cf', '-', '.'],
                             stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    deadline, size = time.monotonic() + seconds, 0
    selector = selectors.DefaultSelector()
    selector.register(child.stdout, selectors.EVENT_READ)
    try:
        with target.open('wb') as stream:
            while selector.get_map():
                if time.monotonic() >= deadline:
                    raise TimeoutError('workspace export deadline')
                for key, _ in selector.select(min(.1, max(0, deadline-time.monotonic()))):
                    data = os.read(key.fileobj.fileno(), 65536)
                    if not data:
                        selector.unregister(key.fileobj)
                        continue
                    size += len(data)
                    if size > ARCHIVE_BYTES:
                        raise ExportRejected('Workspace archive exceeds the bounded export limit.')
                    stream.write(data)
        child.wait(timeout=max(.001, deadline-time.monotonic()))
        if child.returncode:
            raise ExportRejected('Workspace could not be exported; changes were discarded.')
    finally:
        if child.poll() is None:
            child.kill()
        child.wait()
        child.stdout.close()
        selector.close()


def unpack(archive, destination, deadline):
    """Validate the entire bounded archive before writing any regular-file contents.

    Return symlink names without creating links on the host. Hard links to regular
    archive members are materialized as independent files. Modes retain only the
    executable bit; candidate ownership and permission restrictions are discarded.
    """
    if time.monotonic() >= deadline:
        raise TimeoutError('workspace validation deadline')
    if Path(archive).stat().st_size > ARCHIVE_BYTES:
        raise ExportRejected('Workspace archive exceeds the bounded export limit.')
    members, paths, links, size = [], set(), [], 0
    entries = set()
    with tarfile.open(archive, 'r:') as source:
        for member in source:
            if time.monotonic() >= deadline:
                raise TimeoutError('workspace validation deadline')
            path = PurePosixPath(member.name)
            if path.is_absolute() or '..' in path.parts:
                raise ExportRejected('Workspace archive contains an unsafe path.')
            if str(path) == '.' and member.isdir():
                continue
            try:
                encoded = str(path).encode('utf8')
            except UnicodeEncodeError:
                raise ExportRejected('Workspace names must be valid UTF-8.') from None
            if len(encoded) > PATH_BYTES or str(path) in paths:
                raise ExportRejected('Workspace contains an overlong or duplicate path.')
            paths.add(str(path))
            entries.update(str(item) for item in (path, *path.parents) if str(item) != '.')
            if len(entries) > WORKSPACE_ENTRIES:
                raise ExportRejected('Workspace exceeds 4096 entries.')
            if member.issym():
                links.append(str(path))
            elif not (member.isdir() or member.isfile() or member.islnk()):
                raise ExportRejected('Only regular files and directories are allowed.')
            elif member.islnk():
                target = PurePosixPath(member.linkname)
                if target.is_absolute() or '..' in target.parts:
                    raise ExportRejected('Workspace hard link has an unsafe target.')
            if not member.issym() and not member.mode & 0o400:
                raise ExportRejected('Unreadable workspace entries are not allowed.')
            if member.size < 0 or member.sparse is not None:
                raise ExportRejected('Sparse or negative-size workspace entries are not allowed.')
            size += member.size
            if size > WORKSPACE_BYTES:
                raise ExportRejected('Workspace exceeds 64 MiB.')
            members.append((member, path))
        if links:
            return {'symlinks': sorted(links)}
        kinds = {str(path): member.isdir() for member, path in members}
        for member, path in members:
            if time.monotonic() >= deadline:
                raise TimeoutError('workspace validation deadline')
            if any(str(parent) in kinds and not kinds[str(parent)]
                   for parent in path.parents if str(parent) != '.'):
                raise ExportRejected('Workspace file is also used as a directory.')
            if member.islnk():
                target = source.getmember(member.linkname)
                if not target.isfile():
                    raise ExportRejected('Workspace hard link must target a regular file.')
                size += target.size
                if size > WORKSPACE_BYTES:
                    raise ExportRejected('Expanded workspace exceeds 64 MiB.')
        destination.mkdir()
        for member, relative in members:
            if time.monotonic() >= deadline:
                raise TimeoutError('workspace extraction deadline')
            target = destination / str(relative)
            if member.isdir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            with source.extractfile(member) as incoming, target.open('xb') as output:
                remaining = member.size if member.isfile() else source.getmember(member.linkname).size
                while remaining:
                    if time.monotonic() >= deadline:
                        raise TimeoutError('workspace extraction deadline')
                    chunk = incoming.read(min(1024 * 1024, remaining))
                    if not chunk:
                        raise ExportRejected('Workspace file is truncated.')
                    output.write(chunk)
                    remaining -= len(chunk)
            target.chmod(0o755 if member.mode & 0o100 else 0o644)
    return {}


def capture(name, tree, seconds):
    """Replace a private action copy only after a complete, safe bounded export."""
    deadline = time.monotonic() + seconds
    with tempfile.TemporaryDirectory(prefix='mosslight-export-', dir=tree.parent) as folder:
        root = Path(folder)
        try:
            _download(name, root/'workspace.tar', seconds)
            result = unpack(root/'workspace.tar', root/'tree', deadline)
        except (ExportRejected, tarfile.TarError, KeyError, OSError) as exc:
            return {'workspace_rejected': str(exc)}
        if result:
            return result
        # The caller's tree is an isolated action copy, never the canonical head.
        backup = root/'previous'
        tree.rename(backup)
        try:
            (root/'tree').rename(tree)
        except BaseException:
            backup.rename(tree)
            raise
    return {}
