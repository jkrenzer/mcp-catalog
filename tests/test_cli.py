from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

import mcp_catalog.cli as cli
from mcp_catalog import get_logger
from mcp_catalog.cli import app, main
from mcp_catalog.interfaces.builds import _run, build_image_for_server
from mcp_catalog.interfaces.docker_catalog import (
    CATALOG_ARTIFACT_TYPE,
    catalog_annotations,
    docker_catalog_artifact,
    publish_catalog,
    publish_catalog_from_manifest,
    verify_catalog_artifact,
)
from mcp_catalog.interfaces.docker_entry import image_labels, image_metadata
from mcp_catalog.io.yaml import dump_yaml_file
from mcp_catalog.models import BuildServer, GitSourceModel
from mcp_catalog.workflows import (
    build_plan,
    build_server_image,
    docker_catalog,
    load_catalog,
    schema_drift,
    write_schemas,
)

runner = CliRunner()


def _build_server(name: str, *, enabled: bool = True) -> dict[str, object]:
    return {
        'schema_version': 1,
        'schema_kind': 'https://mcp-catalog.schema.krenzer.space/server.schema.json',
        'name': name,
        'kind': 'build',
        'title': name.title(),
        'description': f'{name} server',
        'enabled': enabled,
        'source': {
            'repository': 'https://github.com/example/server.git',
            'revision': '0123456789abcdef0123456789abcdef01234567',
            'context': '.',
            'dockerfile': 'Dockerfile',
        },
        'build': {
            'platforms': ['linux/amd64'],
            'args': {'ZED': 'last', 'ALPHA': 'first'},
        },
    }


def _write_catalog(path, servers: list[dict[str, object]], **fields: object) -> None:
    dump_yaml_file(
        path,
        {
            'schema_version': 1,
            'schema_kind': 'https://mcp-catalog.schema.krenzer.space/catalog.schema.json',
            'name': 'test-catalog',
            'title': 'Test Catalog',
            'description': 'Catalog used by CLI tests.',
            **fields,
            'servers': servers,
        },
    )


def _described_server(name: str) -> dict[str, object]:
    return {
        **_build_server(name),
        'icon': 'https://example.com/icon.png',
        'readme': 'https://example.com/docs',
        'date_added': '2026-01-15T12:30:00+02:00',
        'metadata': {'category': 'devops', 'tags': ['demo'], 'license': 'MIT', 'owner': 'me'},
        'runtime': {
            'command': ['--transport=stdio'],
            'volumes': [f'{{{{{name}.data_dir}}}}:/data'],
            'user': '1000:1000',
            'long_lived': True,
            'disable_network': True,
            'allow_hosts': ['api.example.com:443'],
            'extra_hosts': ['host.docker.internal:host-gateway'],
            'env': [{'name': 'DEMO_REGION', 'value': f'{{{{{name}.region}}}}'}],
        },
        'secrets': [
            {
                'name': f'{name}.api_key',
                'env': 'DEMO_API_KEY',
                'example': '<token>',
                'description': 'API key',
                'required': True,
            }
        ],
        'config': [
            {
                'description': 'Demo settings',
                'properties': {
                    'data_dir': {'type': 'string'},
                    'region': {'type': 'string', 'default': 'eu'},
                },
                'required': ['data_dir'],
                'any_of': [{'required': ['region']}],
            }
        ],
        'tools': [
            {
                'name': 'search',
                'description': 'Search things.',
                'arguments': [{'name': 'query', 'desc': 'Terms', 'optional': True}],
                'annotations': {'read_only_hint': True},
            }
        ],
        'prefix': 'demo_',
    }


def test_validate_accepts_catalog_with_embedded_servers(tmp_path):
    catalog = tmp_path / 'catalog.yaml'
    _write_catalog(catalog, [_build_server('example')])

    result = runner.invoke(app, ['validate', str(catalog)])

    assert result.exit_code == 0
    assert result.stdout == ''
    assert 'Validated' in result.stderr


def test_schema_generate_and_check(tmp_path):
    result = runner.invoke(app, ['schema', 'generate', str(tmp_path)])

    assert result.exit_code == 0
    assert schema_drift(tmp_path) == []
    assert (tmp_path / 'server.schema.json').is_file()


def test_committed_schemas_are_current():
    schema_dir = Path(__file__).parents[1] / 'schemas'

    assert schema_drift(schema_dir) == []


