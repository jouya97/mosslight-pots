#!/usr/bin/env python3
"""Check whether any one stored inverse repair clears other defect oracles."""
import argparse
from concurrent.futures import ThreadPoolExecutor,as_completed
import json
from pathlib import Path
import shutil
import tempfile
import time
import verify

HOST=verify.HOST
entries=json.loads((HOST/'manifest.json').read_text())['entries']
def row(entry):
    with tempfile.TemporaryDirectory(prefix='overlap-',dir=HOST) as tmp:
        variant=Path(tmp)/'mosslight';shutil.copytree(verify.COMBINED,variant,ignore=verify.IGNORED)
        verify.mutate(variant,entry,reverse=True)
        cleared=[]
        for other in entries:
            if verify.check(other,variant)['passed']:cleared.append(other['id'])
    return {'repair':entry['id'],'passing_checks':cleared,'expected':[entry['id']], 'independent':cleared==[entry['id']]}
started=time.monotonic();results=[]
with ThreadPoolExecutor(max_workers=12) as pool:
    pending=[pool.submit(row,e) for e in entries]
    for future in as_completed(pending):
        r=future.result();results.append(r)
        if not r['independent']:print('Cross-clear:',r,flush=True)
        if len(results)%12==0:print(f'Completed {len(results)}/{len(entries)} inverse-repair rows',flush=True)
results.sort(key=lambda r:r['repair'])
report={'size':len(entries),'check_executions':len(entries)**2,'independent_repairs':sum(r['independent'] for r in results),'elapsed_s':round(time.monotonic()-started,2),'rows':results,'scope':'Every stored inverse mutation is applied alone to the combined app, then every focused oracle is run in a fresh interpreter. This audits the supplied repairs, not all conceivable broad redesigns.'}
(HOST/'overlap_matrix.json').write_text(json.dumps(report,indent=2)+'\n')
print({k:v for k,v in report.items() if k!='rows'})
raise SystemExit(0 if report['independent_repairs']==len(entries) else 1)
