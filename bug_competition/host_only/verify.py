#!/usr/bin/env python3
"""Host-only mutation audit. No model calls and no network access.

Snapshots, checks, source replacements and results all remain under host_only.
Do not distribute this directory or the clean archive with the competitor app.
"""
from __future__ import annotations
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import copy
import difflib
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time

HOST=Path(__file__).resolve().parent
ROOT=HOST.parent
WORK=ROOT/'mosslight'
ARCHIVE=ROOT/'archives/mosslight-clean-2026-09-24'
BASE=HOST/'expanded_baseline'
COMBINED=HOST/'integrated_snapshot'
IGNORED=shutil.ignore_patterns('__pycache__','*.pyc','.DS_Store','.git')


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def tree_hashes(root):
    return {str(p.relative_to(root)):digest(p) for p in sorted(root.rglob('*'))
            if p.is_file() and '__pycache__' not in p.parts and p.suffix!='.pyc' and '.git' not in p.parts and p.name!='.DS_Store'}


def replacements(e):
    return e.get('replacements',[{'file':e['file'],'old':e['old'],'new':e['new']}])


def mutate(root,entry,reverse=False):
    for r in replacements(entry):
        path=root/r['file']; data=path.read_text()
        old,new=(r['new'],r['old']) if reverse else (r['old'],r['new'])
        if data.count(old)!=1:
            raise RuntimeError(f'{entry["id"]}: {path}: anchor count {data.count(old)} (reverse={reverse})')
        path.write_text(data.replace(old,new),encoding='utf-8')


def check(entry,root):
    # cwd controls project import resolution, and bytecode caches are disabled.
    program=HOST/'checks'/f'{entry["id"]}.py'
    source='import sys\nsys.path.insert(0, '+repr(str(root))+')\n'+program.read_text()
    started=time.monotonic()
    result=subprocess.run([sys.executable,'-B','-c',source],cwd=root,text=True,capture_output=True,timeout=25,
                          env={**os.environ,'PYTHONDONTWRITEBYTECODE':'1'})
    return {'passed':result.returncode==0,'returncode':result.returncode,
            'duration_s':round(time.monotonic()-started,4),
            'stdout':result.stdout[-3000:],'stderr':result.stderr[-5000:]}


