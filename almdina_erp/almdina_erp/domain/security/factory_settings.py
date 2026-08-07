from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from types import MappingProxyType

from .authorization import Capability, normalize_capabilities


class FactorySettingsSection:
    CUTTING = "cutting"
    COSTING = "costing"
    PRODUCTION = "production"


SECTION_FIELDS = MappingProxyType(
    {
        FactorySettingsSection.CUTTING: frozenset(
            {
                "default_kerf_mm",
                "default_trim_margin_mm",
                "default_packing_mode",
                "default_cutting_machine_type",
                "default_optimization_time_limit_sec",
                "optimal_search_piece_limit",
            }
        ),
        FactorySettingsSection.COSTING: frozenset(
            {
                "default_cutting_cost_per_board_usd",
                "default_special_design_fee_usd",
                "default_special_cnc_fee_usd",
                "default_special_manual_edge_fee_usd",
                "default_special_margin_percent",
            }
        ),
        FactorySettingsSection.PRODUCTION: frozenset(
            {
                "default_production_routing",
                "allow_stage_override",
                "allow_unplaced_approval",
            }
        ),
    }
)
SECTION_CAPABILITIES = MappingProxyType(
    {
        FactorySettingsSection.CUTTING: Capability.EDIT_FACTORY_CUTTING_DEFAULTS,
        FactorySettingsSection.COSTING: Capability.EDIT_FACTORY_COST_DEFAULTS,
        FactorySettingsSection.PRODUCTION: Capability.EDIT_FACTORY_PRODUCTION_CONTROLS,
    }
)
ALL_SETTINGS_FIELDS = frozenset().union(*SECTION_FIELDS.values())


@dataclass(frozen=True, slots=True)
class FactorySettingsDecision:
    allowed: bool
    code: str
    reason: str


def expand_factory_settings_capabilities(
    capabilities: Iterable[str] | None,
) -> frozenset[str]:
    """Apply only safe dependencies between granular factory-setting grants."""

    granted = set(normalize_capabilities(capabilities))
    if any(capability in granted for capability in SECTION_CAPABILITIES.values()):
        granted.add(Capability.VIEW_FACTORY_SETTINGS)
    return frozenset(granted)


def settings_context(capabilities: Iterable[str] | None) -> dict[str, object]:
    granted = expand_factory_settings_capabilities(capabilities)
    return {
        "can_view": Capability.VIEW_FACTORY_SETTINGS in granted,
        "sections": {
            section: {
                "editable": required in granted,
                "capability": required,
                "fields": sorted(SECTION_FIELDS[section]),
            }
            for section, required in SECTION_CAPABILITIES.items()
        },
    }


def decide_settings_update(
    capabilities: Iterable[str] | None,
    payload: Mapping[str, object] | None,
) -> FactorySettingsDecision:
    granted = expand_factory_settings_capabilities(capabilities)
    supplied = frozenset(str(key) for key in dict(payload or {}))
    unknown = supplied.difference(ALL_SETTINGS_FIELDS)
    if unknown:
        return FactorySettingsDecision(
            False,
            "unknown_fields",
            f"Unsupported factory setting fields: {', '.join(sorted(unknown))}",
        )
    if not supplied:
        return FactorySettingsDecision(
            False,
            "empty_update",
            "No factory setting changes were supplied.",
        )
    for section, fields in SECTION_FIELDS.items():
        if supplied.intersection(fields) and SECTION_CAPABILITIES[section] not in granted:
            return FactorySettingsDecision(
                False,
                "missing_capability",
                "You do not have permission to update this factory settings section.",
            )
    return FactorySettingsDecision(True, "allowed", "Allowed.")


def section_for_field(fieldname: str) -> str:
    for section, fields in SECTION_FIELDS.items():
        if fieldname in fields:
            return section
    raise ValueError(f"Unknown factory setting field: {fieldname}")


__all__ = [
    "ALL_SETTINGS_FIELDS",
    "SECTION_CAPABILITIES",
    "SECTION_FIELDS",
    "FactorySettingsDecision",
    "FactorySettingsSection",
    "decide_settings_update",
    "expand_factory_settings_capabilities",
    "section_for_field",
    "settings_context",
]
