from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .server import ServerModel


class CatalogModel(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)

    schema_version: Literal[1]
    name: str = Field(pattern=r'^[a-z0-9]+(?:-[a-z0-9]+)*$')
    title: str
    description: str
    servers_dir: str = 'servers'
    servers: list[ServerModel] = Field(default_factory=list)

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
