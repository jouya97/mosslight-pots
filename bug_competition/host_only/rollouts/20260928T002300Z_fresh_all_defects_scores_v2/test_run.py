"""Focused offline checks for fresh-run wiring; no Docker or model calls."""
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from inspect_ai.model import ModelOutput

import run
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
        self.assertEqual(len(prompt.encode('utf-8')), 1756)
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


if __name__ == '__main__':
    unittest.main()
