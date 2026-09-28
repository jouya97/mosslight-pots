"""Compatibility entrypoint for fresh OpenRouter launches; shared logic in fresh_rollout."""
import sys
from pathlib import Path

if __name__ == '__main__':
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
    from bug_competition.host_only.tools.fresh_rollout import main
    raise SystemExit(main(default_provider='openrouter'))
else:
    from bug_competition.host_only.tools import fresh_rollout
    sys.modules[__name__] = fresh_rollout
