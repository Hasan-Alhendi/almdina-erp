from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def source(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def test_order_edge_dropdown_uses_scoped_lookup_not_master_data_list() -> None:
    ux = source(
        "public/js/door_cutting_order/order_entry/edge_banding/door_cutting_order_multi_edge_ux.js"
    )
    defaults = source(
        "public/js/door_cutting_order/order_entry/door_cutting_order_defaults.js"
    )

    assert "edge_banding_lookup_service.get_order_edge_banding_options" in ux
    assert "edge_banding_lookup_service.get_order_edge_banding_options" in defaults
    assert 'frappe.db.get_list("Edge Banding Type"' not in ux
    assert 'frappe.db.get_value("Edge Banding Type"' not in defaults
    assert 'fieldtype: "Select"' in ux
    assert 'options: profileSelectOptions(frm, current)' in ux
    assert 'options: "Edge Banding Type"' not in ux


def test_safe_options_prime_legacy_fast_entry_before_it_can_query_master_data() -> None:
    defaults = source(
        "public/js/door_cutting_order/order_entry/door_cutting_order_defaults.js"
    )

    assert "frm._dco_edge_types_loaded = true;" in defaults
    assert "frm._dco_edge_types = frm._dco_edge_types || [];" in defaults
    assert "loadSafeEdgeOptions(frm);" in defaults
    assert "window.AlmdinaOrderEdgeOptions" in defaults


def test_nonfinancial_order_lookup_never_overwrites_edge_cost_fields() -> None:
    ux = source(
        "public/js/door_cutting_order/order_entry/edge_banding/door_cutting_order_multi_edge_ux.js"
    )

    sync_block = ux.split("function syncPreviewFields", 1)[1].split(
        "function detailForSide", 1
    )[0]
    assert "if (!financialProfilesAvailable(frm)) return;" in sync_block
    assert "row.edge_long_rate_usd = result.longRate;" in sync_block
    assert "row.edge_cost_usd = result.edgeCost;" in sync_block

    render_row = ux.split("function renderRow", 1)[1].split(
        "function renderHelp", 1
    )[0]
    assert "if (orderCanEdit(frm))" in render_row
    assert "syncPreviewFields" in render_row

    assert "rate_usd_per_meter: includeFinancial" in ux
    assert "profile.rate_usd_per_meter !== null" in ux


def test_drawing_worker_can_choose_profile_without_editing_edge_position() -> None:
    ux = source(
        "public/js/door_cutting_order/order_entry/edge_banding/door_cutting_order_multi_edge_ux.js"
    )

    assert 'hasDocumentCapability(frm, "edit_special_drawing")' in ux
    assert "save_order_edge_banding_override" in ux
    assert 'toggle.dataset.edgePositionReadonly = "1";' in ux
    assert 'toggle.dataset.edgePositionReadonly === "1"' in ux
    assert "event.stopImmediatePropagation();" in ux
    assert "if (!sideSelected(row, side))" in ux
    assert "usesDirectDrawingSave(frm)" in ux


def test_edge_profile_controls_reconcile_after_authoritative_permission_update() -> None:
    refresh = source(
        "public/js/door_cutting_order/core/door_cutting_order_permission_refresh_ux.js"
    )
    event_block = refresh.split(
        'window.addEventListener("almdina:permissions-updated"', 1
    )[1].split("window.AlmdinaOrderPermissionRefreshUX", 1)[0]

    assert "window.AlmdinaMultiEdgeBanding" in event_block
    assert 'typeof edgeBanding.schedule === "function"' in event_block
    assert "edgeBanding.schedule(frm);" in event_block


def test_drawing_profile_command_is_narrow_and_stage_authorized() -> None:
    service = source("almdina_erp/services/edge_banding_lookup_service.py")
    command = service.split("def save_order_edge_banding_override", 1)[1]

    assert "Capability.EDIT_ORDER" in service
    assert "Capability.EDIT_SPECIAL_DRAWING" in service
    assert "is_order_at_drawing_stage(order)" in service
    assert "require_stage_operational_access(order)" in service
    assert "approved_plan" in service
    assert "_SIDE_FIELDS.get(side_key)" in command
    assert "if not cint(getattr(piece, selected_field, 0))" in command
    assert "FrappeOrderCutDimensionAdapter" in service
    assert "invalidate_stale_draft_plans(order)" in service
    assert "ignore_permissions" not in service

    # The command persists the selected override plus derived operational cutting
    # dimensions only. It must not accept arbitrary request field dictionaries.
    assert "frappe.parse_json" not in command
    assert "setattr(piece, override_field, normalized_type)" in command
    assert "rate_usd_per_meter" not in command


def test_safe_lookup_is_order_authorized_and_cost_gated() -> None:
    service = source("almdina_erp/services/edge_banding_lookup_service.py")

    assert "Capability.VIEW_ORDERS" in service
    assert "require_document_capability" in service
    assert "Capability.CREATE_ORDER" in service
    assert "Capability.VIEW_COSTS" in service
    assert '"rate_usd_per_meter"' in service
    assert "if include_financial:" in service
    operational = service.split("_OPERATIONAL_FIELDS = (", 1)[1].split(")", 1)[0]
    assert "rate_usd_per_meter" not in operational


def test_master_edge_banding_permission_is_not_widened_to_drawing_viewers() -> None:
    resource_permissions = source("resource_permissions.py")
    edge_block = resource_permissions.split("def edge_banding_type_query", 1)[1].split(
        "def production_routing_query", 1
    )[0]

    # Viewing an order or editing its drawing may use the safe lookup API, but it
    # must never become full read access to the Edge Banding Type master record.
    assert "Capability.VIEW_ORDERS" not in edge_block
    assert "Capability.EDIT_SPECIAL_DRAWING" not in edge_block
