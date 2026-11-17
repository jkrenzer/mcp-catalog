"""Build and publish images of the mcp-catalog tooling itself.

The repository Dockerfile has a ``command`` target (the CLI) and an ``mcp`` target (the
FastMCP stdio server). Both are published under the ``self`` namespace next to the server
images, following the same branch-aware naming rules.
"""

from __future__ import annotations

from dataclasses import dataclass
from importlib import metadata
from pathlib import Path
from typing import Any

from ..branching import build_server_tag, self_image_reference
from ..expansion import git_base_directory
from ..logging_config import get_logger
from .builds import _run
from .docker_entry import OCI_LABEL_PREFIX, label_arguments

logger = get_logger(__name__)
DEFAULT_PLATFORMS = ['linux/amd64']
LATEST_TAG = 'latest'


@dataclass(frozen=True)
class SelfImage:
    component: str
    target: str
    title: str
    description: str


SELF_IMAGES: dict[str, SelfImage] = {
    'cli': SelfImage(
        component='cli',
        target='command',
        title='mcp-catalog CLI',
        description='Command-line interface of the mcp-catalog suite.',
    ),
    'mcp': SelfImage(
        component='mcp',
        target='mcp',
        title='mcp-catalog MCP server',
        description='FastMCP stdio server exposing the mcp-catalog operations as tools.',
    ),
}


def self_image(component: str) -> SelfImage:
    try:
        return SELF_IMAGES[component]
    except KeyError:
        raise ValueError(
            f'Unknown tooling image {component!r}; choose from {", ".join(SELF_IMAGES)}.'
        ) from None


def package_version() -> str | None:
    try:
        return metadata.version('mcp-catalog')
    except metadata.PackageNotFoundError:
        return None


def self_image_tags(component: str, *, branch: str, catalog_commit: str) -> list[str]:
    """Return the immutable commit tag followed by the moving ``latest`` tag."""
    return [
        self_image_reference(component, branch, build_server_tag(catalog_commit)),
        self_image_reference(component, branch, LATEST_TAG),
    ]


def self_image_labels(
    component: str,
    *,
    repository: str | None = None,
    catalog_commit: str | None = None,
) -> dict[str, str]:
    image = self_image(component)
    labels = {
        f'{OCI_LABEL_PREFIX}title': image.title,
        f'{OCI_LABEL_PREFIX}description': image.description,
    }
    if (version := package_version()) is not None:
        labels[f'{OCI_LABEL_PREFIX}version'] = version
    if repository is not None:
        labels[f'{OCI_LABEL_PREFIX}source'] = repository
        labels[f'{OCI_LABEL_PREFIX}url'] = repository
    if catalog_commit:
        labels[f'{OCI_LABEL_PREFIX}revision'] = catalog_commit
    return dict(sorted(labels.items()))


def self_image_plan(
    *,
    branch: str,
    catalog_commit: str,
    repository: str | None = None,
    platforms: list[str] | None = None,
) -> dict[str, Any]:
    """Return a deterministic plan of the tooling images for a branch and commit."""
    images = []
    for component in sorted(SELF_IMAGES):
        image = SELF_IMAGES[component]
        tags = self_image_tags(component, branch=branch, catalog_commit=catalog_commit)
        images.append(
            {
                'component': component,
                'target': image.target,
                'platforms': list(platforms or DEFAULT_PLATFORMS),
                'image': tags[0],
                'tags': tags,
                'labels': self_image_labels(
                    component, repository=repository, catalog_commit=catalog_commit
                ),
            }
        )
    return {'catalog_commit': catalog_commit, 'branch': branch, 'images': images}


def default_build_context() -> Path:
    """Return the repository root containing the tooling Dockerfile."""
    return git_base_directory(Path.cwd()) or Path.cwd().resolve()


def build_self_image(
    component: str,
    *,
    context: str | Path | None = None,
    branch: str = 'main',
    catalog_commit: str,
    repository: str | None = None,
    platform: str | list[str] | None = None,
    push: bool = False,
    cache_from: str | list[str] | None = None,
    cache_to: str | None = None,
) -> str:
    """Build one tooling image with Buildx and return its commit-tagged reference."""
    image = self_image(component)
    platforms = [platform] if isinstance(platform, str) else platform
    if not platforms:
        platforms = list(DEFAULT_PLATFORMS)
    if not push and len(platforms) != 1:
        raise ValueError(
            'Local image builds require exactly one platform; pass --push for '
            'multi-platform builds.'
        )
    context_path = Path(context) if context is not None else default_build_context()
    context_path = context_path.resolve()
    dockerfile = context_path / 'Dockerfile'
    if not dockerfile.is_file():
        raise FileNotFoundError(f'Tooling Dockerfile does not exist: {dockerfile}')
    tags = self_image_tags(component, branch=branch, catalog_commit=catalog_commit)
    logger.info('Building tooling image %s for platform(s) %s', tags[0], ','.join(platforms))
    command = [
        'docker',
        'buildx',
        'build',
        '--push' if push else '--load',
        '--platform',
        ','.join(platforms),
        '--file',
        str(dockerfile),
        '--target',
        image.target,
    ]
    for tag in tags:
        command.extend(['--tag', tag])
    cache_sources = [cache_from] if isinstance(cache_from, str) else cache_from or []
    if push:
        cache_sources = [
            f'type=registry,ref={tags[1]}',
            *cache_sources,
        ]
    for cache_source in cache_sources:
        command.extend(['--cache-from', cache_source])
    if cache_to:
        command.extend(['--cache-to', cache_to])
    if push:
        command.extend(['--build-arg', 'BUILDKIT_INLINE_CACHE=1'])
    command.extend(
        label_arguments(
            self_image_labels(component, repository=repository, catalog_commit=catalog_commit)
        )
    )
    command.append(str(context_path))
    _run(command)
    return tags[0]
