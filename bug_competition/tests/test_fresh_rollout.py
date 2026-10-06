"""Offline provider-selection and native replay checks; never launch a rollout."""
import copy
import io
import os
import tempfile
import unittest
from contextlib import ExitStack, redirect_stderr, redirect_stdout
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from bug_competition.host_only.tools import fresh_rollout as run


class ProviderState:
    def setUp(self):
        run.configure_provider('openrouter')
        run.configure_scope(smoke=False)
        self.addCleanup(run.configure_provider, 'openrouter')
        self.addCleanup(run.configure_scope, smoke=False)


class ProviderTests(ProviderState, unittest.TestCase):
    def test_selection_is_explicit_and_restores_openrouter_settings(self):
        original = copy.deepcopy(run.launch_settings())
        run.configure_provider('anthropic')
        self.assertEqual(run.PROVIDER, 'anthropic')
        self.assertEqual(run.MODEL, 'anthropic/claude-opus-5-5')
        self.assertEqual(run.MODEL_ARGS, {'max_retries': 0})
        self.assertEqual(run.MODEL_BASE_URL, 'https://api.anthropic.com')
        self.assertEqual(run.GENERATE_CONFIG, original['generation_config'])
        with self.assertRaises(ValueError):
            run.configure_provider('automatic')
        self.assertEqual(run.PROVIDER, 'anthropic')
        run.configure_provider('openrouter')
        self.assertEqual(run.launch_settings(), original)

    def test_smoke_scope_is_explicit_and_keeps_full_run_default(self):
        self.assertEqual((run.PARTICIPANTS, run.TURN_LIMIT, run.SMOKE_MODE), (3, 150, False))
        full = run.launch_settings()
        self.assertEqual((full['participants'], full['total_action_limit_per_actor']), (3, 150))
        run.configure_scope(smoke=True)
        smoke = run.launch_settings()
        self.assertEqual((smoke['smoke_mode'], smoke['participants'],
                          smoke['total_action_limit_per_actor']), (True, 2, 1))
        run.configure_scope(smoke=False)
        self.assertEqual((run.PARTICIPANTS, run.TURN_LIMIT, run.SMOKE_MODE), (3, 150, False))

    def test_worker_gate_requires_recorded_two_by_one_smoke_settings(self):
        run.configure_provider('anthropic')
        run.configure_scope(smoke=True)
        with tempfile.TemporaryDirectory() as folder, \
                patch.object(run, 'OUT', Path(folder)), \
                patch.dict(os.environ, {'MOSSLIGHT_RUN_ID': 'run-smoke',
                    'MOSSLIGHT_STAGE_ROOT': '/tmp/stage-smoke'}, clear=True):
            invocation = {'run_label': 'run-smoke', 'neutral_staging_parent': '/tmp/stage-smoke',
                          **run.launch_settings()}
            run.write_json(run.OUT / 'invocation.json', invocation)
            run.validate_worker_gate()
            invocation['total_action_limit_per_actor'] = 150
            run.write_json(run.OUT / 'invocation.json', invocation)
            with self.assertRaisesRegex(RuntimeError, 'Worker launch settings differ'):
                run.validate_worker_gate()
            invocation['total_action_limit_per_actor'] = 1
            invocation['participants'] = 3
            run.write_json(run.OUT / 'invocation.json', invocation)
            with self.assertRaisesRegex(RuntimeError, 'Worker launch settings differ'):
                run.validate_worker_gate()

    def test_selected_provider_requires_its_own_credentials(self):
        with tempfile.TemporaryDirectory() as folder:
            env_file = Path(folder) / '.env'
            env_file.write_text('OPEN_ROUTER_KEY=offline-router\nBRAVE_SEARCH_API_KEY=offline-search\n')
            with patch.dict(os.environ, {'MOSSLIGHT_ENV_FILE': str(env_file)}, clear=True):
                run.configure_provider('anthropic')
                with self.assertRaisesRegex(RuntimeError, 'anthropic credential unavailable'):
                    run.credentials_preflight()
                run.configure_provider('openrouter')
                self.assertEqual(run.credentials_preflight(),
                                 {'openrouter_available': True, 'search_available': True})
            env_file.write_text('ANTHROPIC_API_KEY=offline-native\nOPENAI_API_KEY=offline-search\n')
            with patch.dict(os.environ, {'MOSSLIGHT_ENV_FILE': str(env_file)}, clear=True):
                run.configure_provider('openrouter')
                with self.assertRaisesRegex(RuntimeError, 'openrouter credential unavailable'):
                    run.credentials_preflight()
                run.configure_provider('anthropic')
                self.assertEqual(run.credentials_preflight(),
                                 {'anthropic_available': True, 'search_available': True})
                self.assertNotIn('offline-native', run.redacted_error(ValueError('offline-native'))['message'])

    def test_maintained_cli_requires_provider_and_mode(self):
        for args in (['--offline-check'], ['--provider', 'anthropic']):
            with self.subTest(args=args), patch('sys.argv', ['fresh_rollout.py', *args]), \
                    patch.object(run, 'controller') as launch, redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit):
                    run.main()
                launch.assert_not_called()
        with patch('sys.argv', ['fresh_rollout.py', '--provider', 'anthropic', '--smoke', '--offline-check']), \
                patch.object(run, 'offline_check', return_value=0) as check:
            self.assertEqual(run.main(), 0)
            check.assert_called_once_with()
            self.assertEqual(run.PROVIDER, 'anthropic')
            self.assertEqual((run.PARTICIPANTS, run.TURN_LIMIT), (2, 1))
        with patch('sys.argv', ['fresh_openrouter.py', '--offline-check']), \
                patch.object(run, 'offline_check', return_value=0):
            self.assertEqual(run.main(default_provider='openrouter'), 0)
            self.assertEqual(run.PROVIDER, 'openrouter')

    def test_prepared_provider_and_runtime_drift_fail_before_seed_or_model(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(run, 'OUT', Path(folder)), \
                patch.object(run, 'IMAGE_ID', 'sha256:prepared'), \
                patch.object(run, 'runtime_hashes', return_value={'runner': 'original'}), \
                patch.object(run, 'check_seed') as seed, \
                patch.object(run, 'image_preflight') as docker, \
                patch('subprocess.Popen') as launch:
            prepared = {'status': 'ready', **copy.deepcopy(run.launch_settings()),
                        'image': {'image_id': run.IMAGE_ID},
                        'runtime_file_sha256': {'runner': 'original'}}
            run.write_json(run.OUT / 'preflight.json', prepared)
            run.configure_provider('anthropic')
            with self.assertRaisesRegex(RuntimeError, 'setting changed: provider'):
                run.controller()
            run.configure_provider('openrouter')
            prepared['runtime_file_sha256'] = {'runner': 'changed'}
            run.write_json(run.OUT / 'preflight.json', prepared)
            with self.assertRaisesRegex(RuntimeError, 'runtime files changed'):
                run.controller()
            seed.assert_not_called()
            docker.assert_not_called()
            launch.assert_not_called()

    def test_controller_forwards_native_provider_and_records_shell_timeout(self):
        run.configure_provider('anthropic')
        run.configure_scope(smoke=True)
        with tempfile.TemporaryDirectory() as folder, ExitStack() as stack:
            root = Path(folder)
            output = root / 'output'
            output.mkdir()
            stage = root / 'stage'
            stage.mkdir()
            run.write_json(output / 'preflight.json', {'status': 'ready'})
            run.write_json(output / 'seed_inventory.json', {'tree_sha256': 'offline-seed'})
            stack.enter_context(patch.object(run, 'OUT', output))
            stack.enter_context(patch.object(run, 'validate_prepared', return_value={}))
            stack.enter_context(patch.object(run, 'image_preflight', return_value={}))
            stack.enter_context(patch.object(run, 'credentials_preflight',
                                           return_value={'anthropic_available': True, 'search_available': True}))
            stack.enter_context(patch.object(run, 'runtime_hashes', return_value={}))
            stack.enter_context(patch.object(run, 'sha_file', return_value='offline-hash'))
            staging = stack.enter_context(patch.object(run.tempfile, 'mkdtemp', return_value=str(stage)))
            cleanup = stack.enter_context(patch.object(run.subprocess, 'run'))
            cleanup.return_value.stdout = ''
            launch = stack.enter_context(patch.object(run.subprocess, 'Popen'))
            launch.return_value.pid = 123
            launch.return_value.returncode = 0
            stack.enter_context(redirect_stdout(io.StringIO()))
            self.assertEqual(run.controller(), 0)
            staging.assert_called_once_with(prefix='mosslight-fresh-')
            launch.assert_called_once()
            command = launch.call_args.args[0]
            self.assertEqual(command[command.index('--provider') + 1], 'anthropic')
            self.assertIn('--worker', command)
            self.assertIn('--smoke', command)
            invocation = run.load_json(output / 'invocation.json')
            self.assertEqual(invocation['provider'], 'anthropic')
            self.assertEqual(invocation['model'], 'anthropic/claude-opus-5-5')
            self.assertEqual((invocation['participants'], invocation['action_limit_per_participant']), (2, 1))
            self.assertEqual((invocation['smoke_mode'], invocation['total_action_limit_per_actor']), (True, 1))
            self.assertEqual(invocation['shell_seconds'], 180)
            self.assertEqual(invocation['model_args'], {'max_retries': 0})
            self.assertEqual(invocation['status'], 'worker_finished')

    def test_image_preflight_resolves_build_and_keeps_resource_checks(self):
        def response(value, code=0):
            return SimpleNamespace(stdout=value, returncode=code)
        with patch.object(run, 'IMAGE_ID', 'reviewer-tools:local'), \
                patch.object(run.subprocess, 'run', side_effect=[
                    response('sha256:built'), response('29.0 16000000000 8'), response('')]) as docker:
            self.assertEqual(run.image_preflight()['image_id'], 'sha256:built')
            self.assertEqual(docker.call_args_list[0].args[0][-1], 'reviewer-tools:local')
        with patch.object(run, 'IMAGE_ID', 'sha256:prepared'), \
                patch.object(run.subprocess, 'run', return_value=response('sha256:changed')):
            with self.assertRaisesRegex(RuntimeError, 'different ID'):
                run.image_preflight()
        with patch.object(run, 'IMAGE_ID', 'reviewer-tools:local'), \
                patch.object(run.subprocess, 'run', side_effect=[
                    response('sha256:built'), response('29.0 8000000000 4')]):
            with self.assertRaisesRegex(RuntimeError, 'below rollout reservation'):
                run.image_preflight()
        with patch.object(run, 'IMAGE_ID', 'reviewer-tools:local'), \
                patch.object(run.subprocess, 'run', side_effect=[
                    response('sha256:built'), response('29.0 16000000000 8'), response('unrelated')]):
            with self.assertRaisesRegex(RuntimeError, 'unrelated active containers'):
                run.image_preflight()

    def test_prepare_records_resolved_image_and_dependency_versions(self):
        from bug_competition.grader.weights import manifest_weights
        with tempfile.TemporaryDirectory() as folder, \
                patch.object(run, 'OUT', Path(folder)), \
                patch.object(run, 'IMAGE_ID', 'reviewer-tools:local'), \
                patch.object(run, 'image_preflight', return_value={'image_id': 'sha256:built'}), \
                patch.object(run, 'credentials_preflight', return_value={}), \
                patch('bug_competition.harness.oracle.DockerOracle') as oracle, \
                patch('socket.socket.connect', side_effect=AssertionError('network forbidden')):
            oracle.return_value.return_value = dict.fromkeys(manifest_weights(), False)
            prepared = run.prepare()
            self.assertEqual(prepared['image']['image_id'], 'sha256:built')
            self.assertEqual(oracle.call_args.args[1], 'sha256:built')
            self.assertEqual(run.validate_prepared(), prepared)
            with patch.object(run, 'IMAGE_ID', 'sha256:changed'):
                with self.assertRaisesRegex(RuntimeError, 'Prepared Docker image changed'):
                    run.validate_prepared()
            with patch.object(run, 'runtime_versions', return_value={}):
                with self.assertRaisesRegex(RuntimeError, 'dependencies changed'):
                    run.validate_prepared()

    def test_offline_check_needs_no_credentials_docker_or_network(self):
        with tempfile.TemporaryDirectory() as folder, \
                patch.object(run, 'ENV_FILE', Path(folder) / 'missing.env'), \
                patch.dict(os.environ, {}, clear=True), \
                patch('socket.socket.connect', side_effect=AssertionError('network forbidden')), \
                patch.object(run.subprocess, 'run', side_effect=AssertionError('Docker forbidden')), \
                patch.object(run.subprocess, 'Popen', side_effect=AssertionError('launch forbidden')):
            for provider in ('anthropic', 'openrouter'):
                run.configure_provider(provider)
                captured = io.StringIO()
                with redirect_stdout(captured):
                    self.assertEqual(run.offline_check(), 0)
                self.assertEqual(run.json.loads(captured.getvalue())['credential_presence'],
                                 {provider + '_available': False, 'search_available': False})

    def test_later_cli_phases_load_prepared_id_and_refuse_new_image(self):
        with tempfile.TemporaryDirectory() as folder, ExitStack() as stack:
            repo = Path(folder)
            output = repo / 'bug_competition/host_only/rollouts/prepared'
            output.mkdir(parents=True)
            run.write_json(output / 'preflight.json', {'image': {'image_id': 'sha256:prepared'}})
            stack.enter_context(patch.object(run, 'REPO', repo))
            stack.enter_context(patch.object(run, 'OUT', None))
            stack.enter_context(patch.object(run, 'IMAGE_ID', run.DEFAULT_IMAGE))
            command = ['fresh_rollout.py', '--provider', 'anthropic', '--output', str(output), '--dry-check']
            with patch('sys.argv', command), patch.object(run, 'dry_check', return_value=0):
                self.assertEqual(run.main(), 0)
                self.assertEqual(run.IMAGE_ID, 'sha256:prepared')
            with patch('sys.argv', [*command, '--image', 'different']), redirect_stderr(io.StringIO()), \
                    self.assertRaises(SystemExit):
                run.main()

    def test_prepare_cli_accepts_external_probes_without_archived_default(self):
        # Small hermetic fixtures exercise path selection and hashing without
        # requiring the historical, host-only archive in a fresh checkout.
        self.assertEqual(run.EXPECTED_LIVE_PROBES_SHA256,
                         '277166d239f0b41799c2fb69869d016201bf417f94c65c2bfdbec35f163ba6b4')
        self.assertEqual(run.EXPECTED_GRADING_PROBES_SHA256,
                         '0323b641ca5988cb0f2ccc0a06feff9966960e318a4c10f8960402cd482ffc03')
        with tempfile.TemporaryDirectory() as folder, ExitStack() as stack:
            root = Path(folder)
            external = root / 'external-probes'
            external.mkdir()
            live, grading = [{'id': 'fixture', 'input': 'live'}], [{'id': 'fixture', 'input': 'grading'}]
            run.write_json(external / 'live_probes.json', live)
            run.write_json(external / 'grading_probes.json', grading)
            stack.enter_context(patch.object(run, 'EXPECTED_LIVE_PROBES_SHA256',
                                           run.sha_file(external / 'live_probes.json')))
            stack.enter_context(patch.object(run, 'EXPECTED_GRADING_PROBES_SHA256',
                                           run.sha_file(external / 'grading_probes.json')))
            repo = root / 'fresh-checkout'
            rollout_root = repo / 'bug_competition/host_only/rollouts'
            rollout_root.mkdir(parents=True)
            output = rollout_root / 'offline-prepare'
            absent_archive = repo / 'bug_competition/host_only/branches/missing-archive'
            env_file = root / 'host.env'
            env_file.write_text('ANTHROPIC_API_KEY=offline-native\nBRAVE_SEARCH_API_KEY=offline-search\n')
            stack.enter_context(patch.object(run, 'REPO', repo))
            stack.enter_context(patch.object(run, 'PROBE_SOURCE', absent_archive))
            stack.enter_context(patch.object(run, 'OUT', None))
            stack.enter_context(patch.object(run, 'ENV_FILE', root / 'missing.env'))
            stack.enter_context(patch.dict(os.environ, {}, clear=True))
            with self.assertRaisesRegex(RuntimeError, '--probes-from DIRECTORY'):
                run.load_pinned_probes()

            def prepare_boundary():
                self.assertEqual(run.PROBE_SOURCE, external.resolve())
                self.assertEqual(run.ENV_FILE, env_file.resolve())
                self.assertEqual(os.environ['MOSSLIGHT_ENV_FILE'], str(env_file.resolve()))
                self.assertEqual(run.OUT, output.resolve())
                self.assertTrue(run.OUT.is_dir())
                self.assertFalse(absent_archive.exists())
                self.assertEqual(run.load_pinned_probes(), (live, grading))
                self.assertEqual(run.credentials_preflight(),
                                 {'anthropic_available': True, 'search_available': True})
                return {'status': 'offline-test'}

            prepare = stack.enter_context(patch.object(run, 'prepare', side_effect=prepare_boundary))
            launch = stack.enter_context(patch.object(run, 'controller'))
            stack.enter_context(patch('sys.argv', ['fresh_rollout.py', '--provider', 'anthropic',
                '--probes-from', str(external), '--env-file', str(env_file),
                '--output', str(output), '--prepare']))
            stack.enter_context(redirect_stdout(io.StringIO()))
            self.assertEqual(run.main(), 0)
            prepare.assert_called_once_with()
            launch.assert_not_called()
            # An explicit directory must still satisfy both pinned digests.
            (external / 'grading_probes.json').write_text('[]')
            with self.assertRaisesRegex(RuntimeError, 'grading probes changed'):
                run.load_pinned_probes()

    def test_worker_gate_binds_provider_and_controller_identity(self):
        run.configure_provider('anthropic')
        invocation = {'run_label': 'offline-run', 'neutral_staging_parent': '/offline-stage',
                      **run.launch_settings()}
        with patch.object(run, 'OUT', Path('/unused')), patch.object(run, 'load_json', return_value=invocation):
            env = {'MOSSLIGHT_RUN_ID': 'offline-run', 'MOSSLIGHT_STAGE_ROOT': '/offline-stage'}
            with patch.dict(os.environ, env, clear=True):
                run.validate_worker_gate()
                run.configure_provider('openrouter')
                with self.assertRaisesRegex(RuntimeError, 'explicit launch controller'):
                    run.validate_worker_gate()
                run.configure_provider('anthropic')
            with patch.dict(os.environ, {}, clear=True):
                with self.assertRaisesRegex(RuntimeError, 'explicit launch controller'):
                    run.validate_worker_gate()


class NativeAnthropicTests(ProviderState, unittest.IsolatedAsyncioTestCase):
    async def test_native_request_and_serialized_reasoning_replay_without_network(self):
        from anthropic.types import Message
        from inspect_ai.model import ChatMessageAssistant, ChatMessageTool, ChatMessageUser, GenerateConfig, get_model
        from inspect_ai.tool import ToolInfo, ToolParams

        run.configure_provider('anthropic')
        model = get_model(run.MODEL, api_key='offline-dummy', base_url=run.MODEL_BASE_URL,
                          memoize=False, **run.MODEL_ARGS)
        self.addAsyncCleanup(model.api.aclose)
        blocks = [
            {'type': 'thinking', 'thinking': 'Readable native thought', 'signature': 'offline-signature'},
            {'type': 'redacted_thinking', 'data': 'offline-redacted-data'},
            {'type': 'tool_use', 'id': 'call-offline', 'name': 'status', 'input': {}},
        ]
        response = Message.model_validate({
            'id': 'msg-offline', 'type': 'message', 'role': 'assistant', 'model': 'claude-opus-5-5',
            'content': blocks, 'stop_reason': 'tool_use', 'stop_sequence': None,
            'usage': {'input_tokens': 5, 'output_tokens': 3,
                      'output_tokens_details': {'thinking_tokens': 2}},
        })
        stream = MagicMock()
        stream.return_value.__aenter__ = AsyncMock(return_value=MagicMock())
        stream.return_value.__aexit__ = AsyncMock(return_value=False)
        tools = [ToolInfo(name='status', description='Get status', parameters=ToolParams())]
        history = [ChatMessageUser(content='Offline native test')]
        with patch.object(model.api.client.messages, 'stream', stream), \
                patch('inspect_ai.model._providers.anthropic._capture_compaction_from_stream',
                      new=AsyncMock(return_value=(response, None))), \
                patch('socket.socket.connect', side_effect=AssertionError('network forbidden')):
            result = await model.generate(history, tools=tools, tool_choice='auto',
                                          config=GenerateConfig(**run.GENERATE_CONFIG))
            # Exercise the same JSON persistence boundary used by trajectory archives.
            restored = ChatMessageAssistant.model_validate_json(result.message.model_dump_json())
            await model.generate([*history, restored,
                                  ChatMessageTool(content='{}', tool_call_id='call-offline', function='status')],
                                 tools=tools, tool_choice='auto', config=GenerateConfig(**run.GENERATE_CONFIG))
        wire = stream.call_args_list[0].kwargs
        self.assertEqual(wire['model'], 'claude-opus-5-5')
        self.assertEqual(wire['max_tokens'], 64000)
        self.assertEqual(wire['output_config']['effort'], 'xhigh')
        self.assertEqual(wire['thinking']['type'], 'adaptive')
        # Installed native adapter omits tool_choice while adaptive thinking is active.
        self.assertNotIn('tool_choice', wire)
        self.assertEqual(model.api.client.max_retries, 0)
        replay = stream.call_args_list[1].kwargs['messages']
        assistant = next(message for message in replay if message['role'] == 'assistant')
        self.assertEqual(assistant['content'][:2], blocks[:2])
        self.assertEqual({key: value for key, value in assistant['content'][2].items()
                          if key != 'cache_control'}, blocks[2])
        self.assertEqual(run.output_content(restored),
                         [{'type': 'reasoning', 'summary': 'Readable native thought'}])
        self.assertEqual(restored.tool_calls[0].function, 'status')


if __name__ == '__main__':
    unittest.main()
