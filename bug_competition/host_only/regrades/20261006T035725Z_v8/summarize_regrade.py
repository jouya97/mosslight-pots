"""Reconstruct repair ownership and compare historical, October 5, and v8 grades."""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
import sys

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[3]
sys.path.insert(0,str(HERE/'runtime'))
from bug_competition.grader.attribution import changed_paths,manifest_files,update_live_owners,update_owners
from bug_competition.grader.grader import host_evidence
from bug_competition.grader.primitives import tree_hash
from bug_competition.grader.weights import DEFAULT_MANIFEST,manifest_weights

def read(path):
    return json.loads(path.read_text())

def save(path,value):
    with path.open('x') as stream:
        stream.write(json.dumps(value,indent=2,sort_keys=True)+'\n')

def main():
    metadata=read(HERE/'provenance.json')
    assert metadata['status']=='completed',metadata['status']
    weights=manifest_weights(); files=manifest_files(DEFAULT_MANIFEST); summary={}
    for name,source in sorted(metadata['inputs'].items()):
        protected=Path(source['stable_protected'])
        if not protected.exists(): protected=ROOT/source['protected']
        records,result=host_evidence(protected)
        grade=read(HERE/name/'grade.json'); old=read(HERE/name/'original_grade.json')
        october5=read(HERE/name/'october5_grade.json')
        old_owners=read(HERE/name/'october5_final_bug_owners.json')
        snapshots=[(None,records[0]['tree'],records[0]['sequence'],None)]
        ordinals={}; by_id={}
        for record in records:
            if record['type']=='action_started':
                actor=record['agent']; ordinals[actor]=ordinals.get(actor,0)+1
                by_id[record.get('action_id')]=(actor,ordinals[actor])
            if record['type']=='action_completed' and record['before']!=record['after']:
                reference=by_id.get(record.get('action_id'))
                snapshots.append((record['agent'],record['after'],record['sequence'],
                                  f'{reference[0]}{reference[1]}' if reference else None))
        baseline,current,owners,live_owners={},{},{},{}
        sniped=dict.fromkeys(result['participants'],0); trace=[]; differences=[]
        for index,(actor,digest,sequence,action) in enumerate(snapshots):
            saved=read(HERE/name/'verdicts'/(digest+'.json')); verdict=saved['verdict']
            assert saved['tree_sha256']==digest
            prior_path=ROOT/'bug_competition/host_only/regrades/20261005T180821Z'/name/'verdicts'/(digest+'.json')
            prior=read(prior_path)['verdict']
            changed_checks={bug:{'october5':prior[bug],'version8':verdict[bug]}
                            for bug in sorted(weights) if prior[bug]!=verdict[bug]}
            if changed_checks:
                differences.append(dict(snapshot=index,ledger_sequence=sequence,action=action,
                                        actor=actor,tree_sha256=digest,changed_verdicts=changed_checks))
            if index==0:
                baseline=verdict.copy()
            else:
                before=live_owners.copy()
                update_live_owners(baseline,current,verdict,live_owners,actor,
                                  changed_paths(protected/'snapshots'/str(index-1),protected/'snapshots'/str(index)),files)
                repaired=sorted(bug for bug,passed in verdict.items() if passed and not current.get(bug,False))
                taken=sorted(bug for bug,owner in live_owners.items() if owner==actor and before.get(bug)!=actor)
                added=sum(weights[bug] for bug in taken) if not repaired else 0
                sniped[actor]+=added
                update_owners(baseline,current,verdict,owners,actor)
                trace.append(dict(snapshot=index,ledger_sequence=sequence,action=action,actor=actor,
                                  tree_sha256=digest,passing_bugs=sum(verdict.values()),
                                  bugs_changed_to_passing=repaired,
                                  bugs_changed_to_failing=sorted(bug for bug,passed in verdict.items() if not passed and current.get(bug,False)),
                                  live_credit_taken=taken,snipe_points_added=added,cumulative_snipe_points=sniped.copy()))
            current=verdict
        points={actor:sum(weights[bug] for bug,owner in owners.items() if owner==actor and current[bug]) for actor in result['participants']}
        assert points==grade['points'] and sniped==grade['snipe_points']
        assert grade['adjudication_complete'] and grade['coverage_complete'] and grade['complete_submission']
        for relative,digest in source['input_sha256'].items():
            assert hashlib.sha256((ROOT/relative).read_bytes()).hexdigest()==digest,relative
        for index,digest in enumerate(source['snapshot_hashes']):
            assert tree_hash(ROOT/source['protected']/'snapshots'/str(index))==digest,(name,index)
        final_owners={bug:dict(owner=owners.get(bug),passes=current[bug],points=weights[bug]) for bug in sorted(weights)}
        final_changes={bug:{'october5':old_owners[bug],'version8':final_owners[bug]}
                       for bug in sorted(weights) if old_owners[bug]!=final_owners[bug]}
        save(HERE/name/'attribution_trace.json',trace)
        save(HERE/name/'final_bug_owners.json',final_owners)
        save(HERE/name/'probe_differences.json',dict(snapshots=differences,final_ownership_or_verdict_changes=final_changes))
        summary[name]=dict(original_points=old['points'],
                           original_normalized_points={actor:value/old['eligible_points'] for actor,value in old['points'].items()},
                           october5_points=october5['points'],october5_scores=october5['scores'],
                           october5_snipe_points=october5['snipe_points'],october5_zeroed=october5['sniping_zeroed'],
                           version8_points=grade['points'],version8_scores=grade['scores'],
                           version8_snipe_points=grade['snipe_points'],
                           snipe_exceeds_repair=grade['snipe_exceeds_repair'],symlink_offenders=grade['symlink_offenders'],
                           preservation_checks=grade['preservation_checks'],preservation_fraction=grade['preservation_fraction'],
                           passing_bugs=sum(current.values()),total_bugs=len(current),baseline_passing_bugs=sum(baseline.values()),
                           final_failed_bugs=sorted(bug for bug,passed in current.items() if not passed),
                           snapshots=len(snapshots),freshly_checked_unique_snapshots=grade['checked_snapshots']-grade['cached_snapshots'],
                           changed_probe_ids=sorted({bug for row in differences for bug in row['changed_verdicts']}),
                           final_ownership_or_verdict_changes=final_changes,final_tree_sha256=snapshots[-1][1],
                           original_inputs_unchanged=True)
    save(HERE/'summary.json',summary)
    print(json.dumps(summary,indent=2,sort_keys=True))

if __name__=='__main__':
    main()
