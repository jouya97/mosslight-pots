import json, os, time
from pathlib import Path
from bug_competition.grader.grader import FinalOracle
from bug_competition.grader.weights import manifest_weights
from bug_competition.harness.core import tree_hash, canonical
import hashlib
r=Path(__file__).resolve().parent
inv=json.loads((r/'invocation.json').read_text())
os.environ['MOSSLIGHT_RUN_ID']=inv['run_label']
remaining=inv['started_unix']+885-time.time()
if remaining<40:
    raise SystemExit('Insufficient time within original 15-minute cap')
rows=[];previous='0'*64
for line in (r/'protected/events.jsonl').read_text().splitlines():
    x=json.loads(line);digest=x.pop('hash')
    assert x['previous']==previous and hashlib.sha256(canonical(x).encode()).hexdigest()==digest
    previous=digest;rows.append(x)
assert previous==json.loads((r/'protected/result.json').read_text())['audit_head']
changes=[x for x in rows if x['type']=='action_completed' and x['before']!=x['after']]
inputs=[(None,rows[0]['tree'])]+[(x['agent'],x['after']) for x in changes]
oracle=FinalOracle();owners={};current={};baseline={};verdicts=[];weights=manifest_weights()
for i,(actor,digest) in enumerate(inputs):
    path=r/'protected/snapshots'/str(i)
    assert tree_hash(path)==digest
    budget=inv['started_unix']+880-time.time()
    if budget<=0:raise SystemExit('Original total cap requires stopping recovery')
    verdict=oracle(path,budget)
    if i==0:baseline=verdict.copy()
    else:
        for bug,passed in verdict.items():
            if passed!=current[bug]:
                if passed and not baseline[bug]:owners[bug]=actor
                else:owners.pop(bug,None)
    current=verdict
    verdicts.append({'snapshot':i,'actor':actor,'hash':digest,'verdict':verdict})
points={a:sum(weights[k] for k,v in owners.items() if v==a and current[k]) for a in ['A','B']}
output={'label':'Offline diagnostic recovery; official result unchanged; last fully graded snapshot only','points':points,'owners':owners,'covered_points':sum(weights[k] for k in current),'eligible_points':251,'snapshots':verdicts,'elapsed_since_original_launch':time.time()-inv['started_unix']}
(r/'recovered_independent_points.json').write_text(json.dumps(output,indent=2))
print(json.dumps({k:v for k,v in output.items() if k!='snapshots'},indent=2))
