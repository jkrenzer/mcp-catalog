import typer

from ..interfaces.branching import get_branch_slug

app = typer.Typer()


@app.command('branch-slug', help='Normalize and hash a branch name.')
def branch_slug_command(branch_name: str = typer.Argument(help='Branch name.')) -> None:
    typer.echo(get_branch_slug(branch_name))
