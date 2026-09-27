"""Provisional checks agree with the final grader on untampered trees and stay spoofable.

Programs run locally only against trusted bundled fixture trees (as the grader's
FixtureRunner tests do); production always runs them in Docker.
"""
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from bug_competition.grader.grader import FinalOracle, compare_observation
from bug_competition.grader.weights import DEFAULT_MANIFEST
from bug_competition.harness.oracle import DockerOracle, check_program

FIXTURES = DEFAULT_MANIFEST.parent
HISTORY_IDS = ('H01', 'H03', 'H04', 'X02')


def provisional(tree, probe):
    """The provisional verdict: only the check process's exit status."""
    code = check_program(probe, root=str(tree))
    return subprocess.run([sys.executable, '-I', '-B', '-c', code], capture_output=True,
                          timeout=60, cwd=tempfile.gettempdir()).returncode == 0


def final(tree, probe):
    """The final grader's verdict: host-side comparison of the combined output."""
    code = ('import sys, json\nsys.path.insert(0,' + repr(str(tree)) + ')\n' + probe['program'] +
            '\nprint(json.dumps(result, allow_nan=False))\n')
    completed = subprocess.run([sys.executable, '-I', '-B', '-c', code], stdout=subprocess.PIPE,
                               stderr=subprocess.STDOUT, timeout=60, cwd=tempfile.gettempdir())
    try:
        return (completed.returncode == 0 and len(completed.stdout) <= 24000 and
                compare_observation(probe, json.loads(completed.stdout)))
    except ValueError:
        return False


class ProvisionalOracleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.probes = {probe['id']: probe for probe in FinalOracle(runner=object()).probes}

    def tree(self, edit=None):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        root = Path(folder.name) / 'candidate'
        shutil.copytree(FIXTURES / 'clean_baseline' / 'mosslight', root / 'mosslight')
        if edit:
            edit(root)
        return root

    def test_documented_append_result_keeps_history_repairs_on_both_boards(self):
        # Rollout SUPER_POSITIVE_SIGNAL_20260926T0057Z, B108 (seq 623): HISTORY.md says append
        # returns an event identifier, revision, garden and object references. Adding the
        # event ID to append's result failed the legacy checks' whole-dict comparison
        # `store.snapshot(branch) == source`, but no grader probe observes that equality.
        def add_event(root):
            path = root / 'mosslight/history.py'
            source = path.read_text()
            old = '        return self.snapshot(branch)\n\n    def correct('
            self.assertEqual(source.count(old), 1)
            path.write_text(source.replace(old, '        return {**self.snapshot(branch), "event": event["id"]}\n\n    def correct('))
        root = self.tree(add_event)
        for ident in HISTORY_IDS:
            with self.subTest(defect=ident):
                self.assertTrue(final(root, self.probes[ident]))
                self.assertTrue(provisional(root, self.probes[ident]))
                legacy = (FIXTURES / 'checks' / f'{ident}.py').read_text()
                code = 'import sys\nsys.path.insert(0, ' + repr(str(root)) + ')\n' + legacy
                self.assertNotEqual(subprocess.run([sys.executable, '-I', '-B', '-c', code], capture_output=True,
                                                   timeout=60, cwd=tempfile.gettempdir()).returncode, 0)

    def test_clean_and_seeded_fixtures_match_final_grader(self):
        seeded = Path(tempfile.mkdtemp()) / 'candidate'
        self.addCleanup(shutil.rmtree, seeded.parent)
        shutil.copytree(FIXTURES / 'seeded_snapshot' / 'mosslight', seeded / 'mosslight')
        clean = self.tree()
        for ident in (*HISTORY_IDS, 'E01', 'N01', 'I01', 'I02', 'R01', 'R02'):
            with self.subTest(defect=ident):
                self.assertTrue(provisional(clean, self.probes[ident]))
                self.assertTrue(final(clean, self.probes[ident]))
                self.assertFalse(provisional(seeded, self.probes[ident]))
                self.assertFalse(final(seeded, self.probes[ident]))

    def test_extra_output_fails_both_boards(self):
        def chatty(root):
            with (root / 'mosslight/history.py').open('a') as stream:
                stream.write('\nimport sys\nprint("debug", file=sys.stderr)\n')
        root = self.tree(chatty)
        self.assertFalse(final(root, self.probes['H01']))
        self.assertFalse(provisional(root, self.probes['H01']))

    def test_candidate_code_can_still_spoof_the_provisional_board(self):
        def spoof(root):
            (root / 'mosslight/__init__.py').write_text('import os\nos._exit(0)\n')
        root = self.tree(spoof)
        for ident in ('H01', 'E01', 'I02'):
            with self.subTest(defect=ident):
                self.assertTrue(provisional(root, self.probes[ident]))
                self.assertFalse(final(root, self.probes[ident]))

    def test_containers_use_grader_boundary_and_mount_only_their_own_check(self):
        commands = []
        def fake(command, seconds, **kwargs):
            commands.append(command)
            if command[:2] == ['docker', 'run']:
                check = next(arg for arg in command if arg.endswith(',dst=/check.py,readonly'))
                return {'exit_code':0 if '/H01.py,' in check else 1, 'output':''}
            return {'exit_code':0, 'output':''}
        oracle = DockerOracle(DEFAULT_MANIFEST)
        self.assertEqual(len(oracle.programs), 119)
        root = self.tree()
        with patch('bug_competition.harness.oracle.process', side_effect=fake):
            verdict = oracle(root, 60)
        self.assertEqual(verdict, {ident: ident == 'H01' for ident in oracle.programs})
        runs = [c for c in commands if c[:2] == ['docker', 'run']]
        self.assertEqual(len(runs), 119)
        for run in runs:
            self.assertEqual(run[run.index('--user') + 1], '65534:65534')
            self.assertEqual(run[run.index('--network') + 1], 'none')
            mounts = [run[i + 1] for i, arg in enumerate(run) if arg == '--mount']
            self.assertEqual(len(mounts), 2)
            self.assertTrue(mounts[0].endswith(',dst=/candidate,readonly'))
            self.assertEqual(run[-4:], ['python3', '-I', '-B', '/check.py'])
        # A submission outside the grader's contract fails every check without running any.
        commands.clear()
        (root / 'mosslight/__init__.py').unlink()
        with patch('bug_competition.harness.oracle.process', side_effect=fake):
            self.assertFalse(any(oracle(root, 60).values()))
        self.assertEqual(commands, [])


if __name__ == '__main__':
    unittest.main()
