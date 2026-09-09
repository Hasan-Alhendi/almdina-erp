from __future__ import annotations

import pytest

from almdina_erp.almdina_erp.domain.orders.lifecycle import (
    PRODUCTION_ORDER_STATUS,
    StageState,
    derive_order_status,
    order_status_for_stage_type,
    production_path_sequence,
)
from almdina_erp.almdina_erp.domain.orders.production_routing import ProductionRoute, RoutingStage


def _stage(sequence: int, code: str, label: str | None = None, *, planning: bool = False) -> RoutingStage:
    return RoutingStage(sequence=sequence, stage_type=code, department_label=label or code, operational_role=f"Role {sequence}", is_planning_stage=planning)


def test_arbitrary_six_stage_route_uses_configured_sequence() -> None:
    route = ProductionRoute(name="Custom", label="Custom", stages=tuple(_stage(i * 10, f"S{i}") for i in range(1, 7)))
    assert route.first_stage.stage_type == "S1"
    assert route.next_stage("S4").stage_type == "S5"
    assert route.next_stage("S6") is None


def test_planning_stage_is_metadata_not_stage_name() -> None:
    route = ProductionRoute(name="Custom", label="Custom", stages=(_stage(10, "ANY", planning=True), _stage(20, "OTHER")))
    assert route.starts_with_planning is True


def test_physical_stage_code_never_changes_generic_order_status() -> None:
    assert order_status_for_stage_type("CNC") == PRODUCTION_ORDER_STATUS
    assert order_status_for_stage_type("Brand New Stage") == PRODUCTION_ORDER_STATUS
    assert derive_order_status(current_status="Draft", production_path="Any Route", current_stage=StageState("Brand New Stage", "Pending"), stages=(), has_open_replacements=False) == PRODUCTION_ORDER_STATUS


def test_fixed_path_registry_is_retired() -> None:
    with pytest.raises(ValueError, match="Fixed production paths are retired"):
        production_path_sequence("Drawing")