def test_schema_check_reports_drift(tmp_path):
    write_schemas(tmp_path)
    (tmp_path / 'server.schema.json').write_text('{}\n', encoding='utf-8')

    result = runner.invoke(app, ['schema', 'check', str(tmp_path)])

    assert result.exit_code == 1
    assert 'out of date' in result.output


def test_server_crud_updates_embedded_catalog(tmp_path):
    catalog = tmp_path / 'catalog.yaml'
    source = tmp_path / 'new-server.yaml'
    _write_catalog(catalog, [_build_server('original')])
    dump_yaml_file(source, _build_server('added'))

    add_result = runner.invoke(app, ['server', 'add', str(catalog), '--manifest', str(source)])
    list_result = runner.invoke(app, ['server', 'list', str(catalog)])
    show_result = runner.invoke(app, ['server', 'show', 'added', str(catalog)])
    remove_result = runner.invoke(app, ['server', 'remove', 'added', str(catalog)])

    assert add_result.exit_code == 0, add_result.output
    assert list_result.exit_code == 0
    assert 'added\tbuild\tenabled' in list_result.stdout
    assert show_result.exit_code == 0
    assert 'name: added' in show_result.stdout
    assert remove_result.exit_code == 0
    assert [server.name for server in load_catalog(catalog).servers] == ['original']


def test_server_crud_updates_catalog_server_files(tmp_path):
    catalog = tmp_path / 'catalog.yaml'
    servers_dir = tmp_path / 'servers'
    servers_dir.mkdir()
    dump_yaml_file(
        catalog,
        {
            'schema_version': 1,
            'schema_kind': 'https://mcp-catalog.schema.krenzer.space/catalog.schema.json',
            'name': 'test-catalog',
            'title': 'Test Catalog',
            'description': 'Catalog used by CLI tests.',
            'servers_dir': 'servers',
        },
    )
    dump_yaml_file(servers_dir / 'original.yaml', _build_server('original'))
    source = tmp_path / 'new-server.yaml'
    dump_yaml_file(source, _build_server('added'))

    add_result = runner.invoke(app, ['server', 'add', str(catalog), '--manifest', str(source)])
    assert add_result.exit_code == 0, add_result.output
    assert (servers_dir / 'added.yaml').is_file()

    remove_result = runner.invoke(app, ['server', 'remove', 'added', str(catalog)])

    assert remove_result.exit_code == 0, remove_result.output
    assert not (servers_dir / 'added.yaml').exists()
    assert [server.name for server in load_catalog(catalog).servers] == ['original']


def test_upstream_resolve_is_read_only_and_update_is_explicit(tmp_path, monkeypatch):
    catalog = tmp_path / 'catalog.yaml'
    servers_dir = tmp_path / 'servers'
    servers_dir.mkdir()
    dump_yaml_file(
        catalog,
        {
            'schema_version': 1,
            'schema_kind': 'https://mcp-catalog.schema.krenzer.space/catalog.schema.json',
            'name': 'test-catalog',
            'title': 'Test Catalog',
            'description': 'Catalog used by CLI tests.',
            'servers_dir': 'servers',
        },
    )
    server_path = servers_dir / 'example.yaml'
    dump_yaml_file(server_path, _build_server('example'))
    updated_revision = 'abcdef0123456789abcdef0123456789abcdef01'
    monkeypatch.setattr(
        'mcp_catalog.interfaces.upstream.resolve_upstream_revision',
        lambda repository, ref: updated_revision,
    )

    resolved = runner.invoke(app, ['upstream', 'resolve', 'example', str(catalog), '--ref', 'main'])

    assert resolved.exit_code == 0
    assert resolved.stdout.strip() == updated_revision
    resolved_server = load_catalog(catalog).servers[0]
    assert isinstance(resolved_server, BuildServer)
    assert isinstance(resolved_server.source, GitSourceModel)
    assert resolved_server.source.revision == '0123456789abcdef0123456789abcdef01234567'

    updated = runner.invoke(app, ['upstream', 'update', 'example', str(catalog), '--ref', 'main'])

    assert updated.exit_code == 0, updated.output
    updated_server = load_catalog(catalog).servers[0]
    assert isinstance(updated_server, BuildServer)
    assert isinstance(updated_server.source, GitSourceModel)
    assert updated_server.source.revision == updated_revision


