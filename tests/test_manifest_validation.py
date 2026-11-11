from pydantic import ValidationError

from mcp_catalog.interfaces.catalog import load_server_manifest
from mcp_catalog.models import (
    BuildServer,
    CatalogModel,
    GitSourceModel,
    LocalSourceModel,
    RemoteServer,
)


def test_build_manifest_works():
    build = {
        'schema_version': 1,
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
