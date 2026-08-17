from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CUTTING_PLAN = ROOT / "public" / "js" / "door_cutting_order" / "cutting_plan"
PLAN_CONTROLS = CUTTING_PLAN / "door_cutting_order_plan_controls_ux.js"
FIELD_ACCESS = CUTTING_PLAN / "door_cutting_order_plan_field_access_adapter.js"
FAST_SAVE = CUTTING_PLAN / "door_cutting_order_fast_save_ux.js"
SECURE_DXF_UPLOAD = CUTTING_PLAN / "secure_dxf_upload.js"
MANIFEST = ROOT / "frontend_assets.py"


def source(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_focused_plan_fields_bridge_native_frappe_status_without_document_write() -> None:
    controls = source(PLAN_CONTROLS)
    adapter = source(FIELD_ACCESS)

    for fieldname in (
        "packing_mode",
        "cutting_machine_type",
        "kerf_mm",
        "trim_margin_mm",
        "optimization_time_limit_sec",
    ):
        assert f'"{fieldname}"' in adapter
        assert f'"{fieldname}"' in controls

    # PlanControls remains the permission-policy owner. The adapter only turns
    # its df.read_only decision into the native Control display status that
    # Frappe otherwise derives from broad DocType write permission.
    assert "controls.applyOptimizerFieldAccess(frm)" in adapter
    assert "field.get_status = function almdinaFocusedPlanFieldStatus" in adapter
    assert 'frameworkStatus === "None"' in adapter
    assert '? "Write"' in adapter
    assert ': "Read"' in adapter
    assert "almdina_edit_session_changed(frm) { schedule(frm); }" in adapter
    assert "refresh_plan_controls(frm) { schedule(frm); }" in adapter

    # Never synthesize or mutate broad Door Cutting Order permissions in the UI.
    assert "frm.perm" not in adapter
    assert "AlmdinaPermissions" not in adapter
    assert "user_roles" not in adapter
    assert "set_df_property" not in adapter


def test_kerf_and_trim_follow_optimizer_command_not_order_save_checkpoint() -> None:
    fast_save = source(FAST_SAVE)

    assert "kerf_mm(frm) { markOptimizerPlanStale(frm); }" in fast_save
    assert "trim_margin_mm(frm) { markOptimizerPlanStale(frm); }" in fast_save
    assert "kerf_mm(frm) { markOrderInputPlanStale(frm); }" not in fast_save
    assert "trim_margin_mm(frm) { markOrderInputPlanStale(frm); }" not in fast_save
    assert "focused recalculation command" in fast_save


def test_secure_dxf_owner_is_private_unattached_and_loaded_before_plan_ui() -> None:
    uploader = source(SECURE_DXF_UPLOAD)
    manifest = source(MANIFEST)

    config = uploader.split("new frappe.ui.FileUploader({", 1)[1].split(
        "on_success(file)", 1
    )[0]
    assert "make_attachments_public: false" in config
    assert "allow_toggle_private: false" in config
    assert "allow_multiple: false" in config
    assert "disable_file_browser: true" in config
    assert "allow_web_link: false" in config
    assert "doctype:" not in config
    assert "docname:" not in config
    assert "fieldname:" not in config

    # A stale/legacy helper cannot win merely because it was registered first.
    assert "__secureDxfUploadInstalled" in uploader
    assert 'frappe.almdina.upload_production_dxf = uploadProductionDxf' in uploader
    assert 'typeof frappe.almdina.upload_production_dxf === "function"' not in uploader

    global_secure = (
        '"/assets/almdina_erp/js/door_cutting_order/cutting_plan/secure_dxf_upload.js"'
    )
    form_secure = '"public/js/door_cutting_order/cutting_plan/secure_dxf_upload.js"'
    plan_ui = '"public/js/door_cutting_order/cutting_plan/door_cutting_order_plan_ux.js"'
    controls = '"public/js/door_cutting_order/cutting_plan/door_cutting_order_plan_controls_ux.js"'
    revision = '"public/js/door_cutting_order/core/door_cutting_order_revision_ux.js"'
    adapter = (
        '"public/js/door_cutting_order/cutting_plan/door_cutting_order_plan_field_access_adapter.js"'
    )

    # Secure upload has exactly one runtime owner: global Desk bootstrap. This
    # makes it available before the form plan UI without violating the frontend
    # ownership closure by dual-loading the same module.
    assert global_secure in manifest
    assert form_secure not in manifest
    assert manifest.index(global_secure) < manifest.index(plan_ui)

    # The policy owner loads before the compatibility edit-session layer; the
    # focused status bridge runs last and reapplies PlanControls after that layer.
    assert manifest.index(controls) < manifest.index(revision) < manifest.index(adapter)
