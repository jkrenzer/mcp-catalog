from __future__ import annotations

from pathlib import Path

import typer

from ..interfaces.changes import ChangeSet, parse_assignments
from ..interfaces.scaffold import scaffold_from_repository, scaffold_report
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


DRY_RUN = typer.Option(False, '--dry-run', help='Show the change as a diff without writing.')
SET_OPTION = typer.Option(
    None,
    '--set',
    help="Repeatable 'path=value'; paths look like metadata.license, tools[0].description, "
    'runtime.env[+] (append) or runtime.env[name=X].value. Values are parsed as YAML.',
)


def _report(change: ChangeSet) -> None:
    if change.applied:
        logger.info('%s: %s', change.action, change.details.get('name', change.target))
    else:
        typer.echo(change.summary(), nl=False)


@app.command('add', help='Add a server from a manifest file and/or --set fields.')
def server_add(
    catalog_path: Path = typer.Argument(Path('catalog.yaml'), help='Catalog manifest.'),
    manifest: Path | None = typer.Option(
        None, '--manifest', exists=True, dir_okay=False, readable=True
    ),
    set_values: list[str] | None = SET_OPTION,
    dry_run: bool = DRY_RUN,
) -> None:
    change = action(
        lambda: add_server_operation(
            catalog_path, manifest, fields=parse_assignments(set_values), dry_run=dry_run
        )
    )
    _report(change)


@app.command('update', help='Replace a server manifest with a validated manifest of the same name.')
def server_update(
    name: str = typer.Argument(help='Existing server name.'),
    catalog_path: Path = typer.Argument(Path('catalog.yaml'), help='Catalog manifest.'),
    manifest: Path = typer.Option(..., '--manifest', exists=True, dir_okay=False, readable=True),
    dry_run: bool = DRY_RUN,
) -> None:
    _report(action(lambda: update_server_operation(catalog_path, name, manifest, dry_run=dry_run)))


@app.command('edit', help='Change individual fields of a server manifest in place.')
def server_edit(
    name: str = typer.Argument(help='Existing server name.'),
    catalog_path: Path = typer.Argument(Path('catalog.yaml'), help='Catalog manifest.'),
    set_values: list[str] | None = SET_OPTION,
    unset: list[str] | None = typer.Option(
        None, '--unset', help='Repeatable path of a field or list item to remove.'
    ),
    dry_run: bool = DRY_RUN,
) -> None:
    change = action(
        lambda: edit_server_operation(
            catalog_path,
            name,
            set_values=parse_assignments(set_values),
            unset_paths=list(unset or []),
            dry_run=dry_run,
        )
    )
    _report(change)


@app.command('remove', help='Remove a server manifest.')
def server_remove(
    name: str = typer.Argument(help='Server name to remove.'),
    catalog_path: Path = typer.Argument(Path('catalog.yaml'), help='Catalog manifest.'),
    dry_run: bool = DRY_RUN,
) -> None:
    _report(action(lambda: remove_server_operation(catalog_path, name, dry_run=dry_run)))


@app.command('scaffold-from-repo', help='Draft a manifest from an upstream Git repository.')
def server_scaffold_from_repo(
    repository: str = typer.Argument(help='HTTP(S) clone URL of the upstream repository.'),
    ref: str = typer.Option('HEAD', '--ref', help='Branch or tag to inspect.'),
    name: str | None = typer.Option(None, '--name', help='Server name; defaults to owner-repo.'),
    output: Path | None = typer.Option(
        None, '--output', '-o', help='Write the draft manifest here instead of stdout.'
    ),
) -> None:
    result = action(lambda: scaffold_from_repository(repository, ref, name=name))
    rendered = dump_yaml(result['manifest'])
    if output is None:
        typer.echo(rendered, nl=False)
    else:
        output.write_text(rendered, encoding='utf-8')
        logger.info('Wrote draft manifest to %s', output)
    typer.echo(scaffold_report(result), err=True)