def test_build_plan_is_name_and_argument_sorted(tmp_path):
    catalog_path = tmp_path / 'catalog.yaml'
    _write_catalog(catalog_path, [_build_server('zulu'), _build_server('alpha')])
    catalog = load_catalog(catalog_path)

    first = build_plan(catalog, catalog_commit='deadbeef', branch='main')
    second = build_plan(catalog, catalog_commit='deadbeef', branch='main')

    assert first == second
    assert [build['name'] for build in first['builds']] == ['alpha', 'zulu']
    assert first['builds'][0]['args'] == {'ALPHA': 'first', 'ZED': 'last'}


def test_local_build_plan_and_image_build_use_local_context(tmp_path, monkeypatch):
    context = tmp_path / 'local-context'
    context.mkdir()
    dockerfile = context / 'Dockerfile'
    dockerfile.write_text('FROM scratch\n', encoding='utf-8')
    catalog_path = tmp_path / 'catalog.yaml'
    server = _build_server('example')
    server['source'] = {'context': 'local-context', 'dockerfile': 'Dockerfile'}
    _write_catalog(catalog_path, [server])
    catalog = load_catalog(catalog_path)
    server_model = catalog.servers[0]
    assert isinstance(server_model, BuildServer)
    commands = []
    monkeypatch.setattr(
        'mcp_catalog.interfaces.builds._run',
        lambda command, **kwargs: commands.append(command),
    )

    plan = build_plan(catalog, catalog_commit='deadbeef', branch='main')
    build_server_image(server_model, image='example/local:latest', platform='linux/amd64')

    source = plan['builds'][0]['source']
    assert source == {
        'type': 'local',
        'context': str(context),
        'dockerfile': str(dockerfile),
    }
    assert len(commands) == 1
    assert commands[0][0:3] == ['docker', 'buildx', 'build']
    assert commands[0][-1] == str(context)
    assert commands[0][commands[0].index('--file') + 1] == str(dockerfile)


def test_image_build_push_uses_all_platforms_and_build_cache(tmp_path, monkeypatch):
    context = tmp_path / 'local-context'
    context.mkdir()
    (context / 'Dockerfile').write_text('FROM scratch\n', encoding='utf-8')
    catalog_path = tmp_path / 'catalog.yaml'
    server = _build_server('example')
    server['source'] = {'context': 'local-context', 'dockerfile': 'Dockerfile'}
    server['build'] = {'platforms': ['linux/amd64', 'linux/arm64'], 'args': {}}
    _write_catalog(catalog_path, [server])
    catalog = load_catalog(catalog_path)
    model = catalog.servers[0]
    assert isinstance(model, BuildServer)
    commands = []
    monkeypatch.setattr(
        'mcp_catalog.interfaces.builds._run',
        lambda command, **kwargs: commands.append(command),
    )

    build_server_image(
        model,
        image='example/local:latest',
        push=True,
        cache_from=['type=gha,scope=example', 'type=registry,ref=example/local:latest'],
        cache_to='type=gha,scope=example,mode=max',
    )

    command = commands[0]
    assert '--push' in command
    assert '--load' not in command
    assert command[command.index('--platform') + 1] == 'linux/amd64,linux/arm64'
    cache_sources = [
        command[index + 1] for index, option in enumerate(command) if option == '--cache-from'
    ]
    assert cache_sources == [
        'type=gha,scope=example',
        'type=registry,ref=example/local:latest',
    ]
    assert command[command.index('--cache-to') + 1] == 'type=gha,scope=example,mode=max'
    assert 'BUILDKIT_INLINE_CACHE=1' in command


def test_docker_build_does_not_inherit_git_credentials(monkeypatch):
    observed = {}

    def run(command, **kwargs):
        observed.update(kwargs)

    monkeypatch.setenv('GIT_CONFIG_VALUE_0', 'AUTHORIZATION: basic sensitive')
    monkeypatch.setattr('mcp_catalog.interfaces.builds.subprocess.run', run)

    _run(['docker', 'buildx', 'build'])

    assert 'GIT_CONFIG_VALUE_0' not in observed['env']


