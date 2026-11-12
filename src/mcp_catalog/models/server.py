"""Pydantic models for server manifests.

The models describe everything the Docker MCP catalog (``docker mcp`` gateway and
the Docker MCP registry) can express for a server entry, so the generated catalog
documents and image labels are complete. Field documentation is exported into the
JSON Schema as ``description`` entries.
"""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import PurePosixPath
from typing import Annotated, Any, Literal, Union

from pydantic import (
    BaseModel,
    ConfigDict,
    DirectoryPath,
    Field,
    FilePath,
    HttpUrl,
    field_validator,
    model_validator,
)

from ..expansion import expand_environment

ENV_NAME_PATTERN = r'^[A-Za-z_][A-Za-z0-9_]*$'
SECRET_NAME_PATTERN = r'^[A-Za-z0-9_-]+\.[A-Za-z0-9._-]+$'
TEMPLATE_REFERENCE = re.compile(r'\{\{\s*([^.}|\s]+)\.')


def _expand_url(value: Any) -> Any:
    return expand_environment(str(value)) if value is not None else value


class SourceModel(BaseModel):
    """Git repository checkout used as the Docker build context."""

    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)

    repository: HttpUrl = Field(
        description='HTTP(S) clone URL of the Git repository. Environment variables are expanded.'
    )
    revision: str = Field(
        ...,
        pattern=r'^[a-fA-F0-9]{40}$',
        description='Full 40-character commit SHA that is checked out and built.',
    )
    context: str = Field(
        default='.',
        description='Build context directory relative to the repository root.',
    )
    dockerfile: str = Field(
        default='Dockerfile',
        description='Dockerfile path relative to the build context.',
    )

    @field_validator('repository', mode='before')
    @classmethod
    def _expand_repository_url(cls, value: str) -> str:
        return expand_environment(str(value))

    @field_validator('context', 'dockerfile')
    @classmethod
    def _ensure_relative_paths(cls, value: str) -> str:
        value = expand_environment(value)
        path = PurePosixPath(value)
        if not value or path.is_absolute() or '\\' in value:
            raise ValueError('Paths must be relative to the repository root.')
        if '..' in path.parts:
            raise ValueError('Traversal outside the repository root is not allowed.')
        return path.as_posix()


class LocalSourceModel(BaseModel):
    """Build context maintained next to the manifest instead of in an upstream repository."""

    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)

    context: DirectoryPath = Field(
        description=(
            'Existing build context directory. Relative paths resolve from the manifest '
            'directory; $GIT_BASE, $CWD and environment variables are expanded.'
        )
    )
    dockerfile: FilePath = Field(
        description='Existing Dockerfile inside the context; relative paths resolve from it.'
    )

    @model_validator(mode='after')
    def _ensure_dockerfile_is_in_context(self) -> 'LocalSourceModel':
        if not self.dockerfile.resolve().is_relative_to(self.context.resolve()):
            raise ValueError('The Dockerfile must be inside the local build context.')
        return self


GitSourceModel = SourceModel


class BuildOptions(BaseModel):
    """Docker Buildx options for a build server."""

    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)

    platforms: list[str] = Field(
        default_factory=lambda: ['linux/amd64'],
        description='Target platforms passed to docker buildx build --platform.',
    )
    args: dict[str, str] = Field(
        default_factory=dict,
        description='Build arguments (--build-arg). Never put credentials here.',
    )


class RemoteEndpoint(BaseModel):
    """Hosted MCP endpoint reached over HTTP."""

    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)

    url: HttpUrl = Field(
        description='HTTP(S) URL of the remote MCP endpoint. Environment variables are expanded.'
    )
    transport_type: Literal['streamable-http', 'sse'] = Field(
        default='streamable-http',
        description='MCP transport used by the endpoint (Docker catalog remote.transport_type).',
    )
    headers: dict[str, str] = Field(
        default_factory=dict,
        description=(
            'Static HTTP headers sent with every request. Values may reference configuration '
            'with {{server-name.property}} templates.'
        ),
    )

    @field_validator('url', mode='before')
    @classmethod
    def _expand_url(cls, value: str) -> str:
        return expand_environment(str(value))


