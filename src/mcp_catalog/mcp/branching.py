from __future__ import annotations

from ..interfaces.branching import get_branch_slug
from .server import mcp


@mcp.tool
def branch_slug(branch_name: str) -> str:
    """Normalize and hash a branch name for use in image namespaces."""
    return get_branch_slug(branch_name)