def test_catalog_publish_pushes_oras_artifact(monkeypatch):
    commands = []
    verified = []
    monkeypatch.setattr(
        'mcp_catalog.interfaces.docker_catalog._run',
        lambda command, cwd=None: commands.append((command, cwd)),
    )
    monkeypatch.setattr(
        'mcp_catalog.interfaces.docker_catalog.verify_catalog_artifact', verified.append
    )

    publish_catalog(
        {'title': 'Example', 'servers': []},
        'ghcr.io/example/catalog:latest',
        annotations={'org.opencontainers.image.title': 'Example'},
    )

    command, cwd = commands[0]
    assert command == [
        'oras',
        'push',
        '--artifact-type',
        CATALOG_ARTIFACT_TYPE,
        '--annotation',
        'org.opencontainers.image.title=Example',
        'ghcr.io/example/catalog:latest',
        'catalog.json:application/json',
    ]
    assert cwd is not None
    assert verified == ['ghcr.io/example/catalog:latest']


def test_verify_catalog_artifact_checks_artifact_type(monkeypatch):
    monkeypatch.setattr('mcp_catalog.interfaces.docker_catalog.require_executable', lambda _: None)

    def fetch(artifact_type):
        class Result:
            stdout = json.dumps({'artifactType': artifact_type})

        return lambda *args, **kwargs: Result()

    monkeypatch.setattr(
        'mcp_catalog.interfaces.docker_catalog.subprocess.run', fetch(CATALOG_ARTIFACT_TYPE)
    )
    verify_catalog_artifact('ghcr.io/example/catalog:latest')

    monkeypatch.setattr('mcp_catalog.interfaces.docker_catalog.subprocess.run', fetch(None))
    with pytest.raises(ValueError, match='artifact type'):
        verify_catalog_artifact('ghcr.io/example/catalog:latest')


def test_docker_catalog_artifact_wraps_entries_in_snapshots(tmp_path):
    catalog_path = tmp_path / 'catalog.yaml'
    remote = {
        'schema_version': 1,
        'schema_kind': 'https://mcp-catalog.schema.krenzer.space/server.schema.json',
        'name': 'remote-example',
        'kind': 'remote',
        'title': 'Remote example',
        'description': 'Remote server',
        'remote': {'url': 'https://example.com/mcp'},
    }
    _write_catalog(
        catalog_path, [_build_server('enabled'), _build_server('disabled', enabled=False), remote]
    )

    document = docker_catalog_artifact(
        load_catalog(catalog_path), images={'enabled': 'example/enabled:latest'}
    )

    assert set(document) == {'title', 'servers'}
    image_server, remote_server = document['servers']
    assert image_server['type'] == 'image'
    assert image_server['image'] == 'example/enabled:latest'
    assert image_server['snapshot']['server']['name'] == 'enabled'
    assert remote_server['type'] == 'remote'
    assert remote_server['endpoint'] == 'https://example.com/mcp'
    assert remote_server['snapshot']['server']['type'] == 'remote'


def test_docker_catalog_excludes_disabled_servers(tmp_path):
    catalog_path = tmp_path / 'catalog.yaml'
    _write_catalog(
        catalog_path, [_build_server('enabled'), _build_server('disabled', enabled=False)]
    )

    document = docker_catalog(
        load_catalog(catalog_path), images={'enabled': 'example/enabled:latest'}
    )

    assert list(document['registry']) == ['enabled']
    assert document['registry']['enabled']['image'] == 'example/enabled:latest'
    assert document['registry']['enabled']['type'] == 'server'
    assert document['registry']['enabled']['ref'] == '0123456789abcdef0123456789abcdef01234567'


def test_docker_catalog_entry_includes_docker_spec_fields(tmp_path):
    catalog_path = tmp_path / 'catalog.yaml'
    _write_catalog(catalog_path, [_described_server('demo')])

    entry = docker_catalog(load_catalog(catalog_path), images={'demo': 'example/demo:latest'})[
        'registry'
    ]['demo']

    assert entry['icon'] == 'https://example.com/icon.png'
    assert entry['readme'] == 'https://example.com/docs'
    assert entry['dateAdded'] == '2026-01-15T10:30:00Z'
    assert entry['upstream'] == 'https://github.com/example/server.git'
    assert entry['source'] == 'https://github.com/example/server.git'
    assert entry['metadata'] == {
        'category': 'devops',
        'tags': ['demo'],
        'license': 'MIT',
        'owner': 'me',
    }
    assert entry['command'] == ['--transport=stdio']
    assert entry['volumes'] == ['{{demo.data_dir}}:/data']
    assert entry['user'] == '1000:1000'
    assert entry['longLived'] is True
    assert entry['disableNetwork'] is True
    assert entry['allowHosts'] == ['api.example.com:443']
    assert entry['extraHosts'] == ['host.docker.internal:host-gateway']
    assert entry['env'] == [{'name': 'DEMO_REGION', 'value': '{{demo.region}}'}]
    assert entry['secrets'] == [
        {
            'name': 'demo.api_key',
            'env': 'DEMO_API_KEY',
            'example': '<token>',
            'description': 'API key',
            'required': True,
        }
    ]
    assert entry['config'] == [
        {
            'name': 'demo',
            'description': 'Demo settings',
            'type': 'object',
            'properties': {
                'data_dir': {'type': 'string'},
                'region': {'type': 'string', 'default': 'eu'},
            },
            'required': ['data_dir'],
            'anyOf': [{'required': ['region']}],
        }
    ]
    assert entry['tools'] == [
        {
            'name': 'search',
            'description': 'Search things.',
            'arguments': [{'name': 'query', 'type': 'string', 'desc': 'Terms', 'optional': True}],
            'annotations': {'readOnlyHint': True},
        }
    ]
    assert entry['prefix'] == 'demo_'
    assert entry['prompts'] == 0
    assert entry['resources'] == {}


