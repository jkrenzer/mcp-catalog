from __future__ import annotations

from pathlib import Path
from typing import Any

from ..interfaces.catalog import validate_catalog_document as _validate_catalog_document
from ..interfaces.catalog import validate_server_document as _validate_server_document
from ..models import CatalogModel, ServerModel


def validate_catalog_document(document: dict[str, Any]) -> CatalogModel:
    return _validate_catalog_document(document, base_dir='.')


def validate_server_document(document: dict[str, Any]) -> ServerModel:
    return _validate_server_document(document, base_dir=Path.cwd())
