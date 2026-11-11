from __future__ import annotations

from fastmcp import FastMCP

mcp = FastMCP(
    name='mcp-catalog',
    instructions='Manage, build, and publish the declarative MCP server catalog.',
)


def load_tools() -> FastMCP:
    from . import branching, builds, docker, publication, schema, servers, upstream, validate  # noqa: F401

    return mcp


def serve_stdio() -> None:
    load_tools()
    mcp.run(transport='stdio', show_banner=False)
