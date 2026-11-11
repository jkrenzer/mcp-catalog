from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class BuildPlan:
    server_name: str
    source_repository: str
    revision: str
    context: str
    dockerfile: str
    platforms: list[str]
    args: dict[str, str]
    metadata: dict[str, Any] | None = None
