from pathlib import Path
import shutil,json,subprocess,os
b=Path('/Users/jian/Documents/GitHub/opus-honeypot/opus-honeypot/bug_competition');r=b/'host_only/rollouts/20260925T125655Z_two_opus_retry';target=Path('/tmp/opus-repair-audit-normalized');target.mkdir(exist_ok=True)
shutil.copytree(r/'protected/snapshots/20/mosslight',target/'mosslight',dirs_exist_ok=True)
manifest=json.loads((b/'host_only/v7/manifest.json').read_text())['entries'];owners=json.loads((r/'reconstructed_ledger.json').read_text())['owners']
for e in manifest:
 if e['id'] in owners:continue
 path=target/e['file'];text=path.read_text()
 if e['new'] in text:path.write_text(text.replace(e['new'],e['old'],1))
 else:print('uncredited mutation modified:',e['id'])
env={**os.environ,'PYTHONPATH':str(target),'PYTHONDONTWRITEBYTECODE':'1'}
script='''import unittest,json,sys
s=unittest.defaultTestLoader.discover(sys.argv[1])
def flatten(s):
 for t in s:
  if isinstance(t,unittest.TestSuite):yield from flatten(t)
  else:yield t
s=unittest.TestSuite(t for t in flatten(s) if not t.id().startswith('test_api.') and 'test_http_lifecycle' not in t.id())
r=unittest.TextTestRunner(verbosity=1).run(s)
print(json.dumps({'run':r.testsRun,'failures':[t.id() for t,_ in r.failures],'errors':[t.id() for t,_ in r.errors]}))
'''
p=subprocess.run(['python3','-B','-c',script,str(b/'host_only/v7/clean_baseline/tests')],env=env,capture_output=True,text=True,timeout=150)
Path('/tmp/opus-audit-normalized-tests.log').write_text(p.stdout+p.stderr);print(p.stdout,p.stderr[-3500:])
