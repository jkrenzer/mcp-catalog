from __future__ import annotations

import hashlib
import re
from typing import Any

DEFAULT_REGISTRY = 'ghcr.io/jkrenzer/mcp-catalog'


def _coerce_branch_name(branch_name: Any) -> str:
    return '' if branch_name is None else str(branch_name)


def branch_slug(branch_name: Any, *, max_readable_length: int = 40) -> str:
    """Return a normalized branch namespace with a stable hash suffix."""
    raw = _coerce_branch_name(branch_name)
    if raw.lower() == 'main':
        return 'main'

    normalized = re.sub(r'[^a-z0-9-]+', '-', raw.lower()).strip('-')
    readable = (normalized or 'branch')[:max_readable_length].rstrip('-') or 'branch'
    digest = hashlib.sha256(raw.encode('utf-8')).hexdigest()[:12]
    return f'{readable}-{digest}'


def branch_namespace(branch_name: Any) -> str:
    return (
        'main' if _coerce_branch_name(branch_name).lower() == 'main' else branch_slug(branch_name)
    )


def build_image_reference(
    server_name: str, branch_name: Any, server_tag: str, *, registry: str = DEFAULT_REGISTRY
) -> str:
    """Return the GHCR image reference for a built server."""
    slug = branch_namespace(branch_name)
    if slug == 'main':
        return f'{registry}/{server_name}:{server_tag}'
    return f'{registry}/{slug}/{server_name}:{server_tag}'


def catalog_reference(branch_name: Any, *, registry: str = DEFAULT_REGISTRY) -> str:
    """Return the GHCR catalog reference for the requested branch."""
    slug = branch_namespace(branch_name)
    if slug == 'main':
        return f'{registry}/catalog:latest'
    return f'{registry}/{slug}/catalog:latest'


def build_server_tag(
    catalog_commit_sha: str,
    github_run_id: str | int | None = None,
    github_run_attempt: str | int | None = None,
) -> str:
    """Return the immutable build tag used for server image builds."""
    if github_run_id is None and github_run_attempt is None:
        return f'build-{catalog_commit_sha}'
    suffix = ''
    if github_run_id is not None:
        suffix = f'-{github_run_id}'
    if github_run_attempt is not None:
        suffix = f'{suffix}-{github_run_attempt}'
    return f'build-{catalog_commit_sha}{suffix}'


image_reference_for_server = build_image_reference
