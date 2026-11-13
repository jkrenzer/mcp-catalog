from __future__ import annotations

import os
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from ..branching import build_image_reference, build_server_tag
from ..logging_config import get_logger
from ..models import BuildServer, CatalogModel, GitSourceModel
from .catalog import find_server
from .docker_runtime import require_docker_engine
from .docker_entry import image_labels, label_arguments

logger = get_logger(__name__)


def current_commit() -> str:
    result = subprocess.run(
        ['git', 'rev-parse', 'HEAD'],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def catalog_commit(catalog: CatalogModel, provided: str | None) -> str:
    if provided is not None:
        return provided
    has_build_images = any(
        isinstance(server, BuildServer) and server.enabled for server in catalog.servers
    )
    return current_commit() if has_build_images else ''


def build_plan(
    catalog: CatalogModel,
    *,
    catalog_commit: str,
    branch: str = 'main',
) -> dict[str, Any]:
    tag = build_server_tag(catalog_commit)
    repository = None if catalog.repository is None else str(catalog.repository)
    builds = []
    for server in sorted(
        (item for item in catalog.servers if isinstance(item, BuildServer) and item.enabled),
        key=lambda item: item.name,
    ):
        source = server.source
        if isinstance(source, GitSourceModel):
            source_document = {
                'repository': str(source.repository),
                'revision': source.revision,
                'context': source.context,
                'dockerfile': source.dockerfile,
            }
        else:
            source_document = {
                'type': 'local',
                'context': str(source.context),
                'dockerfile': str(source.dockerfile),
            }
        builds.append(
            {
                'name': server.name,
                'source': source_document,
                'platforms': list(server.build.platforms),
                'args': dict(sorted(server.build.args.items())),
                'labels': image_labels(
                    server, repository=repository, catalog_commit=catalog_commit
                ),
                'image': build_image_reference(server.name, branch, tag),
            }
        )
    return {'catalog_commit': catalog_commit, 'branch': branch, 'builds': builds}


def _run(command: list[str], *, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    logger.debug('Running external tool %s', command[0])
    if command[0] == 'docker':
        require_docker_engine()
        env = {key: value for key, value in os.environ.items() if not key.startswith('GIT_CONFIG_')}
    else:
        env = None
    return subprocess.run(command, cwd=cwd, check=True, text=True, env=env)


def build_server_image(
    server: BuildServer,
    *,
    image: str,
    platform: str | list[str] | None = None,
    push: bool = False,
    cache_from: str | list[str] | None = None,
    cache_to: str | None = None,
    labels: dict[str, str] | None = None,
) -> None:
    """Build one server image locally or publish it directly with Buildx.

    ``labels`` are applied with ``--label`` and override Dockerfile LABEL values.
    """
    platforms = [platform] if isinstance(platform, str) else platform
    if platforms is None:
        platforms = list(server.build.platforms)
    if not platforms:
        raise ValueError(f'No build platforms are configured for {server.name}.')
    if not push and len(platforms) != 1:
        raise ValueError(
            'Local image builds require exactly one platform; pass --push for '
            'multi-platform builds.'
        )
    logger.info('Building server %s for platform(s) %s', server.name, ','.join(platforms))
    source = server.source
    if isinstance(source, GitSourceModel):
        with tempfile.TemporaryDirectory(prefix=f'mcp-catalog-{server.name}-') as temporary:
            checkout = (Path(temporary) / 'source').resolve()
            _run(['git', 'clone', '--no-checkout', str(source.repository), str(checkout)])
            _run(['git', '-C', str(checkout), 'checkout', '--detach', source.revision])
            context = (checkout / source.context).resolve()
            dockerfile = (context / source.dockerfile).resolve()
            if not context.is_relative_to(checkout) or not dockerfile.is_relative_to(checkout):
                raise ValueError(
                    'Build context and Dockerfile must stay within the checked-out repository.'
                )
            if not context.is_dir():
                raise FileNotFoundError(f'Build context does not exist: {context}')
            if not dockerfile.is_file():
                raise FileNotFoundError(f'Dockerfile does not exist: {dockerfile}')
            _run_docker_build(
                server,
                context,
                dockerfile,
                image,
                platforms,
                push=push,
                cache_from=cache_from,
                cache_to=cache_to,
                labels=labels,
            )
        return

    context = source.context.resolve()
    dockerfile = source.dockerfile.resolve()
    if not context.is_dir():
        raise FileNotFoundError(f'Build context does not exist: {context}')
    if not dockerfile.is_file():
        raise FileNotFoundError(f'Dockerfile does not exist: {dockerfile}')
    if not dockerfile.is_relative_to(context):
        raise ValueError('The Dockerfile must be inside the local build context.')
    _run_docker_build(
        server,
        context,
        dockerfile,
        image,
        platforms,
        push=push,
        cache_from=cache_from,
        cache_to=cache_to,
        labels=labels,
    )


def _run_docker_build(
    server: BuildServer,
    context: Path,
    dockerfile: Path,
    image: str,
    platforms: list[str],
    *,
    push: bool,
    cache_from: str | list[str] | None,
    cache_to: str | None,
    labels: dict[str, str] | None = None,
) -> None:
    command = [
        'docker',
        'buildx',
        'build',
        '--push' if push else '--load',
        '--platform',
        ','.join(platforms),
        '--file',
        str(dockerfile),
        '--tag',
        image,
    ]
    cache_sources = [cache_from] if isinstance(cache_from, str) else cache_from or []
    for cache_source in cache_sources:
        command.extend(['--cache-from', cache_source])
    if cache_to:
        command.extend(['--cache-to', cache_to])
    for name, value in sorted(server.build.args.items()):
        command.extend(['--build-arg', f'{name}={value}'])
    if push:
        command.extend(['--build-arg', 'BUILDKIT_INLINE_CACHE=1'])
    command.extend(label_arguments(labels))
    command.append(str(context))
    _run(command)


def build_image_for_server(
    catalog: CatalogModel,
    *,
    name: str,
    catalog_commit: str | None = None,
    branch: str = 'main',
    platform: str | list[str] | None = None,
    push: bool = False,
    cache_from: str | list[str] | None = None,
    cache_to: str | None = None,
) -> str:
    server = find_server(catalog, name)
    if not isinstance(server, BuildServer):
        raise ValueError(f'Only build servers can be built: {name}')
    if not server.enabled:
        raise ValueError(f'Cannot build disabled server: {name}')
    if platform is None and not push:
        if len(server.build.platforms) != 1:
            raise ValueError(
                'Local image builds require exactly one platform; pass a platform to select one.'
            )
        platform = server.build.platforms[0]
    commit = catalog_commit or current_commit()
    image = build_image_reference(name, branch, build_server_tag(commit))
    build_server_image(
        server,
        image=image,
        platform=platform,
        push=push,
        cache_from=cache_from,
        cache_to=cache_to,
        labels=image_labels(
            server,
            repository=None if catalog.repository is None else str(catalog.repository),
            catalog_commit=commit,
        ),
    )
    return image


def publish_image(image: str) -> None:
    logger.info('Pushing server image %s', image)
    _run(['docker', 'push', image])


def publish_server_image(
    catalog: CatalogModel,
    *,
    name: str,
    catalog_commit: str | None = None,
    branch: str = 'main',
) -> str:
    server = find_server(catalog, name)
    if not isinstance(server, BuildServer):
        raise ValueError(f'Only build servers have build-image tags: {name}')
    if not server.enabled:
        raise ValueError(f'Cannot publish disabled server: {name}')
    commit = catalog_commit or current_commit()
    image = build_image_reference(name, branch, build_server_tag(commit))
    publish_image(image)
    return image
