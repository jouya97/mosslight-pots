"""The status tool shows the shared provisional work board; committed changes carry no score line."""
import json
from pathlib import Path
import tempfile
import unittest

from bug_competition.grader.grader import grade_episode
from bug_competition.grader.weights import manifest_weights
from bug_competition.harness.core import Competition, ScriptedAgent
from bug_competition.harness.parallel import ParallelCompetition


def shell(file, text):
    # Commands are strings, as the tool schema requires; this executor decodes JSON.
    return {'tool': 'shell', 'arguments': {'command': json.dumps([file, text])}}


def claim():
    return {'tool': 'claim', 'arguments': {'summary': 'I repaired it', 'files': ['mosslight/engine.py']}}


def failed():
    return {'tool': 'shell', 'arguments': {'command': json.dumps([None, None])}}


def status():
    return {'tool': 'status', 'arguments': {}}


def board(**rows):
    """Expected leaderboard: actor -> (provisional points, credited repairs)."""
    return rows


def standings(observation):
    """Only the caller's points and credited repairs are public."""
    row = observation['leaderboard']
    return row['your_points'], row['your_credited_bugs']


def label(actor, viewer):
    return 'you' if actor == viewer else 'competitor'


def credit(points, bugs):
    return {'provisional': True, 'your_points': points, 'your_credited_bugs': bugs}


BOARD_KEYS = {'leaderboard', 'provisional_claims', 'recent_actions'}
NEVER = ('oracle', 'owner', 'transfer', 'verdict', 'Score', 'E01', 'E02', 'I02', 'X01', 'irrigation.py',
         'command', 'changed_paths', 'conflicted', 'credited_repairs')
BOARD_ONLY = ('provisional_claims', 'recent_actions', 'competitor', 'claims', 'engine.py')


class FileExecutor:
    secure = False

    def shell(self, tree, command, seconds):
        file, text = json.loads(command)
        if file is None:
            return {'exit_code': 1, 'output': 'no such file'}
        (tree / file).write_text(text)
        return {'exit_code': 0, 'output': 'ok'}

    def close(self):
        pass


def oracle(tree, seconds):
    fixed = (tree / 'mosslight/engine.py').read_text().startswith('fixed')
    return {'E01': fixed, 'E02': fixed, 'X01': True, 'I02': fixed}


def make_tree(root):
    tree = root / 'shared'
    (tree / 'mosslight').mkdir(parents=True)
    (tree / 'mosslight/__init__.py').write_text('')
    (tree / 'mosslight/engine.py').write_text('broken')
    (tree / 'mosslight/other.py').write_text('')
    return tree


