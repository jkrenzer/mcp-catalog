from __future__ import annotations

import os
from pathlib import Path
from string import Template
from typing import Mapping


def expand_environment(value: str, *, variables: Mapping[str, str] | None = None) -> str:
    """Expand shell-style environment variables, rejecting undefined names."""
    available = dict(os.environ)
    if variables is not None:
        available.update(variables)
    try:
        return Template(value).substitute(available)
    except KeyError as error:
        raise ValueError(f'Environment variable {error.args[0]!r} is not defined.') from error


def git_base_directory(start: str | Path) -> Path | None:
    """Return the nearest parent containing a .git entry, if one exists."""
    current = Path(start).resolve()
    if current.is_file():
        current = current.parent
    for candidate in (current, *current.parents):
        if (candidate / '.git').exists():
            return candidate
    return None