def test_docker_catalog_omits_unset_optional_fields_and_normalizes_description(tmp_path):
    catalog_path = tmp_path / 'catalog.yaml'
    server = _build_server('plain')
    server['description'] = 'Folded\n  description text\n'
    _write_catalog(catalog_path, [server])

    entry = docker_catalog(load_catalog(catalog_path), images={'plain': 'example/plain:1'})[
        'registry'
    ]['plain']

    assert entry['description'] == 'Folded description text'
    assert set(entry) == {
        'name',
        'title',
        'description',
        'type',
        'icon',
        'tools',
        'prompts',
        'resources',
        'ref',
        'source',
        'image',
        'upstream',
    }


def test_local_build_entry_links_to_catalog_repository(tmp_path):
    context = tmp_path / 'local-context'
    context.mkdir()
    (context / 'Dockerfile').write_text('FROM scratch\n', encoding='utf-8')
    catalog_path = tmp_path / 'catalog.yaml'
    server = _build_server('local')
    server['source'] = {'context': 'local-context', 'dockerfile': 'Dockerfile'}
    _write_catalog(catalog_path, [server], repository='https://github.com/example/catalog')
    catalog = load_catalog(catalog_path)

    entry = docker_catalog(catalog, images={'local': 'example/local:1'})['registry']['local']
    labels = image_labels(
        catalog.servers[0],
        repository='https://github.com/example/catalog',
        catalog_commit='deadbeef',
    )

    assert entry['source'] == 'https://github.com/example/catalog'
    assert entry['ref'] == ''
    assert 'upstream' not in entry
    assert labels['org.opencontainers.image.source'] == 'https://github.com/example/catalog'
    assert labels['org.opencontainers.image.revision'] == 'deadbeef'


def test_image_labels_and_self_describing_metadata(tmp_path):
    catalog_path = tmp_path / 'catalog.yaml'
    _write_catalog(catalog_path, [_described_server('demo')])
    server = load_catalog(catalog_path).servers[0]
    assert isinstance(server, BuildServer)

    labels = image_labels(server, catalog_commit='deadbeef')
    metadata = json.loads(labels['io.docker.server.metadata'])

    assert list(labels) == sorted(labels)
    assert labels['org.opencontainers.image.title'] == 'Demo'
    assert labels['org.opencontainers.image.description'] == 'demo server'
    assert labels['org.opencontainers.image.source'] == 'https://github.com/example/server.git'
    assert labels['org.opencontainers.image.revision'] == '0123456789abcdef0123456789abcdef01234567'
    assert labels['org.opencontainers.image.url'] == 'https://github.com/example/server.git'
    assert labels['org.opencontainers.image.documentation'] == 'https://example.com/docs'
    assert labels['org.opencontainers.image.licenses'] == 'MIT'
    assert labels['org.opencontainers.image.vendor'] == 'me'
    assert metadata == image_metadata(server)
    assert metadata['type'] == 'server'
    assert metadata['env'] == [{'name': 'DEMO_REGION'}]
    assert metadata['tools'][0]['name'] == 'search'
    assert metadata['config'][0]['name'] == 'demo'
    assert metadata['metadata']['category'] == 'devops'
    assert not {'image', 'secrets', 'volumes', 'command', 'allowHosts'} & set(metadata)


