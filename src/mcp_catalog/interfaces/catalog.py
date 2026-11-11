from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import TypeAdapter

from ..expansion import expand_environment, git_base_directory
from ..io.yaml import load_yaml_file
from ..logging_config import get_logger
from ..models import CatalogModel, ServerModel

SERVER_ADAPTER = TypeAdapter(ServerModel)
logger = get_logger(__name__)


def _path_variables() -> dict[str, str]:
    cwd = Path.cwd().resolve()
    variables = {'CWD': str(cwd)}
    git_base = git_base_directory(cwd)
    if git_base is not None:
        variables['GIT_BASE'] = str(git_base)
    return variables


def validate_document(document: dict[str, Any]) -> CatalogModel | ServerModel:
    if 'kind' in document:
        return validate_server_document(document, base_dir=Path.cwd())
    return validate_catalog_document(document, base_dir=Path.cwd())


def validate_manifest(path: str | Path) -> CatalogModel | ServerModel:
    logger.debug('Validating manifest %s', path)
    document = load_yaml_file(path)
    if not isinstance(document, dict):
        raise ValueError(f'{path} must contain a YAML mapping.')
    if 'kind' in document:
        return validate_server_document(document, base_dir=Path(path).parent)
    return load_catalog(path)


def load_server_manifest(path: str | Path) -> ServerModel:
    return validate_server_document(load_yaml_file(path), base_dir=Path(path).parent)


def validate_server_document(
    document: Any,
    *,
    base_dir: str | Path,
) -> ServerModel:
    if not isinstance(document, dict):
        raise ValueError('A server manifest must contain a YAML mapping.')
    source = document.get('source')
    if document.get('kind') == 'build' and isinstance(source, dict) and 'repository' not in source:
        normalized_document = dict(document)
        normalized_source = dict(source)
        variables = _path_variables()
        context_value = expand_environment(
            str(normalized_source.get('context', '.')), variables=variables
        )
        context = Path(context_value).expanduser()
        if not context.is_absolute():
            context = Path(base_dir) / context
        context = context.resolve()
        dockerfile_value = expand_environment(
            str(normalized_source.get('dockerfile', 'Dockerfile')),
            variables=variables,
        )
        dockerfile = Path(dockerfile_value).expanduser()
        if not dockerfile.is_absolute():
            dockerfile = context / dockerfile
        normalized_source['context'] = str(context)
        normalized_source['dockerfile'] = str(dockerfile.resolve())
        normalized_document['source'] = normalized_source
        document = normalized_document
    return SERVER_ADAPTER.validate_python(document)


def validate_catalog_document(
    document: Any,
    *,
    base_dir: str | Path,
) -> CatalogModel:
    if not isinstance(document, dict):
        raise ValueError('A catalog manifest must contain a YAML mapping.')
    normalized_document = dict(document)
    if 'servers' in normalized_document:
        normalized_document['servers'] = [
            validate_server_document(server, base_dir=base_dir).model_dump(mode='json')
            for server in normalized_document['servers']
        ]
    return CatalogModel.model_validate(normalized_document)


def load_catalog(path: str | Path) -> CatalogModel:
    """Load a catalog and, when configured, its sorted server manifest files."""
    catalog_path = Path(path)
    logger.debug('Loading catalog manifest %s', catalog_path)
    document = load_yaml_file(catalog_path)
    if not isinstance(document, dict):
        raise ValueError(f'{catalog_path} must contain a YAML mapping.')

    if 'servers' not in document:
        servers_dir_value = expand_environment(
            str(document.get('servers_dir', 'servers')),
            variables=_path_variables(),
        )
        servers_dir = Path(servers_dir_value).expanduser()
        if not servers_dir.is_absolute():
            servers_dir = catalog_path.parent / servers_dir
        servers_dir = servers_dir.resolve()
        if not servers_dir.is_dir():
            raise FileNotFoundError(f'Servers directory does not exist: {servers_dir}')
        servers = []
        for manifest_path in sorted((*servers_dir.glob('*.yaml'), *servers_dir.glob('*.yml'))):
            logger.debug('Loading server manifest %s', manifest_path)
            server_document = load_yaml_file(manifest_path)
            server = validate_server_document(server_document, base_dir=manifest_path.parent)
            if manifest_path.stem != server.name:
                raise ValueError(
                    f'{manifest_path}: file name must match server name {server.name!r}.'
                )
            servers.append(server.model_dump(mode='json'))
        document['servers'] = servers
    else:
        document['servers'] = [
            validate_server_document(server, base_dir=catalog_path.parent).model_dump(mode='json')
            for server in document['servers']
        ]
    return validate_catalog_document(document, base_dir=catalog_path.parent)


def find_server(catalog: CatalogModel, name: str) -> ServerModel:
    for server in catalog.servers:
        if server.name == name:
            return server
    raise ValueError(f'Server not found: {name}')


def server_document(server: ServerModel) -> dict[str, Any]:
    return server.model_dump(mode='json', exclude_unset=False)


def server_manifest_path(catalog_path: Path, document: dict[str, Any], name: str) -> Path:
    if 'servers' in document:
        return catalog_path
    return catalog_path.parent / document.get('servers_dir', 'servers') / f'{name}.yaml'
