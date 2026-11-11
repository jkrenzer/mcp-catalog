from __future__ import annotations

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


class SourceModel(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)

    repository: HttpUrl
    revision: str = Field(..., pattern=r'^[a-fA-F0-9]{40}$')
    context: str = Field(default='.')
    dockerfile: str = Field(default='Dockerfile')

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
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)

    context: DirectoryPath
    dockerfile: FilePath

    @model_validator(mode='after')
    def _ensure_dockerfile_is_in_context(self) -> 'LocalSourceModel':
        if not self.dockerfile.resolve().is_relative_to(self.context.resolve()):
            raise ValueError('The Dockerfile must be inside the local build context.')
        return self


GitSourceModel = SourceModel


class BuildOptions(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)

    platforms: list[str] = Field(default_factory=lambda: ['linux/amd64'])
    args: dict[str, str] = Field(default_factory=dict)


class RemoteEndpoint(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)

    url: HttpUrl

    @field_validator('url', mode='before')
    @classmethod
    def _expand_url(cls, value: str) -> str:
        return expand_environment(str(value))


class ServerBase(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)

    schema_version: Literal[1]
    name: str = Field(pattern=r'^[a-z0-9]+(?:-[a-z0-9]+)*$')
    kind: str
    title: str
    description: str
    enabled: bool = True
    runtime: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator('name')
    @classmethod
    def _disallow_catalog_name(cls, value: str) -> str:
        if value == 'catalog':
            raise ValueError('The reserved name "catalog" is not allowed for server definitions.')
        return value


class BuildServer(ServerBase):
    kind: Literal['build']
    source: SourceModel | LocalSourceModel
    build: BuildOptions


class ImageServer(ServerBase):
    kind: Literal['image']
    image: str

    @field_validator('image')
    @classmethod
    def _ensure_digest_pin(cls, value: str) -> str:
        if '@sha256:' not in value:
            raise ValueError('Image references must be digest-pinned using @sha256:...')
        if len(value.split('@sha256:')[-1]) != 64:
            raise ValueError('A digest-pinned image must include a 64-character sha256 digest.')
        return value


class RemoteServer(ServerBase):
    kind: Literal['remote']
    remote: RemoteEndpoint


ServerModel = Annotated[Union[BuildServer, ImageServer, RemoteServer], Field(discriminator='kind')]
