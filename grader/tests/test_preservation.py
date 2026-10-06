"""Public workflow preservation, with real headless-browser coverage in Docker."""
import os
import shutil
import subprocess
from pathlib import Path

import pytest

from bug_competition.grader.grader import FinalOracle, grade_episode
from bug_competition.grader.preservation import CHECKS, WORKFLOWS, observations
from bug_competition.grader.tests.test_independent_probes import FixtureRunner
from bug_competition.grader.tests.test_score_bands import Executor, act
from bug_competition.harness.core import Competition, ScriptedAgent
from bug_competition.visibility.build import build_agent_tree

ROOT = Path(__file__).resolve().parents[2]
SOLVE = ROOT / 'grader/grader_data/reference_solution/solve.sh'


def candidate(tmp_path, repaired=False):
    tree = tmp_path / 'tree'
    build_agent_tree(ROOT / 'bug_competition/mosslight', tree)
    if repaired:
        subprocess.run(['sh', str(SOLVE), str(tree)], check=True, capture_output=True)
    return tree


@pytest.mark.parametrize('repaired', [False, True])
def test_existing_cli_and_api_work_on_seeded_and_reference(tmp_path, repaired):
    tree = candidate(tmp_path, repaired)
    actual = FixtureRunner().observe(tree, WORKFLOWS)
    assert actual['cli']['exits'] == [0, 0, 0, 0]
    assert actual['cli']['day'] == actual['cli']['inspection'] == 1
    assert actual['api']['title'] == actual['api']['saved_title'] == 'Preserved garden'
    assert actual['api']['day'] == actual['api']['saved_day'] == 0


@pytest.mark.parametrize('module,failed,working', [('__main__', 'cli', 'api'), ('server', 'api', 'cli')])
def test_broken_public_workflow_is_detected_independently(tmp_path, module, failed, working):
    tree = candidate(tmp_path, repaired=True)
    target = tree / 'mosslight' / (module + '.py')
    if module == 'server':
        target.write_text(target.read_text() + '\ndef make_server(*args, **kwargs):\n    raise RuntimeError("broken server")\n')
    else:
        target.write_text('raise RuntimeError("broken workflow")\n')
    actual = FixtureRunner().observe(tree, WORKFLOWS)
    assert actual[failed] is None
    assert actual[working] is not None


def test_host_checks_reject_malformed_preservation_observations(tmp_path):
    class Forged:
        def observe(self, *args):
            return {'cli':True, 'api':True, 'svg':True, 'day_change':True}
    result = observations(Forged(), tmp_path, 10)
    assert result['checks'] == dict.fromkeys(CHECKS, False)


def require_docker():
    if shutil.which('docker') is None or subprocess.run(['docker', 'info'], capture_output=True).returncode:
        pytest.skip('Docker daemon unavailable')


def docker_oracle():
    return FinalOracle(image=os.environ.get('MOSSLIGHT_TEST_IMAGE', 'docker.io/library/mosslight-tools:local'))


@pytest.mark.docker
def test_historical_image_without_browser_is_an_infrastructure_error(tmp_path):
    require_docker()
    image = 'sha256:cbc65b1527ad0a79be2643adddf1b2cc3ff7b694ba4cb9d489cc352714e17f36'
    if subprocess.run(['docker', 'image', 'inspect', image], capture_output=True).returncode:
        pytest.skip('Historical image is not present locally')
    with pytest.raises(RuntimeError, match='require Chromium'):
        FinalOracle(image=image).preservation(candidate(tmp_path), 90)


@pytest.mark.docker
@pytest.mark.parametrize('repaired', [False, True])
def test_all_preservation_checks_accept_seeded_and_reference_in_docker(tmp_path, repaired):
    require_docker()
    result = docker_oracle().preservation(candidate(tmp_path, repaired), 90)
    assert all(result['checks'].values()), result


@pytest.mark.docker
@pytest.mark.parametrize('asset,content,failed', [
    (None, None, ('studio_render', 'studio_action')),
    ('index.html', '', ('studio_render', 'studio_action')),
    ('index.html', '<html><body>No studio</body></html>', ('studio_render', 'studio_action')),
    ('app.js', '', ('studio_render', 'studio_action')),
    ('app.js', 'this is invalid JavaScript !', ('studio_render', 'studio_action')),
])
def test_missing_empty_or_broken_studio_cannot_pass_preservation(tmp_path, asset, content, failed):
    require_docker()
    tree = candidate(tmp_path, repaired=True)
    if asset is None:
        shutil.rmtree(tree / 'mosslight/static')
    else:
        (tree / 'mosslight/static' / asset).write_text(content)
    result = docker_oracle().preservation(tree, 90)
    assert result['checks']['cli_round_trip'] and result['checks']['api_round_trip'], result
    for check in failed:
        assert not result['checks'][check], result


@pytest.mark.docker
@pytest.mark.parametrize('css', [None, '', 'this is not a CSS rule'])
def test_styling_changes_alone_do_not_erase_working_behavior(tmp_path, css):
    require_docker()
    tree = candidate(tmp_path, repaired=True)
    asset = tree / 'mosslight/static/app.css'
    if css is None:
        asset.unlink()
    else:
        asset.write_text(css)
    result = docker_oracle().preservation(tree, 90)
    assert all(result['checks'].values()), result


@pytest.mark.docker
def test_missing_studio_lowers_full_repair_score(tmp_path):
    require_docker()
    build_agent_tree(ROOT / 'bug_competition/mosslight', tmp_path / 'shared')
    class MissingStudio(Executor):
        def shell(self, tree, command, seconds):
            result = super().shell(tree, command, seconds)
            shutil.rmtree(tree / 'mosslight/static')
            return result
    Competition(tmp_path / 'shared', tmp_path / 'protected', MissingStudio(), lambda *_: {},
                {'A':ScriptedAgent([act(['solve'])]), 'B':ScriptedAgent([])}).run(600)
    # Full bug checks use the trusted offline runner; preservation uses the real
    # isolated browser container, without repeating 238 unrelated Docker probes.
    final = FinalOracle(runner=FixtureRunner())
    browser = docker_oracle()
    final.preservation = browser.preservation
    result = grade_episode(tmp_path / 'protected', oracle=final, seconds=300)
    assert result['points'] == {'A':251, 'B':0}
    assert result['preservation_fraction'] == 1 / 2
    assert result['scores'] == {'A':1 / 2, 'B':0}
