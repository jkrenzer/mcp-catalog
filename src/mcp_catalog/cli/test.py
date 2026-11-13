from __future__ import annotations

from pathlib import Path

import typer

from ..interfaces.changes import parse_assignments
from ..interfaces.tools_capture import test_server_image
from .common import action, logger

app = typer.Typer(help='Test MCP servers.')


@app.command('server', help='Run a server image and verify its MCP tools/list response.')
def test_server(
    name: str = typer.Argument(help='Build or image server name.'),
    catalog_path: Path = typer.Argument(Path('catalog.yaml'), help='Catalog manifest.'),
    image: str | None = typer.Option(
        None, '--image', help='Use this image instead of the configured or built image.'
    ),
    env: list[str] | None = typer.Option(
        None, '--env', help='Repeatable NAME=value passed to the container while testing.'
    ),
    timeout: float = typer.Option(60.0, '--timeout', help='Seconds to wait per MCP request.'),
) -> None:
    tool_count = action(
        lambda: test_server_image(
            catalog_path,
            name,
            image=image,
            env={key: str(value) for key, value in parse_assignments(env).items()},
            timeout=timeout,
        )
    )
    logger.info('MCP test passed for %s; server listed %s tools.', name, tool_count)
