from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def source(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def test_edge_profile_master_data_is_not_loaded_for_plain_order_viewers() -> None:
    ux = source(
        "public/js/door_cutting_order/order_entry/edge_banding/door_cutting_order_multi_edge_ux.js"
    )

    assert "EDGE_PROFILE_LOOKUP_CAPABILITIES" in ux
    assert '"view_edge_banding_types"' in ux
    assert '"create_order"' in ux
    assert '"edit_order"' in ux
    assert '"create_order_revision"' in ux
    assert '"view_orders"' not in ux.split("EDGE_PROFILE_LOOKUP_CAPABILITIES", 1)[1].split("]);", 1)[0]
    assert "if (!canLoadProfiles()) return Promise.resolve(profiles(frm));" in ux
    assert 'frappe.db.get_list("Edge Banding Type"' in ux


def test_readonly_order_render_does_not_recompute_or_mutate_edge_cost_fields() -> None:
    ux = source(
        "public/js/door_cutting_order/order_entry/edge_banding/door_cutting_order_multi_edge_ux.js"
    )

    render_row = ux.split("function renderRow", 1)[1].split("function renderHelp", 1)[0]
    assert "if (canMutateOrderPreview(frm))" in render_row
    assert "syncPreviewFields" in render_row

    dialog = ux.split("function openSideDialog", 1)[1].split(
        "function clearOverrideWhenDisabled", 1
    )[0]
    assert "if (!canMutateOrderPreview(frm)) return;" in dialog


def test_edge_profile_lookup_retries_only_after_permission_context_updates() -> None:
    ux = source(
        "public/js/door_cutting_order/order_entry/edge_banding/door_cutting_order_multi_edge_ux.js"
    )

    assert 'window.addEventListener("almdina:permissions-updated"' in ux
    assert "if (!permissionResolved()) return false;" in ux


def test_edge_banding_type_master_rate_remains_protected_from_plain_view_orders() -> None:
    resource_permissions = source("resource_permissions.py")
    edge_block = resource_permissions.split("def edge_banding_type_query", 1)[1].split(
        "def production_routing_query", 1
    )[0]

    # Do not solve the UI error by widening the full Edge Banding Type master data
    # (which contains rate_usd_per_meter) to every user who can merely view orders.
    assert "Capability.VIEW_ORDERS" not in edge_block