class ToolItems(BaseModel):
    """Element schema of an array-typed tool argument."""

    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)

    type: str = Field(description='JSON Schema type of each array element.')


class ToolArgument(BaseModel):
    """Argument accepted by a tool (Docker catalog tools[].arguments[])."""

    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)

    name: str = Field(min_length=1, description='Argument name.')
    type: str = Field(
        default='string',
        description='JSON Schema type such as string, number, boolean, array or object.',
    )
    desc: str = Field(default='', description='Human-readable description of the argument.')
    optional: bool = Field(default=False, description='Whether the argument may be omitted.')
    items: ToolItems | None = Field(
        default=None, description='Element schema when the argument type is array.'
    )


class ToolAnnotations(BaseModel):
    """MCP tool annotations advertised in the catalog (behavioural hints)."""

    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)

    title: str | None = Field(default=None, description='Human-readable tool title.')
    read_only_hint: bool | None = Field(
        default=None, description='The tool only reads data and does not modify state.'
    )
    destructive_hint: bool | None = Field(
        default=None, description='The tool may perform destructive updates.'
    )
    idempotent_hint: bool | None = Field(
        default=None, description='Repeated calls with the same arguments have no extra effect.'
    )
    open_world_hint: bool | None = Field(
        default=None, description='The tool interacts with external systems.'
    )


class ToolModel(BaseModel):
    """Tool advertised by the server for catalog discovery and documentation.

    Docker's registry generates this list by running the server or from a tools.json
    file; this catalog cannot run servers during generation, so the list is declared
    in the manifest. The gateway still discovers tools at runtime.
    """

    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)

    name: str = Field(min_length=1, description='Tool name, unique within the server.')
    description: str = Field(default='', description='What the tool does.')
    arguments: list[ToolArgument] | None = Field(
        default=None, description='Argument definitions shown in the catalog.'
    )
    annotations: ToolAnnotations | None = Field(
        default=None, description='Behavioural hints for the tool.'
    )


class SecretModel(BaseModel):
    """Secret injected by the Docker MCP gateway as an environment variable.

    The secret value itself is never part of the catalog; users store it with
    ``docker mcp secret set``.
    """

    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)

    name: str = Field(
        pattern=SECRET_NAME_PATTERN,
        description='Secret identifier in prefix.name form, usually <server-name>.<key>.',
    )
    env: str = Field(
        pattern=ENV_NAME_PATTERN,
        description='Environment variable that receives the secret value.',
    )
    example: str = Field(default='', description='Example value shown in configuration UIs.')
    description: str = Field(
        default='', description='Help text explaining how to obtain the secret.'
    )
    required: bool = Field(default=False, description='Whether the secret must be configured.')


class EnvModel(BaseModel):
    """Static environment variable set in the server container."""

    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)

    name: str = Field(pattern=ENV_NAME_PATTERN, description='Environment variable name.')
    value: str = Field(
        description=(
            'Value. May reference user configuration with {{server-name.property}} templates.'
        )
    )


class RequirementSet(BaseModel):
    """Alternative set of required configuration properties (anyOf / oneOf)."""

    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)

    required: list[str] = Field(description='Property names that must be provided together.')


class ConfigModel(BaseModel):
    """User-configurable settings schema (Docker catalog ``config[]`` object).

    Properties are JSON Schema fragments and are referenced from env values, command
    arguments, volumes and headers with ``{{server-name.property}}`` templates.
    """

    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)

    name: str | None = Field(
        default=None,
        description='Configuration object name; defaults to the server name.',
    )
    description: str = Field(description='Explains what these settings configure.')
    type: Literal['object'] = Field(default='object', description='Always object.')
    properties: dict[str, dict[str, Any]] = Field(
        description='Property name to JSON Schema (type, description, default, items, enum...).'
    )
    required: list[str] = Field(
        default_factory=list, description='Properties the user must provide.'
    )
    any_of: list[RequirementSet] = Field(
        default_factory=list, description='The user must satisfy at least one requirement set.'
    )
    one_of: list[RequirementSet] = Field(
        default_factory=list, description='The user must satisfy exactly one requirement set.'
    )

    @model_validator(mode='after')
    def _ensure_properties_have_types(self) -> 'ConfigModel':
        for property_name, schema in self.properties.items():
            if not schema.get('type'):
                raise ValueError(f'Configuration property {property_name!r} needs a type.')
        for property_name in self.required:
            if property_name not in self.properties:
                raise ValueError(f'Required property {property_name!r} is not defined.')
        return self


