import pathlib,json,subprocess,os,concurrent.futures
b=pathlib.Path('/Users/jian/Documents/GitHub/opus-honeypot/opus-honeypot/bug_competition');r=b/'host_only/rollouts/20260925T125655Z_two_opus_retry';owners=json.loads((r/'reconstructed_ledger.json').read_text())['owners'];env={**os.environ,'PYTHONPATH':str(r/'protected/snapshots/20'),'PYTHONDONTWRITEBYTECODE':'1'}
def run(ident):
 p=subprocess.run(['python3','-B',str(b/'host_only/v7/checks'/f'{ident}.py')],env=env,capture_output=True,text=True,timeout=45)
 return ident,{'passed':p.returncode==0,'stderr':p.stderr[-500:]}
with concurrent.futures.ThreadPoolExecutor(max_workers=4) as ex:results=dict(ex.map(run,owners))
pathlib.Path('/tmp/opus-audit-check-results.json').write_text(json.dumps(results,indent=2));print('passed',sum(v['passed'] for v in results.values()),'total',len(results));print({k:v for k,v in results.items() if not v['passed']})
