"""Real Docker protocol smoke; a skip does not satisfy the rollout preflight."""
import shutil
import subprocess
import os

import pytest

from bug_competition.host_only.tools.smoke_sp_replication import smoke


@pytest.mark.docker
def test_two_agents_five_actions_without_historical_artifacts(tmp_path):
    if shutil.which('docker') is None:
        pytest.skip('Docker is not installed; rollout preflight remains incomplete')
    try:
        info = subprocess.run(['docker', 'info'], capture_output=True, timeout=10)
    except subprocess.TimeoutExpired:
        pytest.fail('Docker daemon did not respond')
    if info.returncode:
        pytest.skip('Docker daemon unavailable; rollout preflight remains incomplete')
    # A missing docker.io/library/mosslight-tools:local image fails explicitly in DockerShell.
    report = smoke(tmp_path / 'smoke', image=os.environ.get('MOSSLIGHT_TEST_IMAGE', 'docker.io/library/mosslight-tools:local'))
    assert report['smoke'] == 'ok'
    assert report['historical_evidence_required'] is False
    assert report['model_calls'] == 0
