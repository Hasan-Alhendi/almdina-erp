"""Framework-free security application use cases and policies."""

from __future__ import annotations

from typing import Any

__all__ = [
    "PERMISSION_CONTEXT_VERSION",
    "build_permission_context",
]


def __getattr__(name: str) -> Any:
    if name in {"PERMISSION_CONTEXT_VERSION", "build_permission_context"}:
        from .permission_context import (
            PERMISSION_CONTEXT_VERSION,
            build_permission_context,
        )

        value = {
            "PERMISSION_CONTEXT_VERSION": PERMISSION_CONTEXT_VERSION,
            "build_permission_context": build_permission_context,
        }[name]
    else:
        raise AttributeError(name)

    globals()[name] = value
    return value
