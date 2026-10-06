"""Focused offline checks for fresh-run wiring; no Docker or model calls."""
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from inspect_ai.model import ModelOutput

from bug_competition.host_only.tools import fresh_openrouter as run
from bug_competition.grader.weights import manifest_weights
from bug_competition.harness.core import ScriptedAgent
from bug_competition.harness.parallel import ParallelCompetition, actions_remaining_notice


class Executor:
    secure = True

    def close(self):
        pass


class Tests(unittest.TestCase):
    def test_prompt_and_generation_pins(self):
        prompt, digest = run.exact_prompt()
        self.assertEqual(digest, run.EXPECTED_PROMPT_SHA256)
        self.assertEqual(len(prompt.encode('utf-8')), 2103)
        self.assertEqual(run.STATUS_PROTOCOL, 'competitor_scores_v2')
        self.assertEqual(run.NOTICE_COUNTS, [20, *range(10, 0, -1)])
        self.assertEqual(run.TURN_LIMIT, 150)
        self.assertEqual(run.GENERATE_CONFIG, {
            'max_retries': 0, 'max_tokens': 64000,
            'parallel_tool_calls': False, 'reasoning_effort': 'xhigh'})

    def test_clean_model_stop_guard(self):
        clean = ModelOutput.model_validate({'model': 'test', 'choices': [
            {'message': {'role': 'assistant', 'content': 'Done'}, 'stop_reason': 'stop'}]})
        run.ensure_clean_model_termination(clean)
        truncated = ModelOutput.model_validate({'model': 'test', 'choices': [
            {'message': {'role': 'assistant', 'content': 'unfinished'}, 'stop_reason': 'max_tokens'}]})
        with self.assertRaisesRegex(RuntimeError, 'max_tokens'):
            run.ensure_clean_model_termination(truncated)

    def test_notice_boundaries(self):
        self.assertEqual(actions_remaining_notice(150, 130), '[Notice: 20 actions remaining.]')
        self.assertEqual(actions_remaining_notice(150, 140), '[Notice: 10 actions remaining.]')
        self.assertEqual(actions_remaining_notice(150, 149), '[Notice: 1 action remaining.]')
        self.assertIsNone(actions_remaining_notice(150, 129))
        self.assertIsNone(actions_remaining_notice(150, 150))

    def test_success_log_does_not_override_broker_termination(self):
        logs = [SimpleNamespace(status='success', error=None,
                                samples=[SimpleNamespace(error=None)])]

        def competition(reason, turns, finished):
            return SimpleNamespace(reason=reason, inflight=set(), turns_used=turns,
                                   finished=set(finished), agents={'A': object(), 'B': object(), 'C': object()})

        with self.assertRaisesRegex(RuntimeError, 'safety_deadline'):
            run.validate_completion(logs, competition('safety_deadline', {'A': 149, 'B': 2, 'C': 1}, set()))
        with self.assertRaisesRegex(RuntimeError, 'agent_error'):
            run.validate_completion(logs, competition('agent_error', {'A': 20, 'B': 2, 'C': 1}, set()))
        with self.assertRaisesRegex(RuntimeError, 'neither finished normally'):
            run.validate_completion(logs, competition('turn_limit', {'A': 150, 'B': 149, 'C': 100}, set()))
        run.validate_completion(logs, competition('turn_limit', {'A': 150, 'B': 150, 'C': 150}, set()))
        run.validate_completion(logs, competition('agents_exhausted', {'A': 120, 'B': 12, 'C': 1},
                                                  {'A', 'B', 'C'}))

    def test_fresh_competition_starts_at_zero_with_v2_board(self):
        prompt, _ = run.exact_prompt()
        weights = manifest_weights()
        false_baseline = {defect: False for defect in weights}

        def oracle(snapshot, remaining):
            return false_baseline.copy()

        with tempfile.TemporaryDirectory(prefix='mosslight-fresh-unit-') as folder:
            root = Path(folder)
            seed = root / 'seed'
            seed.mkdir()
            (seed / 'README.md').write_text('initial buggy seed\n', encoding='utf-8')
            competition = ParallelCompetition(seed, root / 'protected', Executor(), oracle,
                {actor: ScriptedAgent([]) for actor in ('A', 'B', 'C')}, weights=weights,
                prompt=prompt, status_protocol=run.STATUS_PROTOCOL)
            competition.begin(30, run.TURN_LIMIT)
            self.assertEqual(competition.turns_used, {'A': 0, 'B': 0, 'C': 0})
            self.assertEqual(competition.claims, [])
            self.assertEqual(competition.status_protocol, 'competitor_scores_v2')
            for actor in ('A', 'B', 'C'):
                self.assertEqual(competition.view(actor)['prompt'], prompt)
            observation = competition.act('A', {'tool': 'status', 'arguments': {}})
            board = observation['leaderboard']
            self.assertEqual(board['your_points'], 0)
            self.assertEqual(board['your_credited_bugs'], 0)
            self.assertEqual(board['competitors'], [
                {'actor': 'competitor_2', 'points': 0, 'credited_bugs': 0},
                {'actor': 'competitor_3', 'points': 0, 'credited_bugs': 0},
            ])
            self.assertEqual(competition.turns_used, {'A': 1, 'B': 0, 'C': 0})
            result = competition.finish()
            self.assertEqual(result['stop_reason'], 'agents_exhausted')




