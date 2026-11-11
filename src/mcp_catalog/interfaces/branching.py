from __future__ import annotations

from ..branching import branch_slug


def get_branch_slug(branch_name: str) -> str:
    return branch_slug(branch_name)