class OAuthProvider(BaseModel):
    """OAuth provider whose token the gateway injects as an environment variable."""

    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)

    provider: str = Field(min_length=1, description='Provider identifier such as github.')
    secret: str = Field(
        pattern=SECRET_NAME_PATTERN,
        description='Secret name that stores the token, usually <server-name>.<key>.',
    )
    env: str = Field(pattern=ENV_NAME_PATTERN, description='Environment variable for the token.')


class OAuthModel(BaseModel):
    """OAuth configuration for servers that authenticate users."""

    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)

    providers: list[OAuthProvider] = Field(min_length=1, description='Supported OAuth providers.')
    scopes: list[str] = Field(default_factory=list, description='OAuth scopes to request.')


class MetadataModel(BaseModel):
    """Descriptive metadata used for categorisation in catalog UIs.

    Pull and star counters are computed by Docker Hub and cannot be declared here.
    """

    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)

    category: str | None = Field(
        default=None, description='Category such as devops, database or productivity.'
    )
    tags: list[str] = Field(default_factory=list, description='Search tags.')
    license: str | None = Field(
        default=None, description='SPDX identifier or license name of the server software.'
    )
    owner: str | None = Field(
        default=None, description='Maintainer or organisation owning the server.'
    )


class RuntimeOptions(BaseModel):
    """Container runtime settings applied by the Docker MCP gateway.

    These shape how the container runs and are therefore only read from the catalog,
    never from image labels.
    """

    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)

    command: list[str] = Field(
        default_factory=list,
        description='Arguments appended to the image entrypoint; may use templates.',
    )
    volumes: list[str] = Field(
        default_factory=list,
        description='Volume mounts as host:container[:ro|:rw]; host paths may use templates.',
    )
    user: str | None = Field(default=None, description='User the container runs as (uid:gid).')
    long_lived: bool = Field(
        default=False, description='Keep the container running instead of starting on demand.'
    )
    disable_network: bool = Field(default=False, description='Disable all network access.')
    allow_hosts: list[str] = Field(
        default_factory=list, description='Allowed outbound host:port targets.'
    )
    extra_hosts: list[str] = Field(
        default_factory=list, description='Additional /etc/hosts entries as host:ip.'
    )
    env: list[EnvModel] = Field(
        default_factory=list, description='Static environment variables for the container.'
    )


