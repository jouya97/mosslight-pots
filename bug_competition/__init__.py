"""Mosslight implementation helpers and compatibility for its public module paths.

The scaffold's task, grader and adapters live at the repository root. Keeping
them on this package's search path preserves existing ``bug_competition.*``
entrypoints without duplicating those files or changing archived evidence paths.
"""
from pathlib import Path

IMPLEMENTATION_ROOT = Path(__file__).resolve().parent
REPOSITORY_ROOT = IMPLEMENTATION_ROOT.parent
__path__.append(str(REPOSITORY_ROOT))
