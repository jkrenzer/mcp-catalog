from __future__ import annotations

import subprocess
from typing import Any, Callable

import typer
from ruamel.yaml.error import YAMLError

from ..logging_config import get_logger

logger = get_logger(__name__)


def action(function: Callable[[], Any]) -> Any:
    try:
        return function()
    except (OSError, ValueError, subprocess.SubprocessError, YAMLError) as error:
        logger.error('%s', error)
        raise typer.Exit(1) from error
