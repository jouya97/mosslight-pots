"""Real Docker protocol smoke; a skip does not satisfy the rollout preflight."""
import shutil
import subprocess

import pytest

from bug_competition.host_only.tools.smoke_sp_replication import smoke


@pytest.mark.docker
def test_two_agents_five_actions_match_super_positive_protocol(tmp_path):
    if shutil.which('docker') is None:
        pytest.skip('Docker is not installed; rollout preflight remains incomplete')
    try:
        info = subprocess.run(['docker', 'info'], capture_output=True, timeout=10)
    except subprocess.TimeoutExpired:
        pytest.fail('Docker daemon did not respond')
    if info.returncode:
        pytest.skip('Docker daemon unavailable; rollout preflight remains incomplete')
    # A missing mosslight-tools:local image fails explicitly in DockerShell.
    assert smoke(tmp_path / 'smoke')['smoke'] == 'ok'
