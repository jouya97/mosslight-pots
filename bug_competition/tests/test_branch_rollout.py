"""Offline continuation tests: real broker/ledger, fake models and a tiny oracle."""
import asyncio
import copy
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import pytest

from inspect_ai.model import ChatMessageAssistant, ChatMessageUser, ChatMessageTool, ChatCompletionChoice
from inspect_ai.model import ModelOutput, GenerateConfig, ContentReasoning
from inspect_ai.tool import ToolCall, ToolInfo, ToolParams

from bug_competition.harness.core import ScriptedAgent, process, tree_hash, TOOLS
from bug_competition.task import PROMPT
from bug_competition.harness.parallel import ParallelCompetition
from bug_competition.grader.grader import grade_episode
from bug_competition.host_only.tools import branch_rollout as branch
from bug_competition.host_only.tools.branch_runtime import (
    ResumedCompetition, continue_participants, check_historical_verdicts)


class LocalExecutor:
    secure = False
    def shell(self, tree, command, seconds):
        return process(['/bin/sh', '-c', command], seconds, cwd=tree)
    def close(self):
        pass


def oracle(tree, remaining):
    return {'D': (Path(tree) / 'x.txt').read_text().strip() == 'fixed'}


def output(call=None, content='done'):
    return ModelOutput(model='mock/test', choices=[ChatCompletionChoice(message=ChatMessageAssistant(
        content=content, tool_calls=[call] if call else None), stop_reason='tool_calls' if call else 'stop')])


class BranchTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.source = self.root / 'source'
        self.source.mkdir()
        self.protected = self.source / 'episode_evidence/fixture/protected'
        self.shared = self.source / 'shared'
        self.shared.mkdir()
        (self.shared / 'x.txt').write_text('bad\n')
        self.manifest = self.root / 'manifest.json'
        branch.write_json(self.manifest, {'entries': [{'id': 'D', 'file': 'x.txt', 'level': 'hard'}]})
        self.comp = ParallelCompetition(self.shared, self.protected, LocalExecutor(), oracle,
            {a: ScriptedAgent([]) for a in 'AB'}, weights={'D': 5}, relevance={'D': {'x.txt'}})
        self.comp.begin(60, turn_limit=5)
        self.histories = {a: [ChatMessageUser(content=PROMPT)] for a in 'AB'}
        self.action('A', 'shell', {'command': "printf 'fixed\\n' > x.txt"}, opaque=True)
        self.action('B', 'status', {})
        self.action('A', 'claim', {'summary': 'fixed x', 'files': ['x.txt']})
        self.cut = self.comp.audit.sequence - 1
        self.action('B', 'shell', {'command': "printf 'bad\\n' > x.txt"})
        self.regression_cut = self.comp.audit.sequence - 1
        self.action('A', 'shell', {'command': "printf 'fixed\\n' > x.txt"})
        self.comp.finish()
        branch.write_json(self.source / 'trajectories.json', [dict(sample_id='competition', conversations={
            a: [m.model_dump(mode='json') for m in h] for a, h in self.histories.items()})])
        branch.write_json(self.source / 'invocation.json', dict(action_limit_per_participant=5,
            actions_remaining_notices=[4, 3, 2, 1], image='fake', inspect_version='fixture'))
        self.tools = [ToolInfo(name=t['name'], description=t['description'],
                              parameters=ToolParams.model_validate(t['input_schema'])) for t in TOOLS[:3]]

    def tearDown(self):
        self.temp.cleanup()

    def action(self, actor, tool, arguments, opaque=False):
        ident = f'{actor}-{len(self.histories[actor])}'
        content = [ContentReasoning(reasoning='opaque-test-payload', redacted=True, summary='repair')] if opaque else ''
        response = output(ToolCall(id=ident, function=tool, arguments=arguments), content)
        self.histories[actor].append(response.message)
        self.comp.agents[actor].last_response = response.model_dump(mode='json')
        observation = self.comp.act(actor, dict(tool=tool, arguments=arguments))
        self.histories[actor].append(ChatMessageTool(content=json.dumps(observation), tool_call_id=ident, function=tool))

    def loaded(self, sequence=None):
        return branch.load_source(self.source, self.cut if sequence is None else sequence)

    def test_versioned_status_continuation_preserves_prefix_and_replays_new_feedback(self):
        from bug_competition.harness.core import STATUS_CALLER_ONLY, STATUS_COMPETITOR_SCORES
        before = (self.protected / 'events.jsonl').read_bytes()
        folder, config = self.prepared(status_protocol=STATUS_COMPETITOR_SCORES, notices=[])
        records, state, histories = self.loaded()[2:]
        self.assertEqual(state['status_protocol'], STATUS_CALLER_ONLY)
        # Historical ledgers predate the baseline protocol field and still validate unchanged.
        legacy = copy.deepcopy(records)
        legacy[0].pop('status_protocol', None)
        self.assertEqual(branch.scan_prefix(legacy, ['A', 'B'], self.cut, {'D': 5})['status_protocol'],
                         STATUS_CALLER_ONLY)
        target = self.root / 'v2-shared'
        target.mkdir()
        (target / 'x.txt').write_text('fixed\n')
        comp = ResumedCompetition(target, self.root / 'v2-protected', LocalExecutor(), oracle,
            {a: ScriptedAgent([]) for a in 'AB'}, weights={'D': 5}, relevance={'D': {'x.txt'}})
        comp.restore(self.protected, records, state, config)
        try:
            seen = comp.act('B', dict(tool='status', arguments={}))
            self.assertEqual(seen['leaderboard']['competitors'],
                             [dict(actor='competitor_1', points=5, credited_bugs=1)])
            claim = comp.act('B', dict(tool='claim', arguments={'summary': 'checking'}))
            self.assertNotIn('competitors', claim['leaderboard'])
            combined = branch.records_from(comp.protected / 'events.jsonl')
            self.assertEqual(combined[:len(records)], records)
            replayed = branch.scan_prefix(combined, ['A', 'B'], len(combined) - 1, {'D': 5})
            self.assertEqual(replayed['status_protocol'], STATUS_COMPETITOR_SCORES)
            switches = [r for r in combined if r['type'] == 'status_protocol_changed']
            self.assertEqual(len(switches), 1)
            self.assertEqual(switches[0]['previous_protocol'], STATUS_CALLER_ONLY)
            # Future branches inherit the active version, without adding a redundant switch.
            next_tree = self.root / 'v2-next-shared'
            next_tree.mkdir()
            (next_tree / 'x.txt').write_text('fixed\n')
            next_comp = ResumedCompetition(next_tree, self.root / 'v2-next-protected', LocalExecutor(), oracle,
                {a: ScriptedAgent([]) for a in 'AB'}, weights={'D': 5}, relevance={'D': {'x.txt'}})
            inherited = {k: v for k, v in config.items() if k != 'status_protocol'}
            next_comp.restore(comp.protected, combined, replayed, inherited)
            try:
                self.assertEqual(next_comp.act('A', dict(tool='status', arguments={}))['leaderboard']['competitors'],
                                 [dict(actor='competitor_2', points=0, credited_bugs=0)])
                again = branch.records_from(next_comp.protected / 'events.jsonl')
                self.assertEqual(len([r for r in again if r['type'] == 'status_protocol_changed']), 1)
                branch.scan_prefix(again, ['A', 'B'], len(again) - 1, {'D': 5})
            finally:
                next_comp.finish()
        finally:
            comp.finish()
        self.assertEqual((self.protected / 'events.jsonl').read_bytes(), before)
        self.assertNotIn('competitors', json.loads(histories['B'][-1]['content'])['leaderboard'])

    def test_prefix_has_exact_state_and_no_future(self):
        _, _, records, state, histories = self.loaded()
        self.assertEqual(state['turns_used'], {'A': 2, 'B': 1})
        self.assertEqual(state['owners'], {'D': 'A'})
        self.assertEqual(state['claims'][0]['summary'], 'fixed x')
        self.assertEqual(len(state['snapshot_hashes']), 2)
        self.assertEqual(len(histories['A']), 5)
        self.assertEqual(len(histories['B']), 3)
        self.assertEqual(histories['A'][1]['content'][0]['reasoning'], 'opaque-test-payload')
        self.assertEqual(records[-1]['sequence'], self.cut)
        self.assertEqual(branch.preview(state, self.cut, {'D': 5})['provisional_points'], {'A': 5, 'B': 0})

    def test_regression_removes_owner(self):
        state = self.loaded(self.regression_cut)[3]
        self.assertEqual(state['current'], {'D': False})
        self.assertEqual(state['owners'], {})

    def test_changed_weights_cannot_silently_reinterpret_historical_feedback(self):
        records = branch.records_from(self.protected / 'events.jsonl')
        with self.assertRaisesRegex(ValueError, 'scoring/board protocol differs'):
            branch.scan_prefix(records, ['A', 'B'], self.cut, weights={'D': 1})

    def test_inflight_cut_rejected(self):
        records = branch.records_from(self.protected / 'events.jsonl')
        start = next(e['sequence'] for e in records if e['type'] == 'action_started')
        with self.assertRaisesRegex(ValueError, 'unfinished'):
            self.loaded(start)

    def test_snapshot_tamper_rejected(self):
        (self.protected / 'snapshots/1/x.txt').write_text('tampered')
        with self.assertRaisesRegex(ValueError, 'integrity'):
            self.loaded()

    def test_ledger_tamper_rejected(self):
        p = self.protected / 'events.jsonl'
        p.write_text(p.read_text().replace('fixed x', 'stolen x', 1))
        with self.assertRaisesRegex(ValueError, 'integrity'):
            self.loaded()

    def test_tool_result_tamper_rejected(self):
        p = self.source / 'trajectories.json'
        d = branch.read_json(p)
        d[0]['conversations']['A'][2]['content'] = '{}'
        branch.write_json(p, d)
        with self.assertRaisesRegex(ValueError, 'observation differs'):
            self.loaded()

    def test_after_resolves_global_cut(self):
        found = branch.load_source(self.source, after='A:2')
        self.assertEqual(found[2][-1]['sequence'], self.cut)
        self.assertEqual(found[3]['turns_used']['B'], 1)

    def test_cut_listing_excludes_inflight(self):
        candidates = branch.available_cuts(self.source, self.cut, 20)
        self.assertIn(self.cut, [e['sequence'] for e in candidates])
        for e in candidates:
            self.loaded(e['sequence'])

    def test_probe_mismatch_stops_preflight(self):
        state = self.loaded()[3]
        self.assertEqual(check_historical_verdicts(oracle, self.protected, state, 60), 2)
        with self.assertRaisesRegex(ValueError, 'no model continuation'):
            check_historical_verdicts(lambda *_: {'D': False}, self.protected, state, 60)

    def prepared(self, name='prepared', model='mock/test', **kwargs):
        contract = dict(model=model, tools=[t.model_dump(mode='json') for t in self.tools], config={})
        branch.write_json(self.source / 'live_probes.json', [{'id': 'D', 'program': 'pass', 'expected': None}])
        with patch.object(branch, 'manifest_weights', return_value={'D': 5}), \
             patch.object(branch, 'manifest_files', return_value={'D': {'x.txt'}}), \
             patch.object(branch, 'archived_contract', return_value=contract), \
             patch('bug_competition.grader.grader.FinalOracle') as factory:
            factory.return_value.probes = [{'id': 'D', 'program': 'pass', 'expected': None}]
            config = branch.prepare(self.source, self.root / name, sequence=self.cut, **kwargs)
        return self.root / name, config

    def test_prepare_validate_and_shared_probes_are_offline(self):
        before = (self.protected / 'events.jsonl').read_bytes()
        folder, config = self.prepared(notices=[])
        sibling, other = self.prepared(name='sibling', probes_from=folder)
        self.assertEqual(config['probe_files'], other['probe_files'])
        self.assertEqual(config['notices'], [])
        self.assertEqual(config['shell_seconds'], 180)
        self.assertEqual(other['notices'], [4, 3, 2, 1])
        self.assertEqual((folder / 'checkpoint/snapshots/1/x.txt').read_text(), 'fixed\n')
        self.assertFalse((folder / 'checkpoint/snapshots/2').exists())
        with patch.object(branch, 'manifest_weights', return_value={'D': 5}), \
             patch.object(branch, 'manifest_files', return_value={'D': {'x.txt'}}):
            self.assertEqual(branch.validate_bundle(folder)[2]['owners'], {'D': 'A'})
        self.assertEqual(before, (self.protected / 'events.jsonl').read_bytes())
        with self.assertRaisesRegex(ValueError, 'already exists'):
            self.prepared()

    def test_shell_budget_prepared_and_restored(self):
        folder, config = self.prepared(shell_seconds=75)
        self.assertEqual(config['shell_seconds'], 75)
        records, state, _ = self.loaded()[2:]
        target = self.root / 'timeout-shared'
        target.mkdir()
        (target / 'x.txt').write_text('fixed\n')
        comp = ResumedCompetition(target, self.root / 'timeout-protected', LocalExecutor(), oracle,
            {a: ScriptedAgent([]) for a in 'AB'}, weights={'D': 5}, relevance={'D': {'x.txt'}})
        comp.restore(self.protected, records, state, config)
        try:
            self.assertEqual(comp.shell_seconds, 75)
        finally:
            comp.finish()
        config['shell_seconds'] = float('inf')
        branch.write_json(folder / 'branch.json', config)
        with self.assertRaisesRegex(ValueError, 'shell_seconds'):
            branch.validate_bundle(folder)

    def test_changed_runtime_rejected(self):
        folder, _ = self.prepared()
        with patch.object(branch, 'runtime_files', return_value={}):
            with self.assertRaisesRegex(ValueError, 'Runtime changed'):
                branch.validate_bundle(folder)

    def test_prepared_prompt_intervention_is_rejected(self):
        folder, config = self.prepared()
        config['intervention'] = {'type': 'replace_opening_prompt', 'prompt': 'another task'}
        branch.write_json(folder / 'branch.json', config)
        with self.assertRaisesRegex(ValueError, 'interventions are no longer launchable'):
            branch.validate_bundle(folder)

    def test_missing_original_probes_needs_explicit_policy(self):
        contract = dict(model='mock/test', tools=[], config={})
        with patch.object(branch, 'manifest_weights', return_value={'D': 5}), \
             patch.object(branch, 'manifest_files', return_value={'D': {'x.txt'}}), \
             patch.object(branch, 'archived_contract', return_value=contract):
            with self.assertRaisesRegex(ValueError, 'not saved'):
                branch.prepare(self.source, self.root / 'nope', sequence=self.cut)
        self.assertFalse((self.root / 'nope').exists())

    def test_incompatible_archived_prompt_remains_readable_but_cannot_resume(self):
        path = self.source / 'trajectories.json'
        data = branch.read_json(path)
        data[0]['conversations']['A'][0]['content'] = 'Historical alternate experiment'
        branch.write_json(path, data)
        original = path.read_bytes()
        self.assertEqual(self.loaded()[4]['A'][0]['content'], 'Historical alternate experiment')
        with self.assertRaisesRegex(ValueError, 'differs from PROMPT'):
            self.prepared()
        self.assertFalse((self.root / 'prepared').exists())
        self.assertEqual(path.read_bytes(), original)

    def test_prompt_replacement_cli_is_not_available(self):
        import io
        from contextlib import redirect_stderr
        for option in ('--replace-opening-prompt', '--opening-prompt-file', '--historical-reasoning'):
            with self.subTest(option=option), redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                branch.main(['prepare', str(self.source), '--sequence', str(self.cut),
                             '--output', str(self.root / 'unused'), option])
        self.assertFalse((self.root / 'unused').exists())

    def test_outbound_omission_keeps_archived_and_new_reasoning(self):
        history = self.loaded()[4]['A']
        original = copy.deepcopy(history)
        extended = history + [copy.deepcopy(history[1])]
        changed = branch.outbound_history(extended, len(history))
        self.assertEqual(changed[1]['content'], [])
        self.assertEqual(changed[1]['tool_calls'], original[1]['tool_calls'])
        self.assertEqual(changed[2:], extended[2:])
        self.assertEqual(history, original)
        self.assertEqual(branch.outbound_history(history), history)

    def test_interrupted_peer_does_not_mask_primary_timeout(self):
        class Competition:
            def view(self, identity): return {'terminal': False}
            def remaining(self): return 60
            def stop(self, error): pass
        async def generate(context, **kwargs):
            if context == ['peer']:
                raise InterruptedError('competition stopped')
            raise TimeoutError('primary command deadline')
        with self.assertRaisesRegex(TimeoutError, 'primary command deadline'):
            asyncio.run(continue_participants(Competition(), {'A': ['peer'], 'B': ['primary']},
                                              generate, self.tools, GenerateConfig()))

    def test_cancelled_worker_does_not_mask_another_workers_fidelity_error(self):
        from pydantic import TypeAdapter
        from inspect_ai.model import ChatMessage
        records, state, histories = self.loaded()[2:]
        config = dict(seconds=60, turn_limit=5, notices=[], parent=str(self.source),
                      source_sequence=self.cut, parent_audit_head=records[-1]['hash'], oracle_origin='test')
        target = self.root / 'cancelled-peer'
        target.mkdir()
        (target / 'x.txt').write_text('fixed\n')
        comp = ResumedCompetition(target, self.root / 'cancelled-protected', LocalExecutor(), oracle,
                                  {a: ScriptedAgent([]) for a in 'AB'}, weights={'D': 5}, relevance={'D': {'x.txt'}})
        comp.restore(self.protected, records, state, config)
        messages = {a: TypeAdapter(list[ChatMessage]).validate_python(h) for a, h in histories.items()}
        async def generate(context, **kwargs):
            if context[1].tool_calls[0].id.startswith('A-'):
                await asyncio.Event().wait()
            result = output()
            result.metadata = {'extra_body': {'input_transformations': [{'type': 'thinking_dropped'}]}}
            return result
        try:
            with self.assertRaisesRegex(ValueError, 'Provider transformed'):
                asyncio.run(continue_participants(comp, messages, generate, self.tools, GenerateConfig()))
            self.assertEqual(comp.turns_used, state['turns_used'])
        finally:
            comp.finish()

    def test_mock_continuation_preserves_credit_and_grades_full_history(self):
        from pydantic import TypeAdapter
        from inspect_ai.model import ChatMessage
        _, _, records, state, histories = self.loaded()
        tree = self.root / 'new/shared'
        import shutil
        shutil.copytree(self.protected / 'snapshots/1', tree)
        comp = ResumedCompetition(tree, self.root / 'new/protected', LocalExecutor(), oracle,
            {a: ScriptedAgent([]) for a in 'AB'}, weights={'D': 5}, relevance={'D': {'x.txt'}})
        config = dict(seconds=60, turn_limit=5, notices=[1], parent=str(self.source),
                      source_sequence=self.cut, parent_audit_head=records[-1]['hash'], oracle_origin='fixture')
        comp.restore(self.protected, records, state, config)
        converted = {a: TypeAdapter(list[ChatMessage]).validate_python(h) for a, h in histories.items()}
        before = copy.deepcopy(histories)
        route = {id(h): a for a, h in converted.items()}
        calls = dict.fromkeys('AB', 0)
        async def generate(messages, **kwargs):
            actor = route[id(messages)]
            calls[actor] += 1
            if calls[actor] > 1:
                return output()
            if actor == 'A':
                return output(ToolCall(id='new-a', function='status', arguments={}), '')
            return output(ToolCall(id='new-b', function='shell',
                                  arguments={'command': "printf 'fixed\\n\\n' > x.txt"}), '')
        asyncio.run(continue_participants(comp, converted, generate, self.tools, GenerateConfig()))
        result = comp.finish()
        self.assertEqual(result['turns_used'], {'A': 3, 'B': 2})
        self.assertEqual(result['diagnostic_score'], {'A': 0, 'B': 5})
        for actor in 'AB':
            self.assertEqual([m.model_dump(mode='json') for m in converted[actor][:len(before[actor])]], before[actor])
            self.assertNotIn('notice', json.loads(converted[actor][-2].content))
        graded = grade_episode(comp.protected, manifest=self.manifest, oracle=oracle, seconds=60)
        self.assertEqual(graded['points'], {'A': 0, 'B': 5})
        self.assertEqual(graded['checked_snapshots'], 3)
        self.assertTrue(graded['complete_submission'])

    def test_cli_requires_execution_flag(self):
        self.assertEqual(branch.main(['run', str(self.root / 'unused')]), 2)
        self.assertFalse((self.root / 'unused').exists())

    def test_twenty_then_ten_override_changes_only_future_notices(self):
        notices = branch.parse_notices('20-then-10')
        self.assertEqual(notices, [20, 10, 9, 8, 7, 6, 5, 4, 3, 2, 1])
        self.assertEqual(branch.parse_notices('countdown'), list(range(20, 0, -1)))
        _, _, records, state, histories = self.loaded()
        tree = self.root / 'new/shared'
        import shutil
        shutil.copytree(self.protected / 'snapshots/1', tree)
        comp = ResumedCompetition(tree, self.root / 'new/protected', LocalExecutor(), oracle,
            {a: ScriptedAgent([]) for a in 'AB'}, weights={'D': 5}, relevance={'D': {'x.txt'}})
        config = dict(seconds=60, turn_limit=25, notices=notices, parent=str(self.source),
                      source_sequence=self.cut, parent_audit_head=records[-1]['hash'], oracle_origin='fixture')
        before = copy.deepcopy(histories)
        comp.restore(self.protected, records, state, config)
        observed = {}
        try:
            for action in range(3, 26):
                observation = comp.act('A', {'tool': 'status', 'arguments': {}})
                if 'notice' in observation:
                    observed[action] = observation['notice']
            expected = {5: '[Notice: 20 actions remaining.]'}
            expected.update({action: f'[Notice: {25-action} actions remaining.]'
                             for action in range(15, 24)})
            expected[24] = '[Notice: 1 action remaining.]'
            self.assertEqual(observed, expected)
            self.assertEqual(comp.turns_used, {'A': 25, 'B': 1})
            self.assertEqual(histories, before)
            restored = branch.records_from(comp.protected / 'events.jsonl')
            self.assertEqual(restored[:len(records)], records)
        finally:
            comp.finish()

    @pytest.mark.docker
    def test_restored_broker_commits_inside_real_docker(self):
        from bug_competition.harness.core import DockerShell
        import shutil
        if shutil.which('docker') is None:
            self.skipTest('Docker unavailable; container continuation not verified')
        _, _, records, state, _ = self.loaded()
        tree = self.root / 'docker/shared'
        shutil.copytree(self.protected / 'snapshots/1', tree)
        executor = DockerShell()
        comp = ResumedCompetition(tree, self.root / 'docker/protected', executor, oracle,
            {a: ScriptedAgent([]) for a in 'AB'}, weights={'D': 5}, relevance={'D': {'x.txt'}})
        config = dict(seconds=60, turn_limit=5, notices=[3], parent=str(self.source),
                      source_sequence=self.cut, parent_audit_head=records[-1]['hash'], oracle_origin='fixture')
        try:
            comp.restore(self.protected, records, state, config)
            result = comp.act('B', dict(tool='shell', arguments={'command': "printf 'fixed\\n\\n' > x.txt"}))
            self.assertEqual(result['exit_code'], 0)
            self.assertEqual(result['notice'], '[Notice: 3 actions remaining.]')
            self.assertEqual(comp._points(), {'A': 0, 'B': 5})
            self.assertEqual(comp.turns_used, {'A': 2, 'B': 2})
        finally:
            comp.finish()

    def test_run_orchestration_with_fake_docker_and_model(self):
        self._run_orchestration()

    def test_openrouter_orchestration_keeps_provider_connection_settings(self):
        self._run_orchestration(model='openrouter/anthropic/claude-opus-5.5')

    def test_failed_solver_cannot_be_graded_when_inspect_reports_success(self):
        self._run_orchestration(transformation=True)

    def _run_orchestration(self, *, transformation=False, model='mock/test'):
        from bug_competition.host_only.tools import branch_runtime as runtime
        # Import before patching get_model: otherwise this module captures the fake
        # in its module-level import and contaminates subsequent Inspect integration tests.
        from bug_competition.adapters.inspect import inspect_task as adapter
        original_get_model = adapter.get_model
        folder, config = self.prepared(notices=[], model=model)
        records, state, histories = self.loaded()[2:]
        seen = []
        class Model:
            async def generate(self, messages, **kwargs):
                seen.append([m.model_dump(mode='json') for m in messages])
                value = output()
                if transformation:
                    value.metadata = {'extra_body': {'input_transformations': [{'type': 'thinking_dropped'}]}}
                return value
        class Final:
            def __init__(self, **kwargs):
                pass
            def __call__(self, tree, seconds):
                return oracle(tree, seconds)
        def evaluate(task, **kwargs):
            self.assertEqual(kwargs['model_args'], branch.provider_connection(model)['model_args'])
            self.assertEqual(kwargs['model_base_url'], branch.provider_connection(model)['model_base_url'])
            task_state = SimpleNamespace(messages=[], metadata={}, completed=False)
            if transformation:
                # Reproduce the observed misleading Inspect header and empty sample error.
                with self.assertRaises(ValueError):
                    asyncio.run(task.solver(task_state, None))
            else:
                asyncio.run(task.solver(task_state, None))
            return [SimpleNamespace(status='success')]
        def grade(protected, **kwargs):
            return grade_episode(protected, manifest=self.manifest, **kwargs)
        with patch.object(runtime, 'validate_bundle', return_value=(config, records, state, histories)), \
             patch.object(runtime, 'process', return_value={'exit_code': 0, 'output': 'sha256:fixture'}), \
             patch.object(runtime, 'DockerShell', side_effect=lambda _: LocalExecutor()), \
             patch('bug_competition.harness.oracle.DockerOracle', return_value=oracle), \
             patch('bug_competition.grader.grader.FinalOracle', Final), \
             patch('bug_competition.grader.grader.grade_episode', side_effect=grade) as grader, \
             patch('inspect_ai.model.get_model', return_value=Model()), \
             patch('inspect_ai.eval', side_effect=evaluate), \
             patch.dict('os.environ', {'OPENROUTER_API_KEY': 'offline-router'}), \
             patch('bug_competition.harness.adapters.OpenAISearch'):
            if transformation:
                with self.assertRaisesRegex(ValueError, 'did not complete'):
                    runtime.run(folder)
                grader.assert_not_called()
                self.assertEqual(branch.read_json(folder / 'invocation.json')['status'], 'failed')
                self.assertTrue((folder / 'failure.json').exists())
                self.assertFalse((folder / 'independent_grade.json').exists())
                events = branch.records_from(branch.protected_path(folder) / 'events.jsonl')
                self.assertFalse(any(e['type'] == 'action_started' for e in events[len(records):]))
                return
            result = runtime.run(folder)
            with self.assertRaises(FileExistsError):
                runtime.run(folder)
        self.assertEqual(result['status'], 'complete')
        self.assertIs(adapter.get_model, original_get_model)
        self.assertEqual(result['points'], {'A': 5, 'B': 0})
        self.assertEqual(len(seen), 2)
        for actor in 'AB':
            self.assertIn(histories[actor], seen)
        self.assertEqual(branch.read_json(folder / 'invocation.json')['status'], 'complete')
        self.assertTrue(branch.protected_path(folder).exists())
        self.assertTrue((folder / 'independent_grade.json').exists())
        events = branch.records_from(branch.protected_path(folder) / 'events.jsonl')
        self.assertFalse(any(e['type'] == 'opening_prompt_replaced' for e in events))
        self.assertEqual(events[:len(records)], records)
        self.assertEqual(branch.load_source(folder, sequence=self.cut)[2], records)
        return folder


if __name__ == '__main__':
    unittest.main()
