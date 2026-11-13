"""Draft a server manifest from an upstream Git repository.

The scaffold reads a shallow checkout as untrusted data: it parses files but never
executes anything from the repository. Every value is reported with where it came from,
and every field that could not be found is listed with what is expected and whether the
manifest needs it, so an agent knows exactly what is left to fill in.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import tempfile
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from .servers import SERVER_SCHEMA_KIND

ENV_FILE_NAMES = (
    '.env.example',
    '.env.sample',
    '.env.template',
    '.env.dist',
    'example.env',
    'env.example',
)
SECRET_PATTERN = re.compile(r'(KEY|TOKEN|SECRET|PASSWORD|PASSWD|CREDENTIAL|PRIVATE)', re.I)
IGNORED_DIRECTORIES = {'.git', 'node_modules', 'venv', '.venv', 'tests', 'test', 'examples'}
README_NAMES = ('README.md', 'README.rst', 'README.txt', 'README')
CLONE_TIMEOUT_SECONDS = 300

# (path, required, expectation, hint) for every field a complete manifest should consider.
EXPECTATIONS: tuple[tuple[str, bool, str, str], ...] = (
    ('name', True, 'lowercase a-z0-9 with hyphens', 'Derived from owner and repository.'),
    ('title', True, 'human-readable display name', 'Usually the README heading.'),
    (
        'description',
        True,
        'one or two sentences describing what the server does',
        'Read the README introduction and write a short summary.',
    ),
    (
        'source.dockerfile',
        True,
        'path of a Dockerfile that starts the MCP server over stdio',
        'The repository has no Dockerfile: write one in servers/<name>/ and use a local source.',
    ),
    (
        'icon',
        False,
        'URL of a PNG/SVG/favicon logo, at most 512x512',
        'For example https://www.google.com/s2/favicons?domain=<project domain>&sz=64',
    ),
    (
        'metadata.category',
        False,
        'a short category such as web, database, devops, memory, productivity',
        'Choose the closest category used by other catalog entries (see server_list).',
    ),
    ('metadata.tags', False, 'a few search tags', 'Derive from the README or keywords.'),
    ('metadata.license', False, 'SPDX identifier such as MIT or Apache-2.0', 'See LICENSE.'),
    (
        'tools',
        False,
        'tools advertised by the server',
        'Cannot be read statically; build the image and run `mcp-catalog tools capture`.',
    ),
    (
        'secrets',
        False,
        'credentials the server needs, one entry per environment variable',
        'List API keys and tokens from the README; mark required ones with required: true.',
    ),
)


@dataclass
class _EnvVar:
    name: str
    default: str | None
    description: str
    source: str


def _slug(value: str) -> str:
    return re.sub(r'[^a-z0-9]+', '-', value.lower()).strip('-')


def _repository_identity(repository: str) -> tuple[str, str]:
    parts = [part for part in urlsplit(repository).path.split('/') if part]
    if len(parts) < 2:
        raise ValueError('Repository URL must look like https://host/owner/repo.')
    return parts[0], parts[1].removesuffix('.git')


def _read(path: Path) -> str | None:
    try:
        return path.read_text(encoding='utf-8', errors='replace')
    except OSError:
        return None


def _project_metadata(checkout: Path) -> dict[str, Any]:
    """Description, license, keywords and display name from common project files."""
    found: dict[str, tuple[Any, str]] = {}

    pyproject = _read(checkout / 'pyproject.toml')
    if pyproject is not None:
        try:
            project = tomllib.loads(pyproject).get('project', {})
        except tomllib.TOMLDecodeError:
            project = {}
        if isinstance(project.get('description'), str):
            found['description'] = (project['description'], 'pyproject.toml project.description')
        license_value = project.get('license')
        if isinstance(license_value, dict):
            license_value = license_value.get('text')
        if isinstance(license_value, str) and len(license_value) < 40:
            found['license'] = (license_value, 'pyproject.toml project.license')
        if isinstance(project.get('keywords'), list):
            found['keywords'] = (project['keywords'], 'pyproject.toml project.keywords')

    package_json = _read(checkout / 'package.json')
    if package_json is not None:
        try:
            package = json.loads(package_json)
        except json.JSONDecodeError:
            package = {}
        if isinstance(package, dict):
            if isinstance(package.get('description'), str):
                found.setdefault('description', (package['description'], 'package.json'))
            if isinstance(package.get('license'), str):
                found.setdefault('license', (package['license'], 'package.json'))
            if isinstance(package.get('keywords'), list):
                found.setdefault('keywords', (package['keywords'], 'package.json'))

    cargo = _read(checkout / 'Cargo.toml')
    if cargo is not None:
        try:
            package = tomllib.loads(cargo).get('package', {})
        except tomllib.TOMLDecodeError:
            package = {}
        if isinstance(package.get('description'), str):
            found.setdefault('description', (package['description'], 'Cargo.toml'))
        if isinstance(package.get('license'), str):
            found.setdefault('license', (package['license'], 'Cargo.toml'))

    if 'license' not in found:
        for name in ('LICENSE', 'LICENSE.md', 'LICENSE.txt', 'COPYING'):
            text = _read(checkout / name)
            if text is None:
                continue
            head = text[:2000]
            if 'MIT License' in head:
                found['license'] = ('MIT', f'{name} (recognised text)')
            elif 'Apache License' in head and '2.0' in head:
                found['license'] = ('Apache-2.0', f'{name} (recognised text)')
            elif 'GNU AFFERO GENERAL PUBLIC LICENSE' in head.upper():
                found['license'] = ('AGPL-3.0', f'{name} (recognised text)')
            elif 'GNU GENERAL PUBLIC LICENSE' in head.upper() and 'Version 3' in head:
                found['license'] = ('GPL-3.0', f'{name} (recognised text)')
            break
    return found


def _readme(checkout: Path) -> tuple[str | None, str | None]:
    for name in README_NAMES:
        text = _read(checkout / name)
        if text is not None:
            return name, text
    return None, None


def _readme_title_and_summary(text: str) -> tuple[str | None, str | None]:
    title = None
    summary = None
    for line in text.splitlines():
        stripped = line.strip()
        if title is None and stripped.startswith('# '):
            title = stripped[2:].strip()
            continue
        if (
            summary is None
            and stripped
            and not re.match(r'^(#|\[!\[|!\[|<|\||```|---|===)', stripped)
        ):
            summary = re.sub(r'\s+', ' ', re.sub(r'\[([^\]]+)\]\([^)]*\)', r'\1', stripped))[:300]
        if title and summary:
            break
    return title, summary


def _find_dockerfile(checkout: Path) -> tuple[Path | None, list[Path]]:
    candidates: list[Path] = []
    for path in sorted(checkout.rglob('Dockerfile*')):
        relative = path.relative_to(checkout)
        if path.is_file() and not (set(relative.parts[:-1]) & IGNORED_DIRECTORIES):
            if len(relative.parts) <= 4:
                candidates.append(relative)
    candidates.sort(key=lambda item: (len(item.parts), item.name != 'Dockerfile', str(item)))
    return (candidates[0] if candidates else None), candidates[1:]


def _parse_env_file(text: str, source: str) -> list[_EnvVar]:
    variables: list[_EnvVar] = []
    comments: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith('#'):
            comment = stripped.lstrip('# ').strip()
            if re.match(r'^[A-Z][A-Z0-9_]*=', comment):  # commented-out variable
                name, _, value = comment.partition('=')
                variables.append(
                    _EnvVar(name, value.strip('\'" ') or None, ' '.join(comments), source)
                )
            else:
                comments.append(comment)
            continue
        match = re.match(r'^(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)$', stripped)
        if match:
            value = match.group(2).split(' #')[0].strip('\'" ')
            variables.append(_EnvVar(match.group(1), value or None, ' '.join(comments), source))
        comments = []
    return variables


def _parse_readme_env_table(text: str) -> list[_EnvVar]:
    """Rows such as ``| `NAME` | default | purpose |`` under any heading."""
    variables: list[_EnvVar] = []
    for line in text.splitlines():
        cells = [cell.strip() for cell in line.strip().strip('|').split('|')]
        if len(cells) < 2 or not line.strip().startswith('|'):
            continue
        match = re.fullmatch(r'`([A-Z][A-Z0-9_]{2,})`', cells[0])
        if not match:
            continue
        default = cells[1].strip('`* ') if len(cells) > 2 else ''
        if not default or default.lower().strip('()*_ ') in {
            'unset',
            'none',
            'n/a',
            '-',
            'required',
        }:
            default = ''
        if '…' in default or '...' in default:  # truncated in the table: not a usable default
            default = ''
        description = re.sub(r'[*`]', '', cells[-1]).strip()
        variables.append(_EnvVar(match.group(1), default or None, description, 'README table'))
    return variables


def _environment_variables(checkout: Path, readme: str | None) -> list[_EnvVar]:
    variables: dict[str, _EnvVar] = {}
    for name in ENV_FILE_NAMES:
        text = _read(checkout / name)
        if text is not None:
            for variable in _parse_env_file(text, name):
                variables.setdefault(variable.name, variable)
    if readme is not None:
        for variable in _parse_readme_env_table(readme):
            existing = variables.get(variable.name)
            if existing is None:
                variables[variable.name] = variable
            elif not existing.description:
                existing.description = variable.description
    return list(variables.values())


def _schema_type(default: str | None) -> str:
    if default is not None and default.lower() in {'true', 'false'}:
        return 'boolean'
    if default is not None and re.fullmatch(r'-?\d+', default):
        return 'integer'
    return 'string'


def _typed_default(default: str, schema_type: str) -> Any:
    if schema_type == 'boolean':
        return default.lower() == 'true'
    if schema_type == 'integer':
        return int(default)
    return default


def _configuration(
    name: str, variables: list[_EnvVar]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, str]]]:
    """Split variables into secrets, config properties with runtime.env, and env wiring."""
    secrets: list[dict[str, Any]] = []
    properties: dict[str, dict[str, Any]] = {}
    env: list[dict[str, str]] = []
    for variable in variables:
        description = variable.description or f'Sets {variable.name}.'
        if SECRET_PATTERN.search(variable.name) and not variable.name.endswith(('_URL', '_URI')):
            secrets.append(
                {
                    'name': f'{name}.{variable.name.lower()}',
                    'env': variable.name,
                    'example': f'<{variable.name}>',
                    'description': description,
                    'required': False,
                }
            )
            continue
        key = variable.name.lower()
        schema_type = _schema_type(variable.default)
        schema: dict[str, Any] = {'type': schema_type, 'description': description}
        template = f'{{{{{name}.{key}'
        if variable.default is not None:
            schema['default'] = _typed_default(variable.default, schema_type)
            template += f'|or:{variable.default}'
        properties[key] = schema
        env.append({'name': variable.name, 'value': template + '}}'})
    config = (
        [{'description': 'Settings found in the upstream repository.', 'properties': properties}]
        if properties
        else []
    )
    return secrets, config, env


def scaffold_from_checkout(
    checkout: str | Path,
    repository: str,
    revision: str,
    *,
    name: str | None = None,
) -> dict[str, Any]:
    """Draft a build-server manifest from a checked-out repository.

    Returns ``manifest`` (usable as ``fields`` for ``server_add``), ``found`` (field to
    where it was read), ``missing`` (field, required, expected, hint) and ``notes``.
    """
    root = Path(checkout)
    owner, repo = _repository_identity(repository)
    server_name = name or _slug(f'{owner}-{repo}')
    found: dict[str, str] = {}
    notes: list[str] = []

    manifest: dict[str, Any] = {
        'schema_version': 1,
        'schema_kind': SERVER_SCHEMA_KIND,
        'name': server_name,
        'kind': 'build',
        'enabled': True,
    }
    found['name'] = 'repository owner and name'

    project = _project_metadata(root)
    readme_name, readme = _readme(root)
    readme_title, readme_summary = (
        _readme_title_and_summary(readme) if readme is not None else (None, None)
    )

    manifest['title'] = readme_title or repo.replace('-', ' ').replace('_', ' ').title()
    found['title'] = f'{readme_name} heading' if readme_title else 'repository name'

    if 'description' in project:
        manifest['description'], found['description'] = project['description']
    elif readme_summary:
        manifest['description'] = readme_summary
        found['description'] = f'{readme_name} first paragraph (review wording)'

    base = repository.removesuffix('.git').rstrip('/')
    manifest['upstream'] = base
    found['upstream'] = 'repository URL'
    if readme_name:
        manifest['readme'] = f'{base}/blob/{revision}/{readme_name}'
        found['readme'] = readme_name

    metadata: dict[str, Any] = {'owner': owner}
    found['metadata.owner'] = 'repository owner'
    if 'license' in project:
        metadata['license'], found['metadata.license'] = project['license']
    if 'keywords' in project:
        metadata['tags'], found['metadata.tags'] = project['keywords']
    manifest['metadata'] = metadata

    dockerfile, others = _find_dockerfile(root)
    source: dict[str, Any] = {'repository': repository, 'revision': revision}
    found['source.repository'] = 'repository URL'
    found['source.revision'] = 'checked-out commit'
    if dockerfile is not None:
        context = dockerfile.parent.as_posix()
        source['context'] = context
        source['dockerfile'] = dockerfile.name
        found['source.dockerfile'] = dockerfile.as_posix()
        if context != '.':
            notes.append(
                f'Dockerfile is in {context}/; the build context was set to that directory. '
                'Change source.context to "." and source.dockerfile to the full path if the '
                'Dockerfile copies files from the repository root.'
            )
        if others:
            notes.append(
                'Other Dockerfiles found: ' + ', '.join(path.as_posix() for path in others[:5])
            )
        dockerfile_text = _read(root / dockerfile) or ''
        if re.search(r'^\s*EXPOSE\s', dockerfile_text, re.M):
            notes.append(
                'The Dockerfile exposes a port. The Docker MCP gateway always talks to '
                'containers over stdio, so make sure the default command serves stdio.'
            )
        if re.search(r'^\s*VOLUME\s', dockerfile_text, re.M):
            notes.append('The Dockerfile declares a VOLUME; consider runtime.volumes with config.')
    manifest['source'] = source
    manifest['build'] = {'platforms': ['linux/amd64'], 'args': {}}

    variables = _environment_variables(root, readme)
    if variables:
        secrets, config, env = _configuration(server_name, variables)
        if secrets:
            manifest['secrets'] = secrets
            for secret in secrets:
                found[f'secrets.{secret["env"]}'] = next(
                    v.source for v in variables if v.name == secret['env']
                )
            notes.append(
                'Secrets are marked required: false because requiredness is not machine-readable; '
                'set required: true for credentials the server cannot start without.'
            )
        if config:
            manifest['config'] = config
            manifest['runtime'] = {'env': env}
            found['config'] = 'environment variables in ' + ', '.join(
                sorted({v.source for v in variables})
            )
            if any('|or:' not in entry['value'] for entry in env):
                notes.append(
                    'Config properties without a default pass an empty string when unset, which '
                    'can override the upstream default; add a default or an |or: fallback.'
                )

    missing = [
        {'field': path, 'required': required, 'expected': expected, 'hint': hint}
        for path, required, expected, hint in EXPECTATIONS
        if not _has_value(manifest, path)
    ]
    return {'manifest': manifest, 'found': found, 'missing': missing, 'notes': notes}


def _has_value(document: dict[str, Any], path: str) -> bool:
    current: Any = document
    for key in path.split('.'):
        if not isinstance(current, dict) or key not in current:
            return False
        current = current[key]
    return current not in (None, '', [], {})


def _clone(repository: str, ref: str, directory: Path) -> str:
    parsed = urlsplit(repository)
    if parsed.scheme not in {'http', 'https'} or not parsed.hostname:
        raise ValueError('Repository must be an absolute HTTP(S) URL.')
    command = ['git', 'clone', '--depth', '1', '--quiet']
    if ref != 'HEAD':
        command += ['--branch', ref]
    command += [repository, str(directory)]
    environment = {**os.environ, 'GIT_TERMINAL_PROMPT': '0'}
    subprocess.run(
        command,
        check=True,
        capture_output=True,
        text=True,
        env=environment,
        timeout=CLONE_TIMEOUT_SECONDS,
    )
    result = subprocess.run(
        ['git', '-C', str(directory), 'rev-parse', 'HEAD'],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def scaffold_from_repository(
    repository: str,
    ref: str = 'HEAD',
    *,
    name: str | None = None,
) -> dict[str, Any]:
    """Shallow-clone ``repository`` into a temporary directory and scaffold a manifest."""
    with tempfile.TemporaryDirectory(prefix='mcp-catalog-scaffold-') as temporary:
        checkout = Path(temporary) / 'repository'
        revision = _clone(repository, ref, checkout)
        return scaffold_from_checkout(checkout, repository, revision, name=name)


def scaffold_report(result: dict[str, Any]) -> str:
    """Human-readable summary of what a scaffold found and what is still missing."""
    lines = ['Found:']
    lines += [f'  {field}: {source}' for field, source in result['found'].items()]
    lines.append('Missing (required first):')
    for gap in sorted(result['missing'], key=lambda item: not item['required']):
        level = 'REQUIRED' if gap['required'] else 'optional'
        lines.append(f'  [{level}] {gap["field"]}: {gap["expected"]}. {gap["hint"]}')
    if not result['missing']:
        lines.append('  nothing')
    if result['notes']:
        lines.append('Notes:')
        lines += [f'  - {note}' for note in result['notes']]
    return '\n'.join(lines)
