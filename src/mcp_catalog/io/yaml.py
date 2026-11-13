from __future__ import annotations

from io import StringIO
from pathlib import Path
from typing import Any

from ruamel.yaml import YAML


def _yaml_roundtrip() -> YAML:
    yaml = YAML(typ='rt')
    yaml.allow_duplicate_keys = False
    yaml.preserve_quotes = True
    constructors = dict(yaml.constructor.yaml_constructors)
    for key in list(constructors):
        if key is not None and key.startswith('tag:yaml.org,2002:python/'):
            del yaml.constructor.yaml_constructors[key]
    return yaml


def load_yaml(data: str | bytes | Path) -> Any:
    if isinstance(data, (str, bytes)):
        return _yaml_roundtrip().load(data)
    return _yaml_roundtrip().load(data.read_text(encoding='utf-8'))


def load_yaml_file(path: str | Path) -> Any:
    return load_yaml(Path(path))


def dump_yaml(data: Any) -> str:
    buffer = StringIO()
    yaml = _yaml_roundtrip()
    yaml.dump(data, buffer)
    return buffer.getvalue()


def dump_yaml_file(path: str | Path, data: Any) -> None:
    Path(path).write_text(dump_yaml(data), encoding='utf-8')
