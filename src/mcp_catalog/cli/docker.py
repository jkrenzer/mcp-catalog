from __future__ import annotations

import json
from pathlib import Path

import typer

from ..interfaces.docker_catalog import (
    docker_catalog_artifact_document,
    docker_catalog_document,
    docker_server_document,
    publish_catalog_from_manifest,
    require_executable,
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
    artifact: bool = typer.Option(
        False,
        '--artifact',
        help='Emit the OCI artifact payload used by `docker mcp catalog pull`, not the legacy '
        'registry document accepted by `docker mcp catalog import`.',
    ),
) -> None:
    generate = docker_catalog_artifact_document if artifact else docker_catalog_document
    document = action(
        lambda: generate(
            catalog_path,
            branch=branch,
            catalog_commit=catalog_commit,
        )
    )
    logger.info('Wrote Docker MCP catalog to %s', write_json(output, document))


@catalog_app.command(
    'publish',
    help='Publish the Docker MCP catalog as an OCI artifact for `docker mcp catalog pull`.',
)
def catalog_publish(
    catalog_path: Path = typer.Argument(Path('catalog.yaml'), help='Catalog manifest.'),
    branch: str = typer.Option('main', '--branch'),
    catalog_commit: str | None = typer.Option(None, '--catalog-commit'),
) -> None:
    action(lambda: require_executable('oras'))
    reference = action(
        lambda: publish_catalog_from_manifest(
            catalog_path,
            branch=branch,
            catalog_commit=catalog_commit,
        )
    )
    logger.info('Published %s', reference)
