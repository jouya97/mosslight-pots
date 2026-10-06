"""The scaffold's root entrypoints work with the retained implementation package."""
import importlib
import json
from pathlib import Path
import subprocess
import sys

from bug_competition import IMPLEMENTATION_ROOT, REPOSITORY_ROOT
from bug_competition.task import PROMPT
from bug_competition.visibility.build import build_agent_tree


def test_root_prompt_and_declared_entrypoints_use_canonical_files(tmp_path):
    printed = subprocess.run([sys.executable, '-B', 'task.py', 'standard'],
                             cwd=REPOSITORY_ROOT, capture_output=True, text=True, check=True)
    assert printed.stdout == PROMPT + '\n'
    environment = json.loads((REPOSITORY_ROOT / 'env.json').read_text())
    for key, relative in [('task', 'task.py'), ('grader', 'grader/grader.py'),
                          ('environment_factory', 'bug_competition/environment.py')]:
        module_name, attribute = environment[key].split(':')
        module = importlib.import_module(module_name)
        assert Path(module.__file__).resolve() == REPOSITORY_ROOT / relative
        assert callable(getattr(module, attribute))
    staged = tmp_path / 'workspace'
    build_agent_tree(IMPLEMENTATION_ROOT / 'mosslight', staged)
    assert (staged / 'SUBMISSION.md').read_bytes() == (REPOSITORY_ROOT / 'agent_data/SUBMISSION.md').read_bytes()
    assert not (staged / 'grader').exists()
