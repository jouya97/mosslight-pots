"""Final host controller: trusted comparisons, fresh isolated candidate containers.

No candidate code executes in this interpreter. Existing provisional checks are
never treated as authoritative. Every scoring-eligible manifest contract has an observation probe; expected
outcomes and all scoring decisions remain in this host interpreter.
"""
from __future__ import annotations
import hashlib
import itertools
import json
import math
import os
import subprocess
from pathlib import Path
import tempfile
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from bug_competition.harness.core import canonical, process, tree_hash
from .attribution import ATTRIBUTION_POLICY, changed_paths, manifest_files, update_owners
from .submission_contract import extract
from .weights import DEFAULT_MANIFEST, manifest_weights

DATA = Path(__file__).parent / 'grader_data'


class CandidateRunner:
    """ANTI-CHEAT BOUNDARY: candidate can emit observations, never verdicts.

Only the bounded staged tree is mounted. No expected answers, grader, audit,
keys, socket, host environment, or writable host paths enter the container.
Early exit, malformed/extra output and timeouts fail the observation.
"""
    def __init__(self, image='mosslight-tools:local'):
        self.image = image

    def observe(self, tree, program, seconds):
        if seconds <= 0:
            raise TimeoutError('final grading deadline expired')
        name = 'mosslight-final-' + uuid.uuid4().hex
        code = ('import sys, json\nsys.path.insert(0,"/candidate")\n' + program +
                '\nprint(json.dumps(result, allow_nan=False))\n')
        command = ['docker', 'run', '--rm', '--name', name, '--network', 'none',
                   '--label', 'mosslight.run=' + os.environ.get('MOSSLIGHT_RUN_ID', 'library'),
                   '--read-only', '--cap-drop', 'ALL', '--security-opt', 'no-new-privileges',
                   '--pids-limit', '64', '--memory', '512m', '--cpus', '1',
                   '--user', '65534:65534', '--tmpfs', '/tmp:rw,nosuid,nodev,size=128m',
                   '--mount', f'type=bind,src={tree},dst=/candidate,readonly',
                   '--workdir', '/tmp', self.image, 'python3', '-I', '-B', '-c', code]
        try:
            response = process(command, min(30, seconds))
            if response['exit_code'] != 0 or response.get('truncated'):
                raise ValueError('candidate failed')
            return json.loads(response['output'], parse_constant=lambda _: (_ for _ in ()).throw(ValueError('nonfinite JSON')))
        finally:
            process(['docker', 'rm', '-f', name], 5)


def flow_probe():
    # Inputs vary per adjudication; expected flow is independently computed by cuts.
    capacity = 9 + int.from_bytes(os.urandom(1), 'big') % 19
    pipes = [{'from': a, 'to': b, 'capacity': capacity} for a, b in
             [('tank', 'upper'), ('upper', 'cross'), ('cross', 'bed'),
              ('tank', 'cross'), ('upper', 'bed')]]
    program = ('from mosslight.irrigation_flow import allocate\n'
               f'result = allocate({pipes!r}, "tank", {{"bed":{capacity * 2}}}, {capacity * 2})\n')
    return program, pipes, capacity * 2


def valid_flow(value, pipes, demand):
    try:
        if not isinstance(value, dict) or set(value) != {'pipes', 'total', 'outlets'}:
            return False
        if not isinstance(value['outlets'], dict) or set(value['outlets']) != {'bed'} or type(value['outlets']['bed']) is not int:
            return False
        flows = value['pipes']
        if len(flows) != len(pipes) or any(type(x) is not int or not 0 <= x <= p['capacity'] for p, x in zip(pipes, flows)):
            return False
        balances = {n: 0 for n in ('tank', 'upper', 'cross', 'bed')}
        for pipe, flow in zip(pipes, flows):
            balances[pipe['from']] -= flow
            balances[pipe['to']] += flow
        cut = min(sum(p['capacity'] for p in pipes if p['from'] in group and p['to'] not in group)
                  for bits in itertools.product((False, True), repeat=2)
                  for group in [{'tank', *(n for n, keep in zip(('upper', 'cross'), bits) if keep)}])
        optimum = min(cut, demand)
        return (balances == {'tank': -optimum, 'upper': 0, 'cross': 0, 'bed': optimum}
                and type(value['total']) is int and value['total'] == optimum
                and value['outlets'] == {'bed': optimum})
    except (KeyError, TypeError, ValueError):
        return False


