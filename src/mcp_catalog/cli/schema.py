from __future__ import annotations

from pathlib import Path

import typer

from ..interfaces.schema import schema_drift, write_schemas
from .common import action, logger

app = typer.Typer(help='Generate and verify manifest JSON Schemas.')


@app.command('generate', help='Generate the catalog and server JSON Schemas.')
def schema_generate(
    directory: Path = typer.Argument(Path('schemas'), help='Directory to write schema files into.'),
) -> None:
    for path in action(lambda: write_schemas(directory)):
        logger.info('Generated schema %s', path)


@app.command('check', help='Fail if checked-in JSON Schemas differ from the models.')
def schema_check(
    directory: Path = typer.Argument(
        Path('schemas'), help='Directory containing generated schemas.'
    ),
) -> None:
    drift = action(lambda: schema_drift(directory))
    if drift:
        for message in drift:
            logger.error('%s', message)
        raise typer.Exit(1)
    logger.info('Schemas are current: %s', directory)
