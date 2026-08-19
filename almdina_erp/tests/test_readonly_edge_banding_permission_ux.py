from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def source(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def test_order_edge_dropdown_uses_scoped_lookup_not_master_data_list() -> None:
    ux = source(
        "public/js/door_cutting_order/order_entry/edge_banding/door_cutting_order_multi_edge_ux.js"
    )

    assert "edge_banding_lookup_service.get_order_edge_banding_options" in ux
    assert 'frappe.db.get_list("Edge Banding Type"' not in ux
    assert 'fieldtype: "Select"' in ux
    assert 'options: profileSelectOptions(frm, current)' in ux
    assert 'options: "Edge Banding Type"' not in ux


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

    assert "rate_usd_per_meter: includeFinancial" in ux
    assert "profile.rate_usd_per_meter !== null" in ux


def test_edge_profile_controls_remain_visible_for_order_viewers() -> None:
    ux = source(
        "public/js/door_cutting_order/order_entry/edge_banding/door_cutting_order_multi_edge_ux.js"
    )

    # The fix must not solve the permission error by hiding the side/profile UI.
    assert "is-readonly" not in ux
    assert "canMutateOrderPreview" not in ux
    assert "openSideDialog(frm, tr, indicator.dataset.edgeSide);" in ux


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


def test_master_edge_banding_permission_is_not_widened_to_plain_order_viewers() -> None:
    resource_permissions = source("resource_permissions.py")
    edge_block = resource_permissions.split("def edge_banding_type_query", 1)[1].split(
        "def production_routing_query", 1
    )[0]

    # Viewing an order may use the safe lookup API, but it must never become full
    # read access to the Edge Banding Type master record and its protected pricing.
    assert "Capability.VIEW_ORDERS" not in edge_block
