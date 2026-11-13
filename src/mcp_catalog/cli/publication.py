from __future__ import annotations

import typer

from ..interfaces.docker_catalog import inspect_publication
from .common import action

app = typer.Typer(help='Inspect published OCI images.')


@app.command('inspect', help='Inspect a published image or catalog reference.')
def publication_inspect(
    reference: str = typer.Argument(help='OCI image reference to inspect.'),
) -> None:
    action(lambda: inspect_publication(reference))
