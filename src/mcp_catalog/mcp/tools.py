from __future__ import annotations

from ..interfaces.tools_capture import capture_server_tools
from .server import mcp


@mcp.tool
def tools_capture(
    name: str,
    catalog_path: str = 'catalog.yaml',
    image: str | None = None,
    env: dict[str, str] | None = None,
    timeout: float = 60.0,
    dry_run: bool = False,
) -> str:
    """Run a server image and store its MCP tools/list result in the manifest.

    Build servers are built locally first unless `image` is given (this needs Docker).
    Tools are written to the manifest's tools_file, or inline into `tools` when it has none.
    `env` is passed to the container only while capturing. dry_run=true returns the diff.
    """
    return capture_server_tools(
        catalog_path, name, image=image, env=env, timeout=timeout, dry_run=dry_run
    ).summary()
