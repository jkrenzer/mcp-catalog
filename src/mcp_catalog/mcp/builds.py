from __future__ import annotations

import json

from ..interfaces.builds import (
    build_image_for_server,
    publish_server_image,
)
from ..interfaces.builds import (
    build_plan as create_build_plan,
)
from ..interfaces.builds import (
    catalog_commit as resolve_catalog_commit,
)
from ..interfaces.catalog import load_catalog
from ..interfaces.docker_catalog import require_executable
from ..models import BuildServer, GitSourceModel
from .server import mcp


@mcp.tool
def build_plan(
    catalog_path: str = 'catalog.yaml',
    branch: str = 'main',
    catalog_commit: str | None = None,
) -> str:
    """Create a deterministic JSON build plan for enabled build servers."""
    catalog = load_catalog(catalog_path)
    commit = resolve_catalog_commit(catalog, catalog_commit)
    plan = create_build_plan(catalog, catalog_commit=commit, branch=branch)
    return json.dumps(plan, indent=2, ensure_ascii=False, sort_keys=True)


@mcp.tool
def image_build(
    name: str,
    catalog_path: str = 'catalog.yaml',
    branch: str = 'main',
    catalog_commit: str | None = None,
    platform: list[str] | None = None,
    push: bool = False,
    cache_from: str | None = None,
    cache_to: str | None = None,
) -> str:
    """Build a pinned build server into the local Docker image store."""
    catalog = load_catalog(catalog_path)
    server = next((server for server in catalog.servers if server.name == name), None)
    if not isinstance(server, BuildServer):
        raise ValueError(f'Only build servers can be built: {name}')
    if isinstance(server.source, GitSourceModel):
        require_executable('git')
    image = build_image_for_server(
        catalog,
        name=name,
        catalog_commit=catalog_commit,
        branch=branch,
        platform=platform,
        push=push,
        cache_from=cache_from,
        cache_to=cache_to,
    )
    return f'Published {image}' if push else f'Built {image}'


@mcp.tool
def image_publish(
    name: str,
    catalog_path: str = 'catalog.yaml',
    branch: str = 'main',
    catalog_commit: str | None = None,
) -> str:
    """Push a previously built server image to its registry."""
    image = publish_server_image(
        load_catalog(catalog_path),
        name=name,
        catalog_commit=catalog_commit,
        branch=branch,
    )
    return f'Published {image}'
