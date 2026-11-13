"""Docker MCP catalog entries and OCI image labels derived from server manifests.

The entry shape follows the Docker MCP registry catalog tile (``version: 2``) and the
``docker mcp`` gateway server schema. Image labels follow the OCI image annotation
keys plus the gateway's ``io.docker.server.metadata`` self-describing image label.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pydantic import TypeAdapter

from ..io.yaml import load_yaml_file
from ..models import (
    BuildServer,
    ConfigModel,
    ContainerServer,
    GitSourceModel,
    MetadataModel,
    RemoteServer,
    ServerModel,
    ToolModel,
)

TOOLS_ADAPTER = TypeAdapter(list[ToolModel])
METADATA_LABEL = 'io.docker.server.metadata'
OCI_LABEL_PREFIX = 'org.opencontainers.image.'
METADATA_LABEL_KEYS = (
    'name',
    'type',
    'title',
    'description',
    'icon',
    'readme',
    'tools',
    'config',
    'prefix',
    'metadata',
)


def normalize_description(text: str) -> str:
    """Collapse whitespace so folded YAML descriptions become one line."""
    return ' '.join(text.split())


def format_timestamp(value: datetime) -> str:
    """Render a timestamp as RFC 3339 in UTC, treating naive values as UTC."""
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')


def _optional_url(value: Any) -> str | None:
    return None if value is None else str(value)


def load_tools_file(path: str | Path) -> list[ToolModel]:
    """Load and validate a tools list from a JSON or YAML file."""
    tools_path = Path(path)
    if tools_path.suffix.lower() == '.json':
        document = json.loads(tools_path.read_text(encoding='utf-8'))
    else:
        document = load_yaml_file(tools_path)
    if not isinstance(document, list):
        raise ValueError(f'{tools_path} must contain a list of tools.')
    return TOOLS_ADAPTER.validate_python(document)


def server_tools(server: ServerModel) -> list[ToolModel]:
    """Return the tools declared inline or in the server's tools_file."""
    if server.tools_file is not None:
        return load_tools_file(server.tools_file)
    return list(server.tools)


def _tool_document(tool: ToolModel) -> dict[str, Any]:
    document: dict[str, Any] = {'name': tool.name, 'description': tool.description}
    if tool.arguments is not None:
        document['arguments'] = [
            {
                'name': argument.name,
                'type': argument.type,
                'desc': argument.desc,
                **({'optional': True} if argument.optional else {}),
                **({'items': {'type': argument.items.type}} if argument.items else {}),
            }
            for argument in tool.arguments
        ]
    if tool.annotations is not None:
        annotations = {
            'title': tool.annotations.title,
            'readOnlyHint': tool.annotations.read_only_hint,
            'destructiveHint': tool.annotations.destructive_hint,
            'idempotentHint': tool.annotations.idempotent_hint,
            'openWorldHint': tool.annotations.open_world_hint,
        }
        document['annotations'] = {k: v for k, v in annotations.items() if v is not None}
    return document


def _config_document(config: ConfigModel) -> dict[str, Any]:
    document: dict[str, Any] = {
        'name': config.name,
        'description': config.description,
        'type': config.type,
        'properties': config.properties,
    }
    if config.required:
        document['required'] = list(config.required)
    if config.any_of:
        document['anyOf'] = [{'required': list(item.required)} for item in config.any_of]
    if config.one_of:
        document['oneOf'] = [{'required': list(item.required)} for item in config.one_of]
    return document


def _metadata_document(metadata: MetadataModel) -> dict[str, Any]:
    document: dict[str, Any] = {}
    if metadata.category:
        document['category'] = metadata.category
    if metadata.tags:
        document['tags'] = list(metadata.tags)
    if metadata.license:
        document['license'] = metadata.license
    if metadata.owner:
        document['owner'] = metadata.owner
    return document


def _runtime_document(server: ContainerServer) -> dict[str, Any]:
    runtime = server.runtime
    document: dict[str, Any] = {}
    if runtime.env:
        document['env'] = [{'name': item.name, 'value': item.value} for item in runtime.env]
    if runtime.command:
        document['command'] = list(runtime.command)
    if runtime.volumes:
        document['volumes'] = list(runtime.volumes)
    if runtime.user:
        document['user'] = runtime.user
    if runtime.long_lived:
        document['longLived'] = True
    if runtime.disable_network:
        document['disableNetwork'] = True
    if runtime.allow_hosts:
        document['allowHosts'] = list(runtime.allow_hosts)
    if runtime.extra_hosts:
        document['extraHosts'] = list(runtime.extra_hosts)
    return document


def upstream_url(server: ServerModel) -> str | None:
    """Return the declared upstream project URL, defaulting to the Git source repository."""
    if server.upstream is not None:
        return str(server.upstream)
    if isinstance(server, BuildServer) and isinstance(server.source, GitSourceModel):
        return str(server.source.repository)
    return None


