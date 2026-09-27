#!/usr/bin/env python3
"""Reproducible offline courier baseline properties and delayed-packet trace."""
import copy
import importlib.util
import json
from pathlib import Path
import random
import sys
import tempfile
import verify
HOST=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('courier_baseline',HOST/'expanded_baseline/mosslight/courier.py')
c=importlib.util.module_from_spec(spec);spec.loader.exec_module(c)

def visible(packet):return c.observations(packet)

def trace(module):
    f=module.new_packet('field')
    for record,text in [('R','Field original'),('Q','Only shared Q'),('R','Field updated'),('Q','Only shared Q v2'),('Q','Only shared Q v3')]:
        module.put(f,record,{'text':text})
    selected=module.project(f,['Q'])
    d=module.new_packet('desk');module.put(d,'R',{'text':'Desk edit'})
    joined=module.merge(d,selected)
    direct=module.observations(module.merge(joined,f))
    compact=module.checkpoint(joined)
    delayed=module.observations(module.merge(compact,f))
    return {'before_checkpoint_merge':direct,'after_checkpoint_merge':delayed,'checkpoint_R_context':compact['contexts']['R']}

rng=random.Random(927)
replicas=[c.new_packet(peer) for peer in ('desk','field','shed')]
checks=0
for index in range(300):
    i,j=rng.sample(range(3),2);record=rng.choice(('pond','fern','moss'));operation=rng.randrange(5)
    if operation==0:c.put(replicas[i],record,{'text':f'Observation {index} from {i}'})
    elif operation==1:c.remove(replicas[i],record)
    elif operation==2:replicas[i]=c.merge(replicas[i],replicas[j])
    elif operation==3:replicas[i]=c.checkpoint(replicas[i])
    else:replicas[i]=c.merge(replicas[i],c.project(replicas[j],[record]))
    a,b,d=replicas
    assert visible(c.merge(a,a))==visible(a);checks+=1
    assert visible(c.merge(a,b))==visible(c.merge(b,a));checks+=1
    assert visible(c.merge(c.merge(a,b),d))==visible(c.merge(a,c.merge(b,d)));checks+=1
    assert visible(c.checkpoint(a))==visible(a);checks+=1
for note in ['a','Fern unfurled','水辺の苔','moss\nfern','x'*2000]:
    assert c.recover(c.receipt(note))==note;checks+=1
baseline_trace=trace(c)
assert baseline_trace['before_checkpoint_merge']==baseline_trace['after_checkpoint_merge']
entries=json.loads((HOST/'manifest.json').read_text())['entries'];entry=next(e for e in entries if e['id']=='P34')
with tempfile.TemporaryDirectory(prefix='courier-trace-',dir=HOST) as tmp:
    path=Path(tmp);(path/'mosslight').mkdir()
    (path/'mosslight/courier.py').write_text((HOST/'expanded_baseline/mosslight/courier.py').read_text())
    verify.mutate(path,entry)
    s=importlib.util.spec_from_file_location('courier_trace_seed',path/'mosslight/courier.py');bug=importlib.util.module_from_spec(s);s.loader.exec_module(bug)
    seeded_trace=trace(bug)
assert seeded_trace['before_checkpoint_merge']!=seeded_trace['after_checkpoint_merge']
result={'random_seed':927,'operations':300,'property_assertions':checks,'baseline_trace':baseline_trace,'P34_isolated_trace':seeded_trace,
        'tested_properties':'Materialized-view idempotence, commutativity, associativity and checkpoint preservation after 300 deterministic put/remove/merge/checkpoint/project operations. Five receipt round trips.',
        'limits':'This is a deterministic sampled state-space audit, not a formal convergence proof. The courier is intentionally a local notebook workflow, not a deployed distributed service.'}
(HOST/'courier_audit.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps({'property_assertions':checks,'trace_difference_confirmed':True},indent=2))
