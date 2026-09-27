import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
import uuid

root = Path(__file__).resolve().parent
if '--worker' in sys.argv:
    from inspect_ai import eval
    from bug_competition.harness.credentials import load_host_credentials
    from bug_competition.adapters.inspect.inspect_task import mosslight, competition_solver
    load_host_credentials(Path('.env'))
    assert os.environ.get('ANTHROPIC_API_KEY'), 'Missing Anthropic credential'
    task = mosslight(seconds=600, grading_seconds=240, participants=2)
    task.solver = competition_solver(seconds=600, output_root=os.environ['MOSSLIGHT_STAGE_ROOT'], participants=2)
    logs = eval(task, model='anthropic/claude-opus-5-5', log_dir=str(root / 'inspect'), epochs=1, retry_on_error=0, max_retries=0, display='plain')
    for log in logs:
        (root / 'summary.json').write_text(json.dumps({'status':log.status, 'stats':log.stats.model_dump(mode='json'), 'results':log.results.model_dump(mode='json') if log.results else None, 'error':log.error.model_dump(mode='json') if log.error else None, 'evidence':[s.metadata.get('competition_evidence') for s in log.samples or []]}, indent=2))
    print('ROLLOUT_FINISHED', logs[0].status, flush=True)
else:
    started = time.monotonic()
    label = 'mosslight-' + uuid.uuid4().hex
    stage = tempfile.mkdtemp(prefix='mosslight-session-')
    (root / 'invocation.json').write_text(json.dumps({'model':'anthropic/claude-opus-5-5', 'participants':2, 'seconds':600, 'grading_seconds':240, 'hard_cap_seconds':900, 'worker_kill_seconds':870, 'started_unix':time.time(), 'run_label':label, 'staging_parent':stage}, indent=2))
    env = {**os.environ, 'MOSSLIGHT_RUN_ID':label, 'MOSSLIGHT_STAGE_ROOT':stage}
    child = subprocess.Popen([sys.executable, '-u', str(Path(__file__).resolve()), '--worker'], env=env, start_new_session=True)
    hard_timeout = False
    try:
        child.wait(timeout=max(.1, 870-(time.monotonic()-started)))
    except subprocess.TimeoutExpired:
        hard_timeout = True
        os.killpg(child.pid, signal.SIGKILL)
        child.wait(timeout=2)
    cleanup = {'complete':False}
    try:
        ids = subprocess.run(['docker','ps','-aq','--filter','label=mosslight.run='+label], capture_output=True, text=True, timeout=5, check=True).stdout.split()
        if ids:
            subprocess.run(['docker','rm','-f',*ids], capture_output=True, text=True, timeout=15, check=True)
        cleanup = {'complete':True, 'containers_removed':len(ids)}
    except Exception as exc:
        cleanup = {'complete':False, 'error_type':type(exc).__name__, 'run_label':label}
    (root / 'supervisor.json').write_text(json.dumps({'hard_timeout':hard_timeout, 'worker_returncode':child.returncode, 'elapsed_seconds':time.monotonic()-started, 'cleanup':cleanup}, indent=2))
    print('SUPERVISOR_FINISHED', child.returncode, 'timeout', hard_timeout, flush=True)
