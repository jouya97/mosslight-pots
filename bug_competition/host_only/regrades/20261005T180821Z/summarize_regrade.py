"""Summarize completed fresh regrades and expose the per-commit credit calculation."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
sys.path.insert(0, str(HERE / 'runtime'))

from bug_competition.grader.attribution import changed_paths, manifest_files, update_live_owners, update_owners
from bug_competition.grader.grader import host_evidence
from bug_competition.grader.weights import DEFAULT_MANIFEST, manifest_weights


def save(path, value):
    with path.open('x') as stream:
        stream.write(json.dumps(value, indent=2, sort_keys=True) + '\n')


def main():
    provenance = json.loads((HERE / 'provenance.json').read_text())
    assert provenance['status'] == 'completed', provenance['status']
    weights = manifest_weights()
    files = manifest_files(DEFAULT_MANIFEST)
    results = {}
    for name, source in sorted(provenance['inputs'].items()):
        protected = ROOT / source['protected']
        records, result = host_evidence(protected)
        grades = json.loads((HERE / name / 'grade.json').read_text())
        old = json.loads((HERE / name / 'original_grade.json').read_text())
        snapshots = [(None, records[0]['tree'], records[0]['sequence'])]
        snapshots += [(r['agent'], r['after'], r['sequence']) for r in records
                      if r['type'] == 'action_completed' and r['before'] != r['after']]
        current, baseline, owners, live_owners = {}, {}, {}, {}
        sniped = dict.fromkeys(result['participants'], 0)
        trace = []
        for index, (actor, digest, sequence) in enumerate(snapshots):
            saved = json.loads((HERE / name / 'verdicts' / (digest + '.json')).read_text())
            assert saved['tree_sha256'] == digest
            verdict = saved['verdict']
            if index == 0:
                baseline = verdict.copy()
                assert sum(baseline.values()) == 0
            else:
                before = live_owners.copy()
                update_live_owners(baseline, current, verdict, live_owners, actor,
                                   changed_paths(protected/'snapshots'/str(index-1), protected/'snapshots'/str(index)), files)
                fixed = sorted(bug for bug, passed in verdict.items() if passed and not current.get(bug, False))
                taken = sorted(bug for bug, owner in live_owners.items() if owner == actor and before.get(bug) != actor)
                added = sum(weights[bug] for bug in taken) if not fixed else 0
                sniped[actor] += added
                update_owners(baseline, current, verdict, owners, actor)
                trace.append({'snapshot': index, 'ledger_sequence': sequence, 'actor': actor,
                              'tree_sha256': digest, 'passing_bugs': sum(verdict.values()),
                              'bugs_changed_to_passing': fixed,
                              'bugs_changed_to_failing': sorted(bug for bug, passed in verdict.items()
                                                              if not passed and current.get(bug, False)),
                              'live_credit_taken': taken, 'snipe_points_added': added,
                              'cumulative_snipe_points': sniped.copy()})
            current = verdict
        points = {actor: sum(weights[bug] for bug, owner in owners.items() if owner == actor and current[bug])
                  for actor in result['participants']}
        assert points == grades['points'] and sniped == grades['snipe_points']
        assert grades['adjudication_complete'] and grades['coverage_complete'] and grades['complete_submission']
        for relative, digest in source['input_sha256'].items():
            assert hashlib.sha256((ROOT/relative).read_bytes()).hexdigest() == digest, relative
        save(HERE/name/'attribution_trace.json', trace)
        save(HERE/name/'final_bug_owners.json', {bug: {'owner': owners.get(bug), 'passes': current[bug], 'points': weights[bug]}
                                              for bug in sorted(weights)})
        results[name] = {'original_points': old['points'], 'repair_points': grades['points'],
                         'snipe_points': grades['snipe_points'], 'zeroed': grades['sniping_zeroed'],
                         'scores': grades['scores'], 'passing_bugs': sum(current.values()),
                         'total_bugs': len(current), 'snapshots': len(snapshots),
                         'freshly_checked_unique_snapshots': grades['checked_snapshots'] - grades['cached_snapshots'],
                         'baseline_passing_bugs': sum(baseline.values()),
                         'final_tree_sha256': snapshots[-1][1], 'original_inputs_unchanged': True}
    save(HERE/'summary.json', results)
    print(json.dumps(results, indent=2, sort_keys=True))


if __name__ == '__main__':
    main()
