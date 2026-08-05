from __future__ import annotations

from collections.abc import Iterable
from types import MappingProxyType

from almdina_erp.almdina_erp.application.security.permission_matrix import (
    normalize_capability_state,
)
from almdina_erp.almdina_erp.application.security.permission_templates import (
    template_state,
)
from almdina_erp.almdina_erp.domain.security.authorization import ALL_CAPABILITIES


LEGACY_ROLE_TEMPLATE_KEYS = MappingProxyType(
    {
        "Order Entry": ("order_entry",),
        "Cutting Operator": ("production_operator",),
        "Edge Operator": ("production_operator",),
        "Production Manager": (
            "order_entry",
            "planner_designer",
            "production_supervisor",
            "control_center",
        ),
        "Accounts Management": ("pricing_and_documents",),
        "عامل رسم": ("planner_designer",),
        "عامل شريون": ("production_operator",),
        "عامل CNC": ("production_operator",),
        "عامل تقشيط": ("production_operator",),
    }
)
FULL_ACCESS_LEGACY_ROLES = frozenset({"System Manager"})


def combine_template_states(template_keys: Iterable[str]) -> dict[str, bool]:
    """Return one normalized capability state from multiple optional templates."""

    enabled: dict[str, bool] = {}
    for template_key in template_keys:
        for capability, granted in template_state(template_key).items():
            if granted is True:
                enabled[capability] = True
    return normalize_capability_state(enabled)


def legacy_role_state(role: str) -> dict[str, bool]:
    """Return the least-surprise upgrade state for one historical Almdina role."""

    resolved = str(role or "").strip()
    if resolved in FULL_ACCESS_LEGACY_ROLES:
        return normalize_capability_state(
            {capability: True for capability in ALL_CAPABILITIES}
        )
    try:
        template_keys = LEGACY_ROLE_TEMPLATE_KEYS[resolved]
    except KeyError as exc:
        raise ValueError(f"Unknown legacy Almdina role: {resolved}") from exc
    return combine_template_states(template_keys)


def legacy_roles() -> tuple[str, ...]:
    return tuple(sorted((*LEGACY_ROLE_TEMPLATE_KEYS, *FULL_ACCESS_LEGACY_ROLES)))


__all__ = [
    "FULL_ACCESS_LEGACY_ROLES",
    "LEGACY_ROLE_TEMPLATE_KEYS",
    "combine_template_states",
    "legacy_role_state",
    "legacy_roles",
]
