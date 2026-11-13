from __future__ import annotations

from typing import Any

from ..interfaces.scaffold import scaffold_from_repository
from ..interfaces.servers import (
    add_server as add_server_operation,
)
from ..interfaces.servers import (
    edit_server as edit_server_operation,
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
def server_add(
    catalog_path: str,
    manifest: str | None = None,
    fields: dict[str, Any] | None = None,
    dry_run: bool = False,
) -> str:
    """Add a server from a manifest file, from `fields`, or from both.

    `fields` maps manifest paths to values, e.g. {"name": "x", "kind": "build",
    "source.repository": "https://github.com/o/r.git", "metadata.tags": ["a", "b"],
    "secrets[+]": {"name": "x.key", "env": "KEY"}}. Path syntax: dotted keys, `[0]` index,
    `[+]` append, `[name=value]` select a list item by key. `fields` are applied on top of
    the manifest file; schema_version and schema_kind default to the current schema. The
    manifest is validated before anything is written. With dry_run=true nothing is written
    and the resulting diff is returned.
    """
    return add_server_operation(catalog_path, manifest, fields=fields, dry_run=dry_run).summary()


@mcp.tool
def server_update(name: str, catalog_path: str, manifest: str, dry_run: bool = False) -> str:
    """Replace an existing server manifest wholesale without changing its name.

    Prefer server_edit for changing individual fields. dry_run=true returns the diff only.
    """
    return update_server_operation(catalog_path, name, manifest, dry_run=dry_run).summary()


@mcp.tool
def server_edit(
    name: str,
    catalog_path: str = 'catalog.yaml',
    set: dict[str, Any] | None = None,
    unset: list[str] | None = None,
    dry_run: bool = False,
) -> str:
    """Surgically change fields of a server manifest, leaving everything else untouched.

    `set` maps paths to new values (e.g. {"metadata.license": "MIT", "runtime.env[+]":
    {"name": "A", "value": "b"}, "tools[name=x].description": "..."}); `unset` lists
    paths to remove (a key or a list item). Paths use dotted keys, `[0]` indexes, `[+]` to
    append and `[key=value]` to select a list item. Removals run before assignments. The
    result is validated before writing; dry_run=true returns the diff without writing.
    """
    return edit_server_operation(
        catalog_path, name, set_values=set, unset_paths=unset, dry_run=dry_run
    ).summary()


@mcp.tool
def server_remove(name: str, catalog_path: str = 'catalog.yaml', dry_run: bool = False) -> str:
    """Remove a server manifest from the catalog (dry_run=true returns the diff only)."""
    return remove_server_operation(catalog_path, name, dry_run=dry_run).summary()


@mcp.tool
def server_scaffold_from_repo(
    repository: str,
    ref: str = 'HEAD',
    name: str | None = None,
) -> dict[str, Any]:
    """Draft a build-server manifest from an upstream Git repository (nothing is written).

    Shallow-clones the repository as untrusted data and reads the Dockerfile, project files,
    LICENSE, README and .env examples. Returns `manifest` (pass it as `fields` to server_add
    after filling the gaps), `found` (field -> where it was read), `missing` (field,
    required, expected, hint) and `notes` for items needing review.
    """
    return scaffold_from_repository(repository, ref, name=name)
