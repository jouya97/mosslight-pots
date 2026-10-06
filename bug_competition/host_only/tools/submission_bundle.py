"""Package source and retained Mosslight evidence; verify or safely extract it.

No model calls or uploads. The manifest is delivered beside the archive, not
inside it. Original evidence is copied byte for byte; readable trajectory
exports omit opaque provider reasoning and record their input hashes.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import gzip
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import stat
import subprocess
import tarfile
import tempfile

REPO = Path(__file__).resolve().parents[3]
REPLAY = 'bug_competition/host_only/regrades/20261005T180821Z'
V8_REPLAY = 'bug_competition/host_only/regrades/20261006T035725Z_v8'
PRIOR_DELIVERY = 'bug_competition/host_only/submissions/20261005_v8'
DELIVERY = 'bug_competition/host_only/submissions/20261005_v8_scaffold'
DELIVERY_FILES = ('plan.json', 'images.json')
REVIEW_DOCUMENTS = ('README.md', 'flaw.md', 'grader/README.md', 'bug_competition/host_only/RESULTS.md')
ROOT_FILES = ('RUBRIC.md', '.dockerignore', 'task.py', 'env.json', 'variants.json', 'qc.json', 'flaw.md',
              'pytest.ini', 'bug_competition/__init__.py')
ROOT_DIRECTORIES = ('agent_data', 'grader', 'adapters')
IMAGE = 'sha256:28e3d6cafef1262c380140e04b368814d38a2740cb05002795ad660333b74e75'
BASE = 'python:3.12.10-slim-bookworm@sha256:fd95fa221297a88e1cf49c55ec1828edd7c5a428187e67b5d1805692d11588db'
MAX_FILES, MAX_FILE, MAX_TOTAL = 30000, 128 * 1024**2, 2 * 1024**3
MAX_ARCHIVE, MAX_MANIFEST = 512 * 1024**2, 16 * 1024**2
CACHE = {'.git', '__pycache__', '.pytest_cache', '.mypy_cache', '.ruff_cache', '.venv'}
RUNS = {
    'R1': 'bug_competition/host_only/rollouts/20260928T002300Z_fresh_all_defects_scores_v2',
    'R2': 'bug_competition/host_only/branches/20260928T070429Z_anthropic_seq69_shell180_luna',
    'R3': 'bug_competition/host_only/rollouts/20260928T084120Z_fresh_anthropic_luna',
}


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def encode(value):
    return (json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + '\n').encode()


def safe_name(name):
    if not isinstance(name, str) or not name or len(name.encode()) > 1024:
        raise ValueError('invalid archive path')
    path = PurePosixPath(name)
    if (not path.parts or path.is_absolute() or any(p in {'', '.', '..'} for p in path.parts)
            or path.as_posix() != name or '\\' in name or ':' in name
            or any(ord(c) < 32 for c in name)):
        raise ValueError('unsafe archive path: ' + repr(name))
    return path


def excluded(name):
    path = safe_name(name)
    # Protected snapshots include historical bytecode; dropping it breaks tree hashes.
    if any(name.startswith(folder + '/episode_evidence/') and '/protected/' in name for folder in RUNS.values()):
        return False
    return (any(p in CACHE for p in path.parts) or path.suffix in {'.pyc', '.pyo'}
            or path.name == '.DS_Store' or name.startswith('bug_competition/archives/')
            or (path.name.startswith('.env') and path.name not in {'.env.example', '.env.sample', '.env.template'})
            or (name.startswith(DELIVERY + '/') and path.name not in DELIVERY_FILES))


def regular(root, name):
    path = root.joinpath(*safe_name(name).parts)
    for current in (path, *path.parents):
        if current == root:
            break
        if current.is_symlink():
            raise ValueError('source symlink: ' + name)
    mode = path.stat().st_mode
    if not stat.S_ISREG(mode) or path.stat().st_size > MAX_FILE:
        raise ValueError('nonregular or oversized source: ' + name)
    return path


def replay_integrity(root, relative):
    """Verify one frozen replay without importing any bundled code."""
    replay = root / relative
    record = json.loads((replay / 'provenance.json').read_text())
    if record.get('status') != 'completed':
        raise ValueError('historical replay is not complete')
    expected = {relative + '/runtime/' + name: digest
                for name, digest in record['runtime_files_sha256'].items()}
    expected[relative + '/run_regrade.py'] = record['runner_sha256']
    if 'grading_probes_sha256' in record:
        expected[relative + '/grading_probes.json'] = record['grading_probes_sha256']
    for run in record['inputs'].values():
        expected.update(run['input_sha256'])
    for name, digest in expected.items():
        if sha(regular(root, name)) != digest:
            raise ValueError('historical evidence changed: ' + name)
    snapshot_count = 0
    for run in record['inputs'].values():
        protected = root / run['protected']
        events = [json.loads(line) for line in (protected / 'events.jsonl').read_text().splitlines()]
        trees = [events[0]['tree']] + [event['after'] for event in events
                 if event['type'] == 'action_completed' and event['before'] != event['after']]
        if 'snapshot_hashes' in run and trees != run['snapshot_hashes']:
            raise ValueError('snapshot list differs from replay provenance')
        for index, expected_tree in enumerate(trees):
            tree, digest = protected / 'snapshots' / str(index), hashlib.sha256()
            for path in sorted(tree.rglob('*')):
                if path.is_dir() and not path.is_symlink():
                    continue
                source = regular(root, path.relative_to(root).as_posix())
                header = json.dumps([source.relative_to(tree).as_posix(), source.stat().st_mode & 0o777],
                                    sort_keys=True, separators=(',', ':'), ensure_ascii=False)
                digest.update(header.encode())
                with source.open('rb') as stream:
                    for chunk in iter(lambda: stream.read(1024 * 1024), b''):
                        digest.update(chunk)
            if digest.hexdigest() != expected_tree:
                raise ValueError('historical snapshot hash mismatch: ' + str(tree))
            snapshot_count += 1
    return {'verified_input_and_runtime_files': len(expected), 'verified_snapshot_trees': snapshot_count,
            'provenance_sha256': sha(replay / 'provenance.json'),
            'inputs': record['inputs']}


def historical_integrity(root):
    """Keep both scoring generations independently verifiable."""
    legacy = replay_integrity(root, REPLAY)
    current = replay_integrity(root, V8_REPLAY)
    return {'original_replay': legacy, 'version8_rescore': current,
            'verified_snapshot_references': legacy['verified_snapshot_trees'],
            'note': 'The same retained trees were checked against both frozen replay records.'}


def readable_trajectories(path):
    result = []
    for sample in json.loads(path.read_text()):
        conversations = {}
        for actor, messages in sample['conversations'].items():
            cleaned = []
            for message in messages:
                content = message.get('content')
                if isinstance(content, list):
                    blocks = []
                    for block in content:
                        if block.get('type') == 'text':
                            blocks.append({'type': 'text', 'text': block.get('text', '')})
                        elif block.get('type') == 'reasoning' and isinstance(block.get('summary'), str):
                            blocks.append({'type': 'reasoning', 'summary': block['summary']})
                    content = blocks
                cleaned.append({'role': message.get('role'), 'content': content,
                                'tool_call_id': message.get('tool_call_id'),
                                'tool_calls': [{k: call[k] for k in ('id', 'function', 'arguments') if k in call}
                                               for call in message.get('tool_calls') or []]})
            conversations[actor] = cleaned
        result.append({'sample_id': sample.get('sample_id'), 'conversations': conversations})
    return encode({'source_file': path.name, 'source_sha256': sha(path),
                   'omitted': ['opaque reasoning', 'signatures', 'provider metadata'], 'samples': result})


def source_inventory(root):
    tracked = subprocess.check_output(['git', 'ls-files', '-z'], cwd=root).decode().split('\0')
    paths = {p for p in tracked if p and not excluded(p) and (root / p).exists()}
    # Canonical scaffold slots are now at the root and may be untracked moves.
    for name in ROOT_FILES:
        regular(root, name)
        paths.add(name)
    for name in REVIEW_DOCUMENTS:
        regular(root, name)
        paths.add(name)
    for directory in ROOT_DIRECTORIES:
        if not (root / directory).is_dir():
            raise ValueError('missing scaffold directory: ' + directory)
        for path in (root / directory).rglob('*'):
            name = path.relative_to(root).as_posix()
            if not excluded(name) and not path.is_dir():
                paths.add(name)
    # Additional implementation files stay below bug_competition/.
    for directory in ('bug_competition/harness', 'bug_competition/tests',
                      'bug_competition/host_only/tools'):
        for path in (root / directory).rglob('*.py'):
            name = path.relative_to(root).as_posix()
            if not excluded(name):
                paths.add(name)
    for name in DELIVERY_FILES:
        paths.add(DELIVERY + '/' + name)
    # Retain prior delivery metadata and both frozen regrades as evidence.
    for directory in (PRIOR_DELIVERY, REPLAY, V8_REPLAY):
        for path in (root / directory).rglob('*'):
            name = path.relative_to(root).as_posix()
            if not excluded(name) and not path.is_dir():
                paths.add(name)
    provenance = historical_integrity(root)
    for run in provenance['original_replay']['inputs'].values():
        paths.update(run['input_sha256'])
        for path in (root / run['protected']).rglob('*'):
            name = path.relative_to(root).as_posix()
            if not excluded(name) and not path.is_dir():
                paths.add(name)
    for path in (root / 'bug_competition/host_only/analysis/eval_awareness').glob('*.json'):
        if path.name.endswith(('_RELEVANT_ACTIONS.json', '_SAFE_ACTIONS.json')):
            paths.add(path.relative_to(root).as_posix())
    generated, transforms = {}, []
    for label, folder in RUNS.items():
        source = regular(root, folder + '/trajectories.json')
        paths.add(folder + '/trajectories.json')
        review = folder + '/review_conversations.json'
        if (root / review).exists() or (root / review).is_symlink():
            paths.add(review)
        name = folder + '/submission_readable_summaries.json'
        generated[name] = readable_trajectories(source)
        transforms.append({'run': label, 'source': folder + '/trajectories.json',
                           'source_sha256': sha(source), 'output': name,
                           'rule': 'Keep supplied readable summary/text and tool calls; omit opaque fields.'})
    for name in paths:
        regular(root, name)
    git_head = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=root, text=True).strip()
    status = subprocess.check_output(['git', 'status', '--porcelain=v1', '-z'], cwd=root).decode()
    return paths, generated, {'git_head': git_head, 'git_dirty': bool(status),
                             'git_status_porcelain': status.split('\0'),
                             'historical_evidence': provenance, 'derived_readable_exports': transforms}


def reviewability(root):
    if not (root / 'grader/grader.py').is_file():
        raise ValueError('root grader/grader.py is missing')
    python = {p.relative_to(root).as_posix(): len(p.read_text().splitlines())
              for p in sorted((root / 'grader').glob('*.py'))}
    probes = {p.relative_to(root).as_posix(): sum(len(item['program'].splitlines())
              for item in json.loads(p.read_text()))
              for p in sorted((root / 'grader/grader_data').glob('probes_*.json'))}
    return {'production_python_lines': python, 'executable_probe_program_lines': probes,
            'total_production_python_lines': sum(python.values()),
            'total_executable_probe_program_lines': sum(probes.values()),
            'combined_lines': sum(python.values()) + sum(probes.values()),
            'rubric_target_lines': 1000, 'meets_line_target': sum(python.values()) + sum(probes.values()) < 1000,
            'counting_note': 'Physical splitlines(), including blanks/comments. Probe programs execute and count; browser program strings in preservation.py are already in its Python line count. Tests and authoring helpers excluded.'}


def manifest_index(record):
    if record.get('schema_version') != 1:
        raise ValueError('unsupported manifest schema')
    entries = record.get('files')
    if not isinstance(entries, list) or not 0 < len(entries) <= MAX_FILES:
        raise ValueError('invalid manifest file count')
    expected, folded = {}, set()
    total = 0
    for item in entries:
        name = item['path']
        safe_name(name)
        if name in expected or name.casefold() in folded:
            raise ValueError('duplicate manifest path')
        size, mode, digest = item['size'], item['mode'], item['sha256']
        if (type(size) is not int or not 0 <= size <= MAX_FILE or type(mode) is not int
                or not 0 <= mode <= 0o777 or not isinstance(digest, str) or len(digest) != 64
                or any(c not in '0123456789abcdef' for c in digest)):
            raise ValueError('invalid manifest file metadata')
        expected[name], total = item, total + size
        folded.add(name.casefold())
    for name in expected:
        if any(p.as_posix().casefold() in folded for p in PurePosixPath(name).parents if str(p) != '.'):
            raise ValueError('manifest file is also a parent directory')
    if total > MAX_TOTAL or record.get('file_count') != len(expected) or record.get('uncompressed_file_bytes') != total:
        raise ValueError('manifest size/count mismatch')
    return expected


def create(root, archive, manifest, *, paths=None, generated=None, metadata=None):
    root, archive, manifest = Path(root).resolve(), Path(archive).absolute(), Path(manifest).absolute()
    if archive == manifest or archive.exists() or manifest.exists() or archive.is_symlink() or manifest.is_symlink():
        raise ValueError('outputs must be distinct new paths')
    if paths is None:
        paths, generated, metadata = source_inventory(root)
        metadata.update(environment_version=json.loads((root / 'env.json').read_text())['identity']['version'],
                        tested_image=IMAGE, base_image=BASE, image_delivery=json.loads((root / DELIVERY / 'images.json').read_text()),
                        reviewability=reviewability(root),
                        verification_tool={'path': 'bug_competition/host_only/tools/submission_bundle.py',
                                           'sha256': sha(root / 'bug_competition/host_only/tools/submission_bundle.py')},
                        image_reproducibility='The image ID identifies the tested local image. apt packages are not pinned; rebuilding the Dockerfile is not guaranteed to reproduce it.',
                        grading_versions='September runs: last editor. First frozen October 5 replay: first repair plus credit-transfer penalty. Second frozen replay: version 8 probes and preservation policy applied to the same historical actions; this is retrospective scoring, not a new model rollout.')
    generated, metadata = generated or {}, metadata or {}
    names = set(paths) | set(generated)
    if len(names) > MAX_FILES:
        raise ValueError('too many files')
    for name in names:
        safe_name(name)
        if root / name in (archive, manifest) or excluded(name):
            raise ValueError('excluded file or archive self-inclusion: ' + name)
    for out in (archive, manifest):
        out.parent.mkdir(parents=True, exist_ok=True)
    archive_tmp = manifest_tmp = None
    published_archive = False
    try:
        descriptor, archive_tmp = tempfile.mkstemp(prefix='.submission-', dir=archive.parent)
        inventory, total = [], 0
        with os.fdopen(descriptor, 'wb') as raw, gzip.GzipFile(filename='', mode='wb', fileobj=raw, mtime=0) as zipped:
            with tarfile.open(fileobj=zipped, mode='w', format=tarfile.PAX_FORMAT) as tar:
                for name in sorted(names):
                    if name in generated:
                        data, mode = generated[name], 0o644
                    else:
                        path = regular(root, name)
                        before = path.stat()
                        data, mode = path.read_bytes(), stat.S_IMODE(before.st_mode) & 0o777
                        after = path.stat()
                        if (after.st_size, after.st_mtime_ns, after.st_ino, after.st_mode) != (before.st_size, before.st_mtime_ns, before.st_ino, before.st_mode):
                            raise ValueError('source changed during copy: ' + name)
                    total += len(data)
                    if len(data) > MAX_FILE or total > MAX_TOTAL:
                        raise ValueError('submission exceeds size limits')
                    info = tarfile.TarInfo(name)
                    info.size, info.mode, info.mtime = len(data), mode, 0
                    tar.addfile(info, io.BytesIO(data))
                    inventory.append({'path': name, 'size': len(data), 'mode': mode,
                                      'sha256': hashlib.sha256(data).hexdigest()})
        if Path(archive_tmp).stat().st_size > MAX_ARCHIVE:
            raise ValueError('archive too large')
        record = {'schema_version': 1, 'created_utc': datetime.now(timezone.utc).isoformat(),
                  'archive': archive.name, 'archive_bytes': Path(archive_tmp).stat().st_size,
                  'archive_sha256': sha(archive_tmp), 'file_count': len(inventory),
                  'uncompressed_file_bytes': total, 'files': inventory, 'provenance': metadata,
                  'source_snapshot_sha256': hashlib.sha256(encode(inventory)).hexdigest()}
        manifest_index(record)
        for item in inventory:
            if item['path'] not in generated and sha(regular(root, item['path'])) != item['sha256']:
                raise ValueError('source changed during packaging: ' + item['path'])
        descriptor, manifest_tmp = tempfile.mkstemp(prefix='.submission-', dir=manifest.parent)
        with os.fdopen(descriptor, 'wb') as stream:
            stream.write(encode(record))
        # Hard-link publication refuses replacement, even if a destination appeared meanwhile.
        os.link(archive_tmp, archive)
        published_archive = True
        os.link(manifest_tmp, manifest)
    except BaseException:
        if published_archive:
            archive.unlink()
        raise
    finally:
        for temp in (archive_tmp, manifest_tmp):
            if temp is not None:
                Path(temp).unlink(missing_ok=True)
    return verify(manifest, archive)


def load_manifest(manifest):
    manifest = Path(manifest)
    if manifest.stat().st_size > MAX_MANIFEST:
        raise ValueError('manifest too large')
    record = json.loads(manifest.read_text())
    manifest_index(record)
    if type(record.get('archive_bytes')) is not int or not 0 < record['archive_bytes'] <= MAX_ARCHIVE:
        raise ValueError('invalid archive size')
    return record


class BoundedTarInfo(tarfile.TarInfo):
    def _proc_member(self, tar):
        # Reject giant metadata before tarfile allocates its payload buffer.
        if self.size > MAX_FILE or (self.type in (tarfile.XHDTYPE, tarfile.XGLTYPE,
                                                  tarfile.GNUTYPE_LONGNAME, tarfile.GNUTYPE_LONGLINK)
                                   and self.size > 1024 * 1024):
            raise ValueError('archive header exceeds bounds')
        tar._submission_headers = getattr(tar, '_submission_headers', 0) + 1
        tar._submission_bytes = getattr(tar, '_submission_bytes', 0) + self.size
        if tar._submission_headers > 3 * MAX_FILES or tar._submission_bytes > MAX_TOTAL:
            raise ValueError('archive expansion exceeds bounds')
        return super()._proc_member(tar)


def inspect_archive(record, archive, destination=None):
    expected, seen = manifest_index(record), set()
    archive = Path(archive)
    if archive.stat().st_size != record['archive_bytes'] or sha(archive) != record['archive_sha256']:
        raise ValueError('archive checksum or size mismatch')
    with tarfile.open(archive, 'r|gz', tarinfo=BoundedTarInfo) as tar:
        for member in tar:
            name = member.name
            safe_name(name)
            if not member.isfile() or member.type not in (tarfile.REGTYPE, tarfile.AREGTYPE) or member.sparse:
                raise ValueError('nonregular archive member')
            if name not in expected or name in seen:
                raise ValueError('unexpected or duplicate archive member')
            item = expected[name]
            if member.size != item['size'] or member.mode != item['mode']:
                raise ValueError('member size or mode mismatch')
            target = None
            if destination is not None:
                target = destination.joinpath(*PurePosixPath(name).parts)
                target.parent.mkdir(parents=True, exist_ok=True)
                output = target.open('xb')
            else:
                output = None
            digest, remaining = hashlib.sha256(), member.size
            try:
                stream = tar.extractfile(member)
                while remaining:
                    chunk = stream.read(min(1024 * 1024, remaining))
                    if not chunk:
                        raise ValueError('truncated archive member')
                    digest.update(chunk)
                    if output:
                        output.write(chunk)
                    remaining -= len(chunk)
            finally:
                if output:
                    output.close()
            if digest.hexdigest() != item['sha256']:
                raise ValueError('member checksum mismatch: ' + name)
            if target:
                target.chmod(item['mode'])
            seen.add(name)
    if seen != expected.keys():
        raise ValueError('missing archive members')
    return {'verified': True, 'file_count': len(seen), 'archive': str(archive),
            'archive_sha256': record['archive_sha256'], 'archive_bytes': record['archive_bytes'],
            'source_snapshot_sha256': record.get('source_snapshot_sha256')}


def verify(manifest, archive=None):
    record = load_manifest(manifest)
    archive = Path(archive) if archive else Path(manifest).parent / safe_name(record['archive'])
    return inspect_archive(record, archive)


def extract(manifest, archive, destination):
    record = load_manifest(manifest)
    destination = Path(destination).absolute()
    if destination.exists() or destination.is_symlink():
        raise ValueError('extraction destination must be new')
    inspect_archive(record, archive)
    destination.mkdir(parents=True, exist_ok=False)
    try:
        result = inspect_archive(record, archive, destination)
        result['destination'] = str(destination)
        return result
    except BaseException:
        shutil.rmtree(destination)
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    command = commands.add_parser('create')
    command.add_argument('--root', type=Path, default=REPO)
    command.add_argument('--archive', type=Path, required=True)
    command.add_argument('--manifest', type=Path, required=True)
    command = commands.add_parser('verify')
    command.add_argument('manifest', type=Path)
    command.add_argument('--archive', type=Path)
    command = commands.add_parser('extract')
    command.add_argument('manifest', type=Path)
    command.add_argument('--archive', type=Path, required=True)
    command.add_argument('--destination', type=Path, required=True)
    command = commands.add_parser('check-historical-inputs')
    command.add_argument('--root', type=Path, default=REPO)
    command = commands.add_parser('reviewability')
    command.add_argument('--root', type=Path, default=REPO)
    args = parser.parse_args()
    if args.command == 'create':
        result = create(args.root, args.archive, args.manifest)
    elif args.command == 'verify':
        result = verify(args.manifest, args.archive)
    elif args.command == 'extract':
        result = extract(args.manifest, args.archive, args.destination)
    elif args.command == 'reviewability':
        result = reviewability(args.root)
    else:
        result = historical_integrity(args.root)
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
