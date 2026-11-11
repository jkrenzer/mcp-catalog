import typer

from ..logging_config import get_logger

logger = get_logger(__name__)
app = typer.Typer(help='Serve tools over MCP.')


@app.command('serve', help='Serve catalog management tools over MCP stdio.')
def mcp_serve_command() -> None:
    try:
        from ..mcp.server import serve_stdio
    except ImportError as error:
        logger.error('MCP serving requires the optional FastMCP dependency: %s', error)
        raise typer.Exit(1) from error
    serve_stdio()
