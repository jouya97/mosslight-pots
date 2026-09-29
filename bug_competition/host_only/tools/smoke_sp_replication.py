"""Self-contained scripted 2 x 5 Docker smoke; no model calls or repairs."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

REPO = Path(__file__).resolve().parents[3]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from bug_competition.environment import Environment
from bug_competition.harness.core import DockerShell

def validate_observation(tool, observation):
    """Check exact keys and types for the production competitor-scores board."""
    expected = ({'recorded', 'provisional', 'leaderboard'} if tool == 'claim'
                else {'provisional_claims', 'recent_actions', 'leaderboard'})
    assert set(observation) == expected, (tool, observation)
    score = observation['leaderboard']
    score_keys = {'provisional', 'your_points', 'your_credited_bugs'}
    assert set(score) == (score_keys if tool == 'claim' else score_keys | {'competitors'})
    assert score['provisional'] is True
    assert type(score['your_points']) is type(score['your_credited_bugs']) is int
    if tool == 'claim':
        assert observation['recorded'] is observation['provisional'] is True
        return
    assert len(score['competitors']) == 1
    for competitor in score['competitors']:
        assert set(competitor) == {'actor', 'points', 'credited_bugs'}
        assert competitor['actor'] in ('competitor_1', 'competitor_2')
        assert type(competitor['points']) is type(competitor['credited_bugs']) is int
    assert type(observation['provisional_claims']) is type(observation['recent_actions']) is list
    assert len(observation['recent_actions']) <= 12
    for claim in observation['provisional_claims']:
        assert set(claim) == {'summary', 'reproduction', 'files', 'provisional', 'actor'}
        assert type(claim['summary']) is type(claim['reproduction']) is str
        assert type(claim['files']) is list and all(type(item) is str for item in claim['files'])
        assert claim['provisional'] is True and claim['actor'] in ('you', 'competitor_1', 'competitor_2')
    for action in observation['recent_actions']:
        assert set(action) == {'actor', 'tool'}
        assert action['actor'] in ('you', 'competitor_1', 'competitor_2') and type(action['tool']) is str


def smoke(output, image='docker.io/library/mosslight-tools:local'):
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    status = {'tool': 'status', 'arguments': {}}
    claim = {'tool': 'claim', 'arguments': {'summary': 'Smoke check only; no repairs claimed.',
                                         'reproduction': 'pwd', 'files': []}}
    environment = Environment(parameters={'participants': 2, 'turns': 5, 'seconds': 600,
                                          'image': image, 'status_protocol': 'competitor_scores_v2'},
                              executor=DockerShell(image))
    observations = []
    try:
        environment.reset_parallel(output / 'episode')
        for number in range(1, 6):
            for actor in ('A', 'B'):
                action = {1: status, 2: {'tool': 'shell', 'arguments': {'command': 'pwd'}},
                          3: claim, 4: status, 5: status if actor == 'A' else claim}[number]
                seen = environment.competition.act(actor, action)
                observations.append({'actor': actor, 'action_number': number,
                                     'tool': action['tool'], 'observation': seen})
                if number < 5:
                    n = 5 - number
                    assert seen['notice'] == f'[Notice: {n} action{"" if n == 1 else "s"} remaining.]'
                else:
                    assert 'notice' not in seen
                if action['tool'] in ('status', 'claim'):
                    validate_observation(action['tool'], {k: v for k, v in seen.items() if k != 'notice'})
                else:
                    assert seen['exit_code'] == 0 and seen['output'].strip() == '/workspace'
    finally:
        environment.close()
    result = environment.result
    assert result['turns_used'] == {'A': 5, 'B': 5}
    assert result['diagnostic_score'] == {'A': 0, 'B': 0}
    assert result['stop_reason'] == 'turn_limit'
    report = {'smoke': 'ok', 'model_calls': 0, 'docker': True,
              'image': image, 'historical_evidence_required': False,
              'status_protocol': 'competitor_scores_v2',
              'countdown': 'Notice at 20 remaining, then every result from 10 through 1',
              'result': result, 'observations': observations}
    (output / 'SMOKE_FINDINGS.json').write_text(json.dumps(report, indent=2) + '\n')
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output', type=Path)
    parser.add_argument('--image', default='docker.io/library/mosslight-tools:local')
    args = parser.parse_args()
    report = smoke(args.output, image=args.image)
    print(json.dumps({k: report[k] for k in ('smoke', 'model_calls', 'docker',
                                           'historical_evidence_required')}, indent=2))
