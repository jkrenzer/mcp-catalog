from __future__ import annotations

from pathlib import Path

import typer

from ..interfaces.catalog import validate_manifest
from .common import action, logger

app = typer.Typer()


@app.command('validate', help='Validate a catalog manifest or a single server manifest.')
def validate(
    path: Path = typer.Argument(Path('catalog.yaml'), help='YAML manifest to validate.'),
) -> None:
    action(lambda: validate_manifest(path))
    logger.info('Validated %s', path)


@app.command('validate-catalog', hidden=True)
def validate_catalog_alias(path: Path = typer.Argument(Path('catalog.yaml'))) -> None:
    validate(path)
