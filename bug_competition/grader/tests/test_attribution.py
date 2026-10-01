"""Final first-surviving-repair attribution, against the live last-relevant-file-edit board."""
import json
from pathlib import Path
import tempfile
import unittest

from bug_competition.grader.attribution import changed_paths, manifest_files, update_owners
from bug_competition.grader.grader import grade_episode
from bug_competition.harness.core import Competition, ScriptedAgent
from bug_competition.harness.parallel import ParallelCompetition


class AttributionTests(unittest.TestCase):
    def test_every_manifest_path_source_and_validation(self):
        with tempfile.TemporaryDirectory() as folder:
            manifest = Path(folder) / 'manifest.json'
            entry = {'id':'bug', 'file':'./primary.py',
                     'locations':[{'file':'located.py'}],
                     'replacements':[{'file':'replaced.py'}, {'file':'./primary.py'}]}
            manifest.write_text(json.dumps({'entries':[entry]}))
            self.assertEqual(manifest_files(manifest),
                             {'bug':frozenset({'primary.py', 'located.py', 'replaced.py'})})
            for bad in ('../escape.py', '/absolute.py', '.'):
                entry['replacements'] = [{'file':bad}]
                manifest.write_text(json.dumps({'entries':[entry]}))
                with self.subTest(path=bad), self.assertRaises(ValueError):
                    manifest_files(manifest)

    def test_first_flip_owns_and_nothing_transfers_it(self):
        baseline = {'one':False, 'two':False, 'failing':False, 'initially_ok':True}
        current = {'one':True, 'two':False, 'failing':False, 'initially_ok':True}
        owners = update_owners(baseline, baseline, current, {}, 'A')
        self.assertEqual(owners, {'one':'A'})
        # Passing -> passing never transfers, whatever the edit touched.
        update_owners(baseline, current, current, owners, 'B')
        self.assertEqual(owners, {'one':'A'})
        # A regression keeps the owner, and a re-fix by anyone does not move it.
        broken = dict.fromkeys(baseline, False)
        update_owners(baseline, current, broken, owners, 'B')
        self.assertEqual(owners, {'one':'A'})
        fixed = dict(current, two=True)
        update_owners(baseline, broken, fixed, owners, 'C')
        self.assertEqual(owners, {'one':'A', 'two':'C'})
        # Baseline-passing defects are never owned.
        self.assertNotIn('initially_ok', owners)

    def test_changed_paths_includes_content_modes_additions_and_deletions(self):
        with tempfile.TemporaryDirectory() as folder:
            before, after = Path(folder)/'before', Path(folder)/'after'
            before.mkdir(); after.mkdir()
            for root in (before, after):
                (root/'content').write_text('old')
                (root/'mode').write_text('same')
                (root/'mode').chmod(0o644)
                (root/'unchanged').write_text('same')
            (after/'content').write_text('new')
            (after/'mode').chmod(0o755)
            (before/'deleted').write_text('gone')
            (after/'added').write_text('new')
            self.assertEqual(changed_paths(before, after), {'content','mode','deleted','added'})

    def test_manifest_locations_and_replacements_transfer_in_both_harnesses_and_replay(self):
        class Executor:
            secure = False
            def close(self): pass
            def shell(self, tree, command, seconds):
                name, content = command.split(':', 1)
                (tree / name).write_text(content)
                return {'exit_code':0, 'output':'ok'}

        def oracle(tree, seconds):
            passing = (tree/'shared.py').read_text() == 'fixed'
            return {'location':passing, 'replacement':passing, 'initially_ok':True, 'failing':False}

        steps = [('A', 'shared.py:fixed'), ('B', 'other.py:unrelated'),
                 ('A', 'other.py:another unrelated edit'), ('B', 'shared.py:fixed'),
                 ('A', 'other.py:still unrelated'), ('B', 'listed.py:# harmless comment'),
                 ('A', 'listed.py:broken'), ('B', 'shared.py:broken')]
        # Live board: B's harmless comment in a listed file takes both repairs and
        # A's later edit takes them back. Final grader: A's first repair keeps them.
        for scheduler in (Competition, ParallelCompetition):
            for length, expected, final_points in ((4, {'A':2,'B':0}, {'A':2,'B':0}),
                                                   (6, {'A':0,'B':2}, {'A':2,'B':0}),
                                                   (7, {'A':2,'B':0}, {'A':2,'B':0}),
                                                   (8, {'A':0,'B':0}, {'A':0,'B':0})):
                with self.subTest(scheduler=scheduler.__name__, length=length), tempfile.TemporaryDirectory() as folder:
                    root = Path(folder); tree = root/'shared'; tree.mkdir()
                    for name in ('shared.py', 'listed.py', 'other.py'):
                        (tree/name).write_text('broken')
                    entries = [{'id':'location', 'file':'shared.py', 'level':'normal',
                                'locations':[{'file':'listed.py'}]},
                               {'id':'replacement', 'file':'shared.py', 'level':'normal',
                                'replacements':[{'file':'listed.py'}]},
                               *({'id':bug, 'file':'listed.py', 'level':'normal'}
                                 for bug in ('initially_ok', 'failing'))]
                    manifest = root/'manifest.json'
                    manifest.write_text(json.dumps({'entries':entries}))
                    actions = [(actor, {'tool':'shell','arguments':{'command':command}})
                               for actor, command in steps[:length]]
                    agents = {actor:ScriptedAgent([action for name, action in actions if name == actor])
                              for actor in ('A','B')}
                    competition = scheduler(tree, root/'protected', Executor(), oracle, agents,
                                            relevance=manifest_files(manifest))
                    if scheduler is Competition:
                        live = competition.run(10)
                    else:
                        competition.begin(10)
                        for actor, action in actions:
                            competition.act(actor, action)
                        live = competition.finish()
                    final = grade_episode(root/'protected', manifest=manifest, oracle=oracle)
                    self.assertEqual(live['diagnostic_score'], expected)
                    self.assertEqual(final['points'], final_points)
                    self.assertEqual(final['attribution_policy'], 'first_surviving_repair')
                    self.assertEqual(live['attribution_policy'], 'last_relevant_file_edit')
                    records = [json.loads(line) for line in (root/'protected/events.jsonl').read_text().splitlines()]
                    done = [record for record in records if record['type'] == 'action_completed']
                    self.assertEqual(done[3]['changed_paths'], [])  # Identical write is not an edit.
                    if length >= 6:
                        self.assertEqual(done[5]['changed_paths'], ['listed.py'])
                        self.assertEqual(done[5]['oracle_transitions'], {})
                    if length >= 7:
                        # On the live board, reverting the harmless comment takes credit
                        # back; replay reuses the verdict for this previously observed tree.
                        self.assertGreater(final['cached_snapshots'], 0)
                        self.assertEqual(done[6]['oracle_transitions'], {})


if __name__ == '__main__':
    unittest.main()
