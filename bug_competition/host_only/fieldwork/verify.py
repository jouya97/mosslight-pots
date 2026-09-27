import json, pathlib, shutil, subprocess, sys, tempfile
work=pathlib.Path('/Users/jian/Documents/GitHub/opus-honeypot/opus-honeypot/bug_competition/mosslight')
clean=pathlib.Path('/Users/jian/Documents/GitHub/opus-honeypot/opus-honeypot/bug_competition/archives/mosslight-clean-2026-09-24')
manifest=work.parent/'host_only'/'fieldwork'/'mutations.json'
entries=json.loads(manifest.read_text())
# Reset only owned files from the immutable archive before a reproducible run.
for e in entries:
    rel=pathlib.Path(e['file'])
    shutil.copy2(clean/rel,work/rel)
results=[]
def run(root, code):
    return subprocess.run([sys.executable,'-c',code],cwd=root,text=True,capture_output=True)
with tempfile.TemporaryDirectory(prefix='mosslight-fieldwork-') as td:
    base=pathlib.Path(td)/'base'; shutil.copytree(clean,base)
    for e in entries:
        path=base/e['file']
        source=path.read_text()
        if source.count(e['old'])!=1:
            results.append({'id':e['id'],'status':'baseline-replacement-count-failed','count':source.count(e['old'])}); continue
        clean_check=run(base,e['check'])
        if clean_check.returncode:
            results.append({'id':e['id'],'status':'clean-check-failed','stderr':clean_check.stderr[-1200:]}); continue
        mutant=pathlib.Path(td)/e['id']; shutil.copytree(clean,mutant)
        mpath=mutant/e['file']; original=mpath.read_text(); mpath.write_text(original.replace(e['old'],e['new'],1))
        bug_check=run(mutant,e['check'])
        if bug_check.returncode==0:
            results.append({'id':e['id'],'status':'mutation-not-detected'})
        else:
            # The clean baseline passed immediately before applying this isolated mutation.
            results.append({'id':e['id'],'status':'pass','bug_stderr':bug_check.stderr[-300:]})
# Apply all source replacements to the working tree, after isolated checks.
for e in entries:
    p=work/e['file']; s=p.read_text()
    if s.count(e['old'])!=1: raise RuntimeError(f"working replacement count for {e['id']}: {s.count(e['old'])}")
    p.write_text(s.replace(e['old'],e['new'],1))
combined=[]
for e in entries:
    r=run(work,e['check'])
    combined.append({'id':e['id'],'status':'detected' if r.returncode else 'masked','stderr':r.stderr[-400:]})
report={'entries':len(entries),'isolated':results,'combined':combined,
        'isolated_passed':sum(x['status']=='pass' for x in results),
        'combined_detected':sum(x['status']=='detected' for x in combined)}
(work.parent/'host_only'/'fieldwork'/'verification.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps({k:v for k,v in report.items() if k not in ('isolated','combined')},indent=2))
for x in results:
    if x['status']!='pass': print('ISOLATED ISSUE',json.dumps(x))
for x in combined:
    if x['status']!='detected': print('COMBINED ISSUE',json.dumps(x))
