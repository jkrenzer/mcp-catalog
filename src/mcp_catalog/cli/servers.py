from __future__ import annotations

from pathlib import Path

import typer

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
from .common import action, logger

app = typer.Typer(help='Manage the server manifests in a catalog.')


@app.command('list', help='List servers sorted by name.')
def server_list(
    catalog_path: Path = typer.Argument(Path('catalog.yaml'), help='Catalog manifest.'),
) -> None:
    for server in action(lambda: list_servers(catalog_path)):
        state = 'enabled' if server.enabled else 'disabled'
        typer.echo(f'{server.name}\t{server.kind}\t{state}\t{server.title}')


@app.command('show', help='Print a server manifest as YAML.')
def server_show(
    name: str = typer.Argument(help='Server name.'),
    catalog_path: Path = typer.Argument(Path('catalog.yaml'), help='Catalog manifest.'),
) -> None:
    document = action(lambda: show_server(catalog_path, name))
    typer.echo(dump_yaml(document), nl=False)


@app.command('add', help='Add a validated server manifest.')
def server_add(
    catalog_path: Path = typer.Argument(Path('catalog.yaml'), help='Catalog manifest.'),
    manifest: Path = typer.Option(..., '--manifest', exists=True, dir_okay=False, readable=True),
) -> None:
    server = action(lambda: add_server_operation(catalog_path, manifest))
    logger.info('Added server %s', server.name)


@app.command('update', help='Replace a server manifest with a validated manifest of the same name.')
def server_update(
    name: str = typer.Argument(help='Existing server name.'),
    catalog_path: Path = typer.Argument(Path('catalog.yaml'), help='Catalog manifest.'),
    manifest: Path = typer.Option(..., '--manifest', exists=True, dir_okay=False, readable=True),
) -> None:
    action(lambda: update_server_operation(catalog_path, name, manifest))
    logger.info('Updated server %s', name)


@app.command('remove', help='Remove a server manifest.')
def server_remove(
    name: str = typer.Argument(help='Server name to remove.'),
    catalog_path: Path = typer.Argument(Path('catalog.yaml'), help='Catalog manifest.'),
) -> None:
    action(lambda: remove_server_operation(catalog_path, name))
    logger.info('Removed server %s', name)
