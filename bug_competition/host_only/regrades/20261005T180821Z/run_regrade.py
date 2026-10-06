"""Regrade retained episodes; write fresh evidence without changing original runs.

Run with Python 3.10+ from any directory. Requires the original Docker image.
Each episode uses its pinned probes and the grader copied into runtime/ on the
first invocation. No model APIs are called. Existing completed outputs are never
overwritten. Per-snapshot verdicts come from fresh isolated Docker executions.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import threading
import time
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
RUNTIME = HERE / 'runtime'
RUNS = {
    'R1': 'rollouts/20260928T002300Z_fresh_all_defects_scores_v2',
    'R2': 'branches/20260928T070429Z_anthropic_seq69_shell180_luna',
    'R3': 'rollouts/20260928T084120Z_fresh_anthropic_luna',
}
PRINT_LOCK = threading.Lock()
SECONDS = 10800


def utc():
    return datetime.now(timezone.utc).isoformat()


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write_json(path, value):
    path = Path(path)
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + '\n')
    temporary.replace(path)


def emit(value):
    with PRINT_LOCK:
        print(json.dumps(value, sort_keys=True), flush=True)


def freeze_grader():
    if RUNTIME.exists():
        raise RuntimeError('runtime already exists; use a new output directory for a new replay')
    package = RUNTIME / 'bug_competition'
    package.mkdir(parents=True)
    (package / '__init__.py').write_text('')
    shutil.copytree(ROOT / 'bug_competition/grader', package / 'grader',
                    ignore=shutil.ignore_patterns('__pycache__', 'tests', 'README.md'))
    inventory = {str(path.relative_to(RUNTIME)): sha(path)
                 for path in sorted(RUNTIME.rglob('*')) if path.is_file()}
    return inventory


def main():
    if any((HERE / name).exists() for name in RUNS):
        raise RuntimeError('run output exists; refusing to overwrite previous evidence')
    inventory = freeze_grader()
    sys.path.insert(0, str(RUNTIME))
    from bug_competition.grader.grader import CandidateRunner, FinalOracle, grade_episode, host_evidence
    from bug_competition.grader.primitives import tree_hash
    from bug_competition.grader.weights import manifest_weights, DEFAULT_MANIFEST

    os.environ['MOSSLIGHT_RUN_ID'] = 'regrade-' + HERE.name
    metadata = {
        'started_utc': utc(), 'status': 'running', 'python': sys.version,
        'git_head': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
        'branch': subprocess.check_output(['git', 'branch', '--show-current'], cwd=ROOT, text=True).strip(),
        'runner_sha256': sha(__file__), 'runtime_files_sha256': inventory,
        'grading_seconds_per_run': SECONDS, 'parallel_runs': 3,
        'probe_workers_per_run': 4, 'model_api_calls': 0,
        'docker_server': subprocess.check_output(['docker', 'info', '--format', '{{.ServerVersion}}'], text=True).strip(),
        'inputs': {},
    }
    plans = []
    eligible = set(manifest_weights())
    assert len(eligible) == 119 and sum(manifest_weights().values()) == 251
    for name, relative in RUNS.items():
        source = ROOT / 'bug_competition/host_only' / relative
        candidates = list(source.glob('episode_evidence/*/protected'))
        assert len(candidates) == 1, (name, candidates)
        protected = candidates[0]
        records, result = host_evidence(protected)
        snapshots = [records[0]['tree']] + [r['after'] for r in records
                     if r['type'] == 'action_completed' and r['before'] != r['after']]
        invocation = json.loads((source / 'invocation.json').read_text())
        image = invocation['image']
        inspected = subprocess.check_output(['docker', 'image', 'inspect', image, '--format', '{{.Id}}'], text=True).strip()
        assert image == inspected and image.startswith('sha256:'), (image, inspected)
        probes = json.loads((source / 'grading_probes.json').read_text())
        assert len(probes) == 119 and {p['id'] for p in probes} == eligible
        pinned_hash = invocation.get('grading_probe_sha256')
        if pinned_hash:
            assert sha(source / 'grading_probes.json') == pinned_hash, name
        out = HERE / name
        out.mkdir()
        (out / 'verdicts').mkdir()
        shutil.copyfile(source / 'grading_probes.json', out / 'grading_probes.json')
        shutil.copyfile(source / 'independent_grade.json', out / 'original_grade.json')
        input_hashes = {str(p.relative_to(ROOT)): sha(p) for p in (
            source / 'grading_probes.json', source / 'invocation.json',
            source / 'independent_grade.json', protected / 'events.jsonl', protected / 'result.json')}
        metadata['inputs'][name] = {
            'source': str(source.relative_to(ROOT)), 'protected': str(protected.relative_to(ROOT)),
            'image': image, 'input_sha256': input_hashes, 'audit_head': result['audit_head'],
            'snapshots': len(snapshots), 'unique_snapshots': len(set(snapshots)),
            'manifest_sha256': sha(DEFAULT_MANIFEST),
        }
        plans.append((name, protected, probes, image, out, len(set(snapshots)), input_hashes))
    write_json(HERE / 'provenance.json', metadata)

    def regrade(plan):
        name, protected, probes, image, out, unique_count, input_hashes = plan
        start = time.monotonic()
        state = {'run': name, 'status': 'running', 'started_utc': utc(), 'checked_unique_snapshots': 0,
                 'total_unique_snapshots': unique_count}
        write_json(out / 'progress.json', state)
        emit(state)

        class RecordedOracle(FinalOracle):
            def __init__(self):
                self.runner = CandidateRunner(image)
                self.probes = probes
                self.covered = {p['id'] for p in probes}
                self.checked = 0
                self.last_verdict = None

            def __call__(self, snapshot, remaining):
                snapshot_start = time.monotonic()
                digest = tree_hash(snapshot)
                state.update(current_snapshot=int(snapshot.name), snapshot_started_utc=utc())
                write_json(out / 'progress.json', state)
                verdict = super().__call__(snapshot, remaining)
                assert set(verdict) == eligible and all(type(v) is bool for v in verdict.values())
                self.checked += 1
                self.last_verdict = verdict
                record = {'snapshot': int(snapshot.name), 'tree_sha256': digest, 'verdict': verdict,
                          'passing_bugs': sum(verdict.values()), 'finished_utc': utc(),
                          'elapsed_seconds': round(time.monotonic() - snapshot_start, 3)}
                write_json(out / 'verdicts' / (digest + '.json'), record)
                state.update(checked_unique_snapshots=self.checked, last_passing_bugs=record['passing_bugs'],
                             elapsed_seconds=round(time.monotonic() - start, 3))
                write_json(out / 'progress.json', state)
                emit(state)
                return verdict

        try:
            oracle = RecordedOracle()
            grade = grade_episode(protected, oracle=oracle, seconds=SECONDS)
            write_json(out / 'grade.json', grade)
            assert grade['adjudication_complete'] and grade['complete_submission'] and grade['coverage_complete'], grade
            assert not grade['adjudication_timed_out']
            for relative, digest in input_hashes.items():
                assert sha(ROOT / relative) == digest, 'Original evidence changed: ' + relative
            state.update(status='completed', finished_utc=utc(), elapsed_seconds=round(time.monotonic() - start, 3),
                         points=grade['points'], scores=grade['scores'], snipe_points=grade['snipe_points'],
                         sniping_zeroed=grade['sniping_zeroed'], final_passing_bugs=sum(oracle.last_verdict.values()))
            write_json(out / 'progress.json', state)
            emit(state)
            return state
        except BaseException:
            state.update(status='failed', finished_utc=utc(), error=traceback.format_exc())
            write_json(out / 'progress.json', state)
            emit(state)
            raise

    results, failures = {}, {}
    with ThreadPoolExecutor(max_workers=3) as pool:
        futures = {pool.submit(regrade, plan): plan[0] for plan in plans}
        for future in as_completed(futures):
            name = futures[future]
            try:
                results[name] = future.result()
            except BaseException:
                failures[name] = traceback.format_exc()
    final_inventory = {str(p.relative_to(RUNTIME)): sha(p) for p in sorted(RUNTIME.rglob('*'))
                       if p.is_file() and '__pycache__' not in p.parts}
    assert final_inventory == inventory, 'Frozen grader runtime changed during regrade'
    metadata.update(status='failed' if failures else 'completed', finished_utc=utc(), results=results, failures=failures)
    write_json(HERE / 'provenance.json', metadata)
    emit({'status': metadata['status'], 'output': str(HERE), 'results': results, 'failures': failures})
    return 1 if failures else 0


if __name__ == '__main__':
    raise SystemExit(main())
