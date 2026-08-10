from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PUBLIC = ROOT / "public" / "js"
SERVICES = ROOT / "almdina_erp" / "services"


def source(filename: str) -> str:
    return (PUBLIC / filename).read_text(encoding="utf-8")


def test_form_permissions_reconcile_server_context_with_native_frappe_rights() -> None:
    context = source("permission_context.js")

    assert "STANDARD_CAPABILITY_PERMISSION_TYPES" in context
    assert 'create_order: "create"' in context
    assert 'edit_order: "write"' in context
    assert "nativeDocumentPermission" in context
    assert 'typeof frm.has_perm !== "function"' in context
    assert "canDocument(frm, capability)" in context


def test_all_protected_order_surfaces_use_the_form_aware_resolver() -> None:
    modules = (
        "door_cutting_order_revision_ux.js",
        "order_lifecycle.js",
        "door_cutting_order_tab_permissions_ux.js",
        "door_cutting_order_plan_tabs_ux.js",
        "door_cutting_order_cost_presenter.js",
        "door_cutting_order_cost_permissions_ux.js",
        "door_cutting_order_financial_documents_ux.js",
        "door_cutting_order_customer_invoice_toolbar_ux.js",
        "door_cutting_order_drawing_approval_ux.js",
        "door_cutting_order_drawing_plan_ux.js",
        "shop_floor_order_ux.js",
        "secure_dxf_export.js",
    )

    for filename in modules:
        assert "canDocument" in source(filename), filename


def test_permission_refresh_recovers_editability_tabs_cost_and_plan() -> None:
    revision = source("door_cutting_order_revision_ux.js")
    refresh = source("door_cutting_order_permission_refresh_ux.js")

    assert "applyImmutableFields," in revision
    assert 'window.addEventListener("almdina:permissions-updated"' in revision
    assert "AlmdinaOrderRevisionUX" in refresh
    assert "revision.applyImmutableFields(frm)" in refresh
    assert "AlmdinaOrderTabPermissionsUX" in refresh
    assert "tabs.apply(frm)" in refresh


def test_shop_floor_presentation_cannot_lock_an_order_editor() -> None:
    shop_floor = source("shop_floor_order_ux.js")

    assert '!can(frm, "create_order")' in shop_floor
    assert '!can(frm, "edit_order")' in shop_floor
    assert "__almdinaShopFloorHiddenState" in shop_floor
    assert 'frm.set_df_property(fieldname, "hidden", hidden ? 1 : 0)' in shop_floor
    assert 'window.addEventListener("almdina:permissions-updated"' in shop_floor


def test_locked_order_explains_the_controlled_revision_path() -> None:
    revision = source("door_cutting_order_revision_ux.js")

    assert "canOfferEditSession" in revision
    assert "__(\"تعديل\")" in revision or '__("تعديل")' in revision
    assert "__(\"حفظ\")" in revision or '__("حفظ")' in revision
    assert "commitEditSession" in revision
    assert "lockEditSession" in revision
    assert "frm.add_custom_button(CONFIRM_EDIT_LABEL" not in revision
    assert "At Sharyoun" in revision
    assert "At CNC" in revision
    assert 'can(frm, "edit_order")' in revision


def test_drawing_recalculation_is_capability_driven_not_client_assignment_driven() -> None:
    drawing = source("door_cutting_order_drawing_plan_ux.js")
    block = drawing.split("function canUseDrawingOptimizer(frm)", 1)[1].split(
        "function canUseDrawingOptimizerInbox", 1
    )[0]

    assert 'can("recalculate_plan", frm)' in block
    assert "holdsStageOperationalRole(frm)" in block
    assert "isAssignedToCurrentUser" not in block

    plan_service = (SERVICES / "order_plan_permission_service.py").read_text(
        encoding="utf-8"
    )
    assert "Capability.RECALCULATE_PLAN" in plan_service
    assert "require_stage_operational_access" in plan_service
    assert "user_can_recalculate_drawing_system_plan" in plan_service
    assert "validate_assigned_drawing_action" not in plan_service
