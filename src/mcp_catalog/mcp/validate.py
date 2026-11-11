from __future__ import annotations

from ..interfaces.catalog import validate_manifest
from .server import mcp


@mcp.tool
def validate(path: str = 'catalog.yaml') -> str:
    """Validate a catalog manifest or a single server manifest."""
    validate_manifest(path)
    return f'Validated {path}'
