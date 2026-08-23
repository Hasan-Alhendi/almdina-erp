from __future__ import annotations

from almdina_erp.almdina_erp.application.security.permission_matrix import (
    field_permission_projection,
)
from almdina_erp.almdina_erp.application.security.supporting_doctype_permissions import (
    supporting_field_permission_projection,
)
from almdina_erp.almdina_erp.domain.security.authorization import Capability


def test_edit_cost_settings_gets_only_the_native_permlevel_one_write_prerequisite() -> None:
    state = {
        Capability.EDIT_COST_SETTINGS: True,
        Capability.VIEW_COSTS: True,
    }

    technical = supporting_field_permission_projection("Cutting Plan", state)
    business = field_permission_projection(state)

    # This native grant is a Frappe persistence prerequisite, not business edit authority.
    assert technical[1]["read"] is True
    assert technical[1]["write"] is True

    # The canonical business field projection stays read-only. The native write
    # grant exists only so an already-authorized command can survive Frappe's
    # validate_higher_perm_levels step.
    assert business["Cutting Plan"][1].read is True
    assert business["Cutting Plan"][1].write is False


def test_view_costs_alone_never_gets_native_financial_write() -> None:
    technical = supporting_field_permission_projection(
        "Cutting Plan",
        {Capability.VIEW_COSTS: True},
    )

    assert technical[1]["read"] is True
    assert technical[1]["write"] is False


def test_plan_geometry_edit_capability_does_not_unlock_cost_permlevel() -> None:
    technical = supporting_field_permission_projection(
        "Cutting Plan",
        {
            Capability.EDIT_OPTIMIZER_SETTINGS: True,
            Capability.VIEW_CUTTING_PLAN: True,
        },
    )

    assert technical[1]["write"] is False
