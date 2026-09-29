"""Offline native-wire checks; no model, network, Docker, or archive mutations."""
import asyncio
import copy
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from inspect_ai.model import ContentReasoning
from inspect_ai.model._providers.anthropic import message_block_params
from bug_competition.host_only.tools import branch_rollout as branch


def history(details=None):
    details = details if details is not None else [dict(type='reasoning.text',
        format='anthropic-claude-v1', text='Summary with exact whitespace\n', signature='opaque+/=\n')]
    return [dict(role='user', content='Same prompt'), dict(role='assistant',
        content=[dict(type='reasoning', reasoning='Summary with exact whitespace\n',
            signature=branch.OPENROUTER_REASONING_PREFIX + json.dumps(details)),
            dict(type='text', text='same answer')],
        tool_calls=[dict(id='tool-1', function='status', arguments={}, type='function')]),
        dict(role='tool', content='{"ok":true}', tool_call_id='tool-1', function='status')]


class ProviderTests(unittest.TestCase):
    def test_provider_transport_is_preserved_and_switch_is_explicit(self):
        model = 'openrouter/anthropic/claude-opus-5.5'
        contract = dict(model=model, tools=[], config={'reasoning_effort': 'xhigh'},
                        **branch.provider_connection(model))
        effective, _, _, _ = branch.provider_configuration(contract, {'A': history()}, [])
        self.assertEqual(effective, contract)
        native, _, _, _ = branch.provider_configuration(contract, {'A': history()}, [], 'anthropic')
        self.assertEqual(native['model_args'], {'max_retries': 0})
        self.assertEqual(native['model_base_url'], 'https://api.anthropic.com')
        changed = copy.deepcopy(contract)
        changed['model_args']['stream'] = True
        with self.assertRaisesRegex(ValueError, 'provider setting is unsupported'):
            branch.provider_configuration(changed, {'A': history()}, [])

    def test_continuation_env_file_uses_selected_provider_and_alias(self):
        from bug_competition.harness.credentials import load_model_credentials
        with tempfile.TemporaryDirectory() as folder:
            env_file = Path(folder) / 'credentials.env'
            env_file.write_text('OPEN_ROUTER_KEY=offline-router\nBRAVE_SEARCH_API_KEY=offline-search\n')
            with patch.dict(os.environ, {}, clear=True):
                load_model_credentials('openrouter/anthropic/claude-opus-5.5', env_file)
                self.assertEqual(os.environ['OPENROUTER_API_KEY'], 'offline-router')
                with self.assertRaisesRegex(ValueError, 'ANTHROPIC_API_KEY'):
                    load_model_credentials('anthropic/claude-opus-5-5', env_file)
            with patch.dict(os.environ, {'OPENROUTER_API_KEY': 'offline-existing'}, clear=True):
                load_model_credentials('openrouter/anthropic/claude-opus-5.5', env_file)
                self.assertEqual(os.environ['OPENROUTER_API_KEY'], 'offline-existing')

    def test_native_wire_and_unmodified_archive(self):
        saved = history(); original = copy.deepcopy(saved)
        out = branch.convert_openrouter_history(saved, len(saved))
        self.assertEqual(saved, original)
        self.assertEqual(out[0], saved[0]); self.assertEqual(out[2], saved[2])
        self.assertEqual(out[1]['tool_calls'], saved[1]['tool_calls'])
        self.assertEqual(out[1]['content'][1], saved[1]['content'][1])
        wire = asyncio.run(message_block_params(ContentReasoning.model_validate(out[1]['content'][0])))
        self.assertEqual(wire, [dict(type='thinking', thinking='Summary with exact whitespace\n', signature='opaque+/=\n')])

    def test_redacted_wire_and_order(self):
        details = [dict(type='reasoning.encrypted', format='anthropic-claude-v1', data='opaque-redacted+/='),
            dict(type='reasoning.text', format='anthropic-claude-v1', text='', signature='signed-empty')]
        out = branch.convert_openrouter_history(history(details), 3)
        wire = [asyncio.run(message_block_params(ContentReasoning.model_validate(b)))[0]
                for b in out[1]['content'] if b['type'] == 'reasoning']
        self.assertEqual(wire, [dict(type='redacted_thinking', data='opaque-redacted+/='),
                               dict(type='thinking', thinking='', signature='signed-empty')])

    def test_unknown_unsigned_and_outside_boundary_fail_closed(self):
        for details in [[], [dict(type='reasoning.summary', format='anthropic-claude-v1', summary='no signature')],
                        [dict(type='reasoning.text', format='unknown', text='x', signature='s')],
                        [dict(type='reasoning.text', format='anthropic-claude-v1', text='x')]]:
            with self.subTest(types=[x.get('type') for x in details]), self.assertRaises(ValueError):
                branch.convert_openrouter_history(history(details), 3)
        with self.assertRaises(ValueError): branch.convert_openrouter_history(history(), 1)
        saved = history(); saved[1]['content'][0]['signature'] = 'not-an-envelope'
        with self.assertRaises(ValueError): branch.convert_openrouter_history(saved, 3)

    def test_same_model_only_and_successor_inherits_boundary(self):
        contract = dict(model='openrouter/anthropic/claude-opus-5.5', tools=['unchanged'], config={'reasoning_effort':'xhigh'})
        histories = {'A':history(), 'B':history()}
        effective, intervention, conversion, audit = branch.provider_configuration(contract, histories, [], 'anthropic')
        self.assertEqual(effective['model'], 'anthropic/claude-opus-5-5')
        self.assertEqual(effective['tools'], contract['tools']); self.assertEqual(effective['config'], contract['config'])
        self.assertEqual(conversion['through_message_counts'], {'A':3,'B':3})
        records = [dict(type='provider_changed', reasoning_conversion=conversion)]
        for h in histories.values():
            h.append(dict(role='assistant', content=[dict(type='reasoning', summary='New native', reasoning='new-signature', redacted=True)]))
        successor = branch.provider_configuration(effective, histories, records)
        self.assertIsNone(successor[1]); self.assertEqual(successor[2], conversion); self.assertEqual(successor[3], audit)
        out = branch.convert_openrouter_history(histories['A'], 3)
        self.assertEqual(out[-1], histories['A'][-1])
        for model in ['anthropic/claude-opus-5-5','openrouter/anthropic/claude-opus-4.6','openrouter/other/model']:
            with self.assertRaises(ValueError):
                branch.provider_configuration(dict(contract,model=model), histories, [], 'anthropic')


if __name__ == '__main__': unittest.main()
