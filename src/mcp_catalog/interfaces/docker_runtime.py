from __future__ import annotations

import os
import shutil
import subprocess


def require_docker_engine() -> None:
    """Fail with setup guidance unless the Docker CLI can reach an engine."""
    if shutil.which('docker') is None:
        raise FileNotFoundError('Docker CLI was not found on PATH.')

    try:
        result = subprocess.run(
            ['docker', 'info'],
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
            env={
                key: value
                for key, value in os.environ.items()
                if not key.startswith('GIT_CONFIG_')
            },
        )
    except (OSError, subprocess.SubprocessError) as error:
        raise RuntimeError(
            'Docker CLI is installed, but a Docker engine is not responding. '
            'Start the Docker engine and make its socket or remote endpoint available '
            'to this container.'
        ) from error

    if result.returncode != 0:
        details = result.stderr.strip()
        message = (
            'Docker CLI is installed, but it cannot reach a working Docker engine. '
            'Start the Docker engine and make its socket or remote endpoint available '
            'to this container.'
        )
        if details:
            message = f'{message} Docker reported: {details}'
        raise RuntimeError(message)
