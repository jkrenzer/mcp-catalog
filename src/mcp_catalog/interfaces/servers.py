from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

from ..io.yaml import dump_yaml, load_yaml_file
from ..models import ServerModel
from .catalog import (
    find_server,
    load_catalog,
    load_server_manifest,
    server_document,
    server_manifest_path,
    validate_catalog_document,
    validate_server_document,
)
from .changes import ChangeSet, apply_edits

SERVER_SCHEMA_KIND = 'https://mcp-catalog.schema.krenzer.space/server.schema.json'


def list_servers(catalog_path: str | Path) -> list[ServerModel]:
    catalog = load_catalog(catalog_path)
    return sorted(catalog.servers, key=lambda server: server.name)


def show_server(catalog_path: str | Path, name: str) -> dict[str, Any]:
    server = find_server(load_catalog(catalog_path), name)
    return server_document(server)


def _load_catalog_document(catalog_path: str | Path) -> tuple[Path, dict[str, Any]]:
    path = Path(catalog_path).resolve()
    document = load_yaml_file(path)
    if not isinstance(document, dict):
        raise ValueError(f'{catalog_path} must contain a YAML mapping.')
    return path, document


def _plan_server_change(
    action: str,
    catalog_path: str | Path,
    name: str,
    mutate: Callable[[dict[str, Any] | None], dict[str, Any] | None],
    *,
    dry_run: bool,
    details: dict[str, Any] | None = None,
) -> ChangeSet:
    """Compute, validate and (unless ``dry_run``) write one change to a server manifest.

    ``mutate`` receives the raw stored manifest (``None`` when the server is new) and
    returns the raw manifest to store, or ``None`` to remove the server. Raw documents
    are written, not model dumps, so comments, key order and unset defaults survive.
    """
    path, document = _load_catalog_document(catalog_path)
    target = server_manifest_path(path, document, name)
    inline = 'servers' in document
    index: int | None = None
    existing: dict[str, Any] | None = None
    if inline:
        for position, item in enumerate(document['servers']):
            if item.get('name') == name:
                index, existing = position, item
                break
        before = path.read_text(encoding='utf-8')
    elif target.exists():
        existing = load_yaml_file(target)
        before = target.read_text(encoding='utf-8')
    else:
        before = None

    new = mutate(existing)
    if new is not None:
        if new.get('name') != name:
            raise ValueError(f'The manifest name must be {name!r}, not {new.get("name")!r}.')
        validate_server_document(new, base_dir=target.parent)

    if inline:
        if new is None and index is not None:
            del document['servers'][index]
        elif index is None and new is not None:
            document['servers'].append(new)
        elif new is not None and index is not None:
            document['servers'][index] = new
        validate_catalog_document(document, base_dir=path.parent)
        change = ChangeSet(action, path, before, dump_yaml(document), details=details or {})
    else:
        after = None if new is None else dump_yaml(new)
        change = ChangeSet(action, target, before, after, details=details or {})
    return change if dry_run else change.apply()


def _manifest_document(manifest_path: str | Path) -> dict[str, Any]:
    document = load_yaml_file(manifest_path)
    if not isinstance(document, dict):
        raise ValueError(f'{manifest_path} must contain a YAML mapping.')
    return document


def add_server(
    catalog_path: str | Path,
    manifest_path: str | Path | None = None,
    *,
    fields: dict[str, Any] | None = None,
    dry_run: bool = False,
) -> ChangeSet:
    """Add a server from a manifest file, from ``fields``, or from both.

    ``fields`` maps manifest paths to values (see ``changes.parse_path``) and is applied on
    top of the manifest file. ``schema_version`` and ``schema_kind`` default to the current
    schema, so an agent only has to supply the fields it collected.
    """
    if manifest_path is None and not fields:
        raise ValueError('Provide a manifest file, fields, or both.')
    raw = _manifest_document(manifest_path) if manifest_path is not None else {}
    raw.setdefault('schema_version', 1)
    raw.setdefault('schema_kind', SERVER_SCHEMA_KIND)
    apply_edits(raw, fields)
    name = raw.get('name')
    if not isinstance(name, str) or not name:
        raise ValueError('A server needs a name.')

    def mutate(existing: dict[str, Any] | None) -> dict[str, Any]:
        if existing is not None:
            raise ValueError(f'Server already exists: {name}')
        return raw

    return _plan_server_change(
        'add server', catalog_path, name, mutate, dry_run=dry_run, details={'name': name}
    )


def update_server(
    catalog_path: str | Path,
    name: str,
    manifest_path: str | Path,
    *,
    dry_run: bool = False,
) -> ChangeSet:
    """Replace a server manifest wholesale; use ``edit_server`` for surgical changes."""
    replacement = _manifest_document(manifest_path)
    if replacement.get('name') != name:
        raise ValueError(f'Updated manifest name must remain {name!r}.')

    def mutate(existing: dict[str, Any] | None) -> dict[str, Any]:
        if existing is None:
            raise ValueError(f'Server not found: {name}')
        return replacement

    return _plan_server_change(
        'update server', catalog_path, name, mutate, dry_run=dry_run, details={'name': name}
    )


def edit_server(
    catalog_path: str | Path,
    name: str,
    *,
    set_values: dict[str, Any] | None = None,
    unset_paths: list[str] | None = None,
    dry_run: bool = False,
) -> ChangeSet:
    """Change individual manifest fields in place, leaving everything else untouched."""
    if not set_values and not unset_paths:
        raise ValueError('Provide at least one value to set or path to unset.')

    def mutate(existing: dict[str, Any] | None) -> dict[str, Any]:
        if existing is None:
            raise ValueError(f'Server not found: {name}')
        apply_edits(existing, set_values, unset_paths)
        return existing

    return _plan_server_change(
        'edit server', catalog_path, name, mutate, dry_run=dry_run, details={'name': name}
    )


def remove_server(
    catalog_path: str | Path,
    name: str,
    *,
    dry_run: bool = False,
) -> ChangeSet:
    def mutate(existing: dict[str, Any] | None) -> None:
        if existing is None:
            raise ValueError(f'Server not found: {name}')
        return None

    return _plan_server_change(
        'remove server', catalog_path, name, mutate, dry_run=dry_run, details={'name': name}
    )


def validate_server_manifest(path: str | Path) -> ServerModel:
    return load_server_manifest(path)
