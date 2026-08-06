from __future__ import annotations

import json
from collections.abc import Iterable

from almdina_erp.almdina_erp.domain.orders.production_routing import (
    normalize_eligible_roles,
)


def decode_eligible_roles(
    value: str | Iterable[str] | None,
    *,
    legacy_role: str | None = None,
) -> tuple[str, ...]:
    """Decode a stage role snapshot and fall back to one historical role."""

    if isinstance(value, str):
        raw = value.strip()
        if raw:
            try:
                parsed = json.loads(raw)
            except (TypeError, ValueError) as error:
                raise ValueError("Eligible roles must be valid JSON.") from error
            if not isinstance(parsed, list):
                raise ValueError("Eligible roles JSON must contain a list.")
            roles = normalize_eligible_roles(parsed)
        else:
            roles = ()
    else:
        roles = normalize_eligible_roles(value)
    if roles:
        return roles
    return normalize_eligible_roles(legacy_role)


def encode_eligible_roles(roles: Iterable[str] | str | None) -> str:
    return json.dumps(
        list(normalize_eligible_roles(roles)),
        ensure_ascii=False,
        separators=(",", ":"),
    )


def eligible_roles_display(roles: Iterable[str] | str | None) -> str:
    return "، ".join(normalize_eligible_roles(roles))


__all__ = [
    "decode_eligible_roles",
    "eligible_roles_display",
    "encode_eligible_roles",
]