class ServerBase(BaseModel):
    """Fields shared by every server kind."""

    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)

    schema_version: Literal[1] = Field(description='Manifest schema version; must be 1.')
    name: str = Field(
        pattern=r'^[a-z0-9]+(?:-[a-z0-9]+)*$',
        description='Unique lowercase server name; also the catalog registry key.',
    )
    kind: str = Field(description='Server kind: build, image or remote.')
    title: str = Field(min_length=1, description='Human-readable display name.')
    description: str = Field(min_length=1, description='Short description of the server.')
    enabled: bool = Field(default=True, description='Disabled servers are excluded from output.')
    icon: HttpUrl | None = Field(
        default=None, description='URL of a small PNG, SVG or favicon logo (max 512x512).'
    )
    readme: HttpUrl | None = Field(default=None, description='URL of the server documentation.')
    upstream: HttpUrl | None = Field(
        default=None,
        description=(
            'URL of the upstream project. Defaults to the Git source repository for build '
            'servers; set it when the image wraps a project hosted elsewhere.'
        ),
    )
    date_added: datetime | None = Field(
        default=None,
        description='When the server was added to the catalog (RFC 3339). Declared, not computed.',
    )
    metadata: MetadataModel = Field(
        default_factory=MetadataModel, description='Category, tags, license and owner.'
    )
    tools: list[ToolModel] = Field(
        default_factory=list, description='Tools advertised in the catalog, declared inline.'
    )
    tools_file: FilePath | None = Field(
        default=None,
        description=(
            'JSON or YAML file containing the tools list instead of declaring it inline. '
            'Relative paths resolve from the manifest directory; $GIT_BASE, $CWD and '
            'environment variables are expanded. Mutually exclusive with tools.'
        ),
    )
    secrets: list[SecretModel] = Field(
        default_factory=list, description='Secrets the gateway injects at start-up.'
    )
    config: list[ConfigModel] = Field(
        default_factory=list, description='User-configurable settings schemas.'
    )
    oauth: OAuthModel | None = Field(default=None, description='OAuth providers and scopes.')
    prefix: str | None = Field(
        default=None, description='Prefix the gateway prepends to tool names.'
    )

    @field_validator('icon', 'readme', 'upstream', mode='before')
    @classmethod
    def _expand_optional_urls(cls, value: Any) -> Any:
        return _expand_url(value)

    @field_validator('name')
    @classmethod
    def _disallow_catalog_name(cls, value: str) -> str:
        if value == 'catalog':
            raise ValueError('The reserved name "catalog" is not allowed for server definitions.')
        return value

    @model_validator(mode='after')
    def _tools_are_inline_or_from_file(self) -> 'ServerBase':
        if self.tools and self.tools_file is not None:
            raise ValueError('Declare tools either inline or in tools_file, not both.')
        return self

    @model_validator(mode='after')
    def _default_config_names(self) -> 'ServerBase':
        for entry in self.config:
            if entry.name is None:
                entry.name = self.name
        return self

    @model_validator(mode='after')
    def _validate_template_references(self) -> 'ServerBase':
        allowed = {entry.name for entry in self.config if entry.name is not None} | {self.name}
        for value in self.templated_values():
            for match in TEMPLATE_REFERENCE.finditer(value):
                if match.group(1) not in allowed:
                    raise ValueError(
                        f'Template {value!r} must reference {self.name!r} configuration.'
                    )
        return self

    def templated_values(self) -> list[str]:
        """Return the values that are checked for {{prefix.property}} references."""
        return []


class ContainerServer(ServerBase):
    """Fields shared by servers that run as containers."""

    runtime: RuntimeOptions = Field(
        default_factory=RuntimeOptions, description='Container runtime settings.'
    )

    def templated_values(self) -> list[str]:
        runtime = self.runtime
        return [
            *(entry.value for entry in runtime.env),
            *runtime.command,
            *runtime.volumes,
            *([runtime.user] if runtime.user else []),
        ]


class BuildServer(ContainerServer):
    """Server image built by this catalog from a Git checkout or a local context."""

    kind: Literal['build'] = Field(description='Built from source by this catalog.')
    source: SourceModel | LocalSourceModel = Field(description='Git or local build source.')
    build: BuildOptions = Field(description='Buildx platforms and build arguments.')


class ImageServer(ContainerServer):
    """Server distributed as a prebuilt, digest-pinned image."""

    kind: Literal['image'] = Field(description='Uses an existing image.')
    image: str = Field(description='Digest-pinned image reference (name@sha256:...).')

    @field_validator('image')
    @classmethod
    def _ensure_digest_pin(cls, value: str) -> str:
        if '@sha256:' not in value:
            raise ValueError('Image references must be digest-pinned using @sha256:...')
        if len(value.split('@sha256:')[-1]) != 64:
            raise ValueError('A digest-pinned image must include a 64-character sha256 digest.')
        return value


class RemoteServer(ServerBase):
    """MCP server hosted elsewhere and reached over HTTP."""

    kind: Literal['remote'] = Field(description='Hosted MCP endpoint.')
    remote: RemoteEndpoint = Field(description='Endpoint URL, transport and headers.')

    def templated_values(self) -> list[str]:
        return list(self.remote.headers.values())


ServerModel = Annotated[Union[BuildServer, ImageServer, RemoteServer], Field(discriminator='kind')]