def describe_server(server: ServerModel) -> dict[str, Any]:
    """Return the descriptive part of a catalog entry shared by all server kinds."""
    entry: dict[str, Any] = {
        'name': server.name,
        'title': server.title,
        'description': normalize_description(server.description),
        'type': 'remote' if isinstance(server, RemoteServer) else 'server',
        'icon': _optional_url(server.icon) or '',
        'tools': [_tool_document(tool) for tool in server_tools(server)],
        'prompts': 0,
        'resources': {},
    }
    if server.readme is not None:
        entry['readme'] = str(server.readme)
    if server.date_added is not None:
        entry['dateAdded'] = format_timestamp(server.date_added)
    if (upstream := upstream_url(server)) is not None:
        entry['upstream'] = upstream
    if server.secrets:
        entry['secrets'] = [
            {
                'name': secret.name,
                'env': secret.env,
                'example': secret.example,
                **({'description': secret.description} if secret.description else {}),
                **({'required': True} if secret.required else {}),
            }
            for secret in server.secrets
        ]
    if server.config:
        entry['config'] = [_config_document(config) for config in server.config]
    if server.oauth is not None:
        entry['oauth'] = {
            'providers': [
                {'provider': item.provider, 'secret': item.secret, 'env': item.env}
                for item in server.oauth.providers
            ],
            **({'scopes': list(server.oauth.scopes)} if server.oauth.scopes else {}),
        }
    if metadata := _metadata_document(server.metadata):
        entry['metadata'] = metadata
    if server.prefix:
        entry['prefix'] = server.prefix
    return entry


def docker_server_entry(
    server: ServerModel,
    *,
    image: str | None = None,
    repository: str | None = None,
) -> dict[str, Any]:
    """Return the Docker MCP catalog registry entry for one server.

    ``repository`` is the catalog's own Git repository; it becomes the source link of
    locally built servers.
    """
    entry = describe_server(server)
    entry['ref'] = ''
    entry['source'] = ''
    if isinstance(server, RemoteServer):
        entry['source'] = str(server.remote.url)
        entry['remote'] = {
            'transport_type': server.remote.transport_type,
            'url': str(server.remote.url),
            **({'headers': dict(server.remote.headers)} if server.remote.headers else {}),
        }
        return entry

    entry['image'] = image or getattr(server, 'image', None)
    if not entry['image']:
        raise ValueError(f'An image reference is required for build server {server.name!r}.')
    entry.update(_runtime_document(server))
    if isinstance(server, BuildServer):
        if isinstance(server.source, GitSourceModel):
            entry['source'] = str(server.source.repository)
            entry['ref'] = server.source.revision
        elif repository is not None:
            entry['source'] = repository
    return entry


def image_metadata(server: ServerModel) -> dict[str, Any]:
    """Return the ``io.docker.server.metadata`` document for a server image.

    The gateway parses only descriptive fields from image labels (name, type, title,
    description, icon, readme, env names, tools, config, prefix, metadata); runtime
    settings and secrets are always taken from the catalog.
    """
    entry = describe_server(server)
    document = {key: entry[key] for key in METADATA_LABEL_KEYS if key in entry}
    if isinstance(server, ContainerServer) and server.runtime.env:
        document['env'] = [{'name': item.name} for item in server.runtime.env]
    return document


def image_metadata_label(server: ServerModel) -> str:
    """Serialise the self-describing image metadata as compact, key-sorted JSON."""
    return json.dumps(
        image_metadata(server), ensure_ascii=False, sort_keys=True, separators=(',', ':')
    )


def image_labels(
    server: BuildServer,
    *,
    repository: str | None = None,
    catalog_commit: str | None = None,
) -> dict[str, str]:
    """Return the OCI image labels applied when building a server image.

    Git sources are labelled with their own repository and revision. Local sources
    are labelled with the catalog repository and catalog commit, when known.
    """
    labels = {
        f'{OCI_LABEL_PREFIX}title': server.title,
        f'{OCI_LABEL_PREFIX}description': normalize_description(server.description),
        METADATA_LABEL: image_metadata_label(server),
    }
    if (upstream := upstream_url(server)) is not None:
        labels[f'{OCI_LABEL_PREFIX}url'] = upstream
    if server.readme is not None:
        labels[f'{OCI_LABEL_PREFIX}documentation'] = str(server.readme)
    if server.metadata.license:
        labels[f'{OCI_LABEL_PREFIX}licenses'] = server.metadata.license
    if server.metadata.owner:
        labels[f'{OCI_LABEL_PREFIX}vendor'] = server.metadata.owner
    if isinstance(server.source, GitSourceModel):
        labels[f'{OCI_LABEL_PREFIX}source'] = str(server.source.repository)
        labels[f'{OCI_LABEL_PREFIX}revision'] = server.source.revision
    else:
        if repository is not None:
            labels[f'{OCI_LABEL_PREFIX}source'] = repository
        if catalog_commit:
            labels[f'{OCI_LABEL_PREFIX}revision'] = catalog_commit
    return dict(sorted(labels.items()))


def label_arguments(labels: dict[str, str] | None) -> list[str]:
    """Return ``--label`` arguments for docker buildx build in deterministic order."""
    arguments: list[str] = []
    for name, value in sorted((labels or {}).items()):
        arguments.extend(['--label', f'{name}={value}'])
    return arguments
