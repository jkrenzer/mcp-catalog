from __future__ import annotations

import subprocess

import pytest

from mcp_catalog.interfaces import docker_runtime


def test_require_docker_engine_checks_cli_and_engine(monkeypatch):
    seen = {}
    monkeypatch.setattr(docker_runtime.shutil, 'which', lambda name: '/usr/bin/docker')
    monkeypatch.setenv('GIT_CONFIG_VALUE_0', 'AUTHORIZATION: basic sensitive')

    def run(command, **kwargs):
        seen['command'] = command
        seen['kwargs'] = kwargs
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(docker_runtime.subprocess, 'run', run)

    docker_runtime.require_docker_engine()

    assert seen['command'] == ['docker', 'info']
    assert seen['kwargs']['capture_output'] is True
    assert seen['kwargs']['timeout'] == 10
    assert 'GIT_CONFIG_VALUE_0' not in seen['kwargs']['env']


def test_require_docker_engine_reports_missing_cli(monkeypatch):
    monkeypatch.setattr(docker_runtime.shutil, 'which', lambda _: None)

    with pytest.raises(FileNotFoundError, match='Docker CLI was not found'):
        docker_runtime.require_docker_engine()


def test_require_docker_engine_reports_unreachable_engine(monkeypatch):
    monkeypatch.setattr(docker_runtime.shutil, 'which', lambda _: '/usr/bin/docker')
    monkeypatch.setattr(
        docker_runtime.subprocess,
        'run',
        lambda command, **kwargs: subprocess.CompletedProcess(
            command, 1, stderr='Cannot connect to the Docker daemon'
        ),
    )

    with pytest.raises(RuntimeError, match='cannot reach a working Docker engine') as error:
        docker_runtime.require_docker_engine()

    assert 'Cannot connect to the Docker daemon' in str(error.value)
