from __future__ import annotations

from ..interfaces.docker_catalog import inspect_publication, require_executable
from .server import mcp


@mcp.tool
def publication_inspect(reference: str) -> str:
    """Inspect a published image or catalog reference using Docker Buildx."""
    require_executable('docker')
    inspect_publication(reference)
    return f'Inspected {reference}'