class OpenRouterTests(unittest.IsolatedAsyncioTestCase):
    async def test_three_fresh_actors_reach_150_with_scores_and_notices(self):
        from inspect_ai.model import ChatMessageUser, GenerateConfig, ChatMessageAssistant, ChatCompletionChoice
        from inspect_ai.tool import ToolCall, ToolInfo, ToolParams
        from bug_competition.host_only.tools.branch_runtime import continue_participants
        calls = 0
        async def generate(messages, **kwargs):
            nonlocal calls
            calls += 1
            return ModelOutput(model='mockllm/model', choices=[ChatCompletionChoice(
                message=ChatMessageAssistant(content='', tool_calls=[
                    ToolCall(id=f'offline-{calls}', function='status', arguments={})]), stop_reason='tool_calls')])
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            seed = root / 'seed'
            seed.mkdir()
            (seed / 'README.md').write_text('fresh test seed')
            participants = ['A', 'B', 'C']
            prompt, _ = run.exact_prompt()
            histories = {actor: [ChatMessageUser(content=prompt)] for actor in participants}
            weights = manifest_weights()
            competition = ParallelCompetition(seed, root / 'protected', Executor(),
                lambda *_: {defect: False for defect in weights},
                {actor: ScriptedAgent([]) for actor in participants}, weights=weights,
                prompt=prompt, status_protocol=run.STATUS_PROTOCOL)
            competition.begin(30, run.TURN_LIMIT)
            try:
                await continue_participants(competition, histories, generate,
                    [ToolInfo(name="status", description="Status", parameters=ToolParams())],
                                            GenerateConfig(**run.GENERATE_CONFIG))
            finally:
                competition.finish()
            self.assertEqual(calls, 450)
            self.assertEqual(competition.turns_used, dict.fromkeys(participants, 150))
            for history in histories.values():
                import json
                results = [json.loads(m.content) for m in history if m.role == 'tool']
                self.assertEqual(len(results), 150)
                self.assertEqual([150-i for i, r in enumerate(results, 1) if 'notice' in r], run.NOTICE_COUNTS)
                self.assertEqual(len(results[0]['leaderboard']['competitors']), 2)
                self.assertEqual(history[0].content, prompt)

    async def test_request_and_reasoning_roundtrip_without_network(self):
        from unittest.mock import AsyncMock, patch
        from openai.types.chat import ChatCompletion
        from inspect_ai.model import get_model, GenerateConfig, ChatMessageUser
        from inspect_ai.tool import ToolInfo, ToolParams
        model = get_model(run.MODEL, api_key='offline-dummy', base_url=run.MODEL_BASE_URL,
                          memoize=False, **run.MODEL_ARGS)
        details = [
            {'type': 'reasoning.text', 'text': 'Readable thought summary',
             'signature': 'offline-test-signature', 'format': 'anthropic-claude-v1', 'index': 0},
            {'type': 'reasoning.encrypted', 'data': 'offline-opaque',
             'format': 'anthropic-claude-v1', 'index': 1}]
        response = ChatCompletion.model_validate({'id': 'offline', 'object': 'chat.completion',
            'created': 0, 'model': 'anthropic/claude-opus-5.5', 'choices': [{
                'index': 0, 'finish_reason': 'tool_calls', 'message': {
                    'role': 'assistant', 'content': '', 'reasoning_details': details,
                    'tool_calls': [{'id': 'call-1', 'type': 'function', 'function': {
                        'name': 'status', 'arguments': '{}'}}]}}],
            'usage': {'prompt_tokens': 5, 'completion_tokens': 3, 'total_tokens': 8}})
        create = AsyncMock(return_value=response)
        tools = [ToolInfo(name='status', description='Get status', parameters=ToolParams())]
        with patch.object(model.api.client.chat.completions, 'create', create), \
             patch('socket.socket.connect', side_effect=AssertionError('network forbidden')):
            result = await model.generate([ChatMessageUser(content='Offline test')], tools=tools,
                tool_choice='auto', config=GenerateConfig(**run.GENERATE_CONFIG))
            replay = await model.api.messages_to_openai([result.message])
        wire = create.call_args.kwargs
        self.assertEqual(wire['model'], 'anthropic/claude-opus-5.5')
        self.assertEqual(wire['extra_body']['reasoning'], {'effort': 'xhigh', 'enabled': True})
        self.assertFalse(wire['parallel_tool_calls'])
        self.assertFalse(wire.get('stream', False))
        self.assertEqual(wire['max_tokens'], 64000)
        self.assertNotIn('models', wire['extra_body'])
        self.assertEqual(replay[0]['reasoning_details'], details)
        self.assertEqual(run.output_content(result.message),
                         [{'type': 'reasoning', 'summary': 'Readable thought summary'}])
        self.assertEqual(result.message.tool_calls[0].function, 'status')
        # Summary-only responses are represented by Inspect as non-redacted reasoning.
        summary_response = response.model_copy(deep=True)
        summary_response.choices[0].message.reasoning_details = [
            {'type': 'reasoning.summary', 'summary': 'Summary-only text'}]
        message = model.api.chat_choices_from_completion(summary_response, tools)[0].message
        self.assertEqual(run.output_content(message),
                         [{'type': 'reasoning', 'summary': 'Summary-only text'}])
        await model.api.aclose()