def test_image_build_applies_generated_labels(tmp_path, monkeypatch):
    context = tmp_path / 'local-context'
    context.mkdir()
    (context / 'Dockerfile').write_text('FROM scratch\n', encoding='utf-8')
    catalog_path = tmp_path / 'catalog.yaml'
    server = _described_server('demo')
    server['source'] = {'context': 'local-context', 'dockerfile': 'Dockerfile'}
    _write_catalog(catalog_path, [server], repository='https://github.com/example/catalog')
    commands = []
    monkeypatch.setattr(
        'mcp_catalog.interfaces.builds._run',
        lambda command, **kwargs: commands.append(command),
    )

    build_image_for_server(load_catalog(catalog_path), name='demo', catalog_commit='deadbeef')

    command = commands[0]
    labels = [command[index + 1] for index, item in enumerate(command) if item == '--label']
    assert 'org.opencontainers.image.source=https://github.com/example/catalog' in labels
    assert 'org.opencontainers.image.revision=deadbeef' in labels
    assert any(label.startswith('io.docker.server.metadata={') for label in labels)
    assert labels == sorted(labels)


def test_build_plan_includes_image_labels(tmp_path):
    catalog_path = tmp_path / 'catalog.yaml'
    _write_catalog(catalog_path, [_build_server('example')])

    plan = build_plan(load_catalog(catalog_path), catalog_commit='deadbeef', branch='main')

    assert plan['builds'][0]['labels']['org.opencontainers.image.revision'] == (
        '0123456789abcdef0123456789abcdef01234567'
    )


def test_catalog_publish_applies_catalog_annotations(tmp_path, monkeypatch):
    catalog_path = tmp_path / 'catalog.yaml'
    _write_catalog(catalog_path, [], repository='https://github.com/example/catalog')
    commands = []
    monkeypatch.setattr(
        'mcp_catalog.interfaces.docker_catalog._run',
        lambda command, cwd=None: commands.append(command),
    )
    monkeypatch.setattr('mcp_catalog.interfaces.docker_catalog.require_executable', lambda _: None)
    monkeypatch.setattr('mcp_catalog.interfaces.docker_catalog.verify_catalog_artifact', print)

    publish_catalog_from_manifest(catalog_path, branch='main', catalog_commit='deadbeef')

    command = commands[0]
    annotations = [command[i + 1] for i, item in enumerate(command) if item == '--annotation']
    assert annotations == [
        'org.opencontainers.image.description=Catalog used by CLI tests.',
        'org.opencontainers.image.revision=deadbeef',
        'org.opencontainers.image.source=https://github.com/example/catalog',
        'org.opencontainers.image.title=Test Catalog',
    ]
    assert catalog_annotations(load_catalog(catalog_path)) == {
        'org.opencontainers.image.description': 'Catalog used by CLI tests.',
        'org.opencontainers.image.source': 'https://github.com/example/catalog',
        'org.opencontainers.image.title': 'Test Catalog',
    }


def test_docker_catalog_uses_docker_remote_entry_shape(tmp_path):
    catalog_path = tmp_path / 'catalog.yaml'
    remote = {
        'schema_version': 1,
        'schema_kind': 'https://mcp-catalog.schema.krenzer.space/server.schema.json',
        'name': 'remote-example',
        'kind': 'remote',
        'title': 'Remote example',
        'description': 'Remote server',
        'remote': {'url': 'https://example.com/mcp'},
    }
    _write_catalog(catalog_path, [remote])

    document = docker_catalog(load_catalog(catalog_path))
    entry = document['registry']['remote-example']

    assert document['version'] == 2
    assert entry['type'] == 'remote'
    assert entry['remote'] == {
        'transport_type': 'streamable-http',
        'url': 'https://example.com/mcp',
    }
    assert 'image' not in entry


