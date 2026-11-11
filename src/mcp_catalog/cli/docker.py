from __future__ import annotations

import json
from pathlib import Path

import typer

from ..interfaces.docker_catalog import (
    docker_catalog_document,
    docker_server_document,
    publish_catalog_from_manifest,
    write_json,
)
from ..logging_config import get_logger
from .common import action

logger = get_logger(__name__)
app = typer.Typer(help='Generate Docker MCP server and catalog artifacts.')
catalog_app = typer.Typer(help='Publish a generated Docker MCP catalog.')


@app.command('server-entry', help='Generate one Docker MCP registry server entry.')
def docker_server_entry_command(
    name: str = typer.Argument(help='Server name.'),
    catalog_path: Path = typer.Argument(Path('catalog.yaml'), help='Catalog manifest.'),
    output: Path = typer.Option(
        Path('-'), '--output', '-o', help='JSON output file, or - for stdout.'
    ),
    image: str | None = typer.Option(
        None, '--image', help='Override the generated image reference.'
    ),
    branch: str = typer.Option('main', '--branch'),
    catalog_commit: str | None = typer.Option(None, '--catalog-commit'),
) -> None:
    document = action(
        lambda: docker_server_document(
            catalog_path,
            name,
            image=image,
            branch=branch,
            catalog_commit=catalog_commit,
        )
    )
    if str(output) == '-':
        typer.echo(json.dumps(document, indent=2, ensure_ascii=False, sort_keys=True))
    else:
        logger.info('Wrote Docker MCP server entry to %s', write_json(output, document))


@app.command('catalog', help='Generate a Docker MCP catalog JSON document.')
def docker_catalog_command(
    catalog_path: Path = typer.Argument(Path('catalog.yaml'), help='Catalog manifest.'),
    output: Path = typer.Option(Path('dist/docker-mcp-catalog.json'), '--output', '-o'),
    branch: str = typer.Option('main', '--branch'),
    catalog_commit: str | None = typer.Option(None, '--catalog-commit'),
) -> None:
    document = action(
        lambda: docker_catalog_document(
            catalog_path,
            branch=branch,
            catalog_commit=catalog_commit,
        )
    )
    logger.info('Wrote Docker MCP catalog to %s', write_json(output, document))


@catalog_app.command('publish', help='Publish the generated Docker MCP catalog as an OCI image.')
def catalog_publish(
    catalog_path: Path = typer.Argument(Path('catalog.yaml'), help='Catalog manifest.'),
    branch: str = typer.Option('main', '--branch'),
    catalog_commit: str | None = typer.Option(None, '--catalog-commit'),
    cache_from: str | None = typer.Option(None, '--cache-from', help='Buildx cache source.'),
    cache_to: str | None = typer.Option(None, '--cache-to', help='Buildx cache destination.'),
) -> None:
    reference = action(
        lambda: publish_catalog_from_manifest(
            catalog_path,
            branch=branch,
            catalog_commit=catalog_commit,
            cache_from=cache_from,
            cache_to=cache_to,
        )
    )
    logger.info('Published %s', reference)
