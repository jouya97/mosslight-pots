from pathlib import Path
import subprocess,os,json
b=Path('/Users/jian/Documents/GitHub/opus-honeypot/opus-honeypot/bug_competition'); r=b/'host_only/rollouts/20260925T125655Z_two_opus_retry'
script='''import sys,unittest,json
suite=unittest.defaultTestLoader.discover(sys.argv[1])
def flatten(s):
 for t in s:
  if isinstance(t,unittest.TestSuite): yield from flatten(t)
  else: yield t
suite=unittest.TestSuite(t for t in flatten(suite) if not t.id().startswith('test_api.'))
r=unittest.TextTestRunner(verbosity=1).run(suite)
print(json.dumps({'run':r.testsRun,'failures':[t.id() for t,_ in r.failures],'errors':[t.id() for t,_ in r.errors]}))
'''
for name,tree in [('clean',b/'host_only/v7/clean_baseline'),('final',r/'protected/snapshots/20')]:
 env={**os.environ,'PYTHONPATH':str(tree),'PYTHONDONTWRITEBYTECODE':'1'}
 p=subprocess.run(['python3','-B','-c',script,str(b/'host_only/v7/clean_baseline/tests')],capture_output=True,text=True,env=env,timeout=150)
 Path('/tmp/opus-audit-'+name+'-tests.log').write_text(p.stdout+p.stderr);print(name,p.returncode,p.stdout[-3500:],p.stderr[-500:])
