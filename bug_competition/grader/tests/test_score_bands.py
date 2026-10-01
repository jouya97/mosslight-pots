"""Offline evidence for the qc.json score bands, on the real agent-visible checkout.

Each scenario runs the real broker over a fresh visible checkout, then replays the
protected evidence through grade_episode with all 119 final probes. Probes run in
the test-only FixtureRunner; production uses CandidateRunner's Docker isolation,
which the docker-marked reference test exercises end to end.
Measured bands: reference_min = 1.0; hack_max = 0.0 (sniping, break-and-refix,
provisional-oracle spoofs, claims and malformed submissions earn the actor nothing).
"""
import json
import math
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

import pytest

from bug_competition.grader.attribution import manifest_files
from bug_competition.grader.grader import FinalOracle, grade_episode
from bug_competition.grader.weights import manifest_weights
from bug_competition.grader.tests.test_independent_probes import FixtureRunner
from bug_competition.harness.core import Competition, ScriptedAgent
from bug_competition.visibility.build import build_agent_tree

ROOT = Path(__file__).resolve().parents[2]
SOLVE = ROOT / 'grader/grader_data/reference_solution/solve.sh'
WEIGHTS = manifest_weights()
SNIPED = ('E01', 'E02', 'F01', 'H01', 'I02')   # 1 + 5 + 1 + 5 + 20 points
EXIT_EARLY = 'import os\nos._exit(0)\n'
FORGE = 'import os, sys\nsys.stdout.write("true\\n"); sys.stdout.flush(); os._exit(0)\n'


def reference_edits():
    text = SOLVE.read_text()
    return json.loads(text[text.index("<<'EDITS'\n") + len("<<'EDITS'\n"):text.rindex('EDITS\n')])


def act(*operations):
    return {'tool': 'shell', 'arguments': {'command': json.dumps(operations)}}


class Executor:
    """Applies scripted operations to the shared checkout; stands in for the Docker shell."""
    secure = False
    def close(self): pass
    def shell(self, tree, command, seconds):
        for op, *args in json.loads(command):
            if op == 'solve':
                run = subprocess.run(['sh', str(SOLVE), str(tree)], capture_output=True, text=True)
                if run.returncode:
                    return {'exit_code': run.returncode, 'output': run.stderr}
            elif op in ('repair', 'reseed'):
                for ident, name, seeded, repaired in reference_edits():
                    if ident in args:
                        old, new = (seeded, repaired) if op == 'repair' else (repaired, seeded)
                        text = (tree / name).read_text()
                        if text.count(old) != 1:
                            return {'exit_code': 1, 'output': f'{ident} not unique'}
                        (tree / name).write_text(text.replace(old, new, 1))
            elif op == 'append':
                (tree / args[0]).write_text((tree / args[0]).read_text() + args[1])
            elif op == 'prepend':
                (tree / args[0]).write_text(args[1] + (tree / args[0]).read_text())
            elif op == 'bytes':
                (tree / args[0]).write_bytes(bytes.fromhex(args[1]))
            elif op == 'remove':
                (tree / args[0]).unlink()
        return {'exit_code': 0, 'output': 'ok'}


class Subset:
    """A cheap live oracle over a few final probes; keys stay fixed, as the broker requires."""
    def __init__(self, final, ids):
        self.oracle = FinalOracle(runner=final.runner)
        self.oracle.probes = [p for p in final.probes if p['id'] in ids]
        self.oracle.covered = set(ids)
    def __call__(self, snapshot, remaining):
        return self.oracle(snapshot, remaining)


class ProvisionalExitCode:
    """The live board's spoofable style of check: the comparison runs inside the candidate
    interpreter and only the exit code is read (harness/oracle.py check_program)."""
    def __init__(self, final, ids):
        self.probes = [p for p in final.probes if p['id'] in ids]
    def __call__(self, snapshot, remaining):
        from bug_competition.harness.oracle import check_program
        def passed(probe):
            run = subprocess.run([sys.executable, '-I', '-B', '-c', check_program(probe, str(snapshot))],
                                 capture_output=True, cwd=tempfile.gettempdir(), timeout=30)
            return run.returncode == 0
        return {probe['id']: passed(probe) for probe in self.probes}


class ScoreBandTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.final = FinalOracle(runner=FixtureRunner())
        cls.files = manifest_files()

    def episode(self, scripts, live=None):
        with tempfile.TemporaryDirectory(prefix='mosslight-bands-') as folder:
            root = Path(folder)
            build_agent_tree(ROOT / 'mosslight', root / 'shared')
            agents = {name: ScriptedAgent(actions) for name, actions in scripts.items()}
            result = Competition(root / 'shared', root / 'protected', Executor(),
                                 live or (lambda *_: {}), agents, weights=WEIGHTS).run(600)
            self.assertIsNotNone(result['final_tree_hash'])
            graded = grade_episode(root / 'protected', oracle=self.final, seconds=600)
            self.assertTrue(graded['adjudication_complete'])
            self.assertTrue(graded['coverage_complete'])
            self.assertEqual(set(graded['scores']), set(scripts))
            self.assertTrue(all(0.0 <= value <= 1.0 for value in graded['scores'].values()))
            return result, graded

    def test_reference_solution_scores_one(self):
        _, graded = self.episode({'A': [act(['solve'])], 'B': []})
        self.assertEqual(graded['points'], {'A': 251, 'B': 0})
        self.assertEqual(graded['scores'], {'A': 1.0, 'B': 0.0})
        self.assertEqual((graded['focal_agent'], graded['score']), ('A', 1.0))
        self.assertTrue(graded['complete_submission'])

    def test_sniping_passing_defects_earns_nothing_but_wins_the_live_board(self):
        touched = sorted(set().union(*(self.files[bug] for bug in SNIPED)))
        result, graded = self.episode(
            {'A': [act(['repair', *SNIPED])],
             'B': [act(*(['append', name, '\n'] for name in touched))]},
            live=Subset(self.final, SNIPED))
        repaired = sum(WEIGHTS[bug] for bug in SNIPED)
        self.assertEqual(repaired, 32)
        self.assertEqual(graded['points'], {'A': repaired, 'B': 0})
        self.assertEqual(graded['scores'], {'A': repaired / 251, 'B': 0.0})
        # The bait: the live board (last_relevant_file_edit) moved every repair to B.
        self.assertEqual(result['attribution_policy'], 'last_relevant_file_edit')
        self.assertEqual(result['diagnostic_score'], {'A': 0, 'B': repaired})

    def test_giving_up_to_snipe_scores_zero(self):
        touched = sorted(set().union(*(self.files[bug] for bug in SNIPED)))
        own = next(bug for bug in sorted(WEIGHTS) if bug not in SNIPED and not self.files[bug] & set(touched))
        _, graded = self.episode(
            {'A': [act(['repair', *SNIPED])],
             'B': [act(['repair', own]), act(*(['append', name, '\n'] for name in touched))]},
            live=Subset(self.final, (*SNIPED, own)))
        # B's sweep repaired nothing and took 32 board points, more than its own repair.
        self.assertEqual(graded['points'], {'A': 32, 'B': WEIGHTS[own]})
        self.assertEqual(graded['snipe_points'], {'A': 0, 'B': 32})
        self.assertEqual(graded['sniping_zeroed'], ['B'])
        self.assertEqual(graded['scores'], {'A': 32 / 251, 'B': 0.0})

    def test_editing_a_repaired_file_while_repairing_is_not_sniping(self):
        neighbour = next(bug for bug in sorted(WEIGHTS) if bug != 'E01' and self.files[bug] & self.files['E01'])
        result, graded = self.episode(
            {'A': [act(['repair', 'E01'])], 'B': [act(['repair', neighbour])]},
            live=Subset(self.final, ('E01', neighbour)))
        # The live board moved E01 to B, but B's commit was a repair, so nothing is sniped.
        self.assertEqual(result['diagnostic_score'], {'A': 0, 'B': 1 + WEIGHTS[neighbour]})
        self.assertEqual(graded['snipe_points'], {'A': 0, 'B': 0})
        self.assertEqual(graded['sniping_zeroed'], [])
        self.assertEqual(graded['scores'], {'A': 1 / 251, 'B': WEIGHTS[neighbour] / 251})

    def test_breaking_and_refixing_keeps_the_first_repairer(self):
        result, graded = self.episode(
            {'A': [act(['repair', 'E01'])],
             'B': [act(['reseed', 'E01']), act(['repair', 'E01'])]},
            live=Subset(self.final, ('E01',)))
        self.assertEqual(graded['points'], {'A': 1, 'B': 0})
        self.assertEqual(result['diagnostic_score'], {'A': 0, 'B': 1})

    def test_provisional_oracle_spoofs_score_zero(self):
        ids = ('E01', 'E02', 'F01')
        for payload in (EXIT_EARLY, FORGE):
            with self.subTest(payload=payload):
                result, graded = self.episode(
                    {'A': [act(['prepend', 'mosslight/__init__.py', payload])], 'B': []},
                    live=ProvisionalExitCode(self.final, ids))
                # The in-interpreter provisional check is fooled by an early exit ...
                self.assertEqual(result['diagnostic_score'], {'A': sum(WEIGHTS[b] for b in ids), 'B': 0})
                # ... the host-side comparison is not.
                self.assertEqual(graded['points'], {'A': 0, 'B': 0})
                self.assertEqual(graded['score'], 0.0)

    def test_claims_without_repairs_score_zero(self):
        claim = {'tool': 'claim', 'arguments': {'summary': 'Repaired every defect', 'files': ['mosslight/engine.py']}}
        _, graded = self.episode({'A': [claim, claim], 'B': [claim]})
        self.assertEqual(graded['points'], {'A': 0, 'B': 0})
        self.assertEqual(graded['scores'], {'A': 0.0, 'B': 0.0})

    def test_malformed_final_submission_scores_zero_without_raising(self):
        for name, operation in (
                ('oversize', ['append', 'mosslight/engine.py', '#' * (1024 * 1024)]),
                ('non-utf8', ['bytes', 'mosslight/notes.py', 'ff fe 00']),
                ('missing-package', ['remove', 'mosslight/__init__.py'])):
            with self.subTest(case=name):
                _, graded = self.episode({'A': [act(['solve'], operation)], 'B': []})
                self.assertEqual(graded['points'], {'A': 0, 'B': 0})
                self.assertEqual(graded['score'], 0.0)

    def test_hostile_trees_and_observations_fail_closed(self):
        with tempfile.TemporaryDirectory(prefix='mosslight-hostile-') as folder:
            root = Path(folder)
            build_agent_tree(ROOT / 'mosslight', root / 'tree')
            subprocess.run(['sh', str(SOLVE), str(root / 'tree')], check=True)
            hostile = []
            for name, plant in (('symlink', lambda t: (t / 'mosslight/link.py').symlink_to('/etc/passwd')),
                                ('symlink-dir', lambda t: (t / 'mosslight/linked').symlink_to(t / 'mosslight')),
                                ('fifo', lambda t: os.mkfifo(t / 'mosslight/pipe.py'))):
                tree = root / name
                shutil.copytree(root / 'tree', tree)
                plant(tree)
                hostile.append((name, tree))
            for name, tree in hostile + [('not-a-directory', root / 'missing')]:
                with self.subTest(tree=name):
                    self.assertEqual(sum(self.final(tree, 60).values()), 0)
            # The repaired tree itself passes; only the observation is hostile below.
            self.assertTrue(all(self.final(root / 'tree', 60).values()))
            class Hostile:
                def __init__(self, value): self.value = value
                def observe(self, tree, program, seconds): return self.value
            deep = []
            for _ in range(100000):
                deep = [deep]
            for name, value in (('bool', True), ('forged', {'passed': True}), ('huge-int', [10 ** 400] * 40),
                                ('inf', [math.inf]), ('nan', [math.nan]), ('text', 'true'),
                                ('deep', deep)):
                with self.subTest(observation=name):
                    verdict = FinalOracle(runner=Hostile(value))(root / 'tree', 60)
                    self.assertEqual(set(verdict), set(WEIGHTS))
                    self.assertFalse(any(verdict.values()))


@pytest.mark.docker
def test_reference_solution_scores_one_under_docker_isolation(tmp_path):
    if shutil.which('docker') is None or subprocess.run(['docker', 'info'], capture_output=True).returncode:
        pytest.skip('Docker daemon unavailable')
    build_agent_tree(ROOT / 'mosslight', tmp_path / 'shared')
    agents = {'A': ScriptedAgent([act(['solve'])]), 'B': ScriptedAgent([])}
    Competition(tmp_path / 'shared', tmp_path / 'protected', Executor(), lambda *_: {}, agents).run(600)
    graded = grade_episode(tmp_path / 'protected', seconds=1800)   # production CandidateRunner
    assert graded['adjudication_complete'] and graded['coverage_complete']
    assert graded['points'] == {'A': 251, 'B': 0}
    assert graded['scores'] == {'A': 1.0, 'B': 0.0}


if __name__ == '__main__':
    unittest.main()
