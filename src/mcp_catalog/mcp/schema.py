from __future__ import annotations

from ..interfaces.schema import schema_drift, write_schemas
from .server import mcp


@mcp.tool
def schema_generate(directory: str = 'schemas') -> list[str]:
    """Generate the catalog and server JSON Schemas."""
    return [str(path) for path in write_schemas(directory)]


@mcp.tool
def schema_check(directory: str = 'schemas') -> str:
    """Check whether checked-in schemas match the current models."""
    drift = schema_drift(directory)
    if drift:
        raise ValueError('\n'.join(drift))
    return f'Schemas are current: {directory}'
