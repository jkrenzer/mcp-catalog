from __future__ import annotations

import json
from pathlib import Path

import typer

from ..interfaces.builds import current_commit
from ..interfaces.catalog import load_catalog
from ..interfaces.self_images import build_self_image, self_image_plan
from .common import action, logger

app = typer.Typer(help='Build and publish images of the mcp-catalog tooling itself.')


def _repository(catalog_path: Path) -> str | None:
    catalog = load_catalog(catalog_path)
    return None if catalog.repository is None else str(catalog.repository)


@app.command('plan', help='Write a deterministic JSON plan for the tooling images.')
def self_plan_command(
    catalog_path: Path = typer.Argument(Path('catalog.yaml'), help='Catalog manifest.'),
    output: Path = typer.Option(
        Path('-'), '--output', '-o', help='Output JSON file, or - for stdout.'
    ),
    branch: str = typer.Option('main', '--branch', help='Branch namespace for image references.'),
    catalog_commit: str | None = typer.Option(
        None, '--catalog-commit', help='Use this catalog commit id.'
    ),
    platform: list[str] | None = typer.Option(
        None, '--platform', help='Target platforms; repeat for multiple platforms.'
    ),
) -> None:
    repository = action(lambda: _repository(catalog_path))
    commit = action(lambda: catalog_commit or current_commit())
    plan = self_image_plan(
        branch=branch, catalog_commit=commit, repository=repository, platforms=platform
    )
    serialized = json.dumps(plan, indent=2, ensure_ascii=False, sort_keys=True) + '\n'
    if str(output) == '-':
        typer.echo(serialized, nl=False)
    else:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(serialized, encoding='utf-8')
        logger.info('Wrote tooling image plan to %s', output)


@app.command('build', help='Build or publish one tooling image (cli or mcp).')
def self_build_command(
    component: str = typer.Argument(help='Tooling image: cli or mcp.'),
    catalog_path: Path = typer.Argument(Path('catalog.yaml'), help='Catalog manifest.'),
    context: Path | None = typer.Option(
        None, '--context', help='Repository root with the Dockerfile; defaults to the Git root.'
    ),
    branch: str = typer.Option('main', '--branch'),
    catalog_commit: str | None = typer.Option(None, '--catalog-commit'),
    platform: list[str] | None = typer.Option(
        None, '--platform', help='Target platforms; repeat for multiple platforms.'
    ),
    push: bool = typer.Option(
        False, '--push', help='Push directly; supports multi-platform builds.'
    ),
    cache_from: list[str] | None = typer.Option(
        None, '--cache-from', help='Buildx cache source; may be repeated.'
    ),
    cache_to: str | None = typer.Option(None, '--cache-to', help='Buildx cache destination.'),
) -> None:
    repository = action(lambda: _repository(catalog_path))
    commit = action(lambda: catalog_commit or current_commit())
    image = action(
        lambda: build_self_image(
            component,
            context=context,
            branch=branch,
            catalog_commit=commit,
            repository=repository,
            platform=platform,
            push=push,
            cache_from=cache_from,
            cache_to=cache_to,
        )
    )
    logger.info('%s %s', 'Published' if push else 'Built', image)
