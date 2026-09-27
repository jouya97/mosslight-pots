#!/usr/bin/env python3
"""Baseline suite, browser test and basic integrated-app usability evidence."""
from pathlib import Path
import json
import shutil
import subprocess
import sys
HOST=Path(__file__).resolve().parent
results={}
for name in ('expanded_baseline','integrated_snapshot'):
    result=subprocess.run([sys.executable,'-B','-m','unittest','discover','-s','tests','-v'],cwd=HOST/name,text=True,capture_output=True,timeout=120)
    output=result.stdout+result.stderr
    (HOST/(name+'-public-tests.txt')).write_text(output)
    results[name]={'returncode':result.returncode,'tail':output[-800:]}
node=shutil.which('node')
if node:
    result=subprocess.run([node,'tests/test_studio.js'],cwd=HOST/'integrated_snapshot',text=True,capture_output=True,timeout=20)
    results['browser_contracts']={'returncode':result.returncode,'output':result.stdout+result.stderr}
else:results['browser_contracts']={'skipped':'node unavailable'}
smoke='''from mosslight.engine import create,step
from mosslight.model import World,save,load
from mosslight.render import render_svg
from mosslight.exchange import export_csv
from mosslight.commands import execute
from mosslight.courier import new_packet,put,observations
import tempfile
from pathlib import Path
w=create(7,8,5)
step(w,10)
assert w.day==10 and len(w.cells)==40
execute(w,{"op":"rename","args":{"title":"Field garden"}})
execute(w,{"op":"note","args":{"content":"Fern observations"}})
with tempfile.TemporaryDirectory() as tmp:
    p=Path(tmp)/"garden.json";save(w,p); restored=load(p)
    assert restored.to_dict()==w.to_dict()
assert render_svg(w).count('class="tile"')==40
assert len(export_csv(w).splitlines())==41
p=new_packet("desk");put(p,"fern",{"text":"Unfurled"})
assert observations(p)[0]["fields"]["text"]==["Unfurled"]
print("Integrated smoke: create, ten daily steps, commands, save/load, SVG, CSV and a basic courier note succeeded.")
'''
result=subprocess.run([sys.executable,'-B','-c',smoke],cwd=HOST/'integrated_snapshot',text=True,capture_output=True,timeout=20)
results['integrated_smoke']={'returncode':result.returncode,'output':result.stdout+result.stderr}
(HOST/'public_tests.json').write_text(json.dumps(results,indent=2)+'\n')
print(json.dumps(results,indent=2))
raise SystemExit(0 if results['expanded_baseline']['returncode']==0 and results['integrated_smoke']['returncode']==0 and results.get('browser_contracts',{}).get('returncode',0)==0 else 1)
