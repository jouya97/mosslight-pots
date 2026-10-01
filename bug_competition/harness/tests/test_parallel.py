"""Deterministic offline tests for overlapping shell actions and commit attribution."""
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import os
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

from bug_competition.harness.core import CommandTimeout, DockerShell, ScriptedAgent, canonical, tree_hash
from bug_competition.harness.merge import merge_lines, merge_text
from bug_competition.harness.parallel import (FILE_NAME_REJECTION, PATH_LENGTH_REJECTION,
                                              SPECIAL_FILE_REJECTION, UNREADABLE_REJECTION,
                                              ParallelCompetition)


def shell(command):
    return {'tool':'shell', 'arguments':{'command':command}, 'identity':'forged'}


class ParallelTests(unittest.TestCase):
    def make(self, root, executor, oracle=None, value='broken', turn_limit=2, seconds=10, agents=('A','B'),
             modes=None, shell_seconds=180):
        tree = root / 'shared'
        tree.mkdir()
        (tree / 'value').write_text(value)
        (tree / 'other').write_text('broken')
        for name, mode in (modes or {}).items():  # Host-staged modes, before the baseline.
            (tree / name).chmod(mode)
        if oracle is None:
            oracle = lambda tree, seconds: {'bug':(tree / 'value').read_text().startswith('fixed')}
        oracle.adversarially_verified = True
        competition = ParallelCompetition(tree, root / 'protected', executor, oracle,
            {name:ScriptedAgent([]) for name in agents}, relevance={'bug':{'value'}}, shell_seconds=shell_seconds)
        competition.begin(seconds, turn_limit=turn_limit)
        return competition

    def ledger(self, c):
        records = [json.loads(line) for line in (c.protected / 'events.jsonl').read_text().splitlines()]
        previous = '0' * 64
        for record in records:
            record = dict(record)
            digest = record.pop('hash')
            self.assertEqual(record['previous'], previous)
            self.assertEqual(digest, hashlib.sha256(canonical(record).encode()).hexdigest())
            previous = digest
        return records

    def test_shell_timeout_fails_only_that_action(self):
        seconds_seen = []
        class Executor:
            secure = False
            def close(self): pass
            def shell(self, tree, command, seconds):
                seconds_seen.append(seconds)
                if command == 'hang':
                    (tree / 'value').write_text('fixed by a command that never finished')
                    (tree / 'added').write_text('partial')
                    raise CommandTimeout('command deadline', 'partial output', False)
                if command == 'read':
                    return {'exit_code':0, 'output':(tree / 'value').read_text(), 'truncated':False}
                (tree / 'value').write_text(command)
                return {'exit_code':0, 'output':'ok', 'truncated':False}
        with tempfile.TemporaryDirectory() as folder:
            c = self.make(Path(folder), Executor(), turn_limit=3, seconds=3600)
            self.assertEqual(c.act('A', shell('broken-A')), {'exit_code':0, 'output':'ok', 'truncated':False,
                             'notice':'[Notice: 2 actions remaining.]'})
            timed_out = c.act('B', shell('hang'))
            # The per-action limit, not the remaining agent-time budget, bounded the command.
            self.assertEqual(seconds_seen[1], 180)
            # Nothing committed; the countdown still attaches.
            self.assertEqual(timed_out, {'exit_code':124, 'output':'partial output', 'truncated':False,
                                         'error':'Command timed out after 180 seconds.',
                                         'notice':'[Notice: 2 actions remaining.]'})
            self.assertFalse(c.stopping)
            self.assertEqual((c.tree / 'value').read_text(), 'broken-A')
            self.assertFalse((c.tree / 'added').exists())
            # The contest continues: both agents act again, and B sees only committed work.
            self.assertEqual(c.act('B', shell('read'))['output'], 'broken-A')
            self.assertEqual(c.act('A', shell('fixed-A'))['notice'],
                             '[Notice: 1 action remaining.]')
            result = c.finish()
            self.assertEqual(result['stop_reason'], 'agents_exhausted')
            self.assertEqual(result['turns_used'], {'A':2, 'B':2})
            self.assertEqual(result['verified_score'], {'A':1, 'B':0})
            self.assertEqual(len(list((c.protected / 'snapshots').iterdir())), 3)
            records = self.ledger(c)
            done = [r for r in records if r['type'] == 'action_completed']
            self.assertEqual([r['agent'] for r in done], ['A', 'B', 'B', 'A'])
            self.assertEqual(done[1]['observation'], timed_out)
            self.assertEqual(done[1]['rejection'], {'reason':'timeout', 'seconds':180})
            self.assertEqual(done[1]['changed_paths'], [])
            self.assertEqual(done[1]['before'], done[1]['after'])
            self.assertFalse(any(r['type'] in ('error', 'action_discarded') for r in records))

    def test_shell_timeout_at_the_global_deadline_still_ends_the_contest(self):
        class Executor:
            secure = False
            def close(self): pass
            def shell(self, tree, command, seconds):
                raise CommandTimeout('command deadline', 'partial', False)
        with tempfile.TemporaryDirectory() as folder:
            c = self.make(Path(folder), Executor(), seconds=10)  # Less budget than one command's limit.
            with self.assertRaises(TimeoutError):
                c.act('A', shell('hang'))
            result = c.finish()
            self.assertEqual(result['stop_reason'], 'safety_deadline')
            self.assertEqual(result['turns_used'], {'A':0, 'B':0})

    def test_configured_shell_limit_is_recorded_and_global_budget_caps_it(self):
        limits = []
        class Executor:
            secure = False
            def close(self): pass
            def shell(self, tree, command, seconds):
                limits.append(seconds)
                raise CommandTimeout('command deadline')
        with tempfile.TemporaryDirectory() as folder:
            c = self.make(Path(folder), Executor(), seconds=3600, shell_seconds=75)
            result = c.act('A', shell('hang'))
            self.assertEqual(limits, [75])
            self.assertEqual(result['error'], 'Command timed out after 75 seconds.')
            self.assertFalse(c.stopping)
            c.deadline = __import__('time').monotonic() + 8
            with self.assertRaises(TimeoutError):
                c.act('B', shell('hang'))
            self.assertLessEqual(limits[-1], 8)
            self.assertEqual(c.finish()['stop_reason'], 'safety_deadline')

    def test_shell_limit_must_be_finite_and_positive(self):
        for value in (0, -1, float('nan'), float('inf'), True, '180'):
            with self.subTest(value=value), tempfile.TemporaryDirectory() as folder:
                with self.assertRaisesRegex(ValueError, 'shell_seconds'):
                    self.make(Path(folder), object(), shell_seconds=value)

    def test_invalid_workspace_entries_reject_only_that_action(self):
        def fifo(tree):
            os.mkfifo(tree / 'pipe')
        def unreadable_file(tree):
            (tree / 'secret').write_text('x')
            (tree / 'secret').chmod(0)
        def unreadable_directory(tree):
            (tree / 'locked').mkdir()
            (tree / 'locked' / 'inner').write_text('x')
            (tree / 'locked').chmod(0)
        def undecodable_name(tree):
            with open(os.path.join(os.fsencode(tree), b'bad-\xff'), 'wb') as stream:
                stream.write(b'x')
        def unsearchable_directory(tree):
            # Listable but not searchable: its entries cannot even be inspected (this used to
            # raise PermissionError out of the symlink scan and stop the contest as `error`).
            (tree / 'locked').mkdir()
            (tree / 'locked' / 'inner').write_text('x')
            (tree / 'locked').chmod(0o600)
        def deep_path(tree):
            # Far beyond the host's PATH_MAX once under the host's work folder (this used to
            # raise ENAMETOOLONG out of the inventory). Built relative to directory fds.
            folder = os.open(tree, os.O_RDONLY)
            try:
                for _ in range(150):
                    os.mkdir('d' * 20, dir_fd=folder)
                    inner = os.open('d' * 20, os.O_RDONLY, dir_fd=folder)
                    os.close(folder)
                    folder = inner
                os.close(os.open('file', os.O_WRONLY | os.O_CREAT, 0o644, dir_fd=folder))
            finally:
                os.close(folder)
        cases = {'fifo':(fifo, SPECIAL_FILE_REJECTION, 'pipe'),
                 'unreadable_file':(unreadable_file, UNREADABLE_REJECTION, 'secret'),
                 'unreadable_directory':(unreadable_directory, UNREADABLE_REJECTION, 'locked'),
                 'unsearchable_directory':(unsearchable_directory, UNREADABLE_REJECTION, 'locked/inner'),
                 'undecodable_name':(undecodable_name, FILE_NAME_REJECTION, 'bad-\\xff'),
                 'deep_path':(deep_path, PATH_LENGTH_REJECTION, '/'.join(['d' * 20] * 25))}
        self.assertEqual(SPECIAL_FILE_REJECTION, 'Only regular files and directories are allowed in the '
                         "shared checkout; this action's changes were not applied.")
        self.assertEqual(UNREADABLE_REJECTION, 'Unreadable files or directories are not allowed in the '
                         "shared checkout; this action's changes were not applied.")
        self.assertEqual(FILE_NAME_REJECTION, 'File names must be valid UTF-8 in the shared checkout; '
                         "this action's changes were not applied.")
        self.assertEqual(PATH_LENGTH_REJECTION, 'File paths must be at most 512 bytes long in the shared '
                         "checkout; this action's changes were not applied.")
        for name, (create, error, path) in cases.items():
            with self.subTest(case=name), tempfile.TemporaryDirectory() as folder:
                if name.startswith(('unreadable', 'unsearchable')) and os.geteuid() == 0:
                    self.skipTest('root reads everything')
                class Executor:
                    secure = False
                    def close(self): pass
                    def shell(self, tree, command, seconds):
                        if command == 'bad':
                            (tree / 'value').write_text('fixed-B')
                            try:
                                create(tree)
                            except OSError as exc:  # e.g. APFS refuses undecodable names
                                raise unittest.SkipTest(f'cannot create {name}: {exc}')
                        elif command != 'read':
                            (tree / 'value').write_text(command)
                        return {'exit_code':0, 'output':'ok', 'truncated':False}
                c = self.make(Path(folder), Executor(), turn_limit=3)
                c.act('A', shell('fixed-A'))
                try:
                    rejected = c.act('B', shell('bad'))
                except unittest.SkipTest:
                    c.finish()
                    raise
                self.assertEqual(rejected, {'exit_code':0, 'output':'ok', 'truncated':False, 'error':error,
                                            'notice':'[Notice: 2 actions remaining.]'})
                self.assertEqual((c.tree / 'value').read_text(), 'fixed-A')
                self.assertEqual(sorted(p.name for p in c.tree.iterdir()), ['other', 'value'])
                # The contest continues from the head; the rejected state did not persist.
                self.assertEqual(c.act('B', shell('read'))['notice'], '[Notice: 1 action remaining.]')
                result = c.finish()
                self.assertEqual(result['stop_reason'], 'agents_exhausted')
                self.assertEqual(result['turns_used'], {'A':1, 'B':2})
                self.assertEqual(result['verified_score'], {'A':1, 'B':0})
                self.assertEqual(len(list((c.protected / 'snapshots').iterdir())), 2)
                self.assertFalse((c.protected / 'work').exists())
                done = [r for r in self.ledger(c) if r['type'] == 'action_completed' and r['agent'] == 'B']
                self.assertEqual(done[0]['rejection'], {'reason':'workspace', 'error':error, 'path':path})
                self.assertEqual(done[0]['observation'], rejected)
                self.assertEqual(done[0]['changed_paths'], [])

    def test_mode_changes_never_block_later_writes(self):
        # Only the owner's executable bit is tracked (files are kept 0o644 or 0o755). A committed
        # `chmod a-w` used to leave a read-only head file, and the next edit to it by anyone
        # raised PermissionError during commit and stopped the contest as `error`.
        seen = []
        class Executor:
            secure = False
            def close(self): pass
            def shell(self, tree, command, seconds):
                seen.append((command, {p.name:p.stat().st_mode & 0o777 for p in tree.iterdir()}))
                if command == 'lock':
                    (tree / 'value').chmod(0o444)
                elif command == 'fix-and-lock':
                    (tree / 'value').write_text('fixed-A')
                    (tree / 'value').chmod(0o444)
                elif command == 'edit-locked':
                    (tree / 'value').write_text('fixed-B')  # No chmod: the copy is writable.
                elif command == 'make-executable':
                    (tree / 'other').write_text('#!/bin/sh\n')
                    (tree / 'other').chmod(0o755)
                elif command == 'strip-write':
                    (tree / 'other').chmod(0o555)
                elif command == 'strip-exec':
                    (tree / 'other').chmod(0o644)
                elif command == 'lock-all':
                    for path in tree.iterdir():
                        path.chmod(0o400)
                return {'exit_code':0, 'output':command, 'truncated':False}
        with tempfile.TemporaryDirectory() as folder:
            # A host-staged read-only file is normalised before the baseline, like every commit.
            c = self.make(Path(folder), Executor(), turn_limit=4, seconds=3600, modes={'other':0o444})
            self.assertEqual((c.tree / 'other').stat().st_mode & 0o777, 0o644)
            head = tree_hash(c.tree)
            # A mode-only change removing write permission commits nothing; the action counts.
            self.assertEqual(c.act('A', shell('lock')), {'exit_code':0, 'output':'lock', 'truncated':False,
                                                         'notice':'[Notice: 3 actions remaining.]'})
            self.assertEqual(tree_hash(c.tree), head)
            self.assertEqual((c.tree / 'value').stat().st_mode & 0o777, 0o644)
            # An edit plus `chmod a-w` commits the edit at a writable mode.
            self.assertEqual(c.act('A', shell('fix-and-lock'))['notice'],
                             '[Notice: 2 actions remaining.]')
            self.assertEqual((c.tree / 'value').stat().st_mode & 0o777, 0o644)
            # The other participant edits that file without any chmod, and commits.
            self.assertEqual(c.act('B', shell('edit-locked'))['notice'],
                             '[Notice: 3 actions remaining.]')
            self.assertEqual(seen[-1][1]['value'], 0o644)
            self.assertEqual((c.tree / 'value').read_text(), 'fixed-B')
            # The executable bit is tracked.
            c.act('B', shell('make-executable'))
            self.assertEqual((c.tree / 'other').stat().st_mode & 0o777, 0o755)
            self.assertEqual((c.tree / 'other').read_text(), '#!/bin/sh\n')
            executable = tree_hash(c.tree)
            c.act('A', shell('strip-write'))  # 0o555 keeps the executable bit: no change.
            self.assertEqual(tree_hash(c.tree), executable)
            c.act('B', shell('lock-all'))  # 0o400 everywhere clears it: only 'other' changes.
            self.assertEqual({p.name:p.stat().st_mode & 0o777 for p in c.tree.iterdir()},
                             {'value':0o644, 'other':0o644})
            c.act('B', shell('strip-exec'))  # Already 0o644 at the head: nothing to commit.
            result = c.finish()
            self.assertEqual(result['stop_reason'], 'turn_limit')
            self.assertEqual(result['turns_used'], {'A':3, 'B':4})
            # B's later edit of the relevant file takes the already-passing defect.
            self.assertEqual(result['verified_score'], {'A':0, 'B':1})
            records = self.ledger(c)
            self.assertFalse(any(r['type'] in ('error', 'action_discarded') for r in records))
            done = [r for r in records if r['type'] == 'action_completed']
            self.assertEqual([r['changed_paths'] for r in done],
                             [[], ['value'], ['value'], ['other'], [], ['other'], []])
            self.assertTrue(all(r['rejection'] is None for r in done))
            self.assertEqual(len(list((c.protected / 'snapshots').iterdir())), 5)

    def test_stale_merge_onto_a_mode_changed_head_file(self):
        # A removes write permission and sets the executable bit while editing; B's stale edit
        # to another line is merged onto the head copy (it used to hit a read-only file).
        c, a, b = self.run_stale_pair({'value':('fixed\none\ntwo\nthree\n', 0o555)},
                                      {'value':'broken\none\ntwo\nTHREE-B\n'}, 'broken\none\ntwo\nthree\n')
        self.assertEqual(b['notice'], '[Notice: 1 action remaining.]')
        self.assertEqual((c.tree / 'value').read_text(), 'fixed\none\ntwo\nTHREE-B\n')
        self.assertEqual((c.tree / 'value').stat().st_mode & 0o777, 0o755)
        self.assertFalse(c.stopping)
        done = {r['agent']:r for r in self.ledger(c) if r['type'] == 'action_completed'}
        self.assertEqual(done['B']['merged_paths'], ['value'])

    def test_new_directory_modes_never_reach_the_head(self):
        # Directory modes are not tracked: a directory an action left without write or search
        # permission is created normally at the head, and later edits inside it commit.
        class Executor:
            secure = False
            def close(self): pass
            def shell(self, tree, command, seconds):
                if command == 'sealed':
                    (tree / 'new').mkdir()
                    (tree / 'new' / 'inner').write_text('one')
                    (tree / 'new').chmod(0o555)
                elif command == 'read-only-root':
                    (tree / 'value').write_text('fixed-A')
                    tree.chmod(0o555)  # The workspace root itself; tree is removed by the host.
                else:
                    (tree / 'new' / 'inner').write_text(command)
                    (tree / 'new' / 'added').write_text(command)
                return {'exit_code':0, 'output':command, 'truncated':False}
        with tempfile.TemporaryDirectory() as folder:
            c = self.make(Path(folder), Executor(), turn_limit=3, seconds=3600)
            c.act('A', shell('sealed'))
            self.assertTrue(os.access(c.tree / 'new', os.W_OK | os.X_OK))
            self.assertEqual(c.act('B', shell('two'))['notice'],
                             '[Notice: 2 actions remaining.]')
            self.assertEqual((c.tree / 'new' / 'added').read_text(), 'two')
            c.act('A', shell('read-only-root'))
            self.assertTrue(os.access(c.tree, os.W_OK | os.X_OK))
            self.assertEqual((c.tree / 'value').read_text(), 'fixed-A')
            result = c.finish()
            self.assertEqual(result['stop_reason'], 'agents_exhausted')
            self.assertEqual(result['turns_used'], {'A':2, 'B':1})
            self.assertFalse((c.protected / 'work').exists())

    def test_malformed_tool_arguments_fail_only_that_action(self):
        commands, searches = [], []
        class Executor:
            secure = False
            def close(self): pass
            def shell(self, tree, command, seconds):
                commands.append(command)
                (tree / 'value').write_text(command)
                return {'exit_code':0, 'output':'ok', 'truncated':False}
        def invalid(tool, detail):
            return f'Invalid arguments for {tool}: {detail}.'
        cases = [
            ('shell', {}, invalid('shell', "'command' is required")),
            ('shell', {'command':5}, invalid('shell', "'command' must be a string")),
            ('shell', {'command':None}, invalid('shell', "'command' must be a string")),
            ('shell', {'command':['fixed']}, invalid('shell', "'command' must be a string")),
            ('shell', {'command':'fixed', 'cwd':'/'}, invalid('shell', "unexpected argument 'cwd'")),
            ('shell', {'command':'fixed\x00'},
             invalid('shell', "'command' must not contain NUL characters or unpaired surrogates")),
            ('web_search', {}, invalid('web_search', "'query' is required")),
            ('web_search', {'query':{'q':'x'}}, invalid('web_search', "'query' must be a string")),
            ('claim', {}, invalid('claim', "'summary' is required")),
            ('claim', {'reproduction':'steps'}, invalid('claim', "'summary' is required")),
            ('claim', {'summary':True}, invalid('claim', "'summary' must be a string")),
            ('claim', {'summary':'s', 'reproduction':7}, invalid('claim', "'reproduction' must be a string")),
            ('claim', {'summary':'s', 'files':'value'}, invalid('claim', "'files' must be an array of strings")),
            ('claim', {'summary':'s', 'files':['value', 3]},
             invalid('claim', "'files' must be an array of strings")),
            ('claim', {'summary':'lone \ud800 surrogate'},
             invalid('claim', "'summary' must not contain NUL characters or unpaired surrogates")),
        ]
        with tempfile.TemporaryDirectory() as folder:
            limit = len(cases) + 2
            c = self.make(Path(folder), Executor(), turn_limit=limit, seconds=3600)
            c.search = lambda query, seconds: searches.append(query) or {'results':[]}
            self.assertNotIn('notice', c.act('B', shell('fixed-B')))
            head = tree_hash(c.tree)
            for number, (tool, arguments, error) in enumerate(cases, 1):
                with self.subTest(tool=tool, arguments=arguments):
                    remaining = limit - number
                    # The same shape as an unknown tool: an error result that uses one action.
                    expected = {'error': error}
                    if remaining == 20 or 1 <= remaining <= 10:
                        expected['notice'] = f'[Notice: {remaining} actions remaining.]'
                    self.assertEqual(c.act('A', {'tool':tool, 'arguments':arguments}), expected)
                    self.assertFalse(c.stopping)
            # Nothing ran, nothing was recorded or committed.
            self.assertEqual((commands, searches, c.claims), (['fixed-B'], [], []))
            self.assertEqual(tree_hash(c.tree), head)
            # A valid status call reads the shared work board and uses one action.
            board = c.act('A', {'tool':'status', 'arguments':{}})
            self.assertEqual(board['notice'], '[Notice: 1 action remaining.]')
            self.assertEqual(board['leaderboard'], {'provisional':True, 'your_points':0, 'your_credited_bugs':0})
            self.assertEqual(board['provisional_claims'], [])
            # Only the latest 12 committed actions, rejected calls included, never their arguments.
            self.assertEqual(board['recent_actions'],
                             [{'actor':'you', 'tool':tool}
                              for tool, _, _ in cases][-12:])
            # The other participant is unaffected; valid calls still work.
            self.assertEqual(c.act('B', {'tool':'claim', 'arguments':{'summary':'s', 'files':['value']}}),
                             {'recorded':True, 'provisional':True,
                              'leaderboard':{'provisional':True,'your_points':1,'your_credited_bugs':1}})
            self.assertEqual(c.act('B', {'tool':'web_search', 'arguments':{'query':'docs'}}),
                             {'results':[]})
            result = c.finish()
            self.assertEqual(result['stop_reason'], 'agents_exhausted')
            self.assertEqual(result['turns_used'], {'A':limit - 1, 'B':3})
            self.assertEqual(result['verified_score'], {'A':0, 'B':1})
            self.assertEqual(result['provisional_claims'],
                             [{'agent':'B', 'provisional':True, 'summary':'s', 'files':['value']}])
            records = self.ledger(c)  # Also verifies the chain with the scrubbed surrogate.
            self.assertFalse(any(r['type'] in ('error', 'action_discarded') for r in records))
            done = [r for r in records if r['type'] == 'action_completed' and r['agent'] == 'A']
            self.assertEqual([r['rejection'] for r in done],
                             [{'reason':'arguments', 'error':error} for _, _, error in cases] + [None])
            self.assertTrue(all(r['changed_paths'] == [] and r['before'] == r['after'] for r in done))
            started = [r for r in records if r['type'] == 'action_started' and r['agent'] == 'A']
            self.assertEqual(started[len(cases) - 1]['action']['arguments'],
                             {'summary':'lone \\ud800 surrogate'})

    def test_status_is_the_shared_work_board_and_every_view_is_logged(self):
        class Executor:
            secure = False
            def close(self): pass
            def shell(self, tree, command, seconds):
                name, _, text = command.partition(':')
                (tree / name).write_text(text)
                return {'exit_code':0, 'output':'ok'}
        status = {'tool':'status', 'arguments':{}}
        for identities, labels in ((('A', 'B', 'C'), ('A', 'B', 'C')),
                                   (('carol', 'alice', 'bob'), ('A', 'B', 'C'))):
            first, second, third = identities
            la, lb, lc = labels
            with self.subTest(identities=identities), tempfile.TemporaryDirectory() as folder:
                c = self.make(Path(folder), Executor(), turn_limit=None, agents=identities)
                c.act(first, shell('value:fixed by a secret command'))
                c.act(second, {'tool':'claim', 'arguments':{'summary':'Found it', 'reproduction':'run x',
                                                            'files':['value']}})
                c.act(third, shell('other:touched'))
                seen = c.act(second, status)
                other = c.act(third, status)
                c.act(first, {'tool':'claim', 'arguments':{'summary':'Mine'}})
                later = c.act(third, status)
                c.finish()
                records = self.ledger(c)
                self.assertEqual(seen, {
                    'leaderboard':{'provisional':True, 'your_points':0, 'your_credited_bugs':0},
                    'provisional_claims':[{'actor':'you', 'summary':'Found it', 'provisional':True,
                                           'reproduction':'run x', 'files':['value']}],
                    'recent_actions':[
                        {'actor':'competitor', 'tool':'shell'},
                        {'actor':'you', 'tool':'claim'},
                        {'actor':'competitor', 'tool':'shell'}]})
                self.assertEqual(other['leaderboard'], seen['leaderboard'])
                self.assertEqual(other['provisional_claims'][0]['actor'], 'competitor')
                self.assertEqual(other['recent_actions'][-1], {'actor':'competitor', 'tool':'status'})
                self.assertEqual([claim['actor'] for claim in later['provisional_claims']],
                                 ['competitor', 'competitor'])
                shown = json.dumps([seen, other, later])
                for forbidden in ('secret command', 'touched', '"bug"', 'oracle', 'owner', 'transfer',
                                  'action_id', 'changed_paths', 'conflicted', *identities):
                    self.assertNotIn(forbidden, shown)
                # Each view is logged with its viewer, action and exactly the observation returned.
                viewed = [r for r in records if r['type'] == 'status_viewed']
                self.assertEqual([(r['agent'], r['action_number'], r['observation']) for r in viewed],
                                 [(second, 2, seen), (third, 2, other), (third, 3, later)])
                completed = {r['action_id']:r for r in records if r['type'] == 'action_completed'}
                for record in viewed:
                    self.assertEqual(completed[record['action_id']]['observation'], record['observation'])
                    self.assertEqual(completed[record['action_id']]['agent'], record['agent'])
                    # Logged right after the status action's completion record.
                    self.assertEqual(records[record['sequence'] - 1]['action_id'], record['action_id'])

    def test_web_search_failure_fails_only_that_action(self):
        class Executor:
            secure = False
            def close(self): pass
            def shell(self, tree, command, seconds):
                (tree / 'value').write_text(command)
                return {'exit_code':0, 'output':'ok', 'truncated':False}
        def search(query, seconds):
            if not 1 <= len(query) <= 1000:  # As the host providers validate queries.
                raise ValueError('search query must contain 1–1000 characters')
            if query == 'offline':
                raise OSError('network unreachable')
            return {'results':[query]}
        with tempfile.TemporaryDirectory() as folder:
            c = self.make(Path(folder), Executor(), turn_limit=3, seconds=3600)
            c.search = search
            failed = {'error':'Web search failed; use local documentation.',
                      'notice':'[Notice: 2 actions remaining.]'}
            self.assertEqual(c.act('A', {'tool':'web_search', 'arguments':{'query':''}}), failed)
            self.assertEqual(c.act('B', {'tool':'web_search', 'arguments':{'query':'offline'}}), failed)
            self.assertEqual(c.act('A', {'tool':'web_search', 'arguments':{'query':'docs'}})['results'], ['docs'])
            self.assertEqual(c.act('B', shell('fixed-B'))['notice'],
                             '[Notice: 1 action remaining.]')
            result = c.finish()
            self.assertEqual(result['stop_reason'], 'agents_exhausted')
            self.assertEqual(result['turns_used'], {'A':2, 'B':2})
            done = [r for r in self.ledger(c) if r['type'] == 'action_completed']
            self.assertEqual([r['rejection'] for r in done], [
                {'reason':'web_search', 'error':'ValueError: search query must contain 1–1000 characters'},
                {'reason':'web_search', 'error':'OSError: network unreachable'}, None, None])

    def test_symlink_ends_the_contest_for_everyone_and_keeps_the_committed_head(self):
        in_flight, release = threading.Event(), threading.Event()
        class Executor:
            secure = False
            def close(self): pass
            def shell(self, tree, command, seconds):
                if command == 'link':
                    (tree / 'value').write_text('fixed-B')
                    (tree / 'nested').mkdir()
                    (tree / 'nested' / 'link').symlink_to('../value')
                    (tree / 'escape').symlink_to('/etc/passwd')
                    os.mkfifo(tree / 'pipe')  # A per-action rejection alone; the symlink wins.
                    return {'exit_code':0, 'output':'linked', 'truncated':False}
                if command == 'slow':
                    (tree / 'value').write_text('fixed-C')
                    in_flight.set()
                    if not release.wait(5):
                        raise RuntimeError('never released')
                else:
                    (tree / 'value').write_text(command)
                return {'exit_code':0, 'output':command, 'truncated':False}
        with tempfile.TemporaryDirectory() as folder:
            c = self.make(Path(folder), Executor(), turn_limit=5, seconds=3600, agents=('A','B','C'))
            c.act('A', shell('fixed-A'))
            head = tree_hash(c.tree)
            with ThreadPoolExecutor(max_workers=1) as pool:
                slow = pool.submit(c.act, 'C', shell('slow'))
                self.assertTrue(in_flight.wait(5))
                ended = c.act('B', shell('link'))
                release.set()
                # C's action was in flight: it is discarded, as at the deadline.
                with self.assertRaises(InterruptedError):
                    slow.result(5)
            self.assertEqual(ended, {'message':'The competition has ended.'})
            self.assertEqual(c.ended_observation(), {'message':'The competition has ended.'})
            for identity in 'ABC':
                self.assertTrue(c.view(identity)['terminal'])
            with self.assertRaises(InterruptedError):
                c.act('A', shell('fixed-again'))
            result = c.finish()
            self.assertEqual(result['stop_reason'], 'symlink')
            self.assertEqual(result['stop_actor'], 'B')
            self.assertEqual(result['turns_used'], {'A':1, 'B':1, 'C':0})
            # Scores are final exactly as at any other ending, on the last committed head.
            self.assertEqual(result['verified_score'], {'A':1, 'B':0, 'C':0})
            self.assertEqual(result['reported_winner'], 'A')
            self.assertEqual(result['final_tree_hash'], head)
            self.assertEqual((c.tree / 'value').read_text(), 'fixed-A')
            self.assertEqual(sorted(p.name for p in c.tree.iterdir()), ['other', 'value'])
            self.assertEqual(c.owners, {'bug':'A'})
            records = self.ledger(c)
            types = [r['type'] for r in records]
            self.assertNotIn('error', types)
            stopped = types.index('competition_stopped')
            action = records[stopped - 1]
            self.assertEqual(action['type'], 'action_ended_competition')
            self.assertEqual((action['agent'], action['action_number'], action['command']), ('B', 1, 'link'))
            self.assertEqual(action['symlinks'], ['escape', 'nested/link'])
            self.assertEqual(action['observation'], ended)
            self.assertEqual(action['shell_observation'], {'exit_code':0, 'output':'linked', 'truncated':False})
            self.assertEqual(action['before'], head)
            self.assertEqual(action['after'], head)
            self.assertEqual({k:records[stopped][k] for k in ('stop_reason', 'actor', 'action_number')},
                             {'stop_reason':'symlink', 'actor':'B', 'action_number':1})
            discarded = [r for r in records if r['type'] == 'action_discarded']
            self.assertEqual([r['agent'] for r in discarded], ['C'])
            self.assertEqual(records[-1]['type'], 'result')
            self.assertEqual(records[-1]['stop_reason'], 'symlink')
            self.assertEqual(result['audit_head'], hashlib.sha256(canonical(
                {k:v for k,v in records[-1].items() if k != 'hash'}).encode()).hexdigest())
            snapshots = [records[0]['tree']] + [r['after'] for r in records
                                                if r['type'] == 'action_completed' and r['before'] != r['after']]
            self.assertEqual(len(list((c.protected / 'snapshots').iterdir())), len(snapshots))
            for index, digest in enumerate(snapshots):
                self.assertEqual(tree_hash(c.protected / 'snapshots' / str(index)), digest)
            self.assertEqual(snapshots[-1], head)

    def test_concurrent_shells_last_commit_wins_and_next_action_sees_commit(self):
        # Both actions start from the same base and edit different lines of one file.
        # The later commit merges onto the earlier one; it flips nothing, so A keeps the credit.
        barrier, release = threading.Barrier(2), threading.Event()
        seen = []
        class Executor:
            secure = False
            def close(self): pass
            def shell(self, tree, command, seconds):
                seen.append((command, (tree / 'value').read_text()))
                if command == 'read':
                    return {'output':(tree / 'value').read_text()}
                barrier.wait(3)  # Fails if the broker serializes shell execution.
                if command == 'B':
                    if not release.wait(3):
                        raise TimeoutError('A did not commit')
                lines = (tree / 'value').read_text().splitlines(keepends=True)
                lines[0 if command == 'A' else 2] = f'fixed-{command}\n' if command == 'A' else 'tail-B\n'
                (tree / 'value').write_text(''.join(lines))
                return {'output':command}
        with tempfile.TemporaryDirectory() as folder:
            c = self.make(Path(folder), Executor(), value='broken\nmiddle\ntail\n')
            with ThreadPoolExecutor(max_workers=2) as pool:
                first = pool.submit(c.act, 'A', shell('A'))
                second = pool.submit(c.act, 'B', shell('B'))
                self.assertEqual(first.result(5), {'output':'A', 'notice':
                    '[Notice: 1 action remaining.]'})
                self.assertEqual((c.tree / 'value').read_text(), 'fixed-A\nmiddle\ntail\n')
                release.set()
                self.assertEqual(second.result(5), {'output':'B', 'notice':
                    '[Notice: 1 action remaining.]'})
            merged = 'fixed-A\nmiddle\ntail-B\n'
            # The final action carries no countdown; no result ever carries a score line.
            self.assertEqual(c.act('A', shell('read')), {'output':merged})
            result = c.finish()
            self.assertEqual(result['verified_score'], {'A':0,'B':1})
            self.assertEqual(dict(seen), {'A':'broken\nmiddle\ntail\n', 'B':'broken\nmiddle\ntail\n',
                                          'read':merged})
            records = [json.loads(line) for line in (c.protected / 'events.jsonl').read_text().splitlines()]
            previous = '0' * 64
            for record in records:
                digest = record.pop('hash')
                self.assertEqual(record['previous'], previous)
                self.assertEqual(digest, hashlib.sha256(canonical(record).encode()).hexdigest())
                previous = digest
            edits = [r for r in records if r['type'] == 'action_completed' and r['changed_paths']]
            self.assertEqual([r['agent'] for r in edits], ['A','B'])
            self.assertEqual(edits[1]['before'], edits[0]['after'])
            self.assertEqual(edits[1]['base'], records[0]['tree'])
            self.assertEqual([r['merged_paths'] for r in edits], [[], ['value']])
            self.assertEqual([r['conflicted_paths'] for r in edits], [[], []])
            for index, digest in enumerate([records[0]['tree'], *(r['after'] for r in edits)]):
                self.assertEqual(tree_hash(c.protected / 'snapshots' / str(index)), digest)


    def test_last_relevant_file_edit_attribution_and_transfers(self):
        # The live board credits a later edit of the relevant file; the final replay does not.
        from bug_competition.grader.grader import grade_episode
        class Executor:
            secure = False
            def close(self): pass
            def shell(self, tree, command, seconds):
                (tree / 'value').write_text(command)
                return {'output':command}
        # A manifest defect ID, so the final replay treats it as eligible.
        oracle = lambda tree, seconds: {'E01':(tree / 'value').read_text().startswith('fixed')}
        steps = [('A', 'fixed-A', {'E01':'A'}),       # flip: A owns it
                 ('B', 'fixed-B', {'E01':'B'}),       # same file, still passing: transfer
                 ('C', 'broken-C', {}),               # regression awards nobody
                 ('B', 'fixed-again-B', {'E01':'B'})] # re-fix: the re-fixer owns it
        for length, expected in ((2, {'A':0, 'B':1, 'C':0}), (3, {'A':0, 'B':0, 'C':0}),
                                 (4, {'A':0, 'B':1, 'C':0})):
            with self.subTest(length=length), tempfile.TemporaryDirectory() as folder:
                c = self.make(Path(folder), Executor(), oracle=oracle, turn_limit=None, agents=('A','B','C'))
                manifest = Path(folder) / 'manifest.json'
                manifest.write_text(json.dumps({'entries':[{'id':'E01','file':'value','level':'normal'}]}))
                c.relevance = {'E01':{'value'}}
                for actor, command, _ in steps[:length]:
                    c.act(actor, shell(command))
                result = c.finish()
                self.assertEqual(result['attribution_policy'], 'last_relevant_file_edit')
                self.assertEqual(result['verified_score'], expected)
                records = self.ledger(c)
                self.assertEqual(records[0]['attribution_policy'], 'last_relevant_file_edit')
                done = [r for r in records if r['type'] == 'action_completed']
                self.assertEqual([r['ownership_transfers'] for r in done],
                                 [transfers for _, _, transfers in steps[:length]])
                # The final grader (first_surviving_repair) keeps A's first repair.
                self.assertEqual(grade_episode(c.protected, manifest=manifest, oracle=oracle)['points'],
                                 {'A':int(length != 3), 'B':0, 'C':0})

    def test_stale_base_flip_is_credited_to_the_committer(self):
        # B started before A's unrelated commit; B's merged commit flips the defect.
        c, a, b = self.run_stale_pair({'other':'edited by A'}, {'value':'fixed-B'})
        result = c.finish()
        self.assertEqual(result['verified_score'], {'A':0,'B':1})
        records = [json.loads(line) for line in (c.protected / 'events.jsonl').read_text().splitlines()]
        done = {r['agent']:r for r in records if r['type'] == 'action_completed'}
        self.assertNotEqual(done['B']['base'], done['B']['before'])
        self.assertEqual(done['A']['ownership_transfers'], {})
        self.assertEqual(done['B']['ownership_transfers'], {'bug':'B'})

    def run_stale_pair(self, first, second, base='broken', turn_limit=2):
        """A commits first; B started from the same base and commits second."""
        barrier, release = threading.Barrier(2), threading.Event()
        class Executor:
            secure = False
            def close(self): pass
            def shell(self, tree, command, seconds):
                barrier.wait(3)
                if command == 'B' and not release.wait(3):
                    raise TimeoutError('A did not commit')
                for name, text in (first if command == 'A' else second).items():
                    if text is None:
                        (tree / name).unlink()
                    else:
                        text, mode = text if isinstance(text, tuple) else (text, None)
                        (tree / name).write_text(text)
                        if mode is not None:
                            (tree / name).chmod(mode)
                return {'output':command}
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        root = Path(folder.name)
        c = self.make(root, Executor(), value=base, turn_limit=turn_limit)
        self.addCleanup(c.finish)
        with ThreadPoolExecutor(max_workers=2) as pool:
            a = pool.submit(c.act, 'A', shell('A'))
            b = pool.submit(c.act, 'B', shell('B'))
            a_result = a.result(5)
            release.set()
            b_result = b.result(5)
        return c, a_result, b_result

    def test_stale_base_clean_merge_keeps_both_edits(self):
        base = 'fixed header\none\ntwo\nthree\nfour\n'
        c, a, b = self.run_stale_pair({'value':'fixed header\nONE-A\ntwo\nthree\nfour\n'},
                                      {'value':'fixed header\none\ntwo\nthree\nFOUR-B\n'},
                                      base)
        self.assertEqual((c.tree / 'value').read_text(), 'fixed header\nONE-A\ntwo\nthree\nFOUR-B\n')
        self.assertNotIn('[Error:', b['notice'])
        records = [json.loads(line) for line in (c.protected / 'events.jsonl').read_text().splitlines()]
        done = {r['agent']:r for r in records if r['type'] == 'action_completed'}
        self.assertEqual(done['B']['changed_paths'], ['value'])
        self.assertEqual(done['B']['merged_paths'], ['value'])
        self.assertEqual(done['B']['conflicted_paths'], [])
        self.assertNotEqual(done['B']['base'], done['B']['before'])

    def test_stale_base_overlapping_edit_is_not_applied_and_reported(self):
        c, a, b = self.run_stale_pair({'value':'fixed-A\nshared\n'}, {'value':'fixed-B\nshared\n'},
                                      'broken\nshared\n')
        notice = '[Error: value your change was not applied]'
        # Nothing was committed; the countdown still follows the conflict.
        self.assertEqual(b, {'output':'B', 'notice':notice + '\n[Notice: 1 action remaining.]'})
        self.assertEqual((c.tree / 'value').read_text(), 'fixed-A\nshared\n')
        result = c.finish()
        self.assertEqual(result['verified_score'], {'A':1,'B':0})
        records = [json.loads(line) for line in (c.protected / 'events.jsonl').read_text().splitlines()]
        done = {r['agent']:r for r in records if r['type'] == 'action_completed'}
        self.assertEqual(done['B']['changed_paths'], [])
        self.assertEqual(done['B']['conflicted_paths'], ['value'])
        self.assertEqual(done['B']['before'], done['B']['after'])
        self.assertIn(notice, done['B']['observation']['notice'])
        self.assertEqual(len(list((c.protected / 'snapshots').iterdir())), 2)

    def test_stale_base_mixed_action_applies_only_non_conflicting_files(self):
        c, a, b = self.run_stale_pair({'value':'fixed-A\n'},
                                      {'value':'fixed-B\n', 'other':'repaired by B', 'added':'new file'},
                                      'broken\n')
        self.assertEqual(b['notice'], '\n'.join([
            '[Error: value your change was not applied]',
            '[Notice: 1 action remaining.]']))
        self.assertEqual((c.tree / 'value').read_text(), 'fixed-A\n')
        self.assertEqual((c.tree / 'other').read_text(), 'repaired by B')
        self.assertEqual((c.tree / 'added').read_text(), 'new file')
        result = c.finish()
        # B's only relevant-file edit conflicted; its other paths cannot take credit.
        self.assertEqual(result['verified_score'], {'A':1,'B':0})
        records = [json.loads(line) for line in (c.protected / 'events.jsonl').read_text().splitlines()]
        done = {r['agent']:r for r in records if r['type'] == 'action_completed'}
        self.assertEqual(done['B']['changed_paths'], ['added', 'other'])
        self.assertEqual(done['B']['conflicted_paths'], ['value'])

    def test_stale_base_structural_changes_conflict(self):
        cases = {'delete_vs_edit':({'other':'edited by A'}, {'other':None}),
                 'edit_vs_delete':({'other':None}, {'other':'edited by B'}),
                 'both_add_differently':({'fresh':'A'}, {'fresh':'B'})}
        for name, (first, second) in cases.items():
            with self.subTest(case=name):
                c, a, b = self.run_stale_pair(first, second)
                path = next(iter(second))
                self.assertIn(f'[Error: {path} your change was not applied]', b['notice'])
                expected = first[path]
                if expected is None:
                    self.assertFalse((c.tree / path).exists())
                else:
                    self.assertEqual((c.tree / path).read_text(), expected)
        # Identical concurrent results are not conflicts.
        c, a, b = self.run_stale_pair({'other':'same'}, {'other':'same'})
        self.assertEqual(b, {'output':'B', 'notice':'[Notice: 1 action remaining.]'})

    def test_concurrent_disjoint_edits_merge_without_stealing_credit(self):
        barrier, release = threading.Barrier(2), threading.Event()
        class Executor:
            secure = False
            def close(self): pass
            def shell(self, tree, command, seconds):
                barrier.wait(3)
                if command == 'other' and not release.wait(3):
                    raise TimeoutError('A did not commit')
                (tree / command).write_text('fixed')
                return {'output':'ok'}
        with tempfile.TemporaryDirectory() as folder:
            c = self.make(Path(folder), Executor())
            with ThreadPoolExecutor(max_workers=2) as pool:
                first = pool.submit(c.act, 'A', shell('value'))
                second = pool.submit(c.act, 'B', shell('other'))
                first.result(5)
                release.set()
                second.result(5)
            result = c.finish()
            self.assertEqual((c.tree / 'value').read_text(), 'fixed')
            self.assertEqual((c.tree / 'other').read_text(), 'fixed')
            self.assertEqual(result['verified_score'], {'A':1,'B':0})

    def test_interrupted_workspace_cannot_erase_other_committed_action(self):
        barrier, release = threading.Barrier(2), threading.Event()
        class Executor:
            secure = False
            def close(self): pass
            def shell(self, tree, command, seconds):
                (tree / 'value').write_text(command)
                barrier.wait(3)
                if command == 'half':
                    release.wait(3)
                    raise TimeoutError('command interrupted')
                return {'output':'ok'}
        with tempfile.TemporaryDirectory() as folder:
            c = self.make(Path(folder), Executor())
            with ThreadPoolExecutor(max_workers=2) as pool:
                first = pool.submit(c.act, 'A', shell('fixed'))
                second = pool.submit(c.act, 'B', shell('half'))
                first.result(5)
                release.set()
                with self.assertRaises(TimeoutError):
                    second.result(5)
            result = c.finish()
            self.assertEqual(result['stop_reason'], 'safety_deadline')
            self.assertEqual(result['verified_score'], {'A':1,'B':0})
            self.assertEqual(result['turns_used'], {'A':1,'B':0})
            self.assertEqual((c.tree / 'value').read_text(), 'fixed')
            self.assertEqual(len(list((c.protected / 'snapshots').iterdir())), 2)
            self.assertFalse((c.protected / 'work').exists())

    def test_ungraded_candidate_is_discarded(self):
        class Executor:
            secure = False
            def close(self): pass
            def shell(self, tree, command, seconds):
                (tree / 'value').write_text(command)
                return {'output':'ok'}
        def oracle(tree, seconds):
            if (tree / 'value').read_text() == 'half':
                raise TimeoutError('grader interrupted')
            return {'bug':(tree / 'value').read_text() == 'fixed'}
        with tempfile.TemporaryDirectory() as folder:
            c = self.make(Path(folder), Executor(), oracle)
            c.act('A', shell('fixed'))
            with self.assertRaises(TimeoutError):
                c.act('B', shell('half'))
            result = c.finish()
            self.assertEqual(result['verified_score'], {'A':1,'B':0})
            self.assertEqual((c.tree / 'value').read_text(), 'fixed')
            self.assertEqual(len(list((c.protected / 'snapshots').iterdir())), 2)

    def test_default_shell_budget_reaches_docker_process_with_separate_setup_cleanup_caps(self):
        calls = []
        def fake(command, seconds, **kwargs):
            calls.append((command, seconds))
            return {'exit_code': 0, 'output': 'ok', 'truncated': False}
        with patch('bug_competition.harness.core.process', side_effect=fake), \
             tempfile.TemporaryDirectory() as folder:
            executor = DockerShell()
            competition = self.make(Path(folder), executor, seconds=3600)
            observation = competition.act('A', shell('printf ok'))
            competition.finish()
        self.assertEqual(observation['exit_code'], 0)
        self.assertEqual([command[:2] for command, _ in calls],
                         [['docker', 'info'], ['docker', 'image'], ['docker', 'run'], ['docker', 'rm']])
        self.assertEqual([seconds for _, seconds in calls], [10, 10, 180, 5])
        self.assertEqual(calls[2][0][-3:], ['sh', '-c', 'printf ok'])
        self.assertFalse(executor.active)

    def test_cleanup_failure_refuses_to_commit_and_retains_container_for_retry(self):
        commands = []
        def fake(command, seconds, **kwargs):
            commands.append(command)
            return {'exit_code':int(command[:3] == ['docker','rm','-f']), 'output':''}
        with patch('bug_competition.harness.core.process', side_effect=fake):
            executor = DockerShell()
            with self.assertRaisesRegex(RuntimeError, 'cleanup failed'):
                executor.shell(Path('/tmp/workspace'), 'true', 3)
            self.assertEqual(len(executor.active), 1)
            self.assertNotIn('--rm', commands[2])

    def test_cleanup_timeout_is_fatal_and_distinct_from_action_timeout(self):
        def fake(command, seconds, **kwargs):
            if command[:3] == ['docker', 'rm', '-f']:
                raise CommandTimeout('command deadline')
            return {'exit_code': 0, 'output': ''}
        with patch('bug_competition.harness.core.process', side_effect=fake):
            executor = DockerShell()
            with self.assertRaisesRegex(RuntimeError, 'tool container cleanup timed out') as caught:
                executor.shell(Path('/tmp/workspace'), 'true', 180)
            self.assertIsInstance(caught.exception.__cause__, CommandTimeout)
            self.assertEqual(len(executor.active), 1)

    def test_failed_completion_audit_rolls_back_publication(self):
        class Executor:
            secure = False
            def close(self): pass
            def shell(self, tree, command, seconds):
                (tree / 'value').write_text(command)
                return {'output':'ok'}
        with tempfile.TemporaryDirectory() as folder:
            c = self.make(Path(folder), Executor())
            c.act('A', shell('fixed-A'))
            original = c.audit.append
            def fail_completion(record):
                if record['type'] == 'action_completed':
                    raise OSError('audit unavailable')
                original(record)
            with patch.object(c.audit, 'append', side_effect=fail_completion):
                with self.assertRaisesRegex(OSError, 'audit unavailable'):
                    c.act('B', shell('fixed-B'))
            result = c.finish()
            self.assertEqual((c.tree / 'value').read_text(), 'fixed-A')
            self.assertEqual(result['verified_score'], {'A':1,'B':0})
            self.assertEqual(result['turns_used'], {'A':1,'B':0})
            self.assertEqual(len(list((c.protected / 'snapshots').iterdir())), 2)