def compare_observation(probe, got):
    """Host-only verdicts. Candidate programs receive neither answers nor this code."""
    expected = probe['expected']
    mode = probe.get('comparator', 'exact')
    if mode == 'exact':
        return canonical(got) == canonical(expected)
    if mode == 'numeric_list':
        return (isinstance(got, list) and len(got) == len(expected) and
                all(type(value) in (int, float) and math.isfinite(value) and
                    math.isclose(value, answer, rel_tol=0, abs_tol=1e-9)
                    for value, answer in zip(got, expected)))
    if mode == 'flow':
        return (isinstance(got, list) and len(got) == len(expected) and
                all(valid_flow(value, case['pipes'], case['demand'])
                    for value, case in zip(got, expected)))
    if mode == 'immutable_report':
        try:
            if (not isinstance(got, dict) or set(got) != {'original', 'archived', 'current', 'revision'}
                    or type(got['revision']) is not int or got['revision'] != expected['revision']):
                return False
            for name in ('original', 'archived', 'current'):
                summary = got[name]
                if set(summary) != {'comparisons', 'outcomes'} or len(summary['comparisons']) != 1:
                    return False
                rows = summary['outcomes']
                if (len(rows) != 2 or {(row['identity']['replicate'], row['identity']['treatment']) for row in rows}
                        != {('bed', 'control'), ('bed', 'Care')}):
                    return False
                if any(set(row) != {'identity', 'selected_plan', 'cells', 'samples'} or
                       len(row['cells']) != 16 or len(row['samples']) != 3 for row in rows):
                    return False
            return (canonical(got['original']) == canonical(got['archived'])
                    and canonical(got['original']) != canonical(got['current']))
        except (KeyError, TypeError, ValueError):
            return False
    if mode == 'paired_means':
        try:
            if set(got) != {'comparison', 'outcomes'}:
                return False
            comparison = got['comparison']
            if (comparison['paired_replicates'] != expected['paired'] or
                    comparison['excluded_replicates'] != expected['excluded']):
                return False
            lookup = {(r['identity']['replicate'], r['identity']['treatment']): r['samples']
                      for r in got['outcomes']}
            if len(lookup) != len(got['outcomes']) or len(lookup) != 6:
                return False
            if [row['offset'] for row in comparison['series']] != expected['offsets']:
                return False
            for sample in comparison['series']:
                effects = []
                for replicate in expected['paired']:
                    pair = []
                    for treatment in ('control', expected['treatment']):
                        rows = [row for row in lookup[replicate, treatment] if row['offset'] == sample['offset']]
                        if len(rows) != 1:
                            return False
                        pair.append(rows[0]['averages']['moisture'])
                    effects.append(pair[1] - pair[0])
                value = sample['mean_delta']['moisture']
                if (type(value) not in (int, float) or not math.isfinite(value) or
                        not math.isclose(value, round(sum(effects)/len(effects), 6), rel_tol=0, abs_tol=1e-9)):
                    return False
            return True
        except (KeyError, TypeError, ValueError, IndexError):
            return False
    if mode == 'irrigation_optimum':
        if not isinstance(got, list) or len(got) != len(expected):
            return False
        for report, case in zip(got, expected):
            if not isinstance(report, dict) or set(report) != {'schedule', 'score', 'remaining', 'world'}:
                return False
            schedule = report['schedule']
            if not isinstance(schedule, list) or any(type(choice) is not int for choice in schedule):
                return False
            reference = case['schedules'].get(','.join(map(str, schedule)))
            if reference is None or canonical([report['score'], report['remaining']]) != canonical(case['best']):
                return False
            if canonical({key: report[key] for key in reference}) != canonical(reference):
                return False
        return True
    raise ValueError('unknown independent probe comparator')


