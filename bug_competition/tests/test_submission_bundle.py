"""Submission delivery integrity and hostile-archive rejection; no Docker/API calls."""
import gzip
import hashlib
import io
import json
from pathlib import Path
import tarfile

import pytest

from bug_competition.host_only.tools import submission_bundle as bundle


def source(tmp_path):
    root = tmp_path / 'source'
    (root / 'code').mkdir(parents=True)
    (root / 'code/app.py').write_text('print("hello")\n')
    (root / 'code/app.py').chmod(0o755)
    (root / 'README.md').write_text('Review this source.\n')
    return root


def build(tmp_path):
    root = source(tmp_path)
    archive, manifest = tmp_path / 'submission.tar.gz', tmp_path / 'manifest.json'
    bundle.create(root, archive, manifest, paths={'README.md', 'code/app.py'})
    return root, archive, manifest


def hostile(tmp_path, members, *, manifest_names=None):
    archive, manifest = tmp_path / 'hostile.tar.gz', tmp_path / 'hostile.json'
    files = []
    with tarfile.open(archive, 'w:gz') as tar:
        for name, kind, data in members:
            info = tarfile.TarInfo(name)
            info.type, info.size, info.mode = kind, len(data), 0o644
            if kind in (tarfile.SYMTYPE, tarfile.LNKTYPE):
                info.linkname = '../../outside'
            tar.addfile(info, io.BytesIO(data))
            files.append({'path': name, 'size': len(data), 'mode': 0o644,
                          'sha256': hashlib.sha256(data).hexdigest()})
    if manifest_names is not None:
        files = [dict(files[0], path=name) for name in manifest_names]
    manifest.write_text(json.dumps({'schema_version': 1, 'archive': archive.name,
                                   'archive_bytes': archive.stat().st_size, 'archive_sha256': bundle.sha(archive),
                                   'files': files, 'file_count': len(files),
                                   'uncompressed_file_bytes': sum(f['size'] for f in files)}))
    return archive, manifest


def test_round_trip_preserves_content_modes_and_refuses_overwrite(tmp_path):
    root, archive, manifest = build(tmp_path)
    out = tmp_path / 'extracted'
    assert bundle.verify(manifest, archive)['file_count'] == 2
    bundle.extract(manifest, archive, out)
    assert (out / 'code/app.py').read_bytes() == (root / 'code/app.py').read_bytes()
    assert (out / 'code/app.py').stat().st_mode & 0o777 == 0o755
    with pytest.raises(ValueError, match='new'):
        bundle.extract(manifest, archive, out)
    with pytest.raises(ValueError, match='new paths'):
        bundle.create(root, archive, manifest, paths={'README.md'})


@pytest.mark.parametrize('name', ['../outside', '/outside', 'a/../../outside', 'a\\outside',
                                  './README.md', 'a//b', 'C:/outside', '.', 'bad\x00name'])
def test_rejects_unsafe_paths(tmp_path, name):
    with pytest.raises(ValueError):
        bundle.safe_name(name)


@pytest.mark.parametrize('kind', [tarfile.SYMTYPE, tarfile.LNKTYPE, tarfile.DIRTYPE,
                                  tarfile.FIFOTYPE, tarfile.CHRTYPE])
def test_rejects_nonregular_members_before_extracting(tmp_path, kind):
    archive, manifest = hostile(tmp_path, [('link', kind, b'')])
    with pytest.raises(ValueError, match='nonregular'):
        bundle.extract(manifest, archive, tmp_path / 'out')
    assert not (tmp_path / 'out').exists()


def test_rejects_duplicate_archive_members_even_with_matching_manifest(tmp_path):
    archive, manifest = hostile(tmp_path, [('same', tarfile.REGTYPE, b'x')]*2, manifest_names=['same'])
    with pytest.raises(ValueError, match='duplicate'):
        bundle.verify(manifest, archive)


@pytest.mark.parametrize('names', [['same', 'same'], ['same', 'SAME'], ['parent', 'parent/child']])
def test_rejects_manifest_duplicates_and_file_directory_conflicts(tmp_path, names):
    archive, manifest = hostile(tmp_path, [('same', tarfile.REGTYPE, b'x')], manifest_names=names)
    with pytest.raises(ValueError):
        bundle.verify(manifest, archive)


def test_rejects_content_tampering_and_manifest_size_lies(tmp_path):
    _, archive, manifest = build(tmp_path)
    record = json.loads(manifest.read_text())
    record['files'][0]['sha256'] = '0'*64
    manifest.write_text(json.dumps(record))
    with pytest.raises(ValueError, match='member checksum'):
        bundle.verify(manifest, archive)
    record['files'][0]['size'] = bundle.MAX_FILE + 1
    manifest.write_text(json.dumps(record))
    with pytest.raises(ValueError, match='metadata'):
        bundle.verify(manifest, archive)


