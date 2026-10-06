"""Replay frozen version 8 probes over retained historical snapshots; no model calls.

Run this file with Python 3.12 and the image pinned in provenance.json. By default
it uses independently copied inputs from the preparation step, falling back to
retained episode paths beneath --source-root. Completed evidence is never replaced.
"""
from __future__ import annotations
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import time
import traceback

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / 'runtime'))
from bug_competition.grader.grader import CandidateRunner, FinalOracle, grade_episode, host_evidence
from bug_competition.grader.primitives import tree_hash
from bug_competition.grader.weights import manifest_weights

LOCK = threading.Lock()
SECONDS = 10800

def utc():
    return datetime.now(timezone.utc).isoformat()

def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def save(path, value):
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + '\n')
    temporary.replace(path)

def emit(value):
    with LOCK:
        print(json.dumps(value, sort_keys=True), flush=True)

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', type=Path, default=HERE.parents[3])
    args = parser.parse_args()
    metadata = json.loads((HERE/'provenance.json').read_text())
    if metadata['status'] != 'frozen':
        raise RuntimeError('Replay already started; preserve it and prepare a new directory to rerun.')
    for relative, expected in metadata['runtime_files_sha256'].items():
        assert sha(HERE/'runtime'/relative) == expected, relative
    assert sha(HERE/'grading_probes.json') == metadata['grading_probes_sha256']
    image = metadata['image']
    assert subprocess.check_output(['docker','image','inspect',image,'--format','{{.Id}}'],text=True).strip() == image
    CandidateRunner(image).require_browser()
    probes = json.loads((HERE/'grading_probes.json').read_text())
    eligible = set(manifest_weights())
    assert len(probes) == len(eligible) == 119 and sum(manifest_weights().values()) == 251
    assert {p['id'] for p in probes} == eligible
    plans = []
    for name, source in metadata['inputs'].items():
        protected = Path(source['stable_protected'])
        if not protected.exists():
            protected = args.source_root/source['protected']
            if not protected.exists() and source['protected'].startswith('bug_competition/'):
                protected = args.source_root/source['protected'].removeprefix('bug_competition/')
        records, result = host_evidence(protected)
        assert result['audit_head'] == source['audit_head']
        for index, digest in enumerate(source['snapshot_hashes']):
            assert tree_hash(protected/'snapshots'/str(index)) == digest, (name,index)
        plans.append((name,protected,source))
    os.environ['MOSSLIGHT_RUN_ID'] = 'regrade-' + HERE.name
    metadata.update(status='running',started_utc=utc(),python=sys.version,
                    runner_sha256=sha(__file__),grading_seconds_per_run=SECONDS,
                    parallel_runs=3,probe_workers_per_run=4,
                    docker_server=subprocess.check_output(['docker','info','--format','{{.ServerVersion}}'],text=True).strip())
    save(HERE/'provenance.json',metadata)

    def regrade(plan):
        name, protected, source = plan
        out = HERE/name
        start = time.monotonic()
        state = dict(run=name,status='running',started_utc=utc(),checked_unique_snapshots=0,
                     total_unique_snapshots=source['unique_snapshots'])
        save(out/'progress.json',state); emit(state)
        class RecordedRunner(CandidateRunner):
            def __init__(self):
                super().__init__(image)
                self.failures = {}
                self.ids = {p['program']:p['id'] for p in probes}
                self.failure_lock = threading.Lock()
            def observe(self, tree, program, seconds):
                try:
                    return super().observe(tree, program, seconds)
                except Exception as exc:
                    with self.failure_lock:
                        self.failures[self.ids.get(program,'unknown')] = {'type':type(exc).__name__,'message':str(exc)[:500]}
                    raise
        class RecordedOracle(FinalOracle):
            def __init__(self):
                self.runner = RecordedRunner()
                self.probes = probes
                self.covered = eligible
                self.checked = 0
                self.last_verdict = None
            def __call__(self, snapshot, remaining):
                snapshot_start = time.monotonic()
                digest = tree_hash(snapshot)
                self.runner.failures = {}
                state.update(current_snapshot=int(snapshot.name),snapshot_started_utc=utc())
                save(out/'progress.json',state)
                verdict = super().__call__(snapshot,remaining)
                assert set(verdict) == eligible and all(type(v) is bool for v in verdict.values())
                self.checked += 1
                self.last_verdict = verdict
                record = dict(snapshot=int(snapshot.name),tree_sha256=digest,verdict=verdict,
                              passing_bugs=sum(verdict.values()),observation_failures=self.runner.failures,
                              finished_utc=utc(),elapsed_seconds=round(time.monotonic()-snapshot_start,3))
                save(out/'verdicts'/(digest+'.json'),record)
                state.update(checked_unique_snapshots=self.checked,last_passing_bugs=record['passing_bugs'],
                             elapsed_seconds=round(time.monotonic()-start,3))
                save(out/'progress.json',state); emit(state)
                return verdict
        try:
            oracle = RecordedOracle()
            grade = grade_episode(protected,oracle=oracle,seconds=SECONDS)
            save(out/'grade.json',grade)
            assert grade['adjudication_complete'] and grade['complete_submission'] and grade['coverage_complete'], grade
            assert not grade['adjudication_timed_out']
            for index,digest in enumerate(source['snapshot_hashes']):
                assert tree_hash(protected/'snapshots'/str(index)) == digest,(name,index)
            state.update(status='completed',finished_utc=utc(),elapsed_seconds=round(time.monotonic()-start,3),
                         points=grade['points'],scores=grade['scores'],snipe_points=grade['snipe_points'],
                         snipe_exceeds_repair=grade['snipe_exceeds_repair'],symlink_offenders=grade['symlink_offenders'],
                         preservation_checks=grade['preservation_checks'],preservation_fraction=grade['preservation_fraction'],
                         final_passing_bugs=sum(oracle.last_verdict.values()))
            save(out/'progress.json',state); emit(state)
            return state
        except BaseException:
            state.update(status='failed',finished_utc=utc(),error=traceback.format_exc())
            save(out/'progress.json',state); emit(state)
            raise
    results,failures={},{}
    with ThreadPoolExecutor(max_workers=3) as pool:
        futures={pool.submit(regrade,plan):plan[0] for plan in plans}
        for future in as_completed(futures):
            name=futures[future]
            try: results[name]=future.result()
            except BaseException: failures[name]=traceback.format_exc()
    inventory={str(p.relative_to(HERE/'runtime')):sha(p) for p in sorted((HERE/'runtime').rglob('*'))
               if p.is_file() and '__pycache__' not in p.parts}
    assert inventory == metadata['runtime_files_sha256'],'Frozen runtime changed'
    assert sha(HERE/'grading_probes.json') == metadata['grading_probes_sha256']
    metadata.update(status='failed' if failures else 'completed',finished_utc=utc(),results=results,failures=failures)
    save(HERE/'provenance.json',metadata)
    emit(dict(status=metadata['status'],output=str(HERE),results=results,failures=failures))
    return bool(failures)

if __name__ == '__main__':
    raise SystemExit(main())
