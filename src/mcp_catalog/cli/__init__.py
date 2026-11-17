from __future__ import annotations

import typer

from ..logging_config import (
    begin_buffering,
    configure_logging,
    dump_buffer_to_stderr,
    is_configured,
)
from .branching import app as branching_app
from .builds import app as builds_app
from .clone import app as clone_app
from .docker import app as docker_app
from .docker import catalog_app
from .mcp import app as mcp_app
from .publication import app as publication_app
from .schema import app as schema_app
from .self_images import app as self_app
from .servers import app as server_app
from .test import app as test_app
from .tools import app as tools_app
from .upstream import app as upstream_app
from .validate import app as validation_app

app = typer.Typer(
    name='mcp-catalog',
    help='Manage, build, and publish a declarative Docker MCP catalog.',
    no_args_is_help=True,
)


@app.callback()
def configure_cli_logging(
    log_level: str = typer.Option(
        'INFO',
        '--log-level',
        help='Minimum log level for stderr and log files (DEBUG, INFO, WARNING, ERROR, CRITICAL).',
    ),
    log_file: list[str] | None = typer.Option(
        None,
        '--log-file',
        help="Repeatable log file path or 'loglevel:filepath'.",
    ),
) -> None:
    configure_logging(log_level, log_file or ())


app.add_typer(validation_app)
app.add_typer(clone_app)
app.add_typer(schema_app, name='schema')
app.add_typer(server_app, name='server')
app.add_typer(upstream_app, name='upstream')
app.add_typer(tools_app, name='tools')
app.add_typer(test_app, name='test')
app.add_typer(builds_app)
app.add_typer(docker_app, name='docker')
app.add_typer(catalog_app, name='catalog')
app.add_typer(publication_app, name='publication')
app.add_typer(mcp_app, name='mcp')
app.add_typer(self_app, name='self')
app.add_typer(branching_app)


def main(argv: list[str] | None = None) -> None:
    begin_buffering()
    try:
        app(args=argv, prog_name='mcp-catalog')
    except BaseException:
        if not is_configured():
            dump_buffer_to_stderr()
        raise


if __name__ == '__main__':
    main()
