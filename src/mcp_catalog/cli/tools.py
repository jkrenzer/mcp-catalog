from __future__ import annotations

from pathlib import Path

import typer

from ..interfaces.changes import parse_assignments
from ..interfaces.tools_capture import capture_server_tools
from .common import action, logger

app = typer.Typer(help='Discover the tools a server image advertises.')


@app.command('capture', help='Run a server image and store its MCP tools/list in the manifest.')
def tools_capture(
    name: str = typer.Argument(help='Build or image server name.'),
    catalog_path: Path = typer.Argument(Path('catalog.yaml'), help='Catalog manifest.'),
    image: str | None = typer.Option(
        None, '--image', help='Use this image instead of building the server locally.'
    ),
    env: list[str] | None = typer.Option(
        None, '--env', help='Repeatable NAME=value passed to the container while capturing.'
    ),
    timeout: float = typer.Option(60.0, '--timeout', help='Seconds to wait per MCP request.'),
    dry_run: bool = typer.Option(False, '--dry-run', help='Show the change without writing.'),
) -> None:
    change = action(
        lambda: capture_server_tools(
            catalog_path,
            name,
            image=image,
            env={key: str(value) for key, value in parse_assignments(env).items()},
            timeout=timeout,
            dry_run=dry_run,
        )
    )
    if change.applied:
        logger.info('Captured %s tools for %s', change.details['tools'], name)
    else:
        typer.echo(change.summary(), nl=False)
