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
    normalize_description,
)

__all__ = [
    'CATALOG_ARTIFACT_TYPE',
    'catalog_annotations',
    'docker_catalog',
    'docker_catalog_artifact',
    'docker_catalog_artifact_document',
    'docker_catalog_document',
    'docker_server_document',
    'docker_server_entry',
    'image_for_server',
    'inspect_publication',
    'publish_catalog',
    'publish_catalog_from_manifest',
    'publish_image_from_catalog',
    'require_executable',
    'verify_catalog_artifact',
    'write_json',
]

CATALOG_ARTIFACT_TYPE = 'application/vnd.docker.mcp.catalog.v1+json'
CATALOG_LAYER_MEDIA_TYPE = 'application/json'

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


def docker_catalog_artifact(
    catalog: CatalogModel,
    *,
    images: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Return the payload of the ``docker mcp catalog pull`` OCI artifact.

    Each enabled server becomes an ``image`` or ``remote`` entry whose ``snapshot.server`` holds
    the same Docker MCP server entry used by the legacy ``registry`` document, so the gateway
    does not need to resolve image labels on pull.
    """
    image_map = images or {}
    repository = None if catalog.repository is None else str(catalog.repository)
    servers: list[dict[str, Any]] = []
    for server in sorted(catalog.servers, key=lambda item: item.name):
        if not server.enabled:
            continue
        entry = docker_server_entry(server, image=image_map.get(server.name), repository=repository)
        item: dict[str, Any]
        if server.kind == 'remote':
            item = {'type': 'remote', 'endpoint': entry['remote']['url']}
        else:
            image = entry.get('image')
            if not image:
                raise ValueError(f'Server has no image reference: {server.name}')
            item = {'type': 'image', 'image': image}
        item['snapshot'] = {'server': entry}
        servers.append(item)
    return {'title': catalog.title, 'servers': servers}


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


def docker_catalog_artifact_document(
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
    return docker_catalog_artifact(catalog, images=images)


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


def catalog_annotations(
    catalog: CatalogModel, *, catalog_commit: str | None = None
) -> dict[str, str]:
    """Return the OCI manifest annotations applied to the published catalog artifact."""
    annotations = {
        f'{OCI_LABEL_PREFIX}title': catalog.title,
        f'{OCI_LABEL_PREFIX}description': normalize_description(catalog.description),
    }
    if catalog.repository is not None:
        annotations[f'{OCI_LABEL_PREFIX}source'] = str(catalog.repository)
    if catalog_commit:
        annotations[f'{OCI_LABEL_PREFIX}revision'] = catalog_commit
    return dict(sorted(annotations.items()))


def publish_catalog(
    catalog_document: dict[str, Any],
    reference: str,
    *,
    annotations: dict[str, str] | None = None,
) -> None:
    """Push a catalog payload with oras as a ``docker mcp catalog pull`` compatible artifact.

    The artifact is an OCI image manifest with ``artifactType`` set to the Docker MCP catalog
    type, an empty config and a single ``application/json`` layer holding the payload.
    """
    logger.info('Publishing Docker MCP catalog %s', reference)
    with tempfile.TemporaryDirectory(prefix='mcp-catalog-publish-') as temporary:
        context = Path(temporary)
        write_json(context / 'catalog.json', catalog_document)
        command = ['oras', 'push', '--artifact-type', CATALOG_ARTIFACT_TYPE]
        for name, value in sorted((annotations or {}).items()):
            command.extend(['--annotation', f'{name}={value}'])
        command.extend([reference, f'catalog.json:{CATALOG_LAYER_MEDIA_TYPE}'])
        # oras records layer titles from the path as given, so run from the payload directory.
        _run(command, cwd=context)
    verify_catalog_artifact(reference)


def publish_catalog_from_manifest(
    catalog_path: str | Path,
    *,
    branch: str = 'main',
    catalog_commit: str | None = None,
) -> str:
    require_executable('oras')
    catalog = load_catalog(catalog_path)
    commit = _catalog_commit(catalog, catalog_commit)
    document = docker_catalog_artifact_document(
        catalog_path,
        branch=branch,
        catalog_commit=commit,
    )
    reference = catalog_reference(branch)
    publish_catalog(
        document,
        reference,
        annotations=catalog_annotations(catalog, catalog_commit=commit),
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


def _run(command: list[str], *, cwd: str | Path | None = None) -> subprocess.CompletedProcess[str]:
    logger.debug('Running external tool %s', command[0])
    return subprocess.run(command, check=True, text=True, cwd=cwd)


def verify_catalog_artifact(reference: str) -> None:
    """Fail unless the reference resolves to a Docker MCP catalog artifact."""
    require_executable('oras')
    result = subprocess.run(
        ['oras', 'manifest', 'fetch', reference],
        check=True,
        text=True,
        capture_output=True,
    )
    artifact_type = json.loads(result.stdout).get('artifactType')
    if artifact_type != CATALOG_ARTIFACT_TYPE:
        raise ValueError(
            f'{reference} has artifact type {artifact_type!r}, expected {CATALOG_ARTIFACT_TYPE!r}.'
        )


def inspect_publication(reference: str) -> None:
    logger.info('Inspecting publication %s', reference)
    _run(['docker', 'buildx', 'imagetools', 'inspect', reference])


def require_executable(name: str) -> None:
    if shutil.which(name) is None:
        raise FileNotFoundError(f'Required executable was not found on PATH: {name}')