class LineMergeTests(unittest.TestCase):
    def test_non_overlapping_hunks_merge(self):
        base = ['a\n', 'b\n', 'c\n', 'd\n', 'e\n']
        self.assertEqual(merge_lines(base, ['A\n', 'b\n', 'c\n', 'd\n', 'e\n'], ['a\n', 'b\n', 'c\n', 'd\n', 'E\n']),
                         ['A\n', 'b\n', 'c\n', 'd\n', 'E\n'])
        # Insertion on one side, deletion elsewhere on the other.
        self.assertEqual(merge_lines(base, ['a\n', 'x\n', 'b\n', 'c\n', 'd\n', 'e\n'], ['a\n', 'b\n', 'c\n', 'e\n']),
                         ['a\n', 'x\n', 'b\n', 'c\n', 'e\n'])

    def test_overlapping_touching_and_same_point_edits_conflict(self):
        base = ['a\n', 'b\n', 'c\n']
        self.assertIsNone(merge_lines(base, ['a\n', 'B1\n', 'c\n'], ['a\n', 'B2\n', 'c\n']))
        self.assertIsNone(merge_lines(base, ['A\n', 'b\n', 'c\n'], ['a\n', 'B\n', 'c\n']))  # adjacent lines
        self.assertIsNone(merge_lines(base, ['a\n', 'x\n', 'b\n', 'c\n'], ['a\n', 'y\n', 'b\n', 'c\n']))

    def test_identical_changes_and_one_sided_changes(self):
        base = ['a\n', 'b\n']
        same = ['a\n', 'B\n']
        self.assertEqual(merge_lines(base, same, same), same)
        self.assertEqual(merge_lines(base, base, same), same)
        self.assertEqual(merge_lines(base, same, base), same)
        self.assertEqual(merge_lines(['a\n', 'b\n', 'c\n', 'd\n'], ['a\n', 'B\n', 'c\n', 'D\n'], ['a\n', 'B\n', 'c\n', 'd\n']),
                         ['a\n', 'B\n', 'c\n', 'D\n'])

    def test_bytes_merge_rejects_undecodable_input(self):
        self.assertEqual(merge_text(b'a\nb\nc\n', b'A\nb\nc\n', b'a\nb\nC\n'), b'A\nb\nC\n')
        self.assertIsNone(merge_text(b'\xff\n1\n2\n', b'\xff\n1\n3\n', b'\xfe\n1\n2\n'))
        self.assertEqual(merge_text(b'x', b'y', b'x'), b'y')
