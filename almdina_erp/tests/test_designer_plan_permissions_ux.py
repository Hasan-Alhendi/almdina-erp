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


def _door_cutting_order_assets(manifest: str) -> str:
    return manifest.split('"Door Cutting Order": [', 1)[1].split(
        '],\n    "Edge Banding Type"', 1
    )[0]


def test_focused_plan_fields_use_frappe_native_df_status_without_document_write() -> None:
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

    # PlanControls remains the only business-policy owner. The adapter records
    # its decision and uses Frappe v16's supported df.get_status extension point,
    # which is evaluated before broad DocType write permission.
    assert "controls.applyOptimizerFieldAccess(frm)" in adapter
    assert "df.get_status = function almdinaFocusedPlanFieldStatus" in adapter
    assert 'STATUS_KEY = "__almdinaFocusedPlanStatus"' in adapter
    assert 'field.df[STATUS_KEY] = Number(field.df.read_only || 0) === 0' in adapter
    assert 'this.hidden || this.hidden_due_to_dependency' in adapter
    assert '? "Write"' in adapter
    assert ': "Read"' in adapter
    assert "almdina_edit_session_changed(frm) { schedule(frm); }" in adapter
    assert "refresh_plan_controls(frm) { schedule(frm); }" in adapter

    # Never synthesize or mutate broad Door Cutting Order permissions in the UI.
    assert "frm.perm" not in adapter
    assert "AlmdinaPermissions" not in adapter
    assert "user_roles" not in adapter
    assert "ignore_permissions" not in adapter


def test_plan_field_status_adapter_is_the_final_dco_runtime_owner() -> None:
    manifest = source(MANIFEST)
    dco_assets = _door_cutting_order_assets(manifest)

    adapter = (
        '"public/js/door_cutting_order/cutting_plan/door_cutting_order_plan_field_access_adapter.js"'
    )
    revision = '"public/js/door_cutting_order/core/door_cutting_order_revision_ux.js"'
    lifecycle = '"public/js/door_cutting_order/core/order_lifecycle.js"'
    stability = '"public/js/input_stability.js"'
    mobile = '"public/js/door_cutting_order/responsive/door_cutting_order_mobile_cards_ux.js"'

    assert dco_assets.count(adapter) == 1
    assert dco_assets.index(revision) < dco_assets.index(adapter)
    assert dco_assets.index(lifecycle) < dco_assets.index(adapter)
    assert dco_assets.index(stability) < dco_assets.index(adapter)
    assert dco_assets.index(mobile) < dco_assets.index(adapter)
    assert dco_assets.rstrip().endswith(adapter + ",")


def test_kerf_and_trim_follow_optimizer_command_not_order_save_checkpoint() -> None:
    fast_save = source(FAST_SAVE)

    assert "kerf_mm(frm) { markOptimizerPlanStale(frm); }" in fast_save
    assert "trim_margin_mm(frm) { markOptimizerPlanStale(frm); }" in fast_save
    assert "kerf_mm(frm) { markOrderInputPlanStale(frm); }" not in fast_save
    assert "trim_margin_mm(frm) { markOrderInputPlanStale(frm); }" not in fast_save
    assert "focused recalculation command" in fast_save


def test_secure_dxf_owner_is_private_unattached_and_form_scoped_before_plan_ui() -> None:
    uploader = source(SECURE_DXF_UPLOAD)
    manifest = source(MANIFEST)
    dco_assets = _door_cutting_order_assets(manifest)
    global_assets = manifest.split("app_include_js = [", 1)[1].split("]\n\ndoctype_js", 1)[0]

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

    assert "__secureDxfUploadInstalled" in uploader
    assert 'frappe.almdina.upload_production_dxf = uploadProductionDxf' in uploader

    global_secure = (
        '"/assets/almdina_erp/js/door_cutting_order/cutting_plan/secure_dxf_upload.js"'
    )
    form_secure = '"public/js/door_cutting_order/cutting_plan/secure_dxf_upload.js"'
    plan_ui = '"public/js/door_cutting_order/cutting_plan/door_cutting_order_plan_ux.js"'

    # The helper must be evaluated in the same deterministic doctype script batch
    # before plan_ux registers the upload button. Loading it only as a Desk global
    # allowed the legacy document-attached fallback to win in real sessions.
    assert global_secure not in global_assets
    assert dco_assets.count(form_secure) == 1
    assert dco_assets.index(form_secure) < dco_assets.index(plan_ui)
