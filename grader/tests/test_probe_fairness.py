"""Probe acceptance tests for different correct implementations.

Only trusted authoring fixtures execute outside Docker. These alternatives cover
specific formerly brittle assumptions; they are not a universal validity proof.
The full clean/seeded/individual-repair matrix lives in test_independent_probes.
"""
import json
import re
from pathlib import Path
import shutil
import tempfile
import unittest

from bug_competition.grader.grader import FinalOracle, compare_observation
from bug_competition.grader.weights import DEFAULT_MANIFEST
from .test_independent_probes import FIXTURES, FixtureRunner


class ProbeFairnessTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.probes = {p['id']: p for p in FinalOracle(runner=FixtureRunner()).probes}
        cls.entries = {p['id']: p for p in json.loads(DEFAULT_MANIFEST.read_text())['entries']}

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='mosslight-trusted-alternative-')
        self.addCleanup(self.temp.cleanup)
        self.tree = Path(self.temp.name) / 'fixture'
        shutil.copytree(FIXTURES / 'clean_baseline', self.tree)

    def replace(self, path, old, new, count=1):
        source = self.tree / 'mosslight' / path
        text = source.read_text()
        self.assertEqual(text.count(old), count, 'alternative fixture anchor changed')
        source.write_text(text.replace(old, new))

    def accepts(self, *bugs):
        for bug in bugs:
            with self.subTest(bug=bug):
                probe = self.probes[bug]
                value = FixtureRunner().observe(self.tree, probe['program'])
                self.assertTrue(compare_observation(probe, value), repr(value))

    def test_command_can_validate_real_operations_before_dispatch(self):
        self.replace('commands.py', '    args = mapping(command.get("args",{}),"Command arguments")',
                     '    if command.get("op") not in command_catalog():\n'
                     '        raise ValueError("Unknown command")\n'
                     '    args = mapping(command.get("args",{}),"Command arguments")')
        self.accepts('P13')

    def test_undo_can_use_bounded_deque_initialized_by_real_server(self):
        self.replace('server.py', 'import copy\n', 'import copy\nfrom collections import deque\n')
        self.replace('server.py', 'self.undo_stack = []', 'self.undo_stack = deque(maxlen=30)')
        self.replace('server.py', '            self.undo_stack = self.undo_stack[-30:]\n', '')
        self.accepts('P14', 'P15')

    def test_cli_can_raise_system_exit_instead_of_returning(self):
        self.replace('__main__.py', 'return 2', 'raise SystemExit(2)')
        self.accepts('P21')

    def test_transaction_can_inline_checkpoint_write(self):
        self.replace('campaigns.py', 'self._checkpoint(claim["campaign"], claim["ordinal"], state)',
                     'encoded = _json(state)\n'
                     '                self.db.execute("INSERT INTO checkpoints VALUES (?, ?, ?, ?, ?)",\n'
                     '                    (claim["campaign"], claim["ordinal"], state["next_offset"] - 1, encoded,\n'
                     '                     hashlib.sha256(encoded.encode()).hexdigest()))')
        self.accepts('V04')

    def test_history_cache_and_branch_tables_can_be_renamed(self):
        for source in (self.tree / 'mosslight').glob('*.py'):
            source.write_text(source.read_text().replace('history_checkpoints', 'replay_acceleration')
                              .replace('history_branches', 'history_heads'))
        self.accepts('X02', 'H02', 'H03', 'H05', 'X03')

    def test_history_can_omit_checkpoint_cache(self):
        source = self.tree / 'mosslight/history.py'
        text = source.read_text().replace('if use_cache:', 'if False:')
        text = text.replace('''            self.db.execute("INSERT OR IGNORE INTO history_checkpoints VALUES (?, ?, ?)",
                            (key, root["id"], _json(state)))''', '')
        source.write_text(text)
        self.accepts('X02', 'H02', 'H03', 'H05', 'X03')

    def test_ensemble_can_assign_requested_identity_at_publication(self):
        entry = self.entries['R03']
        self.replace('ensemble_compute.py', entry['old'], entry['new'])
        self.replace('ensembles.py', 'outcome = {"identity": computed["identity"],',
                     'outcome = {"identity": {key: ticket["spec"][key] for key in ("replicate", "treatment")},')
        self.accepts('R03')

    def test_nursery_private_batch_helper_can_be_renamed(self):
        source = self.tree / 'mosslight/nursery.py'
        source.write_text(re.sub(r'\b_batch\(', '_make_seedling(', source.read_text()))
        self.accepts('E21', 'E22', 'E23')

    def test_courier_causality_can_be_repaired_where_heads_are_selected(self):
        entry = self.entries['P24']
        self.replace('courier.py', entry['old'], entry['new'])
        self.replace('courier.py', 'precedes({event["peer"]: event["counter"]}, other["context"])',
                     'event["counter"] <= other["context"].get(event["peer"], 0)')
        self.accepts('P24', 'P28')

    def test_courier_heads_helper_can_be_renamed(self):
        source = self.tree / 'mosslight/courier.py'
        source.write_text(source.read_text().replace('_heads(', '_current_events('))
        self.accepts('P28')

    def test_chart_can_anchor_at_zero_and_use_other_numeric_formatting(self):
        self.replace('charts.py', 'first,last = history[0]["day"],history[-1]["day"]',
                     'first,last = 0,history[-1]["day"]')
        source = self.tree / 'mosslight/charts.py'
        source.write_text(source.read_text().replace('{x:.2f}', '{x:.4f}'))
        self.accepts('F32')

    def test_save_merge_can_allocate_different_unused_identifiers(self):
        self.replace('save_merge.py', 'next_id = max(value["workbench"]["next_id"] for value in source)',
                     'next_id = 10 + max(value["workbench"]["next_id"] for value in source)')
        self.accepts('M01')


if __name__ == '__main__':
    unittest.main()
