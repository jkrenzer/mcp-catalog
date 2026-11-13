import pytest
from pydantic import ValidationError

from mcp_catalog.interfaces.catalog import load_server_manifest
from mcp_catalog.models import (
    BuildServer,
    CatalogModel,
    GitSourceModel,
    ImageServer,
    LocalSourceModel,
    RemoteServer,
)


def test_build_manifest_works():
    build = {
        'schema_version': 1,
        'schema_kind': 'https://mcp-catalog.schema.krenzer.space/server.schema.json',
        'name': 'demo-build',
        'kind': 'build',
        'title': 'Demo build',
        'description': 'Built from source',
        'enabled': True,
        'source': {
            'repository': 'https://github.com/example/demo.git',
            'revision': '0123456789abcdef0123456789abcdef01234567',
            'context': '.',
            'dockerfile': 'Dockerfile',
        },
        'build': {
            'platforms': ['linux/amd64'],
            'args': {},
        },
    }
    model = BuildServer.model_validate(build)
    assert model.name == 'demo-build'


def test_catalog_model_accepts_empty_servers():
    catalog = CatalogModel.model_validate(
        {
            'schema_version': 1,
            'schema_kind': 'https://mcp-catalog.schema.krenzer.space/catalog.schema.json',
            'name': 'personal-mcp-catalog',
            'title': 'Personal MCP Catalog',
            'description': 'Example catalog',
            'servers_dir': 'servers',
        }
    )
    assert catalog.name == 'personal-mcp-catalog'


def test_local_build_paths_resolve_relative_to_manifest(tmp_path, monkeypatch):
    manifest_dir = tmp_path / 'manifests'
    context = manifest_dir / 'context'
    context.mkdir(parents=True)
    dockerfile = context / 'Dockerfile'
    dockerfile.write_text('FROM scratch\n', encoding='utf-8')
    manifest_dir.joinpath('local.yaml').write_text(
        'schema_version: 1\n'
        'schema_kind: https://mcp-catalog.schema.krenzer.space/server.schema.json\n'
        'name: local-build\n'
        'kind: build\n'
        'title: Local build\n'
        'description: Local context\n'
        'source:\n'
        '  context: context\n'
        '  dockerfile: Dockerfile\n'
        'build: {}\n',
        encoding='utf-8',
    )
    monkeypatch.chdir(tmp_path)

    server = load_server_manifest(manifest_dir / 'local.yaml')

    assert isinstance(server.source, LocalSourceModel)
    assert server.source.context == context
    assert server.source.dockerfile == dockerfile


def test_local_build_paths_expand_git_base_cwd_and_shell_env(tmp_path, monkeypatch):
    git_base = tmp_path / 'repository'
    cwd = git_base / 'working'
    context = git_base / 'local-context'
    (git_base / '.git').mkdir(parents=True)
    cwd.mkdir()
    context.mkdir()
    (context / 'Dockerfile').write_text('FROM scratch\n', encoding='utf-8')
    manifest = tmp_path / 'server.yaml'
    manifest.write_text(
        'schema_version: 1\n'
        'schema_kind: https://mcp-catalog.schema.krenzer.space/server.schema.json\n'
        'name: local-build\n'
        'kind: build\n'
        'title: Local build\n'
        'description: Local context\n'
        'source:\n'
        '  context: $GIT_BASE/$LOCAL_CONTEXT\n'
        '  dockerfile: $CWD/../$LOCAL_CONTEXT/Dockerfile\n'
        'build: {}\n',
        encoding='utf-8',
    )
    monkeypatch.chdir(cwd)
    monkeypatch.setenv('LOCAL_CONTEXT', context.name)

    server = load_server_manifest(manifest)

    assert server.source.context == context
    assert server.source.dockerfile == context / 'Dockerfile'


def test_local_build_paths_require_existing_directory_and_file(tmp_path):
    manifest = tmp_path / 'server.yaml'
    manifest.write_text(
        'schema_version: 1\n'
        'schema_kind: https://mcp-catalog.schema.krenzer.space/server.schema.json\n'
        'name: local-build\n'
        'kind: build\n'
        'title: Local build\n'
        'description: Local context\n'
        'source:\n'
        '  context: missing\n'
        '  dockerfile: Dockerfile\n'
        'build: {}\n',
        encoding='utf-8',
    )

    try:
        load_server_manifest(manifest)
    except ValidationError:
        pass
    else:
        raise AssertionError('Expected an invalid local context to fail validation')


def test_local_dockerfile_must_be_inside_context(tmp_path):
    context = tmp_path / 'context'
    context.mkdir()
    outside_dockerfile = tmp_path / 'Dockerfile'
    outside_dockerfile.write_text('FROM scratch\n', encoding='utf-8')
    manifest = tmp_path / 'server.yaml'
    manifest.write_text(
        'schema_version: 1\n'
        'schema_kind: https://mcp-catalog.schema.krenzer.space/server.schema.json\n'
        'name: local-build\n'
        'kind: build\n'
        'title: Local build\n'
        'description: Local context\n'
        'source:\n'
        '  context: context\n'
        '  dockerfile: ../Dockerfile\n'
        'build: {}\n',
        encoding='utf-8',
    )

    try:
        load_server_manifest(manifest)
    except ValidationError:
        pass
    else:
        raise AssertionError('Expected an external Dockerfile to fail validation')


