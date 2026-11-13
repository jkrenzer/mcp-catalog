from __future__ import annotations

import json
from pathlib import Path

import typer

from ..interfaces.builds import (
    build_image_for_server,
    build_plan,
    publish_server_image,
)
from ..interfaces.builds import (
    catalog_commit as resolve_catalog_commit,
)
from ..interfaces.catalog import find_server, load_catalog
from ..interfaces.docker_catalog import require_executable
from ..models import BuildServer, GitSourceModel
from .common import action, logger

app = typer.Typer(help='Build plans and server images.')
image_app = typer.Typer(help='Build and publish server images.')
app.add_typer(image_app, name='image')


@app.command('plan', help='Write a deterministic JSON plan for all build servers.')
def build_plan_command(
    catalog_path: Path = typer.Argument(Path('catalog.yaml'), help='Catalog manifest.'),
    output: Path = typer.Option(
        Path('-'), '--output', '-o', help='Output JSON file, or - for stdout.'
    ),
    branch: str = typer.Option('main', '--branch', help='Branch namespace for image references.'),
    catalog_commit: str | None = typer.Option(
        None, '--catalog-commit', help='Use this catalog commit id.'
    ),
) -> None:
    catalog = action(lambda: load_catalog(catalog_path))
    commit = action(lambda: resolve_catalog_commit(catalog, catalog_commit))
    plan = build_plan(catalog, catalog_commit=commit, branch=branch)
    serialized = json.dumps(plan, indent=2, ensure_ascii=False, sort_keys=True) + '\n'
    if str(output) == '-':
        typer.echo(serialized, nl=False)
    else:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(serialized, encoding='utf-8')
        logger.info('Wrote build plan to %s', output)


@image_app.command('build', help='Build a Git-backed or local build server image.')
def image_build(
    name: str = typer.Argument(help='Build server name.'),
    catalog_path: Path = typer.Argument(Path('catalog.yaml'), help='Catalog manifest.'),
    branch: str = typer.Option('main', '--branch'),
    catalog_commit: str | None = typer.Option(None, '--catalog-commit'),
    platform: list[str] | None = typer.Option(
        None, '--platform', help='Override manifest platforms; repeat for multiple platforms.'
    ),
    push: bool = typer.Option(
        False,
        '--push',
        help='Push directly; defaults to all configured platforms and supports registry caching.',
    ),
    cache_from: list[str] | None = typer.Option(
        None, '--cache-from', help='Buildx cache source; may be repeated.'
    ),
    cache_to: str | None = typer.Option(None, '--cache-to', help='Buildx cache destination.'),
) -> None:
    catalog = action(lambda: load_catalog(catalog_path))
    server = action(lambda: find_server(catalog, name))
    if not isinstance(server, BuildServer):
        raise typer.BadParameter(f'Only build servers can be built: {name}')
    if isinstance(server.source, GitSourceModel):
        action(lambda: require_executable('git'))
    image = action(
        lambda: build_image_for_server(
            catalog,
            name=name,
            catalog_commit=catalog_commit,
            branch=branch,
            platform=platform,
            push=push,
            cache_from=cache_from,
            cache_to=cache_to,
        )
    )
    logger.info('%s %s', 'Published' if push else 'Built', image)


@image_app.command('publish', help='Push a previously built server image to its registry.')
def image_publish(
    name: str = typer.Argument(help='Server name.'),
    catalog_path: Path = typer.Argument(Path('catalog.yaml'), help='Catalog manifest.'),
    branch: str = typer.Option('main', '--branch'),
    catalog_commit: str | None = typer.Option(None, '--catalog-commit'),
) -> None:
    image = action(
        lambda: publish_server_image(
            load_catalog(catalog_path),
            name=name,
            catalog_commit=catalog_commit,
            branch=branch,
        )
    )
    logger.info('Published %s', image)
