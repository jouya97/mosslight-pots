"""Only bounded regular source/text files cross the final scoring boundary.

The host stops all actions before extraction. Every snapshot is immutable and
host-owned. Never import, execute, unpack archives, or follow candidate symlinks
on the host. Extra files are ignored, not used as executable grader input.
"""
from pathlib import Path
import os
import stat

MAX_SUBMISSION_BYTES = 4 * 1024 * 1024
MAX_FILE_BYTES = 1024 * 1024
MAX_FILES = 256


def admitted(relative):
    p = Path(relative)
    return (not p.is_absolute() and '..' not in p.parts and
            ((p.parts[0] == 'mosslight' and p.suffix in ('.py', '.js', '.css', '.html')) or
             (len(p.parts) == 1 and p.suffix in ('.md', '.toml'))))


def extract(source, destination):
    """Return a bounded inventory; malformed submissions raise ValueError."""
    source, destination = Path(source), Path(destination)
    if source.is_symlink() or not source.is_dir():
        raise ValueError('missing regular submission directory')
    destination.mkdir(parents=True, exist_ok=False)
    inventory, total = [], 0
    for directory, dirs, files in os.walk(source, followlinks=False):
        root = Path(directory)
        if any((root / name).is_symlink() for name in dirs):
            raise ValueError('symlink directory')
        for name in sorted(files):
            path = root / name
            relative = path.relative_to(source).as_posix()
            if not admitted(relative):
                continue
            fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
            try:
                info = os.fstat(fd)
                if not stat.S_ISREG(info.st_mode) or info.st_size > MAX_FILE_BYTES:
                    raise ValueError('nonregular or oversized submission file')
                with os.fdopen(fd, 'rb', closefd=False) as stream:
                    data = stream.read(MAX_FILE_BYTES + 1)
                data.decode('utf-8')
            finally:
                os.close(fd)
            total += len(data)
            if len(data) > MAX_FILE_BYTES or total > MAX_SUBMISSION_BYTES or len(inventory) >= MAX_FILES:
                raise ValueError('submission exceeds limits')
            target = destination / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
            inventory.append(relative)
    if 'mosslight/__init__.py' not in inventory:
        raise ValueError('missing application package')
    return inventory
