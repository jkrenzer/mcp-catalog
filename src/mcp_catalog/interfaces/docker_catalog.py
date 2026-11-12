from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from ..branching import build_image_reference, build_server_tag, catalog_reference
from ..logging_config import get_logger
from ..models import BuildServer, CatalogModel, ServerModel
from .builds import current_commit
from .builds import publish_image as _publish_image
from .catalog import find_server, load_catalog
from .docker_entry import (
    OCI_LABEL_PREFIX,
    docker_server_entry,
    label_arguments,
    normalize_description,
)

__all__ = [
    'catalog_labels',
    'docker_catalog',
    'docker_catalog_document',
    'docker_server_document',
    'docker_server_entry',
    'image_for_server',
    'inspect_publication',
    'publish_catalog',
    'publish_catalog_from_manifest',
    'publish_image_from_catalog',
    'require_executable',
    'write_json',
]

logger = get_logger(__name__)


def image_for_server(
    server: ServerModel,
    *,
    commit: str,
    branch: str = 'main',
) -> str | None:
    if isinstance(server, BuildServer):
        return build_image_reference(server.name, branch, build_server_tag(commit))
    if server.kind == 'image':
        return server.image
    return None


def _catalog_commit(catalog: CatalogModel, provided: str | None) -> str:
    if provided is not None:
        return provided
    has_build_images = any(
        isinstance(server, BuildServer) and server.enabled for server in catalog.servers
    )
    return current_commit() if has_build_images else ''


def docker_catalog(
    catalog: CatalogModel,
    *,
    images: dict[str, str] | None = None,
) -> dict[str, Any]:
    image_map = images or {}
    repository = None if catalog.repository is None else str(catalog.repository)
    registry = {}
    for server in sorted(catalog.servers, key=lambda item: item.name):
        if not server.enabled:
            continue
        registry[server.name] = docker_server_entry(
            server, image=image_map.get(server.name), repository=repository
        )
    return {
        'version': 2,
        'name': catalog.name,
        'displayName': catalog.title,
        'registry': registry,
    }


def write_json(path: str | Path, document: dict[str, Any]) -> Path:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(document, indent=2, ensure_ascii=False, sort_keys=True) + '\n',
        encoding='utf-8',
    )
    return output_path


def docker_catalog_document(
    catalog_path: str | Path,
    *,
    branch: str = 'main',
    catalog_commit: str | None = None,
) -> dict[str, Any]:
    catalog = load_catalog(catalog_path)
    commit = _catalog_commit(catalog, catalog_commit)
    images = {
        server.name: image
        for server in catalog.servers
        if server.enabled
        if (image := image_for_server(server, commit=commit, branch=branch)) is not None
    }
    return docker_catalog(catalog, images=images)


def docker_server_document(
    catalog_path: str | Path,
    name: str,
    *,
    image: str | None = None,
    branch: str = 'main',
    catalog_commit: str | None = None,
) -> dict[str, Any]:
    catalog = load_catalog(catalog_path)
    server = find_server(catalog, name)
    commit = _catalog_commit(catalog, catalog_commit)
    entry = docker_server_entry(
        server,
        image=image or image_for_server(server, commit=commit, branch=branch),
        repository=None if catalog.repository is None else str(catalog.repository),
    )
    return {name: entry}


def catalog_labels(catalog: CatalogModel, *, catalog_commit: str | None = None) -> dict[str, str]:
    """Return the OCI labels applied to the published catalog image."""
    labels = {
        f'{OCI_LABEL_PREFIX}title': catalog.title,
        f'{OCI_LABEL_PREFIX}description': normalize_description(catalog.description),
    }
    if catalog.repository is not None:
        labels[f'{OCI_LABEL_PREFIX}source'] = str(catalog.repository)
    if catalog_commit:
        labels[f'{OCI_LABEL_PREFIX}revision'] = catalog_commit
    return dict(sorted(labels.items()))


def publish_catalog(
    catalog_document: dict[str, Any],
    reference: str,
    *,
    cache_from: str | None = None,
    cache_to: str | None = None,
    labels: dict[str, str] | None = None,
) -> None:
    """Publish a generated Docker MCP catalog as a small OCI image."""
    logger.info('Publishing Docker MCP catalog %s', reference)
    with tempfile.TemporaryDirectory(prefix='mcp-catalog-publish-') as temporary:
        context = Path(temporary)
        write_json(context / 'catalog.json', catalog_document)
        (context / 'Dockerfile').write_text(
            'FROM scratch\nCOPY catalog.json /catalog.json\n',
            encoding='utf-8',
        )
        command = [
            'docker',
            'buildx',
            'build',
            '--push',
            '--tag',
            reference,
        ]
        if cache_from:
            command.extend(['--cache-from', cache_from])
        if cache_to:
            command.extend(['--cache-to', cache_to])
        command.extend(label_arguments(labels))
        command.append(str(context))
        _run(command)


def publish_catalog_from_manifest(
    catalog_path: str | Path,
    *,
    branch: str = 'main',
    catalog_commit: str | None = None,
    cache_from: str | None = None,
    cache_to: str | None = None,
) -> str:
    require_executable('docker')
    catalog = load_catalog(catalog_path)
    commit = _catalog_commit(catalog, catalog_commit)
    document = docker_catalog_document(
        catalog_path,
        branch=branch,
        catalog_commit=commit,
    )
    reference = catalog_reference(branch)
    publish_catalog(
        document,
        reference,
        cache_from=cache_from,
        cache_to=cache_to,
        labels=catalog_labels(catalog, catalog_commit=commit),
    )
    return reference


def publish_image_from_catalog(
    catalog_path: str | Path,
    name: str,
    *,
    branch: str = 'main',
    catalog_commit: str | None = None,
) -> str:
    catalog = load_catalog(catalog_path)
    server = find_server(catalog, name)
    if not isinstance(server, BuildServer):
        raise ValueError(f'Only build servers have build-image tags: {name}')
    if not server.enabled:
        raise ValueError(f'Cannot publish disabled server: {name}')
    image = image_for_server(
        server,
        commit=_catalog_commit(catalog, catalog_commit),
        branch=branch,
    )
    if image is None:
        raise ValueError(f'Build server has no image reference: {name}')
    _publish_image(image)
    return image


def _run(command: list[str]) -> subprocess.CompletedProcess[str]:
    logger.debug('Running external tool %s', command[0])
    return subprocess.run(command, check=True, text=True)


def inspect_publication(reference: str) -> None:
    logger.info('Inspecting publication %s', reference)
    _run(['docker', 'buildx', 'imagetools', 'inspect', reference])


def require_executable(name: str) -> None:
    if shutil.which(name) is None:
        raise FileNotFoundError(f'Required executable was not found on PATH: {name}')
