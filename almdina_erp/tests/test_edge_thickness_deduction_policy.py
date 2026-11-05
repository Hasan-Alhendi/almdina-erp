"""Plan-level edge-thickness deduction stays explicit and historical-safe."""

from __future__ import annotations

import json
from pathlib import Path

from almdina_erp.almdina_erp.domain.cutting.piece_cut_dimensions import (
    SIDE_LONG_LEFT,
    SIDE_LONG_RIGHT,
    coerce_deduct_edge_thickness,
    persisted_cut_matches_policy,
    special_bbox_matches_cut_envelope_with_unrecorded_edge_deduction,
)
from almdina_erp.almdina_erp.domain.cutting.plan_settings import (
    normalize_plan_settings,
    settings_for_system_search,
)
from almdina_erp.almdina_erp.domain.orders.costing import (
    PieceCostInput,
    calculate_piece_costs,
)
from almdina_erp.almdina_erp.domain.security.factory_settings import (
    FactorySettingsSection,
    SECTION_FIELDS,
)

APP_ROOT = Path(__file__).resolve().parents[1]


def test_missing_policy_stays_on_and_explicit_zero_stays_off():
    assert coerce_deduct_edge_thickness(None) is True
    assert coerce_deduct_edge_thickness("") is True
    assert coerce_deduct_edge_thickness(0) is False
    assert coerce_deduct_edge_thickness(False) is False
    assert coerce_deduct_edge_thickness("0") is False
    assert coerce_deduct_edge_thickness(1) is True


def test_plan_settings_keep_an_explicit_off_value():
    settings = normalize_plan_settings(
        optimization_mode="smart",
        machine_type="Auto",
        optimization_time_limit_sec=10,
        kerf_mm=3,
        preferred_trim_mm=5,
        deduct_edge_thickness=0,
    )
    assert settings.deduct_edge_thickness is False
    searched = settings_for_system_search(settings)
    assert searched.deduct_edge_thickness is False
    assert searched.optimization_mode == "smart"


def test_saved_cut_matches_only_the_calculated_edge_thickness():
    assert persisted_cut_matches_policy(
        persisted_width_cm=59.8,
        persisted_length_cm=39.8,
        expected_width_cm=59.8,
        expected_length_cm=39.8,
    )
    assert not persisted_cut_matches_policy(
        persisted_width_cm=59.8,
        persisted_length_cm=39.8,
        expected_width_cm=59.6,
        expected_length_cm=39.6,
    )
    assert not persisted_cut_matches_policy(
        persisted_width_cm=59.8,
        persisted_length_cm=39.8,
        expected_width_cm=60,
        expected_length_cm=40,
    )
    assert persisted_cut_matches_policy(
        persisted_width_cm=60,
        persisted_length_cm=40,
        expected_width_cm=60,
        expected_length_cm=40,
    )


def test_special_unrecorded_window_is_unchanged():
    assert special_bbox_matches_cut_envelope_with_unrecorded_edge_deduction(
        59.8, 39.8, 60, 40
    )
    assert not special_bbox_matches_cut_envelope_with_unrecorded_edge_deduction(
        59.7, 40, 60, 40
    )


def test_edge_cost_uses_finished_length_not_the_deducted_cut():
    summary = calculate_piece_costs(
        [
            PieceCostInput(
                width_cm=60,
                length_cm=40,
                qty=1,
                edge_long_right=1,
                edge_long_left=1,
                edge_width_top=0,
                edge_width_bottom=0,
                edge_long_type="PVC",
            )
        ],
        default_edge_type="PVC",
        edge_rates={"PVC": 2},
    )
    piece = summary.pieces[0]
    assert piece.edge_long_right_meters == 0.4
    assert piece.edge_long_left_meters == 0.4
    assert piece.edge_cost_usd == 1.6


def test_schema_defaults_are_enabled_and_not_on_the_order():
    settings = json.loads(
        (APP_ROOT / "almdina_erp/doctype/almdina_erp_settings/almdina_erp_settings.json").read_text()
    )
    plan = json.loads(
        (APP_ROOT / "almdina_erp/doctype/cutting_plan/cutting_plan.json").read_text()
    )
    order = json.loads(
        (APP_ROOT / "almdina_erp/doctype/door_cutting_order/door_cutting_order.json").read_text()
    )
    factory_field = next(row for row in settings["fields"] if row["fieldname"] == "default_deduct_edge_thickness")
    plan_field = next(row for row in plan["fields"] if row["fieldname"] == "deduct_edge_thickness")
    assert factory_field["default"] == "1"
    assert plan_field["default"] == "1"
    assert "deduct_edge_thickness" not in {row["fieldname"] for row in order["fields"]}
    assert "default_deduct_edge_thickness" in SECTION_FIELDS[FactorySettingsSection.CUTTING]


def test_readers_do_not_collapse_an_explicit_zero():
    runtime = (
        APP_ROOT / "almdina_erp/infrastructure/frappe/cutting_plan_runtime_repository.py"
    ).read_text()
    query = (
        APP_ROOT / "almdina_erp/services/cutting_plan_workspace_query_service.py"
    ).read_text()
    api = (
        APP_ROOT / "public/js/door_cutting_order/cutting_plan/door_cutting_order_plan_workspace_api.js"
    ).read_text()
    assert "deduct_edge_thickness or" not in runtime
    assert "value || default" not in api
    assert "deduct_edge_thickness ||" not in api
    assert "coerce_deduct_edge_thickness" in query
    assert SIDE_LONG_RIGHT and SIDE_LONG_LEFT
