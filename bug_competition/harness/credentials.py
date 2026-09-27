"""Load an allowlisted subset of dotenv data without executing shell syntax."""
import os
from pathlib import Path
import shlex

ALLOWED_KEYS = frozenset({"ANTHROPIC_API_KEY", "OPENAI_API_KEY", "BRAVE_SEARCH_API_KEY"})

def load_host_credentials(path: Path) -> None:
    """Existing environment wins. Missing files are allowed; callers validate keys.

    Accept KEY=value, optional export, single/double quotes and inline comments.
    Variable interpolation, command substitution and multiline values are not
    evaluated. Never return, print, or include credential values in exceptions.
    """
    if not path.is_file():
        return
    try:
        lines = path.read_text(encoding="utf8").splitlines()
    except (OSError, UnicodeError):
        raise ValueError("Unable to read the host credential file") from None
    for line in lines:
        line = line.strip()
        if line.startswith("export "):
            line = line[7:].lstrip()
        key, separator, value = line.partition("=")
        key = key.strip()
        if not separator or key not in ALLOWED_KEYS or key in os.environ:
            continue
        try:
            words = shlex.split(value, comments=True, posix=True)
        except ValueError:
            raise ValueError(f"Invalid dotenv quoting for {key}") from None
        if len(words) > 1:
            raise ValueError(f"Dotenv value for {key} must be quoted if it contains spaces")
        if words:
            os.environ[key] = words[0]