def test_docker_catalog_remote_entry_includes_transport_headers_and_oauth(tmp_path):
    catalog_path = tmp_path / 'catalog.yaml'
    remote = {
        'schema_version': 1,
        'schema_kind': 'https://mcp-catalog.schema.krenzer.space/server.schema.json',
        'name': 'remote-example',
        'kind': 'remote',
        'title': 'Remote example',
        'description': 'Remote server',
        'remote': {
            'url': 'https://example.com/sse',
            'transport_type': 'sse',
            'headers': {'X-Team': '{{remote-example.team}}'},
        },
        'config': [{'description': 'Team', 'properties': {'team': {'type': 'string'}}}],
        'oauth': {
            'providers': [
                {
                    'provider': 'example',
                    'secret': 'remote-example.token',
                    'env': 'EXAMPLE_TOKEN',
                }
            ],
            'scopes': ['read'],
        },
    }
    _write_catalog(catalog_path, [remote])

    entry = docker_catalog(load_catalog(catalog_path))['registry']['remote-example']

    assert entry['remote'] == {
        'transport_type': 'sse',
        'url': 'https://example.com/sse',
        'headers': {'X-Team': '{{remote-example.team}}'},
    }
    assert entry['oauth'] == {
        'providers': [
            {'provider': 'example', 'secret': 'remote-example.token', 'env': 'EXAMPLE_TOKEN'}
        ],
        'scopes': ['read'],
    }


def test_plan_command_emits_parseable_json(tmp_path):
    catalog_path = tmp_path / 'catalog.yaml'
    _write_catalog(catalog_path, [_build_server('example')])

    result = runner.invoke(
        app,
        [
            'plan',
            str(catalog_path),
            '--catalog-commit',
            '0123456789abcdef',
        ],
    )

    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout)['builds'][0]['name'] == 'example'


def test_log_file_options_support_default_and_per_file_levels(tmp_path):
    catalog_path = tmp_path / 'catalog.yaml'
    default_log = tmp_path / 'default.log'
    debug_log = tmp_path / 'debug.log'
    _write_catalog(catalog_path, [_build_server('example')])

    result = runner.invoke(
        app,
        [
            '--log-level',
            'WARNING',
            '--log-file',
            str(default_log),
            '--log-file',
            f'DEBUG:{debug_log}',
            'validate',
            str(catalog_path),
        ],
    )

    assert result.exit_code == 0
    assert result.stdout == ''
    assert 'Validated' not in result.stderr
    assert 'Validated' not in default_log.read_text(encoding='utf-8')
    assert 'DEBUG mcp_catalog.interfaces.catalog: Validating manifest' in debug_log.read_text(
        encoding='utf-8'
    )
    assert 'Validated' in debug_log.read_text(encoding='utf-8')


def test_main_dumps_buffered_levels_if_logging_setup_fails(tmp_path, monkeypatch, capsys):
    catalog_path = tmp_path / 'catalog.yaml'
    _write_catalog(catalog_path, [_build_server('example')])
    original_begin_buffering = cli.begin_buffering

    def begin_with_record() -> None:
        original_begin_buffering()
        get_logger('test-before-cli-setup').debug('buffered before CLI setup')

    monkeypatch.setattr(cli, 'begin_buffering', begin_with_record)

    try:
        main(['--log-level', 'INVALID', 'validate', str(catalog_path)])
    except ValueError as error:
        assert 'Unknown log level' in str(error)
    else:
        raise AssertionError('Expected invalid log-level setup to fail')

    captured = capsys.readouterr()
    assert 'DEBUG mcp_catalog.test-before-cli-setup: buffered before CLI setup' in captured.err


def test_fastmcp_mirrors_public_cli_commands():
    pytest.importorskip('fastmcp')
    from mcp_catalog.mcp.server import load_tools

    tools = asyncio.run(load_tools().list_tools())

    assert {tool.name for tool in tools} == {
        'validate',
        'schema_generate',
        'schema_check',
        'server_list',
        'server_show',
        'server_add',
        'server_update',
        'server_edit',
        'server_remove',
        'server_scaffold_from_repo',
        'tools_capture',
        'upstream_resolve',
        'upstream_update',
        'build_plan',
        'image_build',
        'image_publish',
        'docker_server_entry',
        'docker_catalog',
        'catalog_publish',
        'publication_inspect',
        'branch_slug',
        'self_plan',
        'self_build',
    }


def test_test_server_cli_passes_options_to_mcp_test(monkeypatch, tmp_path):
    seen = {}

    def fake_test_server_image(catalog_path, name, **kwargs):
        seen.update(catalog_path=catalog_path, name=name, **kwargs)
        return 2

    monkeypatch.setattr('mcp_catalog.cli.test.test_server_image', fake_test_server_image)

    result = runner.invoke(
        app,
        [
            'test',
            'server',
            'example',
            str(tmp_path / 'catalog.yaml'),
            '--image',
            'example/image:1',
            '--env',
            'KEY=value',
            '--timeout',
            '12',
        ],
    )

    assert result.exit_code == 0, result.output
    assert seen == {
        'catalog_path': tmp_path / 'catalog.yaml',
        'name': 'example',
        'image': 'example/image:1',
        'env': {'KEY': 'value'},
        'timeout': 12.0,
    }


