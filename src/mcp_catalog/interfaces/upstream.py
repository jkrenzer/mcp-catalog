from __future__ import annotations

import subprocess
from pathlib import Path
from urllib.parse import urlsplit

from ..io.yaml import dump_yaml_file, load_yaml_file
from ..models import BuildServer, GitSourceModel
from .catalog import (
    find_server,
    load_catalog,
    server_manifest_path,
    validate_catalog_document,
    validate_server_document,
)


def resolve_upstream_revision(repository: str, ref: str = 'HEAD') -> str:
    parsed_repository = urlsplit(repository)
    if parsed_repository.scheme not in {'http', 'https'} or not parsed_repository.hostname:
        raise ValueError('Upstream repository must be an absolute HTTP(S) URL.')
    result = subprocess.run(
        ['git', 'ls-remote', repository, ref],
        check=True,
        capture_output=True,
        text=True,
    )
    revisions = [line.split()[0] for line in result.stdout.splitlines() if line.strip()]
    if not revisions:
        raise ValueError(f'No revision found for {repository!r} at ref {ref!r}.')
    if len(revisions) != 1:
        raise ValueError(f'Ref {ref!r} resolved to multiple revisions in {repository!r}.')
    return revisions[0]


def update_upstream_revision(
    catalog_path: str | Path,
    name: str,
    ref: str = 'HEAD',
) -> str:
    catalog_path_abs = Path(catalog_path).resolve()
    document = load_yaml_file(catalog_path_abs)
    if not isinstance(document, dict):
        raise ValueError(f'{catalog_path} must contain a YAML mapping.')
    server = find_server(load_catalog(catalog_path_abs), name)
    if not isinstance(server, BuildServer):
        raise ValueError(f'Upstream revisions apply only to build servers: {name}')
    if not isinstance(server.source, GitSourceModel):
        raise ValueError(f'Upstream revisions apply only to Git-backed build servers: {name}')
    revision = resolve_upstream_revision(str(server.source.repository), ref)
    if 'servers' in document:
        for item in document['servers']:
            if item.get('name') == name:
                item['source']['revision'] = revision
                break
        validate_catalog_document(document, base_dir=catalog_path_abs.parent)
        dump_yaml_file(catalog_path_abs, document)
    else:
        target = server_manifest_path(catalog_path_abs, document, name)
        server_document = load_yaml_file(target)
        server_document['source']['revision'] = revision
        validate_server_document(server_document, base_dir=target.parent)
        dump_yaml_file(target, server_document)
    return revision
