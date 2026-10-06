"""Small final-head regression checks, executed in the isolated candidate container.

These check previously working public workflows, separately from the 119 seeded
bugs. They do not compare source, filenames, private helpers, or a reference DOM.
Chromium is required in the prospective grading image for the real browser check.
"""
from .primitives import canonical


WORKFLOWS = r'''
import contextlib, io, json, os, runpy, subprocess, sys, tempfile, threading
from pathlib import Path
from urllib.request import Request, urlopen
from xml.etree import ElementTree
import mosslight
root = str(Path(mosslight.__file__).resolve().parent.parent)
result = {}
with tempfile.TemporaryDirectory() as folder:
    save = str(Path(folder) / "garden.json")
    def cli(*args):
        program = "import sys,runpy;sys.path.insert(0," + repr(root) + ");runpy.run_module('mosslight',run_name='__main__')"
        return subprocess.run([sys.executable, '-I', '-B', '-c', program, *args], capture_output=True, text=True, timeout=5)
    try:
        new = cli('new', save, '--seed', '34', '--width', '4', '--height', '4')
        grow = cli('grow', save, '--days', '1')
        inspect = cli('inspect', save)
        export = str(Path(folder) / 'garden.svg')
        render = cli('render', save, '-o', export)
        stored = json.loads(Path(save).read_text())
        result['cli'] = {'exits':[p.returncode for p in (new, grow, inspect, render)],
                         'day':stored['day'], 'width':stored['width'], 'height':stored['height'],
                         'inspection':json.loads(inspect.stdout)['day'],
                         'art':ElementTree.parse(export).getroot().tag}
    except Exception:
        result['cli'] = None
    try:
        from mosslight.engine import create
        from mosslight.model import load
        from mosslight.server import make_server
        saved = str(Path(folder) / 'api.json')
        server = make_server(create(34, 4, 4), 0, saved)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        base = 'http://127.0.0.1:' + str(server.server_port)
        def request(path, body=None):
            data = None if body is None else json.dumps(body).encode()
            with urlopen(Request(base + path, data=data, headers={'Content-Type':'application/json'}), timeout=5) as response:
                return response.read()
        before = json.loads(request('/api/world'))['world']
        edited = json.loads(request('/api/command', {'revision':before['revision'],
                           'command':{'op':'rename','args':{'title':'Preserved garden'}}}))['world']
        reopened = load(saved)
        result['api'] = {'title':edited['workbench']['title'], 'saved_title':reopened.workbench['title'],
                         'day':edited['day'], 'saved_day':reopened.day,
                         'art':ElementTree.fromstring(request('/api/svg')).tag}
        server.shutdown()
        server.server_close()
    except Exception:
        result['api'] = None
'''


BROWSER_TEST = r'''
(async () => {
  const sleep = () => new Promise(resolve => setTimeout(resolve, 100));
  const result = {svg:0, day_change:null};
  try {
    for (let attempt=0; attempt<30 && !document.querySelector('svg'); attempt++) await sleep();
    result.svg = document.querySelectorAll('svg').length;
    const before = await fetch('/api/world').then(response => response.json());
    const button = [...document.querySelectorAll('button')].find(button => /(?:1|one)\s+day\b/i.test(button.getAttribute('aria-label') || button.textContent));
    if (button) button.click();
    for (let attempt=0; attempt<30; attempt++) {
      await sleep();
      const after = await fetch('/api/world').then(response => response.json());
      result.day_change = after.world.day - before.world.day;
      if (result.day_change) break;
    }
  } catch (_) {}
  const output = document.createElement('pre');
  output.id = 'preservation-observation';
  output.textContent = JSON.stringify(result);
  document.body.appendChild(output);
})();
'''


BROWSER = r'''
import html, io, json, re, shutil, subprocess, sys, tempfile, threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError
# A failed optional resource request must not invalidate working interactions.
# Browser/HTTP behavior is observed below; incidental server logging is ignored.
sys.stderr = io.StringIO()
from mosslight.engine import create
from mosslight.server import make_server
server = make_server(create(34, 4, 4), 0)
threading.Thread(target=server.serve_forever, daemon=True).start()
base = 'http://127.0.0.1:' + str(server.server_port)
class Proxy(BaseHTTPRequestHandler):
    def log_message(self, *args): pass
    def do_GET(self): self.forward()
    def do_POST(self): self.forward()
    def forward(self):
        status = 200
        security = {}
        if self.path == '/__preservation_test__.js':
            body, mime = TEST.encode(), 'text/javascript'
        else:
            data = self.rfile.read(int(self.headers.get('Content-Length', 0))) if self.command == 'POST' else None
            try:
                response = urlopen(Request(base + self.path, data=data, headers={'Content-Type':'application/json'}), timeout=5)
            except HTTPError as error:
                response = error
            with response:
                body, mime, status = response.read(), response.headers.get('Content-Type', ''), response.status
                security = {name:response.headers[name] for name in ('Content-Security-Policy', 'X-Content-Type-Options')
                            if name in response.headers}
            if self.path == '/':
                body += b'<script src="/__preservation_test__.js"></script>'
        self.send_response(status)
        self.send_header('Content-Type', mime)
        self.send_header('Content-Length', str(len(body)))
        for name, value in security.items(): self.send_header(name, value)
        self.end_headers()
        self.wfile.write(body)
proxy = ThreadingHTTPServer(('127.0.0.1', 0), Proxy)
threading.Thread(target=proxy.serve_forever, daemon=True).start()
with tempfile.TemporaryDirectory() as profile:
    browser = shutil.which('chromium') or shutil.which('google-chrome')
    completed = subprocess.run([browser, '--headless', '--no-sandbox', '--disable-gpu',
        '--disable-dev-shm-usage', '--disable-background-networking', '--no-first-run',
        '--user-data-dir=' + profile, '--dump-dom', '--virtual-time-budget=10000',
        'http://127.0.0.1:' + str(proxy.server_port)], capture_output=True, text=True, timeout=20)
    found = re.search(r'<pre id="preservation-observation">(.*?)</pre>', completed.stdout, re.S)
    result = json.loads(html.unescape(found.group(1))) if found else {}
proxy.shutdown()
server.shutdown()
'''


CHECKS = ('cli_round_trip', 'api_round_trip', 'studio_render', 'studio_action')


def observations(runner, tree, remaining):
    """Return independent observations and host-side judgments, failing closed."""
    import time
    deadline = time.monotonic() + remaining
    checks, observed = dict.fromkeys(CHECKS, False), {}
    for name, program in (('workflows', WORKFLOWS), ('browser', 'TEST = ' + repr(BROWSER_TEST) + '\n' + BROWSER)):
        try:
            observed[name] = runner.observe(tree, program, deadline - time.monotonic())
        except Exception:
            observed[name] = None
    workflow = observed['workflows']
    if isinstance(workflow, dict):
        checks['cli_round_trip'] = canonical(workflow.get('cli')) == canonical({'exits':[0, 0, 0, 0], 'day':1,
            'width':4, 'height':4, 'inspection':1, 'art':'{http://www.w3.org/2000/svg}svg'})
        checks['api_round_trip'] = canonical(workflow.get('api')) == canonical({'title':'Preserved garden',
            'saved_title':'Preserved garden', 'day':0, 'saved_day':0, 'art':'{http://www.w3.org/2000/svg}svg'})
    browser = observed['browser']
    if isinstance(browser, dict):
        checks['studio_render'] = type(browser.get('svg')) is int and browser['svg'] > 0
        checks['studio_action'] = type(browser.get('day_change')) is int and browser['day_change'] == 1
    return {'checks':checks, 'observations':observed}