def test_fastmcp_stdio_uses_protocol_stream_without_banner(monkeypatch):
    pytest.importorskip('fastmcp')

    from mcp_catalog.mcp import server

    run_options = {}
    monkeypatch.setattr(server.mcp, 'run', lambda **kwargs: run_options.update(kwargs))

    server.serve_stdio()

    assert run_options == {'transport': 'stdio', 'show_banner': False}


def test_fastmcp_stdio_client_lists_and_calls_tools():
    pytest.importorskip('fastmcp')

    from fastmcp import Client
    from fastmcp.client.transports import StdioTransport

    async def verify() -> None:
        transport = StdioTransport(
            command='mcp-catalog',
            args=['mcp', 'serve'],
            cwd=str(Path(__file__).parents[1]),
        )
        async with Client(transport) as client:
            tools = await client.list_tools()
            result = await client.call_tool(
                'branch_slug',
                {'branch_name': 'feature/test'},
            )
        assert len(tools) == 23
        assert not result.is_error
        assert result.content[0].text == 'feature-test-59e07aa6356b'

    asyncio.run(verify())


def test_tools_file_resolves_relative_to_manifest_and_feeds_entries(tmp_path, monkeypatch):
    catalog_path = tmp_path / 'catalog.yaml'
    servers_dir = tmp_path / 'servers'
    servers_dir.mkdir()
    dump_yaml_file(
        catalog_path,
        {
            'schema_version': 1,
            'schema_kind': 'https://mcp-catalog.schema.krenzer.space/catalog.schema.json',
            'name': 'test-catalog',
            'title': 'Test Catalog',
            'description': 'Catalog used by CLI tests.',
            'servers_dir': 'servers',
        },
    )
    (servers_dir / 'example.tools.json').write_text(
        json.dumps(
            [
                {
                    'name': 'search',
                    'description': 'Search things.',
                    'arguments': [{'name': 'query', 'type': 'string', 'desc': 'Terms'}],
                }
            ]
        ),
        encoding='utf-8',
    )
    dump_yaml_file(
        servers_dir / 'example.yaml',
        {**_build_server('example'), 'tools_file': 'example.tools.json'},
    )
    monkeypatch.chdir(tmp_path.parent)

    catalog = load_catalog(catalog_path)
    server = catalog.servers[0]
    entry = docker_catalog(catalog, images={'example': 'example/image:1'})['registry']['example']
    metadata = image_metadata(server)

    assert server.tools_file == servers_dir / 'example.tools.json'
    assert entry['tools'] == [
        {
            'name': 'search',
            'description': 'Search things.',
            'arguments': [{'name': 'query', 'type': 'string', 'desc': 'Terms'}],
        }
    ]
    assert metadata['tools'] == entry['tools']


def test_tools_file_and_inline_tools_are_mutually_exclusive(tmp_path):
    tools_file = tmp_path / 'tools.json'
    tools_file.write_text('[]', encoding='utf-8')
    catalog_path = tmp_path / 'catalog.yaml'
    _write_catalog(
        catalog_path,
        [{**_build_server('example'), 'tools': [{'name': 'a'}], 'tools_file': 'tools.json'}],
    )

    with pytest.raises(Exception, match='either inline or in tools_file'):
        load_catalog(catalog_path)


def test_tools_file_must_contain_a_list(tmp_path):
    tools_file = tmp_path / 'tools.yaml'
    tools_file.write_text('name: not-a-list\n', encoding='utf-8')
    catalog_path = tmp_path / 'catalog.yaml'
    _write_catalog(catalog_path, [{**_build_server('example'), 'tools_file': 'tools.yaml'}])

    with pytest.raises(ValueError, match='must contain a list of tools'):
        docker_catalog(load_catalog(catalog_path), images={'example': 'example/image:1'})


def test_repository_tools_file_matches_running_server_shape():
    tools = json.loads(
        (Path(__file__).parents[1] / 'servers/agentralabs-agentic-memory-mcp/tools.json').read_text(
            encoding='utf-8'
        )
    )

    assert len(tools) == 124
    assert [tool['name'] for tool in tools][:2] == ['conversation_log', 'memory_add']
    assert all(tool['description'] for tool in tools)
