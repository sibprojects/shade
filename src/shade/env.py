"""API keys from a local `.env` file (git-ignored).

Variables already set in the environment win over the file. Keys are only
put into the process environment, never written anywhere else.
"""

from __future__ import annotations

from pathlib import Path

from dotenv import load_dotenv

DEFAULT_ENV_PATH = Path(".env")


def load_env(path: Path = DEFAULT_ENV_PATH) -> bool:
    """Load `path` into os.environ without overriding; False if there is no file."""
    if not path.is_file():
        return False
    load_dotenv(path, override=False, encoding="utf-8")
    return True
