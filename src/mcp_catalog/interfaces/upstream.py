from __future__ import annotations

import subprocess
from dataclasses import replace
from pathlib import Path
from urllib.parse import urlsplit

from ..models import BuildServer, GitSourceModel
from .catalog import find_server, load_catalog
from .changes import ChangeSet
from .servers import edit_server


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
    *,
    dry_run: bool = False,
) -> ChangeSet:
    """Resolve ``ref`` and pin it as the build server's revision; ``details['revision']``."""
    server = find_server(load_catalog(catalog_path), name)
    if not isinstance(server, BuildServer):
        raise ValueError(f'Upstream revisions apply only to build servers: {name}')
    if not isinstance(server.source, GitSourceModel):
        raise ValueError(f'Upstream revisions apply only to Git-backed build servers: {name}')
    revision = resolve_upstream_revision(str(server.source.repository), ref)
    change = edit_server(
        catalog_path, name, set_values={'source.revision': revision}, dry_run=dry_run
    )
    return replace(change, details={**change.details, 'revision': revision})