def test_repository_and_remote_urls_expand_environment_variables(monkeypatch):
    monkeypatch.setenv('EXAMPLE_REPOSITORY', 'https://github.com/example/demo.git')
    monkeypatch.setenv('EXAMPLE_REMOTE', 'https://example.com/mcp')

    build = BuildServer.model_validate(
        {
            'schema_version': 1,
            'schema_kind': 'https://mcp-catalog.schema.krenzer.space/server.schema.json',
            'name': 'demo-build',
            'kind': 'build',
            'title': 'Demo build',
            'description': 'Built from source',
            'source': {
                'repository': '$EXAMPLE_REPOSITORY',
                'revision': '0123456789abcdef0123456789abcdef01234567',
            },
            'build': {},
        }
    )
    remote = RemoteServer.model_validate(
        {
            'schema_version': 1,
            'schema_kind': 'https://mcp-catalog.schema.krenzer.space/server.schema.json',
            'name': 'remote-demo',
            'kind': 'remote',
            'title': 'Remote demo',
            'description': 'Remote endpoint',
            'remote': {'url': '${EXAMPLE_REMOTE}'},
        }
    )

    assert isinstance(build.source, GitSourceModel)
    assert str(build.source.repository) == 'https://github.com/example/demo.git'
    assert str(remote.remote.url) == 'https://example.com/mcp'


def _container_fields() -> dict:
    return {
        'schema_version': 1,
        'schema_kind': 'https://mcp-catalog.schema.krenzer.space/server.schema.json',
        'name': 'demo',
        'kind': 'image',
        'title': 'Demo',
        'description': 'Demo server',
        'image': 'ghcr.io/example/demo@sha256:' + '0' * 64,
    }


def test_catalog_fields_accept_docker_catalog_metadata(monkeypatch):
    monkeypatch.setenv('DEMO_ICON', 'https://example.com/icon.png')
    server = ImageServer.model_validate(
        {
            **_container_fields(),
            'icon': '$DEMO_ICON',
            'readme': 'https://example.com/docs',
            'upstream': 'https://github.com/example/demo',
            'date_added': '2026-01-15T00:00:00Z',
            'metadata': {'category': 'devops', 'tags': ['demo'], 'license': 'MIT'},
            'runtime': {
                'volumes': ['{{demo.data_dir}}:/data'],
                'disable_network': True,
                'env': [{'name': 'DEMO_REGION', 'value': '{{demo.region}}'}],
            },
            'secrets': [{'name': 'demo.api_key', 'env': 'DEMO_API_KEY'}],
            'config': [
                {
                    'description': 'Demo settings',
                    'properties': {'data_dir': {'type': 'string'}, 'region': {'type': 'string'}},
                    'required': ['data_dir'],
                }
            ],
            'tools': [{'name': 'search', 'annotations': {'read_only_hint': True}}],
        }
    )

    assert str(server.icon) == 'https://example.com/icon.png'
    assert server.config[0].name == 'demo'
    assert server.runtime.disable_network is True
    assert server.tools[0].annotations is not None
    assert server.tools[0].annotations.read_only_hint is True


def test_secret_names_must_use_prefix_dot_name():
    with pytest.raises(ValidationError, match='secrets.0.name'):
        ImageServer.model_validate(
            {**_container_fields(), 'secrets': [{'name': 'api_key', 'env': 'DEMO_API_KEY'}]}
        )


def test_templates_must_reference_the_server_configuration():
    with pytest.raises(ValidationError, match="must reference 'demo'"):
        ImageServer.model_validate(
            {
                **_container_fields(),
                'runtime': {'env': [{'name': 'DEMO_REGION', 'value': '{{other.region}}'}]},
            }
        )


def test_config_required_properties_must_exist():
    with pytest.raises(ValidationError, match='not defined'):
        ImageServer.model_validate(
            {
                **_container_fields(),
                'config': [
                    {
                        'description': 'Demo settings',
                        'properties': {'region': {'type': 'string'}},
                        'required': ['missing'],
                    }
                ],
            }
        )


def test_remote_servers_reject_container_runtime_and_accept_transport():
    remote = {
        'schema_version': 1,
        'schema_kind': 'https://mcp-catalog.schema.krenzer.space/server.schema.json',
        'name': 'remote-demo',
        'kind': 'remote',
        'title': 'Remote demo',
        'description': 'Remote endpoint',
        'remote': {
            'url': 'https://example.com/sse',
            'transport_type': 'sse',
            'headers': {'X-Team': '{{remote-demo.team}}'},
        },
        'config': [{'description': 'Team', 'properties': {'team': {'type': 'string'}}}],
    }

    server = RemoteServer.model_validate(remote)
    assert server.remote.transport_type == 'sse'

    with pytest.raises(ValidationError, match='runtime'):
        RemoteServer.model_validate({**remote, 'runtime': {'volumes': ['/a:/b']}})
    with pytest.raises(ValidationError, match='transport_type'):
        RemoteServer.model_validate(
            {**remote, 'remote': {'url': 'https://x', 'transport_type': 'stdio'}}
        )


def test_catalog_repository_expands_environment(monkeypatch):
    monkeypatch.setenv('CATALOG_REPOSITORY', 'https://github.com/example/catalog')
    catalog = CatalogModel.model_validate(
        {
            'schema_version': 1,
            'schema_kind': 'https://mcp-catalog.schema.krenzer.space/catalog.schema.json',
            'name': 'demo-catalog',
            'title': 'Demo',
            'description': 'Demo catalog',
            'repository': '$CATALOG_REPOSITORY',
        }
    )

    assert str(catalog.repository) == 'https://github.com/example/catalog'
