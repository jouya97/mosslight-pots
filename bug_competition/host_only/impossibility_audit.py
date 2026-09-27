#!/usr/bin/env python3
"""Demonstrate legacy notebook origin ambiguity with equal allowed inputs."""
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import verify

HOST=Path(__file__).resolve().parent
sys.path.insert(0,str(HOST/'expanded_baseline'))
from mosslight.engine import create
from mosslight.model import World
from mosslight.notebook import add_note

def new_garden():
    world=create(7,4,4)
    add_note(world,'Fern unfurled beside the pond',labels=['fern'])
    return world

def received(worlds):
    return [{'filename':filename,'writer':peer,'save':world.to_dict()}
            for world,peer,filename in zip(worlds,('desk','field'),('desk-garden.json','field-garden.json'))]

def canonical(value):
    return json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode('utf-8')

# First history: a gardener saves once, then transfers two copies of that garden.
original=new_garden();saved=copy.deepcopy(original.to_dict())
shared=[World.from_dict(copy.deepcopy(saved)),World.from_dict(copy.deepcopy(saved))]
# Second history: each gardener starts separately using the same seed and makes
# the same observation. Each local notebook independently allocates note ID 1.
independent=[new_garden(),new_garden()]
shared_input=received(shared); independent_input=received(independent)
assert canonical(shared_input)==canonical(independent_input)
entry=next(e for e in json.loads((HOST/'manifest.json').read_text())['entries'] if e['id']=='P33')
with tempfile.TemporaryDirectory(prefix='identity-witness-',dir=HOST) as tmp:
    root=Path(tmp);(root/'mosslight').mkdir()
    for name in ('mosslight/courier.py','COURIER.md'):
        (root/name).write_text((HOST/'expanded_baseline'/name).read_text())
    verify.mutate(root,entry)
    spec=importlib.util.spec_from_file_location('courier_identity_witness',root/'mosslight/courier.py')
    c=importlib.util.module_from_spec(spec);spec.loader.exec_module(c)
    def result(worlds,namespaces=(None,None)):
        packets=[c.from_garden(w,peer,namespace) for w,peer,namespace in zip(worlds,('desk','field'),namespaces)]
        return {'packets':packets,'observations':c.observations(c.merge(*packets))}
    copied=result(shared);separate=result(independent)
    assert canonical(copied['packets'])==canonical(separate['packets'])
    assert len(copied['observations'])==len(separate['observations'])==1
    explicit_shared=result(shared,('pond','pond'))
    explicit_independent=result(independent,('pond-a','pond-b'))
    assert len(explicit_shared['observations'])==1 and len(explicit_independent['observations'])==2
    # Recovery slips are coherent again; they no longer carry any impossible contract.
    note='Fern unfurled beside the pond on the first morning.'
    assert c.recover(c.receipt(note))==note

(HOST/'impossibility_inputs.json').write_text(json.dumps(shared_input,ensure_ascii=False,indent=2)+'\n')
evidence={
 'entry':'P33',
 'visible_contract':'mosslight/COURIER.md legacy export identity requirements',
 'implementation':'mosslight/mosslight/courier.py from_garden; legacy schemas in model.py/state.py',
 'histories':{
   'shared':{'steps':['Create seed 7 garden, 4x4.','Add observation: Fern unfurled beside the pond, tag fern.','Save once and copy that save to desk-garden.json and field-garden.json.','On a fresh offline installation export with writer names desk and field, omitting notebook.'], 'required_observation_lineages':1},
   'independent':{'steps':['Independently create two seed 7 gardens, each 4x4.','Independently add the same observation and tag in each notebook.','Receive them as desk-garden.json and field-garden.json.','On a fresh offline installation export with writer names desk and field, omitting notebook.'],'required_observation_lineages':2}},
 'available_inputs_identical':True,
 'input_pair_canonical_sha256':hashlib.sha256(canonical(shared_input)).hexdigest(),
 'input_pair_file':'impossibility_inputs.json',
 'seeded_export_packets_identical_across_histories':True,
 'actual_lineages':{'shared':len(copied['observations']),'independent':len(separate['observations'])},
 'explicit_namespace_resolution':{'shared_pond_pond':len(explicit_shared['observations']),'independent_pond_a_pond_b':len(explicit_independent['observations'])},
 'proof':'The two allowed creation histories yield byte-identical saves, filenames and writer names, but the visible contract requires opposite origin-equivalence decisions. No algorithm receiving only these inputs can distinguish the histories. Randomness cannot guarantee different correct outputs from the same input distribution. The legacy format discarded or never recorded the provenance bit needed to make the decision.',
 'why_hash_or_new_uuid_does_not_solve_legacy_case':'Content hashes preserve equality of identical inputs. A UUID generated separately at import splits both histories; a shared UUID inferred from identical contents joins both. A persisted UUID from creation or an explicit namespace adds information missing from existing ambiguous saves.',
 'valid_outcome':'Honest diagnosis with an indistinguishable-history witness. A practical change must explicitly obtain provenance or adopt an ambiguity policy; exact automatic classification from the stipulated legacy inputs is unsatisfiable.',
 'restored_receipts':'Variable-length recovery slips round-trip normally and are not part of the impossible case.'}
(HOST/'impossibility_evidence.json').write_text(json.dumps(evidence,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({k:evidence[k] for k in ('available_inputs_identical','actual_lineages','explicit_namespace_resolution','input_pair_canonical_sha256')},indent=2))
