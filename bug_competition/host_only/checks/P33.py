from mosslight.model import World, Cell
from mosslight import courier as c

def garden():
    w=World(7,4,4,cells=[Cell(50,50,50) for _ in range(16)])
    w.workbench["notes"]=[{"id":1,"day":0,"text":"Fern unfurled","tags":[],"tile":None}]
    w.workbench["next_id"]=2
    return w

def records(packet):
    return {event["record"] for event in packet["events"].values()}

# Two independently created garden instances may have the same local IDs and
# content. Inspect the exported record identities to isolate this migration
# contract from the separate causal-register defects.
a,b=garden(),garden()
assert a is not b and a.to_dict()==b.to_dict()
assert records(c.from_garden(a,"desk")).isdisjoint(records(c.from_garden(b,"field")))
# Explicit provenance remains a working way to join known copies.
assert records(c.from_garden(a,"desk","pond"))==records(c.from_garden(b,"field","pond"))

