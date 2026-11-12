from __future__ import annotations

import json

from typer.testing import CliRunner

from mcp_catalog.branching import self_image_reference
from mcp_catalog.cli import app
from mcp_catalog.interfaces.self_images import build_self_image, self_image_plan
from mcp_catalog.io.yaml import dump_yaml_file

runner = CliRunner()


def test_self_image_references_use_the_self_namespace():
    assert (
        self_image_reference('cli', 'main', 'latest')
        == 'ghcr.io/jkrenzer/mcp-catalog/self/cli:latest'
    )
    assert (
        self_image_reference('mcp', 'main', 'build-abc')
        == 'ghcr.io/jkrenzer/mcp-catalog/self/mcp:build-abc'
    )
    branch_reference = self_image_reference('cli', 'feature/test', 'latest')
    assert branch_reference.startswith('ghcr.io/jkrenzer/mcp-catalog/self/feature-test-')
    assert branch_reference.endswith('/cli:latest')


def test_self_image_plan_is_deterministic_and_labelled():
    first = self_image_plan(
        branch='main', catalog_commit='deadbeef', repository='https://github.com/example/repo'
    )
    second = self_image_plan(
        branch='main', catalog_commit='deadbeef', repository='https://github.com/example/repo'
    )

    assert first == second
    assert [image['component'] for image in first['images']] == ['cli', 'mcp']
    cli = first['images'][0]
    assert cli['target'] == 'command'
    assert cli['tags'] == [
        'ghcr.io/jkrenzer/mcp-catalog/self/cli:build-deadbeef',
        'ghcr.io/jkrenzer/mcp-catalog/self/cli:latest',
    ]
    assert cli['labels']['org.opencontainers.image.source'] == 'https://github.com/example/repo'
    assert cli['labels']['org.opencontainers.image.revision'] == 'deadbeef'
    assert cli['labels']['org.opencontainers.image.title'] == 'mcp-catalog CLI'
    assert first['images'][1]['target'] == 'mcp'


def test_build_self_image_composes_buildx_command(tmp_path, monkeypatch):
    (tmp_path / 'Dockerfile').write_text('FROM scratch\n', encoding='utf-8')
    commands = []
    monkeypatch.setattr(
        'mcp_catalog.interfaces.self_images._run', lambda command: commands.append(command)
    )

    image = build_self_image(
        'mcp',
        context=tmp_path,
        branch='feature/test',
        catalog_commit='deadbeef',
        repository='https://github.com/example/repo',
        push=True,
        platform=['linux/amd64', 'linux/arm64'],
        cache_from='type=gha,scope=self-mcp',
    )

    command = commands[0]
    assert image.startswith('ghcr.io/jkrenzer/mcp-catalog/self/feature-test-')
    assert image.endswith('/mcp:build-deadbeef')
    assert command[:4] == ['docker', 'buildx', 'build', '--push']
    assert command[command.index('--platform') + 1] == 'linux/amd64,linux/arm64'
    assert command[command.index('--target') + 1] == 'mcp'
    tags = [command[index + 1] for index, item in enumerate(command) if item == '--tag']
    assert tags == [image, image.rsplit(':', 1)[0] + ':latest']
    assert command[command.index('--cache-from') + 1] == 'type=gha,scope=self-mcp'
    assert 'org.opencontainers.image.revision=deadbeef' in command
    assert command[-1] == str(tmp_path.resolve())


def test_build_self_image_rejects_unknown_component_and_missing_dockerfile(tmp_path):
    try:
        build_self_image('unknown', context=tmp_path, catalog_commit='deadbeef')
    except ValueError as error:
        assert 'Unknown tooling image' in str(error)
    else:
        raise AssertionError('Expected an unknown component to fail')
    try:
        build_self_image('cli', context=tmp_path, catalog_commit='deadbeef')
    except FileNotFoundError as error:
        assert 'Dockerfile' in str(error)
    else:
        raise AssertionError('Expected a missing Dockerfile to fail')


def test_self_plan_command_reads_catalog_repository(tmp_path):
    catalog_path = tmp_path / 'catalog.yaml'
    dump_yaml_file(
        catalog_path,
        {
            'schema_version': 1,
            'name': 'test-catalog',
            'title': 'Test Catalog',
            'description': 'Catalog used by CLI tests.',
            'repository': 'https://github.com/example/repo',
            'servers': [],
        },
    )

    result = runner.invoke(app, ['self', 'plan', str(catalog_path), '--catalog-commit', 'deadbeef'])

    assert result.exit_code == 0, result.output
    plan = json.loads(result.stdout)
    assert plan['images'][0]['image'] == 'ghcr.io/jkrenzer/mcp-catalog/self/cli:build-deadbeef'
    assert plan['images'][0]['labels']['org.opencontainers.image.source'] == (
        'https://github.com/example/repo'
    )
