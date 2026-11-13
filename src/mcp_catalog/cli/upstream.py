from __future__ import annotations

from pathlib import Path

import typer

from ..interfaces import upstream as upstream_interface
from ..interfaces.catalog import find_server, load_catalog
from ..models import BuildServer, GitSourceModel
from .common import action, logger

app = typer.Typer(help='Resolve and explicitly pin upstream Git revisions.')


@app.command('resolve', help='Resolve a remote Git ref without changing any manifest.')
def upstream_resolve(
    name: str = typer.Argument(help='Build server name.'),
    catalog_path: Path = typer.Argument(Path('catalog.yaml'), help='Catalog manifest.'),
    ref: str = typer.Option('HEAD', '--ref', help='Remote Git ref to resolve.'),
) -> None:
    def run() -> str:
        server = find_server(load_catalog(catalog_path), name)
        if not isinstance(server, BuildServer):
            raise ValueError(f'Upstream revisions apply only to build servers: {name}')
        if not isinstance(server.source, GitSourceModel):
            raise ValueError(f'Upstream revisions apply only to Git-backed build servers: {name}')
        return upstream_interface.resolve_upstream_revision(str(server.source.repository), ref)

    typer.echo(action(run))


@app.command('update', help='Explicitly resolve and write a build server revision.')
def upstream_update(
    name: str = typer.Argument(help='Build server name.'),
    catalog_path: Path = typer.Argument(Path('catalog.yaml'), help='Catalog manifest.'),
    ref: str = typer.Option('HEAD', '--ref', help='Remote Git ref to pin.'),
    dry_run: bool = typer.Option(False, '--dry-run', help='Show the change without writing.'),
) -> None:
    change = action(
        lambda: upstream_interface.update_upstream_revision(
            catalog_path, name, ref, dry_run=dry_run
        )
    )
    if change.applied:
        logger.info('Updated %s revision to %s', name, change.details['revision'])
    else:
        typer.echo(change.summary(), nl=False)