def prepare():
    entries=[]
    for area in ('ecology','fieldwork','platform'):
        entries.extend(json.loads((HOST/area/'mutations.json').read_text()))
    assert len({e['id'] for e in entries})==len(entries)
    assert sum(e['level']=='impossible' for e in entries)==1
    if BASE.exists():shutil.rmtree(BASE)
    shutil.copytree(ARCHIVE,BASE,ignore=IGNORED)
    shutil.copy2(HOST/'platform/courier-baseline.py',BASE/'mosslight/courier.py')
    shutil.copy2(HOST/'platform/COURIER-baseline.md',BASE/'COURIER.md')
    shutil.copy2(HOST/'platform/README-expanded.md',BASE/'README.md')
    (HOST/'checks').mkdir(exist_ok=True);(HOST/'patches').mkdir(exist_ok=True)
    for e in entries:
        (HOST/'checks'/f'{e["id"]}.py').write_text(e['check']+'\n')
        e['hidden_tests']=[f'checks/{e["id"]}.py']
        e['reproduction_command']=f'python3 host_only/run_check.py {e["id"]} --tree mosslight'
        e['difficulty_confidence']='low' if e['level']=='hard' else 'medium'
        if e['level']=='impossible':e['difficulty_confidence']='proof'
        e['locations']=[];patch=[]
        for r in replacements(e):
            data=(BASE/r['file']).read_text()
            assert data.count(r['old'])==1,(e['id'],r['file'])
            line=data[:data.index(r['old'])].count('\n')+1
            e['locations'].append({'file':r['file'],'baseline_line':line})
            patch.extend(difflib.unified_diff(data.splitlines(True),data.replace(r['old'],r['new']).splitlines(True),fromfile='a/'+r['file'],tofile='b/'+r['file']))
        (HOST/'patches'/f'{e["id"]}.patch').write_text(''.join(patch))
        e['audit_patch']=f'patches/{e["id"]}.patch'
    if COMBINED.exists():shutil.rmtree(COMBINED)
    shutil.copytree(BASE,COMBINED,ignore=IGNORED)
    for e in entries:mutate(COMBINED,e)
    for e in entries:
        for location, replacement in zip(e['locations'], replacements(e)):
            source=(COMBINED/replacement['file']).read_text()
            location['combined_line']=source[:source.index(replacement['new'])].count('\n')+1
        e['overlap_verification']={'report':'overlap_matrix.json','repair_row':e['id'],
                                   'scope':'All focused checks after this inverse repair alone.'}
        e['verification_report']={'file':'verification.json','entry':e['id']}
    baseline_hashes=tree_hashes(BASE);combined_hashes=tree_hashes(COMBINED);actual=tree_hashes(WORK)
    mismatches=[p for p in sorted(set(actual)|set(combined_hashes)) if actual.get(p)!=combined_hashes.get(p)]
    (HOST/'snapshot_hashes.json').write_text(json.dumps({'archive':tree_hashes(ARCHIVE),'expanded_baseline':baseline_hashes,'integrated_snapshot':combined_hashes,'working_tree_mismatches':mismatches},indent=2)+'\n')
    manifest={'schema_version':1,'purpose':'Host-only defect ground truth and local verification',
              'count':len(entries),'distribution':{level:sum(e['level']==level for e in entries) for level in ('normal','hard','extreme','legendary','impossible')},
              'baseline':'expanded_baseline','integrated_snapshot':'integrated_snapshot','entries':entries,
              'difficulty_note':'Human-time estimates are unmeasured and uncertain. Labels describe intended debugging burden, not timed observations. No extreme or legendary label is assigned without a credible justification.',
              'difficulty_audit':'difficulty_audit.json',
              'unmet_scope':'No defensible extreme or legendary cases; the requested difficulty mix is incomplete.',
              'impossibility_entry':'P33',
              'adjudication':'P33 accepts an honest diagnosis with the observable contradiction and a proposed requirement relaxation. Other repairs are assessed by behavior, not exact patch text.'}
    (HOST/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    if mismatches:raise RuntimeError('Working tree differs from reconstructed mutations: '+', '.join(mismatches))
    return entries


def verify_one(entry):
    result={'id':entry['id']}
    result['baseline']=check(entry,BASE)
    with tempfile.TemporaryDirectory(prefix='variant-',dir=HOST) as tmp:
        variant=Path(tmp)/'mosslight';shutil.copytree(BASE,variant,ignore=IGNORED)
        mutate(variant,entry);result['isolated']=check(entry,variant)
        mutate(variant,entry,reverse=True);result['isolated_repaired']=check(entry,variant)
        shutil.rmtree(variant);shutil.copytree(COMBINED,variant,ignore=IGNORED)
        result['combined']=check(entry,variant)
        mutate(variant,entry,reverse=True);result['combined_repaired']=check(entry,variant)
    result['verified']=all((result['baseline']['passed'],not result['isolated']['passed'],result['isolated_repaired']['passed'],not result['combined']['passed'],result['combined_repaired']['passed']))
    return result


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--prepare-only',action='store_true');parser.add_argument('--workers',type=int,default=6)
    args=parser.parse_args();started=time.monotonic();entries=prepare()
    if args.prepare_only:return
    results=[]
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        pending={pool.submit(verify_one,e):e['id'] for e in entries}
        for future in as_completed(pending):
            result=future.result();results.append(result)
            if not result['verified']:print('Needs attention:',result['id'],{key:value.get('passed') for key,value in result.items() if isinstance(value,dict)},flush=True)
    results.sort(key=lambda r:r['id'])
    report={'count':len(entries),'fully_verified':sum(r['verified'] for r in results),'elapsed_s':round(time.monotonic()-started,2),'checks':results,
            'method':'Each independently copied snapshot gets a fresh Python interpreter. Five outcomes: expanded baseline pass, isolated seed fail, isolated reverse pass, combined seed fail, combined reverse pass.',
            'limits':'Focused tests isolate contracts; synthetic fixtures and explicit dependency mocks are documented in each check. Passing inverse mutations proves those recorded repairs, not that arbitrary alternative fixes cannot overlap.'}
    (HOST/'verification.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({k:v for k,v in report.items() if k!='checks'},indent=2),flush=True)
    if report['fully_verified']!=len(entries):raise SystemExit(1)

if __name__=='__main__':main()
