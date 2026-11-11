from __future__ import annotations

from pathlib import Path
from typing import Any

from ..io.yaml import dump_yaml_file, load_yaml_file
from ..models import ServerModel
from .catalog import (
    find_server,
    load_catalog,
    load_server_manifest,
    server_document,
    server_manifest_path,
    validate_catalog_document,
)


def list_servers(catalog_path: str | Path) -> list[ServerModel]:
    catalog = load_catalog(catalog_path)
    return sorted(catalog.servers, key=lambda server: server.name)


def show_server(catalog_path: str | Path, name: str) -> dict[str, Any]:
    server = find_server(load_catalog(catalog_path), name)
    return server_document(server)


def add_server(catalog_path: str | Path, manifest_path: str | Path) -> ServerModel:
    new_server = load_server_manifest(manifest_path)
    catalog_path_abs = Path(catalog_path).resolve()
    document = load_yaml_file(catalog_path_abs)
    if not isinstance(document, dict):
        raise ValueError(f'{catalog_path} must contain a YAML mapping.')
    catalog = load_catalog(catalog_path_abs)
    if any(server.name == new_server.name for server in catalog.servers):
        raise ValueError(f'Server already exists: {new_server.name}')
    if 'servers' in document:
        document['servers'].append(server_document(new_server))
        validate_catalog_document(document, base_dir=catalog_path_abs.parent)
        dump_yaml_file(catalog_path_abs, document)
    else:
        target = server_manifest_path(catalog_path_abs, document, new_server.name)
        if target.exists():
            raise FileExistsError(f'Server manifest already exists: {target}')
        target.parent.mkdir(parents=True, exist_ok=True)
        dump_yaml_file(target, server_document(new_server))
        load_catalog(catalog_path_abs)
    return new_server


def update_server(
    catalog_path: str | Path,
    name: str,
    manifest_path: str | Path,
) -> ServerModel:
    updated_server = load_server_manifest(manifest_path)
    if updated_server.name != name:
        raise ValueError(f'Updated manifest name must remain {name!r}.')
    catalog_path_abs = Path(catalog_path).resolve()
    document = load_yaml_file(catalog_path_abs)
    if not isinstance(document, dict):
        raise ValueError(f'{catalog_path} must contain a YAML mapping.')
    catalog = load_catalog(catalog_path_abs)
    find_server(catalog, name)
    if 'servers' in document:
        index = next(i for i, item in enumerate(document['servers']) if item.get('name') == name)
        document['servers'][index] = server_document(updated_server)
        validate_catalog_document(document, base_dir=catalog_path_abs.parent)
        dump_yaml_file(catalog_path_abs, document)
    else:
        target = server_manifest_path(catalog_path_abs, document, name)
        dump_yaml_file(target, server_document(updated_server))
        load_catalog(catalog_path_abs)
    return updated_server


def remove_server(catalog_path: str | Path, name: str) -> None:
    catalog_path_abs = Path(catalog_path).resolve()
    document = load_yaml_file(catalog_path_abs)
    if not isinstance(document, dict):
        raise ValueError(f'{catalog_path} must contain a YAML mapping.')
    catalog = load_catalog(catalog_path_abs)
    find_server(catalog, name)
    if 'servers' in document:
        document['servers'] = [item for item in document['servers'] if item.get('name') != name]
        validate_catalog_document(document, base_dir=catalog_path_abs.parent)
        dump_yaml_file(catalog_path_abs, document)
    else:
        target = server_manifest_path(catalog_path_abs, document, name)
        target.unlink()
        load_catalog(catalog_path_abs)


def validate_server_manifest(path: str | Path) -> ServerModel:
    return load_server_manifest(path)