def test_rejects_source_links_credentials_and_self_inclusion(tmp_path):
    root = source(tmp_path)
    (root / 'link').symlink_to(root / 'README.md')
    with pytest.raises(ValueError, match='symlink'):
        bundle.create(root, tmp_path / 'a.tar.gz', tmp_path / 'a.json', paths={'link'})
    (root / '.env').write_text('SECRET=value')
    with pytest.raises(ValueError, match='excluded'):
        bundle.create(root, tmp_path / 'b.tar.gz', tmp_path / 'b.json', paths={'.env'})
    with pytest.raises(ValueError, match='self-inclusion'):
        bundle.create(root, root / 'output.tar.gz', tmp_path / 'c.json', paths={'output.tar.gz'})


def test_readable_export_keeps_supplied_summary_and_tool_call_only(tmp_path):
    path = tmp_path / 'trajectories.json'
    path.write_text(json.dumps([{'sample_id': 'one', 'conversations': {'A': [
        {'role': 'assistant', 'content': [{'type': 'reasoning', 'reasoning': 'opaque-payload',
                                          'signature': 'private-signature', 'summary': 'Readable summary.'}],
         'tool_calls': [{'id': 'call', 'function': 'shell', 'arguments': {'command': 'ls'}, 'view': 'unused'}]}]}}]))
    data = bundle.readable_trajectories(path)
    assert b'Readable summary.' in data and b'"command": "ls"' in data
    assert b'opaque-payload' not in data and b'private-signature' not in data
    assert json.loads(data)['source_sha256'] == bundle.sha(path)


def test_rejects_large_pax_metadata_before_reading_payload(tmp_path):
    archive, manifest = hostile(tmp_path, [('safe', tarfile.REGTYPE, b'x')])
    header = tarfile.TarInfo('pax')
    header.type, header.size = tarfile.XHDTYPE, 2 * 1024**2
    archive.write_bytes(gzip.compress(header.tobuf()))
    record = json.loads(manifest.read_text())
    record.update(archive_sha256=bundle.sha(archive), archive_bytes=archive.stat().st_size)
    manifest.write_text(json.dumps(record))
    with pytest.raises(ValueError, match='header exceeds'):
        bundle.verify(manifest, archive)


def test_inventory_captures_untracked_root_scaffold_moves_and_both_regrades(tmp_path, monkeypatch):
    root = tmp_path / 'repository'
    def write(name, content='{}'):
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
    for name in bundle.ROOT_FILES:
        write(name)
    for name in ('grader/grader.py', 'grader/grader_data/probes_example.json',
                 'adapters/docker/Dockerfile', 'agent_data/SUBMISSION.md',
                 'bug_competition/harness/new_module.py', 'README.md'):
        write(name)
    for name in ('README.md', 'VALIDATION.md', 'plan.json', 'images.json'):
        write(bundle.DELIVERY + '/' + name)
    write(bundle.DELIVERY + '/manifest.json')
    write(bundle.DELIVERY + '/acceptance.json')
    write(bundle.PRIOR_DELIVERY + '/manifest.json')
    write(bundle.REPLAY + '/R1/grade.json')
    write(bundle.V8_REPLAY + '/R1/grade.json')
    monkeypatch.setattr(bundle, 'RUNS', {})
    monkeypatch.setattr(bundle, 'historical_integrity', lambda _: {'original_replay': {'inputs': {}}, 'version8_rescore': {}})
    def git(command, **kwargs):
        if command[1] == 'ls-files':
            return b'README.md\x00bug_competition/grader/grader.py\x00'
        if command[1] == 'rev-parse':
            return 'base-revision\n'
        return b'?? grader/\x00'
    monkeypatch.setattr(bundle.subprocess, 'check_output', git)
    paths, _, metadata = bundle.source_inventory(root)
    assert 'grader/grader.py' in paths and 'adapters/docker/Dockerfile' in paths
    assert 'agent_data/SUBMISSION.md' in paths and 'task.py' in paths and 'env.json' in paths
    assert 'pytest.ini' in paths
    assert 'bug_competition/__init__.py' in paths
    assert 'bug_competition/grader/grader.py' not in paths
    assert bundle.REPLAY + '/R1/grade.json' in paths
    assert bundle.V8_REPLAY + '/R1/grade.json' in paths
    assert bundle.PRIOR_DELIVERY + '/manifest.json' in paths
    assert bundle.DELIVERY + '/manifest.json' not in paths
    assert bundle.DELIVERY + '/acceptance.json' not in paths
    assert metadata['git_dirty'] is True


def test_reviewability_counts_root_grader_and_executable_programs(tmp_path):
    (tmp_path / 'grader/grader_data').mkdir(parents=True)
    (tmp_path / 'grader/grader.py').write_text('# production\npass\n')
    (tmp_path / 'grader/grader_data/probes_example.json').write_text(json.dumps([{'program': 'first()\nsecond()\n'}]))
    result = bundle.reviewability(tmp_path)
    assert result['combined_lines'] == 4
    assert result['production_python_lines'] == {'grader/grader.py': 2}
    assert result['total_executable_probe_program_lines'] == 2


def test_new_rescore_must_complete_before_packaging(tmp_path):
    replay = tmp_path / bundle.V8_REPLAY
    replay.mkdir(parents=True)
    (replay / 'provenance.json').write_text(json.dumps({'status': 'running'}))
    with pytest.raises(ValueError, match='not complete'):
        bundle.replay_integrity(tmp_path, bundle.V8_REPLAY)
