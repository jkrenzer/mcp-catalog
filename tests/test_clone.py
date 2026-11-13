from __future__ import annotations

import subprocess

import pytest
from typer.testing import CliRunner

import mcp_catalog.cli.clone as clone
from mcp_catalog.cli import app

runner = CliRunner()


def test_clone_parses_pip_style_ref_and_subdirectory():
    clone_url, ref, subdirectory = clone._parse_repository_url(
        'git+https://github.com/example/project.git@release/v1'
        '#egg=project&subdirectory=packages/server'
    )

    assert clone_url == 'https://github.com/example/project.git'
    assert ref == 'release/v1'
    assert subdirectory == 'packages/server'


def test_clone_parses_ssh_ref():
    clone_url, ref, subdirectory = clone._parse_repository_url(
        'git+ssh://git@github.com/example/project.git@0123456789abcdef'
    )

    assert clone_url == 'ssh://git@github.com/example/project.git'
    assert ref == '0123456789abcdef'
    assert subdirectory is None


def test_clone_accepts_plain_https_url(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(clone.shutil, 'which', lambda _: '/usr/bin/git')
    commands: list[list[str]] = []

    def fake_run(arguments: list[str]) -> subprocess.CompletedProcess[str]:
        commands.append(arguments)
        (tmp_path / 'project').mkdir()
        return subprocess.CompletedProcess(arguments, 0, 'Cloning into project...\n', '')

    monkeypatch.setattr(clone, '_run_git', fake_run)
    result = runner.invoke(app, ['clone', 'https://github.com/example/project.git'])

    assert result.exit_code == 0, result.output
    assert commands == [['/usr/bin/git', 'clone', 'https://github.com/example/project.git']]
    assert 'Cloned repository into project' in result.output


def test_clone_forwards_git_options_and_reports_subdirectory(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(clone.shutil, 'which', lambda _: '/usr/bin/git')
    commands: list[list[str]] = []

    def fake_run(arguments: list[str]) -> subprocess.CompletedProcess[str]:
        commands.append(arguments)
        if arguments[1] == 'clone':
            (tmp_path / 'project/packages/server').mkdir(parents=True)
            return subprocess.CompletedProcess(
                arguments, 0, 'Cloning into project...\n', 'Receiving objects: done\n'
            )
        return subprocess.CompletedProcess(arguments, 0, '', '')

    monkeypatch.setattr(clone, '_run_git', fake_run)
    result = runner.invoke(
        app,
        [
            'clone',
            'git+https://github.com/example/project.git@v1#subdirectory=packages/server',
            '--',
            '--depth',
            '1',
        ],
    )

    assert result.exit_code == 0, result.output
    assert commands[0] == [
        '/usr/bin/git',
        'clone',
        '--depth',
        '1',
        'https://github.com/example/project.git',
    ]
    assert commands[1] == [
        '/usr/bin/git',
        '-C',
        'project',
        'checkout',
        'v1',
    ]
    assert 'Cloning into project...' in result.output
    assert 'packages/server' in result.output


def test_clone_reports_missing_git(monkeypatch):
    monkeypatch.setattr(clone.shutil, 'which', lambda _: None)

    result = runner.invoke(app, ['clone', 'https://github.com/example/project.git'])

    assert result.exit_code == 1
    assert 'Git is required' in result.output


def test_clone_reports_git_failure(monkeypatch):
    monkeypatch.setattr(clone.shutil, 'which', lambda _: '/usr/bin/git')
    monkeypatch.setattr(
        clone,
        '_run_git',
        lambda arguments: subprocess.CompletedProcess(arguments, 128, '', 'repository not found\n'),
    )

    result = runner.invoke(app, ['clone', 'https://github.com/example/project.git'])

    assert result.exit_code == 128
    assert 'repository not found' in result.output
    assert 'git clone failed' in result.output


@pytest.mark.skipif(clone.shutil.which('git') is None, reason='Git is not installed')
def test_clone_checks_out_selected_branch_and_reports_project_subdirectory(tmp_path, monkeypatch):
    source = tmp_path / 'remote-repo'
    source.mkdir()
    monkeypatch.setenv('GIT_AUTHOR_NAME', 'Test')
    monkeypatch.setenv('GIT_AUTHOR_EMAIL', 'test@example.com')
    monkeypatch.setenv('GIT_COMMITTER_NAME', 'Test')
    monkeypatch.setenv('GIT_COMMITTER_EMAIL', 'test@example.com')

    def run_git(*arguments: str) -> None:
        subprocess.run(['git', *arguments], cwd=source, check=True, capture_output=True)

    run_git('init', '-b', 'main')
    project = source / 'packages/server'
    project.mkdir(parents=True)
    (project / 'README.md').write_text('main\n', encoding='utf-8')
    run_git('add', '.')
    run_git('commit', '-m', 'Initial commit')
    run_git('switch', '-c', 'feature')
    (project / 'README.md').write_text('feature\n', encoding='utf-8')
    run_git('commit', '-am', 'Feature commit')
    working_directory = tmp_path / 'working'
    working_directory.mkdir()
    monkeypatch.chdir(working_directory)

    result = runner.invoke(
        app,
        ['clone', f'git+{source.as_uri()}@feature#subdirectory=packages/server'],
    )

    assert result.exit_code == 0, result.output
    assert 'Repository subdirectory: remote-repo/packages/server' in result.output
    assert (
        subprocess.run(
            ['git', '-C', 'remote-repo', 'branch', '--show-current'],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        == 'feature'
    )
    assert (working_directory / 'remote-repo/packages/server/README.md').read_text(
        encoding='utf-8'
    ) == 'feature\n'
