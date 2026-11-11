from __future__ import annotations

from typing import Any

from ..branching import build_image_reference, catalog_reference
from ..models import CatalogModel


def generate_catalog_entry(
    server: Any, *, resolved_image: str | None = None, branch_name: str | None = None
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        'name': server.name,
        'title': server.title,
        'description': server.description,
        'kind': server.kind,
        'enabled': server.enabled,
    }

    if server.kind == 'build':
        payload['image'] = resolved_image or build_image_reference(
            server.name, branch_name or 'main', 'build-placeholder-tag'
        )
    elif server.kind == 'image':
        payload['image'] = server.image
    elif server.kind == 'remote':
        payload['remote'] = {'url': str(server.remote.url)}

    return payload


def generate_catalog_map(
    catalog: CatalogModel, *, branch_name: str | None = None
) -> dict[str, Any]:
    result = {
        'name': catalog.name,
        'title': catalog.title,
        'description': catalog.description,
        'servers_dir': catalog.servers_dir,
        'servers': [
            generate_catalog_entry(server, branch_name=branch_name) for server in catalog.servers
        ],
        'catalog_reference': catalog_reference(branch_name or 'main'),
    }
    return result
