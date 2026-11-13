"""Planned file changes (for dry runs) and path-based edits of manifest documents.

Path syntax, designed to be easy for agents to produce:

``metadata.license``           mapping keys separated by dots
``tools[0].description``       list element by index (negative indices count from the end)
``runtime.env[+]``             append to a list
``runtime.env[name=USER_AGENT].value``  list element whose mapping has ``name == USER_AGENT``
"""

from __future__ import annotations

import difflib
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

_TOKEN = re.compile(r'\.?([^.\[\]]+)|\[([^\]]*)\]')


@dataclass(frozen=True)
class ChangeSet:
    """A file write that has been computed and validated but may not be applied yet."""

    action: str
    target: Path
    before: str | None
    after: str | None
    applied: bool = False
    details: dict[str, Any] = field(default_factory=dict)

    @property
    def changed(self) -> bool:
        return self.before != self.after

    @property
    def diff(self) -> str:
        return ''.join(
            difflib.unified_diff(
                (self.before or '').splitlines(keepends=True),
                (self.after or '').splitlines(keepends=True),
                fromfile=f'a/{self.target.name}' if self.before is not None else '/dev/null',
                tofile=f'b/{self.target.name}' if self.after is not None else '/dev/null',
            )
        )

    def apply(self) -> ChangeSet:
        if self.after is None:
            self.target.unlink()
        else:
            self.target.parent.mkdir(parents=True, exist_ok=True)
            self.target.write_text(self.after, encoding='utf-8')
        return ChangeSet(
            self.action, self.target, self.before, self.after, applied=True, details=self.details
        )

    def summary(self) -> str:
        verb = 'Applied' if self.applied else 'Dry run (nothing written):'
        header = f'{verb} {self.action} -> {self.target}'
        if not self.changed:
            return f'{header}\nNo changes.'
        return f'{header}\n{self.diff}'


def parse_path(path: str) -> list[str | int | tuple[str, str]]:
    """Split a manifest path into mapping keys, list indices, appends and selectors."""
    if not path or not path.strip():
        raise ValueError('A manifest path must not be empty.')
    tokens: list[str | int | tuple[str, str]] = []
    position = 0
    while position < len(path):
        match = _TOKEN.match(path, position)
        if match is None or match.end() == position:
            raise ValueError(f'Invalid manifest path {path!r} at offset {position}.')
        position = match.end()
        key, bracket = match.groups()
        if key is not None:
            tokens.append(key)
        elif bracket == '+':
            tokens.append('+')
        elif re.fullmatch(r'-?\d+', bracket):
            tokens.append(int(bracket))
        elif '=' in bracket:
            selector_key, _, selector_value = bracket.partition('=')
            tokens.append((selector_key.strip(), selector_value.strip()))
        else:
            raise ValueError(f'Invalid list selector [{bracket}] in {path!r}.')
    return tokens


def _is_append(token: Any) -> bool:
    return isinstance(token, str) and token == '+'


def _find_item(sequence: list[Any], token: Any, path: str) -> int:
    if isinstance(token, int):
        if not -len(sequence) <= token < len(sequence):
            raise ValueError(f'Index {token} is out of range for {path!r}.')
        return token % len(sequence)
    selector_key, selector_value = token
    for index, item in enumerate(sequence):
        if isinstance(item, dict) and str(item.get(selector_key)) == selector_value:
            return index
    raise ValueError(f'No list item with {selector_key}={selector_value} in {path!r}.')


def _empty_container(next_token: Any) -> Any:
    return [] if isinstance(next_token, (int, tuple)) or _is_append(next_token) else {}


def set_path(document: Any, path: str, value: Any) -> None:
    """Set ``path`` to ``value``, creating missing mappings and lists on the way."""
    tokens = parse_path(path)
    current = document
    for position, token in enumerate(tokens):
        last = position == len(tokens) - 1
        if _is_append(token):
            if not isinstance(current, list):
                raise ValueError(f'[+] needs a list in {path!r}.')
            if last:
                current.append(value)
                return
            current.append(_empty_container(tokens[position + 1]))
            current = current[-1]
            continue
        if isinstance(token, (int, tuple)):
            if not isinstance(current, list):
                raise ValueError(f'List selector used on a non-list in {path!r}.')
            index = _find_item(current, token, path)
            if last:
                current[index] = value
                return
            current = current[index]
            continue
        if not isinstance(current, dict):
            raise ValueError(f'Key {token!r} used on a non-mapping in {path!r}.')
        if last:
            current[token] = value
            return
        if current.get(token) is None:
            current[token] = _empty_container(tokens[position + 1])
        current = current[token]


def unset_path(document: Any, path: str) -> None:
    """Remove the key or list element at ``path``; a missing target is an error."""
    tokens = parse_path(path)
    current = document
    for position, token in enumerate(tokens):
        last = position == len(tokens) - 1
        if isinstance(token, (int, tuple)):
            if not isinstance(current, list):
                raise ValueError(f'List selector used on a non-list in {path!r}.')
            index = _find_item(current, token, path)
            if last:
                del current[index]
                return
            current = current[index]
            continue
        if _is_append(token):
            raise ValueError(f'[+] cannot be removed in {path!r}.')
        if not isinstance(current, dict) or token not in current:
            raise ValueError(f'Nothing to remove at {path!r}.')
        if last:
            del current[token]
            return
        current = current[token]


def apply_edits(
    document: Any,
    set_values: dict[str, Any] | None = None,
    unset_paths: list[str] | None = None,
) -> None:
    """Apply removals first and assignments second, in the order given."""
    for path in unset_paths or []:
        unset_path(document, path)
    for path, value in (set_values or {}).items():
        set_path(document, path, value)


def parse_assignments(assignments: list[str] | None) -> dict[str, Any]:
    """Parse ``path=value`` strings; each value is read as a YAML scalar or flow collection."""
    from ..io.yaml import load_yaml

    values: dict[str, Any] = {}
    for assignment in assignments or []:
        path, separator, raw_value = assignment.partition('=')
        if not separator or not path.strip():
            raise ValueError(f'Expected path=value, got {assignment!r}.')
        values[path.strip()] = load_yaml(raw_value) if raw_value.strip() else ''
    return values
