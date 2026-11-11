from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..models import CatalogModel
from .catalog import SERVER_ADAPTER


def schema_documents() -> dict[str, dict[str, Any]]:
    return {
        'catalog.schema.json': CatalogModel.model_json_schema(),
        'server.schema.json': SERVER_ADAPTER.json_schema(),
    }


def write_schemas(directory: str | Path) -> list[Path]:
    output_dir = Path(directory)
    output_dir.mkdir(parents=True, exist_ok=True)
    paths = []
    for filename, schema in schema_documents().items():
        path = output_dir / filename
        path.write_text(json.dumps(schema, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
        paths.append(path)
    return paths


def schema_drift(directory: str | Path) -> list[str]:
    output_dir = Path(directory)
    drift = []
    for filename, expected in schema_documents().items():
        path = output_dir / filename
        if not path.is_file():
            drift.append(f'Missing schema: {path}')
            continue
        try:
            actual = json.loads(path.read_text(encoding='utf-8'))
        except json.JSONDecodeError as error:
            drift.append(f'Invalid JSON in {path}: {error}')
            continue
        if actual != expected:
            drift.append(f'Schema is out of date: {path}')
    return drift
