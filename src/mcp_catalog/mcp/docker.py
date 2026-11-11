from __future__ import annotations

import json

from ..interfaces.docker_catalog import (
    docker_catalog_document,
    docker_server_document,
    publish_catalog_from_manifest,
)
from .server import mcp


@mcp.tool
def docker_server_entry(
    name: str,
    catalog_path: str = 'catalog.yaml',
    image: str | None = None,
    branch: str = 'main',
    catalog_commit: str | None = None,
) -> str:
    """Generate one Docker MCP registry server entry as JSON."""
    document = docker_server_document(
        catalog_path,
        name,
        image=image,
        branch=branch,
        catalog_commit=catalog_commit,
    )
    return json.dumps(document, indent=2, ensure_ascii=False, sort_keys=True)


@mcp.tool
def docker_catalog(
    catalog_path: str = 'catalog.yaml',
    branch: str = 'main',
    catalog_commit: str | None = None,
) -> str:
    """Generate a Docker MCP catalog document as JSON."""
    document = docker_catalog_document(
        catalog_path,
        branch=branch,
        catalog_commit=catalog_commit,
    )
    return json.dumps(document, indent=2, ensure_ascii=False, sort_keys=True)


@mcp.tool
def catalog_publish(
    catalog_path: str = 'catalog.yaml',
    branch: str = 'main',
    catalog_commit: str | None = None,
) -> str:
    """Publish a generated Docker MCP catalog as an OCI image."""
    reference = publish_catalog_from_manifest(
        catalog_path,
        branch=branch,
        catalog_commit=catalog_commit,
    )
    return f'Published {reference}'
