from __future__ import annotations

import shutil
import subprocess
from pathlib import Path, PurePosixPath
from urllib.parse import parse_qs, unquote, urlsplit, urlunsplit

import typer

from .common import logger

app = typer.Typer()


def _parse_repository_url(value: str) -> tuple[str, str | None, str | None]:
    url, _, fragment = value.partition('#')
    if url.startswith('git+'):
        url = url[4:]

    ref: str | None = None
    parts = urlsplit(url)
    if parts.scheme and parts.netloc:
        if '@' in parts.path:
            path, separator, ref_value = parts.path.rpartition('@')
            if separator:
                url = urlunsplit(parts._replace(path=path))
                ref = unquote(ref_value)
    elif ':' in url:
        prefix, _, path = url.partition(':')
        if '@' in path:
            path, _, ref_value = path.rpartition('@')
            url = f'{prefix}:{path}'
            ref = unquote(ref_value)

    if ref == '':
        raise ValueError('The Git ref after "@" must not be empty.')

    query = parse_qs(fragment, keep_blank_values=True)
    subdirectories = query.get('subdirectory', [])
    if len(subdirectories) > 1:
        raise ValueError('The Git URL may specify only one "subdirectory".')
    subdirectory = subdirectories[0] if subdirectories else None
    if subdirectory is not None:
        subdir_path = PurePosixPath(subdirectory)
        if subdir_path.is_absolute() or '..' in subdir_path.parts:
            raise ValueError('The Git URL subdirectory must stay inside the repository.')

    return url, ref, subdirectory


def _default_checkout_directory(repository_url: str) -> Path:
    parts = urlsplit(repository_url)
    repository_path = parts.path
    if not repository_path and ':' in repository_url:
        repository_path = repository_url.partition(':')[2]

    name = unquote(PurePosixPath(repository_path).name)
    if name.endswith('.git'):
        name = name[:-4]
    if not name or name in {'.', '..'}:
        raise ValueError(f'Could not determine a checkout directory from {repository_url!r}.')
    return Path(name)


def _run_git(arguments: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(arguments, text=True, capture_output=True, check=False)


def _report_git_output(result: subprocess.CompletedProcess[str]) -> None:
    if result.stdout:
        typer.echo(result.stdout, nl=not result.stdout.endswith('\n'))
    if result.stderr:
        typer.echo(result.stderr, err=True, nl=not result.stderr.endswith('\n'))


@app.command(
    'clone',
    help='Clone a Git repository, optionally selecting a ref or subdirectory.',
    context_settings={'allow_extra_args': True, 'ignore_unknown_options': True},
)
def clone_command(
    ctx: typer.Context,
    repository: str = typer.Argument(help='Git URL; pip-style git+ URLs are supported.'),
) -> None:
    try:
        clone_url, ref, subdirectory = _parse_repository_url(repository)
        checkout = _default_checkout_directory(clone_url)
    except ValueError as error:
        logger.error('%s', error)
        raise typer.Exit(1) from error

    git = shutil.which('git')
    if git is None:
        logger.error('Git is required to clone repositories, but was not found on PATH.')
        raise typer.Exit(1)

    try:
        clone_result = _run_git([git, 'clone', *ctx.args, clone_url])
    except OSError as error:
        logger.error('Could not run git clone: %s', error)
        raise typer.Exit(1) from error
    _report_git_output(clone_result)
    if clone_result.returncode:
        logger.error('git clone failed with exit code %s.', clone_result.returncode)
        raise typer.Exit(clone_result.returncode)

    if ref is not None:
        try:
            checkout_result = _run_git([git, '-C', str(checkout), 'checkout', ref])
        except OSError as error:
            logger.error('Could not check out Git ref %r: %s', ref, error)
            raise typer.Exit(1) from error
        _report_git_output(checkout_result)
        if checkout_result.returncode:
            logger.error(
                'Checking out Git ref %r failed with exit code %s.',
                ref,
                checkout_result.returncode,
            )
            raise typer.Exit(checkout_result.returncode)

    if subdirectory is not None:
        project_directory = checkout.joinpath(*PurePosixPath(subdirectory).parts)
        if not project_directory.is_dir():
            logger.error('Repository subdirectory does not exist: %s', project_directory)
            raise typer.Exit(1)
        logger.info('Repository subdirectory: %s', project_directory)
    else:
        logger.info('Cloned repository into %s', checkout)
