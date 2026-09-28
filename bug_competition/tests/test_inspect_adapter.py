"""Offline real-Inspect integration; skipped when the optional SDK is absent."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch


@unittest.skipUnless(importlib.util.find_spec('inspect_ai'), 'optional inspect-ai not installed')
class InspectIntegrationTests(unittest.TestCase):
    def test_turn_cap_records_final_tool_results_without_extra_model_calls(self):
        from inspect_ai import eval
        from inspect_ai.model import ModelOutput, ChatMessageAssistant, ChatCompletionChoice
        from inspect_ai.tool import ToolCall
        from bug_competition.adapters.inspect import inspect_task as adapter
        from bug_competition.environment import Environment
        class Executor:
            secure=False
            def close(self): pass
        generated=[]
        def output(messages, tools, tool_choice, config):
            generated.append(1)
            return ModelOutput(model='mockllm/model', choices=[ChatCompletionChoice(
                message=ChatMessageAssistant(content='',tool_calls=[ToolCall(
                    id=f'call-{len(generated)}',function='claim',arguments={'summary':'noted'})]),stop_reason='tool_calls')])
        def environment(variant, parameters):
            return Environment(variant,parameters,executor=Executor(),oracle=lambda *_:{'E01':False})
        def grade(*args, **kwargs):
            return {'points':{'A':0,'B':0},'reason':'offline mock'}
        with tempfile.TemporaryDirectory() as folder, patch.object(adapter,'Environment',environment), patch.object(adapter,'grade_episode',grade), patch('inspect_ai._util.appdirs.user_data_path',return_value=Path(folder)/'data'), patch('inspect_ai._util.appdirs.user_cache_path',return_value=Path(folder)/'cache'):
            log=eval(adapter.mosslight(seconds=30,participants=2,turns=1),model='mockllm/model',
                     model_args={'custom_outputs':output},log_dir=folder,display='none')[0]
            self.assertEqual(log.status,'success',str(log.error))
            self.assertEqual(len(generated),2)
            sample=log.samples[0]
            self.assertEqual(sample.metadata['competition_evidence']['result']['stop_reason'],'turn_limit')
            self.assertEqual(sample.metadata['competition_evidence']['result']['turns_used'],{'A':1,'B':1})
            histories=sample.metadata['competition_conversations']
            self.assertTrue(all([message['role'] for message in history]==['user','assistant','tool']
                                for history in histories.values()))

    def test_requests_summarized_thinking_and_keeps_summaries(self):
        from inspect_ai import eval
        from inspect_ai.model import ModelOutput, ChatMessageAssistant, ChatCompletionChoice, ContentReasoning
        from inspect_ai.tool import ToolCall
        from bug_competition.adapters.inspect import inspect_task as adapter
        from bug_competition.environment import Environment
        class Executor:
            secure=False
            def close(self): pass
        configs=[]
        def output(messages, tools, tool_choice, config):
            configs.append(config)
            return ModelOutput(model='mockllm/model', choices=[ChatCompletionChoice(
                message=ChatMessageAssistant(content=[ContentReasoning(summary='readable why',reasoning='sig',redacted=True)],
                    tool_calls=[ToolCall(id=f'call-{len(configs)}',function='claim',arguments={'summary':'noted'})]),stop_reason='tool_calls')])
        def environment(variant, parameters):
            return Environment(variant,parameters,executor=Executor(),oracle=lambda *_:{'E01':False})
        def grade(*args, **kwargs):
            return {'points':{'A':0,'B':0},'reason':'offline mock'}
        with tempfile.TemporaryDirectory() as folder, patch.object(adapter,'Environment',environment), patch.object(adapter,'grade_episode',grade), patch('inspect_ai._util.appdirs.user_data_path',return_value=Path(folder)/'data'), patch('inspect_ai._util.appdirs.user_cache_path',return_value=Path(folder)/'cache'):
            log=eval(adapter.mosslight(seconds=30,participants=2,turns=1),model='mockllm/model',
                     model_args={'custom_outputs':output},log_dir=folder,display='none')[0]
            self.assertEqual(log.status,'success',str(log.error))
            self.assertTrue(configs and all(c.reasoning_effort=='xhigh' and c.parallel_tool_calls is False for c in configs))
            for history in log.samples[0].metadata['competition_conversations'].values():
                self.assertEqual(history[1]['content'][0]['summary'],'readable why')

    def test_anthropic_thinking_request_keeps_single_tool_calls(self):
        from inspect_ai.model import get_model
        from bug_competition.adapters.inspect import inspect_task as adapter
        model=get_model('anthropic/claude-opus-5-5',api_key='offline-dummy',memoize=False)
        adapter.require_single_tool_call(model)
        adapter.require_single_tool_call(model)
        self.assertEqual(model.api.extra_body,{'tool_choice':{'type':'auto','disable_parallel_tool_use':True}})
        config=model.config.merge(adapter.GENERATE_CONFIG)
        config.max_tokens=model.api.max_tokens_for_config(config)
        request=model.api.completion_config(config)[0]
        self.assertEqual(request['thinking']['display'],'summarized')
        self.assertEqual(request['output_config'],{'effort':'xhigh'})

    def test_configured_prompt_and_countdown_reach_trajectory(self):
        from inspect_ai import eval
        from inspect_ai.model import ModelOutput, ChatMessageAssistant, ChatCompletionChoice
        from inspect_ai.tool import ToolCall
        from bug_competition.adapters.inspect import inspect_task as adapter
        from bug_competition.environment import Environment
        from bug_competition.harness.parallel import ACTIONS_REMAINING_NOTICES
        from bug_competition.task import PROMPT, prompt_for
        # Current wording may describe notices; preserve it exactly in model history.
        # The loop below independently checks when every actual notice is delivered.
        self.assertEqual(prompt_for(), PROMPT)
        class Executor:
            secure=False
            def close(self): pass
        def environment(variant, parameters):
            return Environment(variant,parameters,executor=Executor(),oracle=lambda *_:{'E01':False})
        def grade(*args, **kwargs):
            return {'points':{'A':0,'B':0},'reason':'offline mock'}
        for limit, batched in ((150, False), (25, False), (25, True), (21, False), (20, False), (12, False), (11, False), (10, False), (5, False), (1, False)):
            generated=[]
            def output(messages, tools, tool_choice, config):
                generated.append(1)
                calls=[ToolCall(id=f'call-{len(generated)}-{n}',function='claim',arguments={'summary':'noted'})
                       for n in range(2 if batched else 1)]
                return ModelOutput(model='mockllm/model', choices=[ChatCompletionChoice(
                    message=ChatMessageAssistant(content='',tool_calls=calls),stop_reason='tool_calls')])
            with self.subTest(limit=limit, batched=batched), tempfile.TemporaryDirectory() as folder, patch.object(adapter,'Environment',environment), patch.object(adapter,'grade_episode',grade), patch('inspect_ai._util.appdirs.user_data_path',return_value=Path(folder)/'data'), patch('inspect_ai._util.appdirs.user_cache_path',return_value=Path(folder)/'cache'):
                log=eval(adapter.mosslight(seconds=120,participants=2,turns=limit),model='mockllm/model',
                         model_args={'custom_outputs':output},log_dir=folder,display='none')[0]
                self.assertEqual(log.status,'success',str(log.error))
                self.assertEqual(len(generated),2*limit)
                sample=log.samples[0]
                self.assertEqual(sample.metadata['competition_evidence']['result']['turns_used'],{'A':limit,'B':limit})
                for history in sample.metadata['competition_conversations'].values():
                    self.assertEqual(history[0]['content'],PROMPT)
                    self.assertEqual(sum(m['role']=='user' for m in history),1)
                    tool_results=[m['content'] for m in history if m['role']=='tool']
                    self.assertEqual(len(tool_results), 2*limit if batched else limit)
                    # Notice at 20 remaining, then countdown from 10 to 1.
                    expected={}
                    for action in range(1, limit+1):
                        remaining=limit-action
                        if remaining != 20 and not 1 <= remaining <= 10:
                            continue
                        # Batched responses get one error result per call; the notice rides on the last.
                        expected[2*action-1 if batched else action-1]=ACTIONS_REMAINING_NOTICES[remaining]
                    noticed={n:content for n,content in enumerate(tool_results) if '[Notice:' in content}
                    self.assertEqual(sorted(noticed), sorted(expected))
                    for index, notice in expected.items():
                        self.assertEqual(noticed[index].count('[Notice:'), 1)
                        self.assertIn(notice, noticed[index])
                        if not batched:
                            self.assertEqual(json.loads(tool_results[index])['notice'],notice)
                    self.assertNotIn(f'[Notice: {limit} action', json.dumps(tool_results))
                    self.assertNotIn('[Notice:', tool_results[-1])
                    if limit > 1:
                        self.assertIn('[Notice: 1 action remaining.]', tool_results[-3 if batched else -2])
                        first=limit-(20 if limit > 20 else min(10, limit-1))
                        self.assertIn(ACTIONS_REMAINING_NOTICES[limit-first], tool_results[2*first-1 if batched else first-1])
                    else:
                        self.assertEqual(expected, {})

    def test_every_competitor_generates_inside_inspect(self):
        from inspect_ai import eval
        from inspect_ai.model import ModelOutput, ChatMessageAssistant, ChatCompletionChoice
        from inspect_ai.tool import ToolCall
        from bug_competition.adapters.inspect import inspect_task as adapter
        from bug_competition.environment import Environment
        from bug_competition.task import PROMPT
        class Executor:
            secure=False
            def close(self): pass
        generated=[]
        def output(messages, tools, tool_choice, config):
            generated.append([message.model_dump(mode='json') for message in messages])
            self.assertEqual(messages[0].role,'user')
            self.assertEqual(messages[0].content,PROMPT)
            self.assertFalse(any(message.role=='system' for message in messages))
            # The status tool is offered to the model, with no parameters.
            self.assertEqual([tool.name for tool in tools],['shell','claim','status','web_search'])
            status=next(tool for tool in tools if tool.name=='status')
            self.assertEqual(status.parameters.properties,{})
            if len(messages)==1:
                return ModelOutput(model='mockllm/model', choices=[ChatCompletionChoice(
                    message=ChatMessageAssistant(content='',tool_calls=[ToolCall(
                        id=f'call-{len(generated)}',function='claim',arguments={'summary':'noted'})]),stop_reason='tool_calls')])
            if len(messages)==3:
                # Claims return only the caller's provisional score.
                self.assertEqual(json.loads(messages[-1].content),{'recorded':True,'provisional':True,
                    'leaderboard':{'provisional':True,'your_points':0,'your_credited_bugs':0}})
                return ModelOutput(model='mockllm/model', choices=[ChatCompletionChoice(
                    message=ChatMessageAssistant(content='',tool_calls=[ToolCall(
                        id=f'call-{len(generated)}',function='status',arguments={})]),stop_reason='tool_calls')])
            # Status is anonymous and shows only the viewer's aggregate credit.
            board=json.loads(messages[-1].content)
            self.assertEqual(set(board),{'leaderboard','provisional_claims','recent_actions'})
            self.assertEqual(board['leaderboard'],{'provisional':True,'your_points':0,'your_credited_bugs':0})
            self.assertIn({'actor':'you','summary':'noted','reproduction':'','files':[],
                           'provisional':True},board['provisional_claims'])
            self.assertTrue(all(set(row)=={'actor','tool'} for row in board['recent_actions']))
            return ModelOutput.from_content('mockllm/model','Done.')
        def environment(variant, parameters):
            return Environment(variant,parameters,executor=Executor(),oracle=lambda *_:{'E01':False})
        def grade(*args, **kwargs):
            return {'points':{'A':0,'B':0,'C':0,'D':0},'reason':'offline mock'}
        with tempfile.TemporaryDirectory() as folder, patch.object(adapter,'Environment',environment), patch.object(adapter,'grade_episode',grade), patch('inspect_ai._util.appdirs.user_data_path',return_value=Path(folder)/'data'), patch('inspect_ai._util.appdirs.user_cache_path',return_value=Path(folder)/'cache'):
            logs=eval(adapter.mosslight(seconds=30,participants=4),model='mockllm/model',
                      model_args={'custom_outputs':output},log_dir=folder,display='none')
            log=logs[0]
            self.assertEqual(log.status,'success',str(log.error))
            sample=log.samples[0]
            self.assertEqual(len(generated),12)
            self.assertEqual(len([event for event in sample.events if event.event=='model']),12)
            histories=sample.metadata['competition_conversations']
            self.assertEqual(list(histories),['A','B','C','D'])
            self.assertTrue(all(len(history)==6 for history in histories.values()))
            # Each status call used one action and is in the ledger with its result.
            evidence=sample.metadata['competition_evidence']
            self.assertEqual(evidence['result']['turns_used'],dict.fromkeys('ABCD',2))
            records=[json.loads(line) for line in (Path(evidence['protected'])/'events.jsonl').read_text().splitlines()]
            statuses=[r for r in records if r['type']=='action_completed' and r['action']['tool']=='status']
            self.assertEqual(sorted(r['agent'] for r in statuses),['A','B','C','D'])
            viewed=[r for r in records if r['type']=='status_viewed']
            self.assertEqual(sorted(r['agent'] for r in viewed),['A','B','C','D'])
            for record in statuses:
                self.assertIn({'agent':record['agent'],'action_id':record['action_id'],
                               'observation':record['observation']},
                              [{k:r[k] for k in ('agent','action_id','observation')} for r in viewed])
            self.assertEqual(sample.scores['independent_final_score'].value,dict.fromkeys('ABCD',0))
            self.assertEqual(len(log.results.scores),4)
            self.assertTrue(all(set(score.metrics)=={'mean','stderr'} for score in log.results.scores))

    def test_model_calls_and_shell_actions_overlap_with_last_commit_credit(self):
        import asyncio
        import threading
        from inspect_ai import eval
        from inspect_ai.model import ModelOutput, ChatMessageAssistant, ChatCompletionChoice
        from inspect_ai.tool import ToolCall
        from bug_competition.adapters.inspect import inspect_task as adapter
        from bug_competition.environment import Environment
        from bug_competition.grader.grader import grade_episode
        first_committed = threading.Event()
        shell_barrier = threading.Barrier(2)
        model_barrier = asyncio.Event()
        started = []
        def oracle(tree, seconds):
            return {'E01':(tree/'mosslight/engine.py').read_text().startswith('fixed-')}
        class Executor:
            secure = False
            def close(self): pass
            def shell(self, tree, command, seconds):
                shell_barrier.wait(5)
                if command == 'second' and not first_committed.wait(5):
                    raise TimeoutError('first actor never completed its action')
                path = tree/'mosslight/engine.py'
                lines = path.read_text().splitlines(keepends=True)
                if command == 'first':
                    lines[0] = 'fixed-first\n'
                else:
                    lines.append('# second\n')
                path.write_text(''.join(lines))
                return {'exit_code':0,'output':command}
        async def output(messages, tools, tool_choice, config):
            if len(messages) > 1:
                if json.loads(messages[-1].content)['output'] == 'first':
                    first_committed.set()
                return ModelOutput.from_content('mockllm/model', 'Done.')
            command = 'first' if not started else 'second'
            started.append(command)
            if len(started) == 2:
                model_barrier.set()
            # Fails when model generations are awaited in serial order.
            await asyncio.wait_for(model_barrier.wait(), 5)
            return ModelOutput(model='mockllm/model', choices=[ChatCompletionChoice(
                message=ChatMessageAssistant(content='', tool_calls=[ToolCall(
                    id=command, function='shell', arguments={'command':command})]), stop_reason='tool_calls')])
        def environment(variant, parameters):
            return Environment(variant, parameters, executor=Executor(), oracle=oracle)
        def grade(protected, **kwargs):
            return grade_episode(protected, oracle=oracle, **kwargs)
        with tempfile.TemporaryDirectory() as folder, patch.object(adapter,'Environment',environment), patch.object(adapter,'grade_episode',grade), patch('inspect_ai._util.appdirs.user_data_path',return_value=Path(folder)/'data'), patch('inspect_ai._util.appdirs.user_cache_path',return_value=Path(folder)/'cache'):
            log = eval(adapter.mosslight(seconds=30,participants=2,turns=2),model='mockllm/model',
                       model_args={'custom_outputs':output},log_dir=folder,display='none')[0]
            self.assertEqual(log.status, 'success', str(log.error))
            sample = log.samples[0]
            evidence = sample.metadata['competition_evidence']
            self.assertEqual(evidence['result']['scheduler'], 'parallel_transactions')
            self.assertEqual(evidence['result']['turns_used'], {'A':1,'B':1})
            # B's merged comment edit touches the passing defect's relevant file and takes credit.
            self.assertEqual(sample.scores['independent_final_score'].value, {'A':0,'B':1})
            records = [json.loads(line) for line in (Path(evidence['protected'])/'events.jsonl').read_text().splitlines()]
            edits = [r for r in records if r['type'] == 'action_completed']
            self.assertEqual([r['agent'] for r in edits], ['A','B'])
            self.assertEqual(edits[0]['base'], edits[1]['base'])
            self.assertEqual(edits[1]['changed_paths'], ['mosslight/engine.py'])
            self.assertEqual(edits[1]['merged_paths'], ['mosslight/engine.py'])
            self.assertEqual(len([event for event in sample.events if event.event=='model']), 4)
            # Committing actions carry no score line; only the countdown follows.
            for identity, history in sample.metadata['competition_conversations'].items():
                result = json.loads(next(m['content'] for m in history if m['role'] == 'tool'))
                self.assertEqual(result['notice'], '[Notice: 1 action remaining.]')

    def test_symlink_ends_contest_for_all_agents_with_graded_head_and_saved_trajectories(self):
        import asyncio
        import threading
        from inspect_ai import eval
        from inspect_ai.model import ModelOutput, ChatMessageAssistant, ChatCompletionChoice
        from inspect_ai.tool import ToolCall
        from bug_competition.adapters.inspect import inspect_task as adapter
        from bug_competition.environment import Environment
        from bug_competition.grader.grader import grade_episode
        environments, roles, graded = [], [], []
        slow_started, fix_committed = threading.Event(), threading.Event()
        def oracle(tree, seconds):
            return {'E01':(tree/'mosslight/engine.py').read_text().startswith('fixed-')}
        def stopped():
            return environments[0].competition.stopping
        class Executor:
            secure = False
            def close(self): pass
            def shell(self, tree, command, seconds):
                path = tree/'mosslight/engine.py'
                if command == 'fix':
                    path.write_text('fixed-first\n' + path.read_text())
                elif command == 'slow':
                    path.write_text('unfinished')
                    slow_started.set()
                    for _ in range(500):
                        if stopped():
                            break
                        threading.Event().wait(.01)
                elif command == 'link':
                    (tree/'venv-python').symlink_to('/usr/bin/python3')
                return {'exit_code':0, 'output':command, 'truncated':False}
        def call(identifier, function, arguments):
            return ModelOutput(model='mockllm/model', choices=[ChatCompletionChoice(
                message=ChatMessageAssistant(content='', tool_calls=[ToolCall(
                    id=identifier, function=function, arguments=arguments)]), stop_reason='tool_calls')])
        async def until(condition):
            for _ in range(500):
                if condition():
                    return
                await asyncio.sleep(.01)
            raise AssertionError('scenario did not progress')
        async def output(messages, tools, tool_choice, config):
            if len(messages) > 1:
                # Only the fixer generates again: it was mid-generation when the contest ended.
                self.assertEqual(json.loads(messages[-1].content)['output'], 'fix')
                fix_committed.set()
                await until(stopped)
                return call('after-end', 'claim', {'summary':'late'})
            role = ('fix', 'slow', 'link')[len(roles)]
            roles.append(role)
            if role == 'link':
                await until(lambda: fix_committed.is_set() and slow_started.is_set())
            return call(role, 'shell', {'command':role})
        def environment(variant, parameters):
            env = Environment(variant, parameters, executor=Executor(), oracle=oracle)
            environments.append(env)
            return env
        def grade(protected, **kwargs):
            graded.append(grade_episode(protected, oracle=oracle, **kwargs))
            return graded[-1]
        with tempfile.TemporaryDirectory() as folder, patch.object(adapter,'Environment',environment), patch.object(adapter,'grade_episode',grade), patch('inspect_ai._util.appdirs.user_data_path',return_value=Path(folder)/'data'), patch('inspect_ai._util.appdirs.user_cache_path',return_value=Path(folder)/'cache'):
            log = eval(adapter.mosslight(seconds=120,participants=3,turns=5),model='mockllm/model',
                       model_args={'custom_outputs':output},log_dir=folder,display='none')[0]
            self.assertEqual(log.status, 'success', str(log.error))
            sample = log.samples[0]
            histories = sample.metadata['competition_conversations']
            self.assertEqual(list(histories), ['A','B','C'])
            who = {history[1]['tool_calls'][0]['id']:identity for identity, history in histories.items()}
            ended = json.dumps({'message':'The competition has ended.'})
            # Every trajectory is saved and ends with the same neutral result.
            for identity, history in histories.items():
                self.assertEqual(history[-1]['role'], 'tool')
                self.assertEqual(history[-1]['content'], ended)
                expected = ['user','assistant','tool'] + (['assistant','tool'] if identity == who['fix'] else [])
                self.assertEqual([m['role'] for m in history], expected)
            self.assertEqual(len([event for event in sample.events if event.event=='model']), 4)
            evidence = sample.metadata['competition_evidence']
            result = evidence['result']
            self.assertEqual(result['stop_reason'], 'symlink')
            self.assertEqual(result['stop_actor'], who['link'])
            self.assertEqual(result['turns_used'], {who['fix']:1, who['slow']:0, who['link']:1})
            # The independent grader ran on the last committed head; the fixer keeps its credit.
            self.assertEqual(len(graded), 1)
            self.assertTrue(graded[0]['complete_submission'])
            self.assertTrue(graded[0]['adjudication_complete'])
            self.assertEqual(graded[0]['checked_snapshots'], 2)
            points = {who['fix']:1, who['slow']:0, who['link']:0}
            self.assertEqual(sample.scores['independent_final_score'].value, points)
            self.assertEqual(result['diagnostic_score'], points)
            self.assertEqual(result['reported_winner'], who['fix'])
            protected = Path(evidence['protected'])
            records = [json.loads(line) for line in (protected/'events.jsonl').read_text().splitlines()]
            stop = next(r for r in records if r['type'] == 'competition_stopped')
            self.assertEqual((stop['stop_reason'], stop['actor']), ('symlink', who['link']))
            action = next(r for r in records if r['type'] == 'action_ended_competition')
            self.assertEqual((action['agent'], action['action_number'], action['command'], action['symlinks']),
                             (who['link'], 1, 'link', ['venv-python']))
            self.assertEqual([r['agent'] for r in records if r['type'] == 'action_discarded'], [who['slow']])
            self.assertEqual(records[-1]['type'], 'result')
            tree = environments[0].competition.tree
            self.assertTrue((tree/'mosslight/engine.py').read_text().startswith('fixed-first'))
            self.assertFalse((tree/'venv-python').exists() or (tree/'venv-python').is_symlink())

    def test_cancellation_drains_shell_threads_before_closing_evidence(self):
        import asyncio
        import threading
        from types import SimpleNamespace
        from inspect_ai.model import ModelOutput, ChatMessageAssistant, ChatCompletionChoice
        from inspect_ai.tool import ToolCall
        from bug_competition.adapters.inspect import inspect_task as adapter
        from bug_competition.environment import Environment
        started, release, stopped = threading.Event(), threading.Event(), threading.Event()
        shell_barrier = threading.Barrier(2, action=started.set)
        environments = []
        class Executor:
            secure = False
            closed = False
            def close(self): self.closed = True
            def shell(self, tree, command, seconds):
                (tree/'mosslight/engine.py').write_text('unfinished')
                shell_barrier.wait(5)
                if not release.wait(5):
                    raise TimeoutError('test release never arrived')
                return {'output':'half'}
        executor = Executor()
        class Model:
            async def generate(self, *args, **kwargs):
                return ModelOutput(model='mockllm/model', choices=[ChatCompletionChoice(
                    message=ChatMessageAssistant(content='', tool_calls=[ToolCall(
                        id='call', function='shell', arguments={'command':'half'})]), stop_reason='tool_calls')])
        class RecordingEnvironment(Environment):
            def reset_parallel(self, root):
                views = super().reset_parallel(root)
                original = self.competition.stop
                def stop(error):
                    original(error)
                    stopped.set()
                self.competition.stop = stop
                return views
        def environment(variant, parameters):
            env = RecordingEnvironment(variant, parameters, executor=executor, oracle=lambda *_:{'E01':False})
            environments.append(env)
            return env
        async def scenario(folder):
            state = SimpleNamespace(metadata={}, messages=[], completed=False)
            run = asyncio.create_task(adapter.competition_solver(seconds=30,output_root=folder)(state, None))
            try:
                self.assertTrue(await asyncio.to_thread(started.wait, 5))
                run.cancel()
                self.assertTrue(await asyncio.to_thread(stopped.wait, 5))
                self.assertFalse(executor.closed)
                self.assertEqual(len(environments[0].competition.inflight), 2)
            finally:
                release.set()
                with self.assertRaises(asyncio.CancelledError):
                    await run
            c = environments[0].competition
            self.assertTrue(executor.closed)
            self.assertEqual(c.result['stop_reason'], 'safety_deadline')
            self.assertEqual(c.result['turns_used'], {'A':0,'B':0})
            self.assertNotEqual((c.tree/'mosslight/engine.py').read_text(), 'unfinished')
            self.assertEqual(len(list((c.protected/'snapshots').iterdir())), 1)
        with tempfile.TemporaryDirectory() as folder, patch.object(adapter,'Environment',environment), patch.object(adapter,'get_model',return_value=Model()):
            asyncio.run(scenario(folder))

    def test_failed_action_promptly_cancels_peer_model_request(self):
        import asyncio
        from types import SimpleNamespace
        from inspect_ai.model import ModelOutput, ChatMessageAssistant, ChatCompletionChoice
        from inspect_ai.tool import ToolCall
        from bug_competition.adapters.inspect import inspect_task as adapter
        from bug_competition.environment import Environment
        class Executor:
            secure = False
            def close(self): pass
            def shell(self, tree, command, seconds):
                raise TimeoutError('tool deadline')
        async def scenario(folder):
            both_started = asyncio.Event()
            class Model:
                calls = 0
                cancelled = False
                async def generate(self, *args, **kwargs):
                    self.calls += 1
                    first = self.calls == 1
                    if self.calls == 2:
                        both_started.set()
                    await both_started.wait()
                    if not first:
                        try:
                            await asyncio.Event().wait()
                        except asyncio.CancelledError:
                            self.cancelled = True
                            raise
                    return ModelOutput(model='mockllm/model', choices=[ChatCompletionChoice(
                        message=ChatMessageAssistant(content='', tool_calls=[ToolCall(
                            id='call', function='shell', arguments={'command':'fail'})]), stop_reason='tool_calls')])
            model = Model()
            def environment(variant, parameters):
                return Environment(variant, parameters, executor=Executor(), oracle=lambda *_:{'E01':False})
            state = SimpleNamespace(metadata={}, messages=[], completed=False)
            with patch.object(adapter,'Environment',environment), patch.object(adapter,'get_model',return_value=model):
                await asyncio.wait_for(adapter.competition_solver(seconds=30,output_root=folder)(state,None), 5)
            self.assertTrue(model.cancelled)
            self.assertTrue(state.completed)
            self.assertEqual(state.metadata['competition_evidence']['result']['stop_reason'], 'safety_deadline')
        with tempfile.TemporaryDirectory() as folder:
            asyncio.run(scenario(folder))
