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
        self.histories = {a: [ChatMessageUser(content='Inspect and repair.')] for a in 'AB'}
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

    def prepared(self, name='prepared', **kwargs):
        contract = dict(model='mock/test', tools=[t.model_dump(mode='json') for t in self.tools], config={})
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
        self.assertEqual(other['notices'], [4, 3, 2, 1])
        self.assertEqual((folder / 'checkpoint/snapshots/1/x.txt').read_text(), 'fixed\n')
        self.assertFalse((folder / 'checkpoint/snapshots/2').exists())
        with patch.object(branch, 'manifest_weights', return_value={'D': 5}), \
             patch.object(branch, 'manifest_files', return_value={'D': {'x.txt'}}):
            self.assertEqual(branch.validate_bundle(folder)[2]['owners'], {'D': 'A'})
        self.assertEqual(before, (self.protected / 'events.jsonl').read_bytes())
        with self.assertRaisesRegex(ValueError, 'already exists'):
            self.prepared()

    def test_changed_runtime_rejected(self):
        folder, _ = self.prepared()
        with patch.object(branch, 'runtime_files', return_value={}):
            with self.assertRaisesRegex(ValueError, 'Runtime changed'):
                branch.validate_bundle(folder)

    def test_missing_original_probes_needs_explicit_policy(self):
        contract = dict(model='mock/test', tools=[], config={})
        with patch.object(branch, 'manifest_weights', return_value={'D': 5}), \
             patch.object(branch, 'manifest_files', return_value={'D': {'x.txt'}}), \
             patch.object(branch, 'archived_contract', return_value=contract):
            with self.assertRaisesRegex(ValueError, 'not saved'):
                branch.prepare(self.source, self.root / 'nope', sequence=self.cut)
        self.assertFalse((self.root / 'nope').exists())

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
        from bug_competition.host_only.tools import branch_runtime as runtime
        # Import before patching get_model: otherwise this module captures the fake
        # in its module-level import and contaminates subsequent Inspect integration tests.
        from bug_competition.adapters.inspect import inspect_task as adapter
        original_get_model = adapter.get_model
        folder, config = self.prepared(notices=[])
        records, state, histories = self.loaded()[2:]
        seen = []
        class Model:
            async def generate(self, messages, **kwargs):
                seen.append([m.model_dump(mode='json') for m in messages])
                return output()
        class Final:
            def __init__(self, **kwargs):
                pass
            def __call__(self, tree, seconds):
                return oracle(tree, seconds)
        def evaluate(task, **kwargs):
            task_state = SimpleNamespace(messages=[], metadata={}, completed=False)
            asyncio.run(task.solver(task_state, None))
            return [SimpleNamespace(status='success')]
        def grade(protected, **kwargs):
            return grade_episode(protected, manifest=self.manifest, **kwargs)
        with patch.object(runtime, 'validate_bundle', return_value=(config, records, state, histories)), \
             patch.object(runtime, 'process', return_value={'exit_code': 0, 'output': 'sha256:fixture'}), \
             patch.object(runtime, 'DockerShell', side_effect=lambda _: LocalExecutor()), \
             patch('bug_competition.harness.oracle.DockerOracle', return_value=oracle), \
             patch('bug_competition.grader.grader.FinalOracle', Final), \
             patch('bug_competition.grader.grader.grade_episode', side_effect=grade), \
             patch('inspect_ai.model.get_model', return_value=Model()), \
             patch('inspect_ai.eval', side_effect=evaluate):
            result = runtime.run(folder)
            with self.assertRaises(FileExistsError):
                runtime.run(folder)
        self.assertEqual(result['status'], 'complete')
        self.assertIs(adapter.get_model, original_get_model)
        self.assertEqual(result['points'], {'A': 5, 'B': 0})
        self.assertEqual(len(seen), 2)
        self.assertIn(histories['A'], seen)
        self.assertIn(histories['B'], seen)
        self.assertEqual(branch.read_json(folder / 'invocation.json')['status'], 'complete')
        self.assertTrue(branch.protected_path(folder).exists())
        self.assertTrue((folder / 'independent_grade.json').exists())


if __name__ == '__main__':
    unittest.main()