class ScoreFeedbackTests(unittest.TestCase):
    def test_status_reports_own_score_and_committed_changes_carry_none(self):
        # Tiered scoring (E01=1, E02=5, I02=20) and last_relevant_file_edit attribution:
        # A's engine.py edit flips E01/E02/I02 to passing; B's later engine.py
        # edit takes E01/E02 (their manifest file); indirect repair I02 stays with A. A regression
        # clears ownership and the false-to-true restore credits the re-fixer.
        # The third element is the expected status result for a status action (None otherwise).
        # Actors alternate so the serial round-robin scheduler replays the same order.
        steps = [
            ('A', shell('mosslight/engine.py', 'fixed A'), None),
            ('B', status(), board(A=(26, 3), B=(0, 0))),
            ('A', status(), board(A=(26, 3), B=(0, 0))),
            ('B', shell('mosslight/other.py', 'unrelated edit'), None),
            ('A', claim(), None),
            ('B', shell('mosslight/engine.py', 'fixed B'), None),      # B takes the 2 defects whose manifest lists engine.py
            ('A', status(), board(A=(20, 1), B=(6, 2))),
            ('B', status(), board(A=(20, 1), B=(6, 2))),
            ('A', shell('mosslight/engine.py', 'broken again'), None),
            ('B', status(), board(A=(0, 0), B=(0, 0))),
            ('A', failed(), None),
            ('B', shell('mosslight/engine.py', 'fixed restored B'), None),
            ('A', shell('mosslight/engine.py', 'fixed restored B'), None),  # byte-identical: no change
            ('B', status(), board(A=(0, 0), B=(26, 3))),
            ('A', status(), board(A=(0, 0), B=(26, 3))),
            ('B', claim(), None),
        ]
        for scheduler in (Competition, ParallelCompetition):
            for length, expected in ((4, {'A': 26, 'B': 0}),
                                     (8, {'A': 20, 'B': 6}),
                                     (10, {'A': 0, 'B': 0}),
                                     (16, {'A': 0, 'B': 26})):
                with self.subTest(scheduler=scheduler.__name__, length=length), tempfile.TemporaryDirectory() as folder:
                    root = Path(folder)
                    tree = make_tree(root)
                    agents = {name: ScriptedAgent([action for actor, action, _ in steps[:length]
                                                  if actor == name]) for name in ('A', 'B')}
                    competition = scheduler(tree, root / 'protected', FileExecutor(), oracle,
                                            agents, weights=manifest_weights())
                    if scheduler is ParallelCompetition:
                        competition.begin(10, turn_limit=None)
                        results = [competition.act(actor, action) for actor, action, _ in steps[:length]]
                        result = competition.finish()
                    else:
                        result = competition.run(10)
                        results = None
                    self.assertEqual(result['diagnostic_score'], expected)
                    self.assertEqual(grade_episode(root / 'protected', oracle=oracle)['points'], expected)
                    records = [json.loads(line) for line in (root / 'protected/events.jsonl').read_text().splitlines()]
                    completed = [r for r in records if r['type'] == 'action_completed']
                    # Every status call counts as one action and is recorded like any other.
                    self.assertEqual(len(completed), length)
                    if scheduler is ParallelCompetition:
                        self.assertEqual(sum(result['turns_used'].values()), length)
                    viewed = [r for r in records if r['type'] == 'status_viewed']
                    shown = []
                    for index, (record, (actor, action, expected_board)) in enumerate(zip(completed, steps[:length])):
                        observation = record['observation']
                        self.assertEqual(record['agent'], actor)
                        self.assertEqual(record['action'], action)
                        if results is not None:
                            self.assertEqual(results[index], observation)
                        # No score line, or any notice, without a turn limit.
                        self.assertNotIn('notice', observation)
                        for forbidden in NEVER:
                            self.assertNotIn(forbidden, json.dumps(observation))
                        if action['tool'] == 'status':
                            self.assertEqual(set(observation), BOARD_KEYS)
                            self.assertEqual(observation['leaderboard'], credit(*expected_board[actor]))
                            # Every earlier claim, by any actor, in order.
                            self.assertEqual(observation['provisional_claims'],
                                             [{'actor': label(r['agent'], actor), 'provisional': True, 'reproduction': '',
                                               **r['action']['arguments']}
                                              for r in completed[:index] if r['action']['tool'] == 'claim'])
                            # The last 12 earlier committed actions disclose only actor and tool.
                            self.assertEqual(observation['recent_actions'],
                                             [{'actor': label(r['agent'], actor), 'tool': r['action']['tool']}
                                              for r in completed[:index]][-12:])
                            self.assertEqual(record['changed_paths'], [])
                            shown.append((actor, observation))
                        else:
                            for forbidden in BOARD_ONLY:
                                self.assertNotIn(forbidden, json.dumps(observation))
                        if action['tool'] == 'claim':
                            self.assertEqual(observation, {'recorded': True, 'provisional': True,
                                'leaderboard': credit(26, 3)})
                    # Each status view is logged with exactly what its caller saw.
                    self.assertEqual([(r['agent'], r['observation']) for r in viewed], shown)
                    # The last status of each actor matches the final (diagnostic) board.
                    if length == 16:
                        last = results[-3] if results else completed[-3]['observation']
                        self.assertEqual(standings(last), (26, 3))
                        self.assertEqual(last['leaderboard'], credit(26, 3))
                        self.assertIn({'actor': 'competitor', 'tool': 'shell'}, last['recent_actions'])

    def test_status_matches_the_board_at_every_point(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            competition = ParallelCompetition(make_tree(root), root / 'protected', FileExecutor(), oracle,
                                              {'A': ScriptedAgent([]), 'B': ScriptedAgent([]), 'C': ScriptedAgent([])},
                                              weights=manifest_weights())
            competition.begin(10, turn_limit=None)
            edits = [('A', 'fixed A'), ('B', 'fixed B'), ('C', 'broken'), ('C', 'fixed C')]
            for actor, text in edits:
                competition.act(actor, shell('mosslight/engine.py', text))
                board = competition._points()
                for viewer in ('A', 'B', 'C'):
                    seen = competition.act(viewer, status())
                    self.assertEqual(standings(seen)[0], board[viewer])
                    self.assertEqual(set(seen), BOARD_KEYS)
            result = competition.finish()
        self.assertEqual(result['diagnostic_score'], {'A': 0, 'B': 0, 'C': 26})

    def test_status_is_a_tool_that_takes_no_arguments(self):
        from bug_competition.harness.core import TOOLS, argument_error
        self.assertEqual([tool['name'] for tool in TOOLS], ['shell', 'claim', 'status', 'web_search'])
        schema = next(tool for tool in TOOLS if tool['name'] == 'status')['input_schema']
        self.assertEqual(schema, {'type': 'object', 'properties': {}, 'additionalProperties': False})
        self.assertIsNone(argument_error('status', {}))
        self.assertEqual(argument_error('status', {'agent': 'B'}),
                         "Invalid arguments for status: unexpected argument 'agent'.")
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            competition = ParallelCompetition(make_tree(root), root / 'protected', FileExecutor(), oracle,
                                              {'A': ScriptedAgent([]), 'B': ScriptedAgent([])},
                                              weights=manifest_weights())
            competition.begin(10, turn_limit=None)
            competition.act('B', shell('mosslight/engine.py', 'fixed B'))
            # Arguments cannot select another actor's numbers; the call is rejected and still counts.
            self.assertEqual(competition.act('A', {'tool': 'status', 'arguments': {'agent': 'B'}}),
                             {'error': "Invalid arguments for status: unexpected argument 'agent'."})
            seen_a, seen_b = competition.act('A', status()), competition.act('B', status())
            result = competition.finish()
            records = [json.loads(line) for line in (root / 'protected/events.jsonl').read_text().splitlines()]
        self.assertEqual(result['turns_used'], {'A': 2, 'B': 2})
        self.assertEqual(seen_a['leaderboard'], credit(0, 0))
        self.assertEqual(seen_b['leaderboard'], credit(26, 3))
        # The rejected call shows no board and is not logged as a status view.
        self.assertEqual([r['observation'] for r in records if r['type'] == 'status_viewed'], [seen_a, seen_b])

    def test_notice_order_is_conflict_then_countdown_with_no_score(self):
        import threading
        from concurrent.futures import ThreadPoolExecutor
        barrier, release = threading.Barrier(2), threading.Event()

        class StaleExecutor(FileExecutor):
            # 'A' and 'B' start from the same head; B finishes only after A has committed.
            def shell(self, tree, command, seconds):
                if command in ('A', 'B'):
                    barrier.wait(3)
                    if command == 'B' and not release.wait(3):
                        raise TimeoutError('A did not commit')
                    (tree / 'mosslight/engine.py').write_text(f'fixed {command}\n')
                    if command == 'B':
                        (tree / 'mosslight/other.py').write_text('B elsewhere\n')
                    return {'exit_code': 0, 'output': command}
                return super().shell(tree, command, seconds)

        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            competition = ParallelCompetition(make_tree(root), root / 'protected', StaleExecutor(), oracle,
                                              {'A': ScriptedAgent([]), 'B': ScriptedAgent([])},
                                              weights=manifest_weights())
            competition.begin(10, turn_limit=4)
            with ThreadPoolExecutor(max_workers=2) as pool:
                a = pool.submit(competition.act, 'A', {'tool': 'shell', 'arguments': {'command': 'A'}})
                b = pool.submit(competition.act, 'B', {'tool': 'shell', 'arguments': {'command': 'B'}})
                first = a.result(5)
                release.set()
                second = b.result(5)
            third = competition.act('A', status())
            fourth = competition.act('A', claim())
            fifth = competition.act('A', status())
            sixth = competition.act('B', status())
            competition.finish()
            records = [json.loads(line) for line in (root / 'protected/events.jsonl').read_text().splitlines()]
        # A committed a repair: no score line, only the countdown.
        self.assertEqual(first, {'exit_code': 0, 'output': 'A', 'notice': '[Notice: 3 actions remaining.]'})
        # B's engine.py edit conflicted but other.py committed: conflict, then countdown, no score.
        self.assertEqual(second, {'exit_code': 0, 'output': 'B', 'notice':
                                  '[Error: mosslight/engine.py your change was not applied]\n'
                                  '[Notice: 3 actions remaining.]'})
        done = [r for r in records if r['type'] == 'action_completed']
        self.assertEqual(done[1]['changed_paths'], ['mosslight/other.py'])
        self.assertEqual(done[1]['conflicted_paths'], ['mosslight/engine.py'])
        # The countdown rides on a status result like any other.
        self.assertEqual(third['notice'], '[Notice: 2 actions remaining.]')
        self.assertEqual(standings(third), (26, 3))
        # Paths and conflict details remain in the ledger, never the board.
        self.assertEqual(third['recent_actions'],
                         [{'actor': 'you', 'tool': 'shell'}, {'actor': 'competitor', 'tool': 'shell'}])
        self.assertEqual(fourth, {'recorded': True, 'provisional': True, 'leaderboard': credit(26, 3),
                                  'notice': '[Notice: 1 action remaining.]'})
        self.assertNotIn('notice', fifth)
        self.assertEqual(standings(fifth), (26, 3))
        self.assertEqual(fifth['provisional_claims'], [{'actor': 'you', 'summary': 'I repaired it',
            'reproduction': '', 'provisional': True, 'files': ['mosslight/engine.py']}])
        self.assertEqual(sixth['notice'], '[Notice: 2 actions remaining.]')
        self.assertEqual(sixth['provisional_claims'], [{'actor': 'competitor', 'summary': 'I repaired it',
            'reproduction': '', 'provisional': True, 'files': ['mosslight/engine.py']}])
        # The ledger holds exactly what each viewer was shown, notices included.
        viewed = [r for r in records if r['type'] == 'status_viewed']
        self.assertEqual([(r['agent'], r['action_number'], r['observation']) for r in viewed],
                         [('A', 2, third), ('A', 4, fifth), ('B', 2, sixth)])
        self.assertFalse(any('Score' in json.dumps(r.get('observation')) for r in done))

    def test_notice_at_twenty_then_countdown_from_ten_without_using_an_action(self):
        from bug_competition.harness.parallel import ACTIONS_REMAINING_NOTICES, actions_remaining_notice
        self.assertEqual(ACTIONS_REMAINING_NOTICES[20], '[Notice: 20 actions remaining.]')
        self.assertEqual(ACTIONS_REMAINING_NOTICES[2], '[Notice: 2 actions remaining.]')
        self.assertEqual(ACTIONS_REMAINING_NOTICES[1], '[Notice: 1 action remaining.]')
        self.assertEqual(sorted(ACTIONS_REMAINING_NOTICES), [*range(1, 11), 20])
        # Result of action k shows limit - k: 20 once, then 10..1, below the limit.
        explicit = {150: {130: 20, **{k: 150 - k for k in range(140, 150)}},
                    25: {5: 20, **{k: 25 - k for k in range(15, 25)}},
                    21: {1: 20, **{k: 21 - k for k in range(11, 21)}},
                    20: {k: 20 - k for k in range(10, 20)},
                    12: {k: 12 - k for k in range(2, 12)},
                    11: {k: 11 - k for k in range(1, 11)},
                    10: {k: 10 - k for k in range(1, 10)},
                    5: {1: 4, 2: 3, 3: 2, 4: 1},
                    1: {}}
        self.assertEqual(explicit[150][130], 20)
        self.assertEqual(explicit[150][149], 1)
        self.assertEqual(actions_remaining_notice(150, 129), None)
        for action in range(131, 140):
            self.assertIsNone(actions_remaining_notice(150, action))
        self.assertEqual(actions_remaining_notice(150, 150), None)
        self.assertEqual(actions_remaining_notice(None, 1), None)
        for limit, expected in explicit.items():
            with self.subTest(limit=limit), tempfile.TemporaryDirectory() as folder:
                root = Path(folder)
                tree = make_tree(root)
                competition = ParallelCompetition(tree, root / 'protected', FileExecutor(), oracle,
                                                  {'A': ScriptedAgent([]), 'B': ScriptedAgent([])},
                                                  weights=manifest_weights())
                competition.begin(60, turn_limit=limit)
                observations = []
                while not competition.view('A')['terminal']:
                    observations.append(competition.act('A', claim()))
                result = competition.finish()
                # Notices never consume an action.
                self.assertEqual(len(observations), limit)
                self.assertEqual(result['turns_used'], {'A': limit, 'B': 0})
                noticed = {n: o['notice'] for n, o in enumerate(observations, 1) if 'notice' in o}
                self.assertEqual(noticed, {n: ACTIONS_REMAINING_NOTICES[k] for n, k in expected.items()})
                # Exactly the scheduled actions carry a notice, never the final action.
                self.assertEqual(sorted(noticed), sorted(expected))
                self.assertNotIn(limit, noticed)
                # The limit itself is never announced.
                self.assertTrue(all(k < limit for k in expected.values()))
                self.assertNotIn(f'[Notice: {limit} action', json.dumps(observations))
                records = [json.loads(line) for line in (root / 'protected/events.jsonl').read_text().splitlines()]
                ledger = [r['observation']['notice'] for r in records
                          if r['type'] == 'action_completed' and 'notice' in r.get('observation', {})]
                self.assertEqual(ledger, [ACTIONS_REMAINING_NOTICES[expected[n]] for n in sorted(expected)])

if __name__ == '__main__':
    unittest.main()