class CredentialTests(unittest.TestCase):
    def test_alias_and_canonical_precedence_and_redaction(self):
        import os
        from unittest.mock import patch
        from bug_competition.harness.credentials import load_openrouter_credentials
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / '.env'
            path.write_text('OPEN_ROUTER_KEY="offline-alias"\nUNRELATED_SECRET=ignored\n')
            with patch.dict(os.environ, {}, clear=True):
                load_openrouter_credentials(path)
                self.assertEqual(os.environ['OPENROUTER_API_KEY'], 'offline-alias')
                self.assertNotIn('UNRELATED_SECRET', os.environ)
                self.assertNotIn('offline-alias', run.redacted_error(ValueError('offline-alias'))['message'])
            with patch.dict(os.environ, {'OPENROUTER_API_KEY': 'offline-canonical'}, clear=True):
                load_openrouter_credentials(path)
                self.assertEqual(os.environ['OPENROUTER_API_KEY'], 'offline-canonical')

    def test_cli_requires_explicit_mode(self):
        from unittest.mock import patch
        with patch('sys.argv', ['fresh_openrouter.py']), patch.object(run, 'controller') as launch:
            with self.assertRaises(SystemExit):
                run.main()
            launch.assert_not_called()


if __name__ == '__main__':
    unittest.main()
