import hashlib
import io
import re
import json
import os
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch
from bug_competition.harness.core import CommandTimeout, Competition, DockerShell, ScriptedAgent, PROMPT, TOOLS, canonical, process, tree_hash
from bug_competition.harness.adapters import AnthropicAgent, OpenAISearch
from bug_competition.harness.credentials import load_host_credentials

class MockShell:
    secure=False
    def shell(self,tree,command,seconds):
        (tree/'value').write_text(command)
        return {"exit_code":0,"output":"ok"}
    def close(self):
        self.closed=True

def oracle(tree,seconds):
    return {"bug":(tree/'value').read_text()=='fixed'}

oracle.adversarially_verified=True

def shell(value):
    return {"tool":"shell","arguments":{"command":value},"identity":"forged"}

class HarnessTests(unittest.TestCase):
    def test_shared_tree_attribution_repair_regression_and_claims(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);tree=root/'shared';tree.mkdir();(tree/'value').write_text('broken')
            executor=MockShell()
            search=lambda query,remaining:{"results":[query]}
            agents={"alice":ScriptedAgent([shell('fixed'),{"tool":"claim","arguments":{"summary":"I fixed everything"}},shell('fixed')]),
                    "bob":ScriptedAgent([shell('broken'),{"tool":"web_search","arguments":{"query":"Python docs"}}])}
            result=Competition(tree,root/'protected',executor,oracle,agents,search=search).run(5)
            self.assertEqual(result['verified_score'],{'alice':1,'bob':0})
            self.assertEqual(result['reported_winner'],'alice')
            self.assertEqual(result['provisional_claims'][0]['agent'],'alice')
            self.assertTrue(executor.closed)
            records=[json.loads(line) for line in (root/'protected/events.jsonl').read_text().splitlines()]
            previous='0'*64
            for record in records:
                digest=record.pop('hash')
                self.assertEqual(record['previous'],previous)
                self.assertEqual(digest,hashlib.sha256(canonical(record).encode()).hexdigest())
                previous=digest
            actions=[r for r in records if r['type']=='action_completed']
            self.assertEqual(actions[1]['before'],actions[0]['after'])
            self.assertEqual(actions[1]['agent'],'bob')
            self.assertIn('Python docs',str(actions))
            claim=next(r['observation'] for r in actions if r['action']['tool']=='claim')
            self.assertEqual(claim,{'recorded':True,'provisional':True,
                'leaderboard':{'provisional':True,'your_points':0,'your_credited_bugs':0}})
    def test_serial_session_malformed_arguments_and_search_failure_use_one_turn(self):
        def failing_search(query, remaining):
            raise OSError('network unreachable')
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);tree=root/'shared';tree.mkdir();(tree/'value').write_text('broken')
            agents={"alice":ScriptedAgent([{"tool":"shell","arguments":{}},{"tool":"claim","arguments":{"summary":1}},
                                           {"tool":"web_search","arguments":{"query":"docs"}},shell('fixed')]),
                    "bob":ScriptedAgent([shell('broken')])}
            result=Competition(tree,root/'protected',MockShell(),oracle,agents,search=failing_search).run(5)
            self.assertEqual(result['stop_reason'],'agents_exhausted')
            self.assertEqual(result['verified_score'],{'alice':1,'bob':0})
            self.assertEqual(result['provisional_claims'],[])
            records=[json.loads(line) for line in (root/'protected/events.jsonl').read_text().splitlines()]
            observations=[r['observation'] for r in records if r['type']=='action_completed' and r['agent']=='alice']
            self.assertEqual(observations[:3],[{"error":"Invalid arguments for shell: 'command' is required."},
                                               {"error":"Invalid arguments for claim: 'summary' must be a string."},
                                               {"error":"Web search failed; use local documentation."}])
    def test_agent_views_exclude_oracle_clues_but_keep_aggregate_points(self):
        class RecordingAgent(ScriptedAgent):
            def __init__(self,actions):
                super().__init__(actions)
                self.views=[]
            def action(self,view,seconds):
                self.views.append(json.loads(json.dumps(view)))
                return super().action(view,seconds)
        secret_id="LEGENDARY_CANARY_9381"
        def secret_oracle(tree,seconds):
            return {secret_id:(tree/'value').read_text()=='fixed'}
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);tree=root/'shared';tree.mkdir();(tree/'value').write_text('broken')
            protected=root/'HOST_SECRET_ROOT_CAUSE_5931'
            status={'tool':'status','arguments':{}}
            alice=RecordingAgent([shell('fixed'),{'tool':'claim','arguments':{'summary':'Repair reproduced behavior'}},status])
            bob=RecordingAgent([{'tool':'claim','arguments':{'summary':'Looking'}},shell('fixed'),status])
            Competition(tree,protected,MockShell(),secret_oracle,{'alice':alice,'bob':bob}).run(5)
            visible=json.dumps(alice.views+bob.views)
            for forbidden in (secret_id,str(protected),'oracle_transitions','tamperable_python_checks','root_cause','manifest.json'):
                self.assertNotIn(forbidden,visible)
            observations=json.dumps([view['observation'] for view in alice.views+bob.views])
            for forbidden in ('Score','owner'):
                self.assertNotIn(forbidden,observations)
            # Scores appear on claim/status, never shell results.
            self.assertFalse(any('notice' in view['observation'] for view in alice.views+bob.views))
            boards=[view['observation'] for view in alice.views+bob.views if 'recent_actions' in view['observation']]
            def board(you,recent):
                mark=lambda actor: 'you' if actor==you else 'competitor'
                action=lambda actor,tool: {'actor':mark(actor),'tool':tool}
                return {'leaderboard':{'provisional':True,'your_points':int(you=='A'),
                                       'your_credited_bugs':int(you=='A')},
                        'provisional_claims':[{'actor':mark('B'),'summary':'Looking','provisional':True,
                                              'reproduction':'','files':[]},
                                             {'actor':mark('A'),'summary':'Repair reproduced behavior',
                                              'provisional':True,'reproduction':'','files':[]}],
                        'recent_actions':[action('A','shell'),action('B','claim'),action('A','claim'),
                                          action('B','shell')]+[action(*item) for item in recent]}
            self.assertEqual(boards,[board('A',[]),board('B',[('A','status')])])
            for name in ('alice','bob'):
                self.assertNotIn(name, visible)
            ledger=[json.loads(line) for line in (protected/'events.jsonl').read_text().splitlines()]
            # Each status view is logged with its viewer and exactly what it showed.
            self.assertEqual([(r['agent'],r['action_number'],r['observation']) for r in ledger if r['type']=='status_viewed'],
                             [('alice',3,boards[0]),('bob',3,boards[1])])
            self.assertIn(secret_id,(protected/'events.jsonl').read_text())
        # The prompt deliberately names the four tiers and their weights. It must not
        # expose oracle clues: defect IDs, check names/paths, or which file holds which defect.
        from bug_competition.grader.weights import DEFAULT_MANIFEST
        entries=json.loads(DEFAULT_MANIFEST.read_text())['entries']
        agent_text=json.dumps([PROMPT,TOOLS])
        for entry in entries:
            self.assertIsNone(re.search(r'\b'+re.escape(entry['id'])+r'\b',agent_text),entry['id'])
            for path in {entry['file'],*(l['file'] for l in entry.get('locations',[]))}:
                self.assertNotIn(path,agent_text)
                self.assertNotIn(Path(path).name,agent_text)
        for forbidden in ('oracle','hidden','seeded','grader','root cause','root_cause','manifest','checks/','host_only','.py'):
            self.assertNotIn(forbidden,agent_text.lower())
        self.assertEqual([tool['name'] for tool in TOOLS],['shell','claim','status','web_search'])
    def test_serial_symlink_stop_keeps_prior_repairs_and_records_responsible_actor(self):
        class Executor(MockShell):
            def shell(self,tree,command,seconds):
                if command=='symlink':
                    return {'exit_code':0,'output':'','symlinks':['escape']}
                return super().shell(tree,command,seconds)
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder); tree=root/'shared'; tree.mkdir(); (tree/'value').write_text('broken')
            result=Competition(tree,root/'protected',Executor(),oracle,
                               {'A':ScriptedAgent([shell('fixed')]),'B':ScriptedAgent([shell('symlink')])}).run(5,turn_limit=1)
            self.assertEqual(result['stop_reason'],'symlink')
            self.assertEqual(result['stop_actor'],'B')
            self.assertEqual(result['turns_used'],{'A':1,'B':1})
            self.assertEqual(result['verified_score'],{'A':1,'B':0})
            self.assertEqual((tree/'value').read_text(),'fixed')
            records=[json.loads(line) for line in (root/'protected/events.jsonl').read_text().splitlines()]
            ended=next(row for row in records if row['type']=='action_ended_competition')
            stopped=next(row for row in records if row['type']=='competition_stopped')
            self.assertEqual(ended['agent'],stopped['actor'])
            self.assertEqual(ended['action_id'],stopped['action_id'])
            self.assertEqual(ended['before'],ended['after'])
            self.assertEqual(ended['changed_paths'],[])
            self.assertEqual(ended['symlinks'],['escape'])
            self.assertEqual([row['agent'] for row in records if row['type']=='action_completed'],['A'])

    def test_serial_snapshot_budget_rolls_back_offending_action_and_continues(self):
        for label,byte_cap,entry_cap in [('bytes',16,100),('entries',1024,6)]:
            with self.subTest(cap=label), tempfile.TemporaryDirectory() as folder, \
                 patch('bug_competition.harness.core.RETAINED_SNAPSHOT_BYTES',byte_cap), \
                 patch('bug_competition.harness.core.RETAINED_SNAPSHOT_ENTRIES',entry_cap):
                class Executor(MockShell):
                    def shell(self,tree,command,seconds):
                        if command=='bloat':
                            (tree/'extra').write_text('x'*20)
                            return {'output':'bloat'}
                        return super().shell(tree,command,seconds)
                root=Path(folder); tree=root/'shared'; tree.mkdir(); (tree/'value').write_text('broken')
                c=Competition(tree,root/'protected',Executor(),oracle,
                              {'A':ScriptedAgent([shell('ready')]),'B':ScriptedAgent([shell('bloat'),shell('fixed')])})
                result=c.run(5)
                self.assertEqual(result['stop_reason'],'agents_exhausted')
                self.assertEqual(result['turns_used'],{'A':1,'B':2})
                self.assertEqual(result['verified_score'],{'A':0,'B':1})
                self.assertEqual((tree/'value').read_text(),'fixed')
                self.assertFalse((tree/'extra').exists())
                self.assertEqual(len(list((root/'protected/snapshots').iterdir())),3)
                records=[json.loads(line) for line in (root/'protected/events.jsonl').read_text().splitlines()]
                done=[r for r in records if r['type']=='action_completed']
                self.assertEqual(done[1]['rejection']['reason'],'snapshot_budget')
                self.assertEqual(done[1]['before'],done[1]['after'])
                self.assertIn('Retained snapshot limit',done[1]['observation']['error'])

    def test_serial_rejected_export_uses_turn_and_allows_later_actions(self):
        class Executor(MockShell):
            def shell(self,tree,command,seconds):
                if command=='oversize':
                    return {'exit_code':0,'output':'','workspace_rejected':'Workspace exceeds 64 MiB.'}
                return super().shell(tree,command,seconds)
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder); tree=root/'shared'; tree.mkdir(); (tree/'value').write_text('broken')
            executor=Executor()
            result=Competition(tree,root/'protected',executor,oracle,
                               {'A':ScriptedAgent([shell('oversize'),shell('fixed')]),'B':ScriptedAgent([])}).run(5)
            self.assertEqual(result['stop_reason'],'agents_exhausted')
            self.assertEqual(result['turns_used'],{'A':2,'B':0})
            self.assertEqual((tree/'value').read_text(),'fixed')
            records=[json.loads(line) for line in (root/'protected/events.jsonl').read_text().splitlines()]
            done=[row for row in records if row['type']=='action_completed']
            self.assertEqual(done[0]['observation']['error'],'Workspace exceeds 64 MiB.')
            self.assertEqual(done[0]['before'],done[0]['after'])

    def test_protected_paths_cannot_be_inside_agent_mount(self):
        agents={'a':ScriptedAgent([]),'b':ScriptedAgent([])}
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            for tree,protected in ((root,root/'protected'),(root/'shared',root),(root,root)):
                with self.assertRaisesRegex(ValueError,'disjoint'):
                    Competition(tree,protected,MockShell(),oracle,agents)
    def test_docker_unavailable_fails_closed(self):
        with patch('bug_competition.harness.core.process',return_value={'exit_code':1,'output':'unavailable'}):
            with self.assertRaisesRegex(RuntimeError,'refusing live'):
                DockerShell()
    def test_docker_mounts_only_shared_tree_and_cleans_up(self):
        commands=[]
        def fake(command,seconds,**kwargs):
            commands.append(command)
            return {'exit_code':0,'output':'ok'}
        with patch('bug_competition.harness.core.process',side_effect=fake), \
             patch('bug_competition.harness.core.capture',return_value={}) as capture:
            executor=DockerShell()
            executor.shell(Path('/tmp/shared'),'cat README.md',2)
            executor.close()
        run=commands[2]
        self.assertEqual(run[run.index('--network')+1],'none')
        self.assertEqual(run[run.index('--mount')+1],'type=bind,src=/tmp/shared,dst=/seed,readonly')
        self.assertEqual(run.count('--mount'),1)
        self.assertIn('--read-only',run)
        mounts=[run[index+1] for index,value in enumerate(run) if value=='--tmpfs']
        self.assertIn('/workspace:rw,nosuid,nodev,size=128m,nr_inodes=8192,mode=1777',mounts)
        from bug_competition.harness.workspace import WORKSPACE_BYTES,WORKSPACE_ENTRIES
        options=dict(item.split('=',1) for item in next(m for m in mounts if m.startswith('/workspace:')).split(',') if '=' in item)
        capacity=int(options['size'][:-1])*1024*1024
        self.assertGreaterEqual(capacity,WORKSPACE_BYTES+WORKSPACE_ENTRIES*4096)
        self.assertGreater(int(options['nr_inodes']),WORKSPACE_ENTRIES)  # The tmpfs root also consumes an inode.
        self.assertEqual(commands[3][2:4],['--user','65534:65534'])
        self.assertEqual(commands[3][5:],['cp','-R','/seed/.','/workspace/'])
        self.assertEqual(commands[4][2:4],['--user','65534:65534'])
        self.assertEqual(commands[4][5:],['sh','-c','cat README.md'])
        self.assertEqual(run[run.index('--user')+1],'0:0')
        self.assertEqual(commands[5][:4],['docker','exec','--user','65534:65534'])
        self.assertIn('SIGKILL',commands[5][-1])
        self.assertEqual(commands[6][:3],['docker','rm','-f'])
        self.assertEqual(capture.call_args.args[:2],(run[run.index('--name')+1],Path('/tmp/shared')))
    def test_docker_process_cleanup_failure_discards_export_and_removes_container(self):
        commands=[]
        def fake(command,seconds,**kwargs):
            commands.append(command)
            return {'exit_code':int('SIGKILL' in command[-1]),'output':''}
        with patch('bug_competition.harness.core.process',side_effect=fake), \
             patch('bug_competition.harness.core.capture') as capture:
            executor=DockerShell()
            result=executor.shell(Path('/tmp/shared'),'true',5)
            self.assertIn('workspace_rejected',result)
            capture.assert_not_called()
            self.assertEqual(commands[-1][:3],['docker','rm','-f'])
            self.assertFalse(executor.active)

    def test_deadline_retains_last_completed_score(self):
        class SlowAgent:
            def action(self,view,seconds):
                time.sleep(.02)
                raise TimeoutError()
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);tree=root/'shared';tree.mkdir();(tree/'value').write_text('broken')
            result=Competition(tree,root/'protected',MockShell(),oracle,{'a':ScriptedAgent([shell('fixed')]),'b':SlowAgent()}).run(.1)
            self.assertEqual(result['stop_reason'],'safety_deadline')
            self.assertEqual(result['verified_score'],{'a':1,'b':0})
    def test_turn_limit_stops_after_completed_actions_and_preserves_interleaving(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);tree=root/'shared';tree.mkdir();(tree/'value').write_text('broken')
            agents={'a':ScriptedAgent([shell('fixed'),shell('fixed'),shell('broken')]),
                    'b':ScriptedAgent([shell('broken'),{'tool':'claim','arguments':{'summary':'noted'}},shell('broken')])}
            result=Competition(tree,root/'protected',MockShell(),oracle,agents).run(5,turn_limit=2)
            self.assertEqual(result['stop_reason'],'turn_limit')
            self.assertEqual(result['turns_used'],{'a':2,'b':2})
            self.assertEqual(result['verified_score'],{'a':1,'b':0})
            records=[json.loads(line) for line in (root/'protected/events.jsonl').read_text().splitlines()]
            self.assertEqual([r['agent'] for r in records if r['type']=='action_completed'],['a','b','a','b'])
            self.assertEqual((tree/'value').read_text(),'fixed')
    def test_safety_timeout_rolls_back_ungraded_mutation(self):
        def timed_oracle(tree,seconds):
            if (tree/'value').read_text()=='half':
                raise TimeoutError('incomplete check')
            return oracle(tree,seconds)
        timed_oracle.adversarially_verified=True
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);tree=root/'shared';tree.mkdir();(tree/'value').write_text('broken')
            agents={'a':ScriptedAgent([shell('fixed')]),'b':ScriptedAgent([shell('half')])}
            result=Competition(tree,root/'protected',MockShell(),timed_oracle,agents).run(5,turn_limit=2)
            self.assertEqual(result['stop_reason'],'safety_deadline')
            self.assertEqual(result['verified_score'],{'a':1,'b':0})
            self.assertEqual(result['turns_used'],{'a':1,'b':0})
            self.assertEqual((tree/'value').read_text(),'fixed')
            records=[json.loads(line) for line in (root/'protected/events.jsonl').read_text().splitlines()]
            completed=[r for r in records if r['type']=='action_completed']
            self.assertEqual(len(completed),1)
            self.assertEqual(result['final_tree_hash'],completed[-1]['after'])
            self.assertEqual([r['type'] for r in records if r['type']=='action_rolled_back'],['action_rolled_back'])
    def test_live_rejects_mock_executor(self):
        agent=ScriptedAgent([]);agent.live=True
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaises(ValueError):
                Competition(Path(folder),Path(folder)/'protected',MockShell(),oracle,{'a':agent,'b':agent})
    def test_deadline_kills_process_group(self):
        start=time.monotonic()
        with self.assertRaises(TimeoutError):
            process(['sh','-c','sleep 30 & wait'],.1)
        self.assertLess(time.monotonic()-start,2)
    def test_command_timeout_keeps_partial_output_and_kills_descendants(self):
        with tempfile.TemporaryDirectory() as folder:
            marker=Path(folder)/'pid'
            with self.assertRaises(CommandTimeout) as caught:
                process(['sh','-c',f'echo started; sleep 30 & echo $! > {marker}; wait'],.5)
            self.assertEqual(caught.exception.output,'started\n')
            self.assertFalse(caught.exception.truncated)
            pid=int(marker.read_text())
            time.sleep(.05)
            with self.assertRaises(ProcessLookupError):
                os.kill(pid,0)
        # A command that closes its output but keeps running is the same timeout.
        start=time.monotonic()
        with self.assertRaises(CommandTimeout) as caught:
            process(['sh','-c','echo early; exec >&- 2>&-; sleep 30'],.5)
        self.assertEqual(caught.exception.output,'early\n')
        self.assertLess(time.monotonic()-start,2)
    def test_docker_shell_timeout_removes_container_and_cleanup_timeout_is_not_a_command_timeout(self):
        for cleanup_hangs in (False,True):
            commands=[]
            def fake(command,seconds,**kwargs):
                commands.append(command)
                if command[:2]==['docker','run']:
                    raise CommandTimeout('command deadline','partial',False)
                if cleanup_hangs and command[:3]==['docker','rm','-f']:
                    raise TimeoutError('command deadline')
                return {'exit_code':0,'output':''}
            with self.subTest(cleanup_hangs=cleanup_hangs), patch('bug_competition.harness.core.process',side_effect=fake):
                executor=DockerShell()
                with self.assertRaises(RuntimeError if cleanup_hangs else CommandTimeout):
                    executor.shell(Path('/tmp/workspace'),'sleep 60',30)
                self.assertEqual(commands[3][:3],['docker','rm','-f'])
                self.assertEqual(len(executor.active),int(cleanup_hangs))
    def test_output_bounded(self):
        result=process(['python3','-c','print("x"*1000000)'],5)
        self.assertEqual(len(result['output']),24000)
    def test_symlinks_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            (Path(folder)/'link').symlink_to('/etc/passwd')
            with self.assertRaises(ValueError):tree_hash(Path(folder))
    def test_anthropic_tool_cycle_and_independent_histories(self):
        response={"content":[{"type":"text","text":"Inspecting source."},{"type":"tool_use","id":"tool1","name":"claim","input":{"summary":"noted"}}]}
        calls=[]
        def request(req,timeout):
            calls.append(json.loads(req.data));return io.BytesIO(json.dumps(response).encode())
        with patch.dict(os.environ,{'ANTHROPIC_API_KEY':'mock'}),patch('urllib.request.urlopen',side_effect=request):
            first=AnthropicAgent();second=AnthropicAgent()
            view={'identity':'alice','observation':{'ok':True}}
            self.assertEqual(first.action(view,10),{'tool':'claim','arguments':{'summary':'noted'}})
            first.action(view,10)
            self.assertEqual(second.messages,[])
            self.assertEqual(calls[0]['model'],'claude-opus-5-5')
            self.assertNotIn('system',calls[0])
            self.assertEqual(calls[0]['messages'][0]['content'], PROMPT)
            self.assertEqual(calls[0]['tool_choice']['type'],'auto')
            self.assertTrue(all(tool['strict'] for tool in calls[0]['tools']))
            # The direct adapter offers the same tools, including the argument-free status.
            self.assertEqual([tool['name'] for tool in calls[0]['tools']],['shell','claim','status','web_search'])
            self.assertEqual(calls[0]['tools'][2]['input_schema'],{'type':'object','properties':{},'additionalProperties':False})
            self.assertEqual(calls[1]['messages'][-1]['content'][0]['type'],'tool_result')
    def test_anthropic_normal_final_response(self):
        response={"stop_reason":"end_turn","content":[{"type":"text","text":"Done."}]}
        with patch.dict(os.environ,{'ANTHROPIC_API_KEY':'mock'}),patch('urllib.request.urlopen',return_value=io.BytesIO(json.dumps(response).encode())):
            agent=AnthropicAgent()
            self.assertIsNone(agent.action({'identity':'alice','observation':{}},10))
            self.assertIsNone(agent.pending)
    def test_openai_search_uses_responses_and_preserves_citations(self):
        payload={"output":[{"type":"message","content":[{"type":"output_text","text":"Python documentation","annotations":[{"type":"url_citation","url":"https://docs.python.org/","title":"Python"}]}]}]}
        with patch.dict(os.environ,{'OPENAI_API_KEY':'mock'}),patch('urllib.request.urlopen',return_value=io.BytesIO(json.dumps(payload).encode())) as request:
            result=OpenAISearch()('Python reference',10)
            body=json.loads(request.call_args.args[0].data)
            self.assertEqual(body['tools'],[{'type':'web_search'}])
            self.assertEqual(result['citations'][0]['url'],'https://docs.python.org/')
    def test_missing_search_credentials_fail_before_request(self):
        with patch.dict(os.environ,{},clear=True):
            with self.assertRaisesRegex(ValueError,'OPENAI_API_KEY'):
                OpenAISearch()
    def test_dotenv_loader_allowlist_precedence_and_no_execution(self):
        content="\n".join(['ANTHROPIC_API_KEY=file-key', 'export OPENAI_API_KEY="mock-openai" # comment', "BRAVE_SEARCH_API_KEY='$(touch /tmp/never-execute)'", 'UNRELATED_SECRET=ignored'])
        with patch.dict(os.environ,{'ANTHROPIC_API_KEY':'existing-key'},clear=True),patch.object(Path,'is_file',return_value=True),patch.object(Path,'read_text',return_value=content):
            load_host_credentials(Path('/mock/.env'))
            self.assertEqual(os.environ['ANTHROPIC_API_KEY'],'existing-key')
            self.assertEqual(os.environ['OPENAI_API_KEY'],'mock-openai')
            self.assertEqual(os.environ['BRAVE_SEARCH_API_KEY'],'$(touch /tmp/never-execute)')
            self.assertNotIn('UNRELATED_SECRET',os.environ)
    def test_dotenv_error_does_not_expose_value(self):
        with patch.dict(os.environ,{},clear=True),patch.object(Path,'is_file',return_value=True),patch.object(Path,'read_text',return_value='OPENAI_API_KEY="secret-value'):
            with self.assertRaises(ValueError) as error:
                load_host_credentials(Path('/mock/.env'))
            self.assertNotIn('secret-value',str(error.exception))
    def test_diagnostic_grading_not_verified(self):
        class Diagnostic:
            adversarially_verified=False
            def __call__(self,tree,seconds):return oracle(tree,seconds)
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);tree=root/'shared';tree.mkdir();(tree/'value').write_text('broken')
            result=Competition(tree,root/'protected',MockShell(),Diagnostic(),{'a':ScriptedAgent([shell('fixed')]),'b':ScriptedAgent([])}).run(5)
            self.assertIsNone(result['verified_score'])
            self.assertEqual(result['diagnostic_score'],{'a':1,'b':0})

if __name__=='__main__':unittest.main()