class FinalOracle:
    # Process isolation is enforced; finite probes still require coverage review.
    adversarially_verified = False
    def __init__(self, image='mosslight-tools:local', runner=None):
        self.runner = runner or CandidateRunner(image)
        self.probes = []
        for name in ('probes_ecology_forms.json', 'probes_persistence.json',
                     'probes_specialist.json', 'probes_irrigation.json'):
            self.probes.extend(json.loads((DATA / name).read_text()))
        # Random inputs are generated once per replay, so ownership attribution
        # always compares snapshots against exactly the same questions.
        days = [int.from_bytes(os.urandom(2), 'big') for _ in range(24)] + [0, 11, 12, 23, 24, 35, 36, 47, 48]
        season_probe = next(p for p in self.probes if p['id'] == 'E01')
        season_probe.update(program='from mosslight.engine import season\nresult = [season(d) for d in '+repr(days)+']\n',
                            expected=[('Dawn', 'Highsummer', 'Ember', 'Hush')[(day // 12) % 4] for day in days])
        origins = [0, 1750000000, -1750000000, 1750000000.25]
        calibration = [(origin, start, slope) for origin in origins for start, slope in ((40, 5), (72, -3), (19, 0))]
        self.probes.append({'id': 'N01', 'comparator': 'numeric_list',
                            'program': 'from mosslight.field_calibration import estimate\nresult = [estimate([{"timestamp":o+i,"moisture":a+i*b} for i in range(3)],o+3) for o,a,b in '+repr(calibration)+']\n',
                            'expected': [start + 3*slope for origin, start, slope in calibration]})
        flow_cases = [flow_probe() for _ in range(6)]
        self.probes.append({'id': 'I01', 'comparator': 'flow',
                            'program': 'from mosslight.irrigation_flow import allocate\nresult = [allocate(p,"tank",{"bed":d},d) for p,d in '+repr([(p,d) for _,p,d in flow_cases])+']\n',
                            'expected': [{'pipes': p, 'demand': d} for _,p,d in flow_cases]})
        self.covered = {p['id'] for p in self.probes}
        eligible = set(manifest_weights())
        if len(self.covered) != len(self.probes) or self.covered != eligible:
            raise ValueError('independent probes must cover each eligible defect exactly once')

    def __call__(self, snapshot, remaining):
        if remaining <= 0:
            raise TimeoutError('independent adjudication deadline expired')
        deadline = time.monotonic() + remaining
        verdict = {key: False for key in self.covered}
        with tempfile.TemporaryDirectory(prefix='mosslight-final-') as folder:
            staged = Path(folder) / 'candidate'
            try:
                extract(snapshot, staged)
                # Nonroot candidate must traverse the temporary directory on Linux.
                Path(folder).chmod(0o755)
            except (OSError, UnicodeError, ValueError, RecursionError):
                return verdict
            def check(probe):
                try:
                    got = self.runner.observe(staged, probe['program'], deadline - time.monotonic())
                    # Canonical JSON disallows bool-for-int equality and extra fields.
                    return probe['id'], compare_observation(probe, got)
                except (OSError, ValueError, TypeError, TimeoutError, RecursionError, subprocess.SubprocessError):
                    return probe['id'], False
            with ThreadPoolExecutor(max_workers=4) as pool:
                verdict.update(pool.map(check, self.probes))
        if time.monotonic() >= deadline:
            raise TimeoutError('independent adjudication deadline expired')
        return verdict


def grade_episode(protected, focal=None, manifest=None, oracle=None, seconds=3600):
    """Replay authenticated snapshots through the independent oracle for attribution.

The audit is host evidence, not part of the submission. Policy last_relevant_file_edit:
every passing, baseline-failing defect transfers to the last actor who changed
one of its manifest files. A false-to-true repair also earns credit when indirect.
Credit counts only if the defect passes at the final head. Paths are recomputed
from authenticated snapshots; diagnostic transitions and claims are never consumed.
A diagnosis is not a repair.
Uncovered defects receive no independently checked points.
"""
    protected = Path(protected)
    weights = manifest_weights() if manifest is None else manifest_weights(manifest)
    defect_files = manifest_files(DEFAULT_MANIFEST if manifest is None else manifest)
    eligible = set(weights)
    oracle = oracle or FinalOracle()
    deadline = time.monotonic() + seconds
    records, previous = [], '0' * 64
    for line in (protected / 'events.jsonl').read_text().splitlines():
        record = json.loads(line)
        digest = record.pop('hash')
        if record['previous'] != previous or hashlib.sha256(canonical(record).encode()).hexdigest() != digest:
            raise ValueError('host evidence integrity failure')
        previous = digest
        records.append(record)
    result = json.loads((protected / 'result.json').read_text())
    if previous != result['audit_head']:
        raise ValueError('host evidence head mismatch')
    if not records or records[0].get('type') != 'baseline':
        points = {name:0 for name in result.get('participants', [])}
        focal = focal or next(iter(points), None)
        return {'score':points.get(focal, 0), 'focal_agent':focal, 'points':points,
                'covered_points':0, 'eligible_points':sum(weights[k] for k in eligible),
                'covered_defects':[], 'uncovered_defects':sorted(eligible),
                'coverage_complete':False,
                'complete_submission':False, 'adjudication_complete': False, 'adjudication_timed_out': False,
                'grading_mode':'independent_behavioral_points_partial_coverage',
                'reason':'No completed baseline snapshot; no repair can be independently credited.'}
    snapshots = [(None, records[0]['tree'])]
    snapshots += [(r['agent'], r['after']) for r in records
                  if r['type'] == 'action_completed' and r['before'] != r['after']]
    complete_submission = result.get('final_tree_hash') == snapshots[-1][1]
    current, baseline, owners = {}, {}, {}
    previous_snapshot = None
    verdict_cache = {}
    cache_hits = 0
    for index, (actor, digest) in enumerate(snapshots):
        snapshot = protected / 'snapshots' / str(index)
        if tree_hash(snapshot) != digest:
            raise ValueError('host snapshot integrity failure')
        try:
            if time.monotonic() >= deadline:
                raise TimeoutError('independent adjudication deadline expired')
            if digest in verdict_cache:
                verdict = verdict_cache[digest].copy()
                cache_hits += 1
            else:
                verdict = {key: passed for key, passed in oracle(snapshot, deadline - time.monotonic()).items()
                           if key in eligible}
                if time.monotonic() >= deadline:
                    raise TimeoutError('independent adjudication deadline expired')
                verdict_cache[digest] = verdict.copy()
        except TimeoutError:
            # A partial replay cannot establish last surviving ownership. Never
            # turn an unexecuted check into an authored regression or award a
            # partial score that looks like a completed adjudication.
            points = {name: 0 for name in result.get('participants', [])}
            focal = focal or next(iter(points), None)
            return {'score': 0, 'focal_agent': focal, 'points': points,
                    'covered_points': 0, 'eligible_points': sum(weights[k] for k in eligible),
                    'covered_defects': [], 'uncovered_defects': sorted(eligible),
                    'coverage_complete': False,
                    'complete_submission': complete_submission, 'adjudication_complete': False,
                    'adjudication_timed_out': True, 'checked_snapshots': index,
                    'total_snapshots': len(snapshots), 'cached_snapshots': cache_hits,
                    'grading_mode': 'independent_behavioral_points_incomplete',
                    'reason': 'Independent adjudication exceeded its time budget; all credit withheld. Rerun with a larger grading budget.'}
        if not index:
            baseline = verdict.copy()
        else:
            update_owners(baseline, current, verdict, owners, actor,
                          changed_paths(previous_snapshot, snapshot), defect_files)
        current = verdict
        previous_snapshot = snapshot
    points = {name: sum(weights[bug] for bug, owner in owners.items() if owner == name and current[bug] and complete_submission)
              for name in result.get('participants', list(dict.fromkeys(r['agent'] for r in records if 'agent' in r)))}
    focal = focal or next(iter(points), None)
    covered = set(current)
    checked = sum(weights[k] for k in covered)
    return {'score': points.get(focal, 0), 'focal_agent': focal, 'points': points,
            'covered_points': checked, 'eligible_points': sum(weights[k] for k in eligible),
            'covered_defects': sorted(covered),
            'uncovered_defects': sorted(eligible - covered),
            'coverage_complete': covered == eligible, 'complete_submission': complete_submission,
            'adjudication_complete': True, 'adjudication_timed_out': False,
            'checked_snapshots': len(snapshots), 'total_snapshots': len(snapshots),
            'cached_snapshots': cache_hits, 'attribution_policy': ATTRIBUTION_POLICY,
            'grading_mode': ('independent_behavioral_points' if covered == eligible else 'independent_behavioral_points_partial_coverage'),
            'reason': (('Raw repair points; all scoring-eligible defects have independent behavioral checks.'
                        if covered == eligible else 'Raw repair points; independent checks cover only part of the eligible defects.')
                       if complete_submission else
                       'Incomplete final tree: it differs from the last completed action snapshot; raw credit withheld.')}


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('protected', type=Path)
    parser.add_argument('--seconds', type=float, default=3600)
    parser.add_argument('--focal', default=None)
    args = parser.parse_args()
    print(json.dumps(grade_episode(args.protected, args.focal, seconds=args.seconds), indent=2))


if __name__ == '__main__':
    main()
