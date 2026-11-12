"""Pydantic model for the catalog manifest."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator, model_validator

from ..expansion import expand_environment
from .server import ServerModel


class CatalogModel(BaseModel):
    """Top-level catalog manifest listing the published servers."""

    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)

    schema_version: Literal[1] = Field(description='Manifest schema version; must be 1.')
    schema_kind: Literal['https://mcp-catalog.schema.krenzer.space/catalog.schema.json'] = Field(
        description='URL identifying the catalog manifest schema.'
    )
    name: str = Field(
        pattern=r'^[a-z0-9]+(?:-[a-z0-9]+)*$',
        description='Catalog identifier (Docker catalog name).',
    )
    title: str = Field(min_length=1, description='Display name (Docker catalog displayName).')
    description: str = Field(min_length=1, description='Short description of the catalog.')
    repository: HttpUrl | None = Field(
        default=None,
        description=(
            'HTTP(S) URL of the Git repository that maintains this catalog. Used as the OCI '
            'source label of the catalog image and of locally built server images, and as the '
            'source link of locally built servers.'
        ),
    )
    servers_dir: str = Field(
        default='servers',
        description='Directory with one server manifest per file, relative to the catalog.',
    )
    servers: list[ServerModel] = Field(
        default_factory=list,
        description='Embedded server definitions; alternative to servers_dir.',
    )

    @field_validator('repository', mode='before')
    @classmethod
    def _expand_repository_url(cls, value: Any) -> Any:
        return expand_environment(str(value)) if value is not None else value

    @field_validator('name')
    @classmethod
    def _disallow_catalog_name(cls, value: str) -> str:
        if value == 'catalog':
            raise ValueError('The reserved name "catalog" is not allowed for catalog definitions.')
        return value

    @model_validator(mode='after')
    def _ensure_unique_server_names(self) -> 'CatalogModel':
        seen: set[str] = set()
        for server in self.servers:
            if server.name in seen:
                raise ValueError(f'Duplicate server name: {server.name}')
            seen.add(server.name)
        return self
