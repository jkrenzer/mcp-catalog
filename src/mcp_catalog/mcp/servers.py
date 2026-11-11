from __future__ import annotations

from ..interfaces.servers import (
    add_server as add_server_operation,
)
from ..interfaces.servers import (
    list_servers,
    show_server,
)
from ..interfaces.servers import (
    remove_server as remove_server_operation,
)
from ..interfaces.servers import (
    update_server as update_server_operation,
)
from ..io.yaml import dump_yaml
from .server import mcp


@mcp.tool
def server_list(catalog_path: str = 'catalog.yaml') -> list[dict[str, str]]:
    """List catalog servers sorted by name, including kind and enabled state."""
    return [
        {
            'name': server.name,
            'kind': server.kind,
            'state': 'enabled' if server.enabled else 'disabled',
            'title': server.title,
        }
        for server in list_servers(catalog_path)
    ]


@mcp.tool
def server_show(name: str, catalog_path: str = 'catalog.yaml') -> str:
    """Show a server's manifest as YAML."""
    return dump_yaml(show_server(catalog_path, name))


@mcp.tool
def server_add(catalog_path: str, manifest: str) -> str:
    """Add a server from a validated YAML manifest file."""
    server = add_server_operation(catalog_path, manifest)
    return f'Added server {server.name}'


@mcp.tool
def server_update(name: str, catalog_path: str, manifest: str) -> str:
    """Replace an existing server manifest without changing its name."""
    server = update_server_operation(catalog_path, name, manifest)
    return f'Updated server {server.name}'


@mcp.tool
def server_remove(name: str, catalog_path: str = 'catalog.yaml') -> str:
    """Remove a server manifest from the catalog."""
    remove_server_operation(catalog_path, name)
    return f'Removed server {name}'
