from __future__ import annotations

import json

from ..interfaces.builds import current_commit
from ..interfaces.catalog import load_catalog
from ..interfaces.self_images import build_self_image, self_image_plan
from .server import mcp


def _repository(catalog_path: str) -> str | None:
    catalog = load_catalog(catalog_path)
    return None if catalog.repository is None else str(catalog.repository)


@mcp.tool
def self_plan(
    catalog_path: str = 'catalog.yaml',
    branch: str = 'main',
    catalog_commit: str | None = None,
    platform: list[str] | None = None,
) -> str:
    """Create a deterministic JSON plan for the mcp-catalog tooling images."""
    plan = self_image_plan(
        branch=branch,
        catalog_commit=catalog_commit or current_commit(),
        repository=_repository(catalog_path),
        platforms=platform,
    )
    return json.dumps(plan, indent=2, ensure_ascii=False, sort_keys=True)


@mcp.tool
def self_build(
    component: str,
    catalog_path: str = 'catalog.yaml',
    context: str | None = None,
    branch: str = 'main',
    catalog_commit: str | None = None,
    platform: list[str] | None = None,
    push: bool = False,
    cache_from: str | None = None,
    cache_to: str | None = None,
) -> str:
    """Build or publish one mcp-catalog tooling image (cli or mcp)."""
    image = build_self_image(
        component,
        context=context,
        branch=branch,
        catalog_commit=catalog_commit or current_commit(),
        repository=_repository(catalog_path),
        platform=platform,
        push=push,
        cache_from=cache_from,
        cache_to=cache_to,
    )
    return f'Published {image}' if push else f'Built {image}'
