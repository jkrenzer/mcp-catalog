from __future__ import annotations

from ..interfaces.catalog import find_server, load_catalog
from ..interfaces.upstream import resolve_upstream_revision, update_upstream_revision
from ..models import BuildServer, GitSourceModel
from .server import mcp


@mcp.tool
def upstream_resolve(
    name: str,
    catalog_path: str = 'catalog.yaml',
    ref: str = 'HEAD',
) -> str:
    """Resolve an upstream Git ref without changing any manifest."""
    server = find_server(load_catalog(catalog_path), name)
    if not isinstance(server, BuildServer):
        raise ValueError(f'Upstream revisions apply only to build servers: {name}')
    if not isinstance(server.source, GitSourceModel):
        raise ValueError(f'Upstream revisions apply only to Git-backed build servers: {name}')
    return resolve_upstream_revision(str(server.source.repository), ref)


@mcp.tool
def upstream_update(
    name: str,
    catalog_path: str = 'catalog.yaml',
    ref: str = 'HEAD',
    dry_run: bool = False,
) -> str:
    """Explicitly resolve and pin a build server's upstream revision.

    With dry_run=true nothing is written and the resulting diff is returned.
    """
    change = update_upstream_revision(catalog_path, name, ref, dry_run=dry_run)
    return change.summary()
