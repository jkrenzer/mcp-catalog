"""Compatibility exports for the transport-independent interface workflows."""

from .interfaces.builds import (
    build_plan,
    build_server_image,
    current_commit,
    publish_image,
)
from .interfaces.catalog import SERVER_ADAPTER, load_catalog, load_server_manifest
from .interfaces.docker_catalog import (
    docker_catalog,
    docker_server_entry,
    inspect_publication,
    require_executable,
    write_json,
)
from .interfaces.schema import schema_documents, schema_drift, write_schemas

__all__ = [
    'SERVER_ADAPTER',
    'build_plan',
    'build_server_image',
    'current_commit',
    'docker_catalog',
    'docker_server_entry',
    'inspect_publication',
    'load_catalog',
    'load_server_manifest',
    'publish_image',
    'require_executable',
    'schema_drift',
    'schema_documents',
    'write_json',
    'write_schemas',
]
