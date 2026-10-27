"""Guard registry: maps a policy 'type' string to a guard class."""

from __future__ import annotations

from app.core.base_guard import BaseGuard
from app.core.errors import PolicyError

GUARD_REGISTRY: dict[str, type[BaseGuard]] = {}


def register_guard(cls: type[BaseGuard]) -> type[BaseGuard]:
    if cls.name in GUARD_REGISTRY:
        raise ValueError(f"Duplicate guard name: {cls.name}")
    GUARD_REGISTRY[cls.name] = cls
    return cls


def get_guard_class(name: str) -> type[BaseGuard]:
    try:
        return GUARD_REGISTRY[name]
    except KeyError as exc:
        known = ", ".join(sorted(GUARD_REGISTRY))
        raise PolicyError(f"Unknown guard type '{name}'. Known: {known}") from exc
