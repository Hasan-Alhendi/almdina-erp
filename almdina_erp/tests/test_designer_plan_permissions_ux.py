from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CUTTING_PLAN = ROOT / "public" / "js" / "door_cutting_order" / "cutting_plan"
PLAN_CONTROLS = CUTTING_PLAN / "door_cutting_order_plan_controls_ux.js"
PLAN_EDIT_SESSION = CUTTING_PLAN / "door_cutting_order_plan_edit_session_ux.js"
FIELD_ACCESS = CUTTING_PLAN / "door_cutting_order_plan_field_access_adapter.js"
FAST_SAVE = CUTTING_PLAN / "door_cutting_order_fast_save_ux.js"
SECURE_DXF_UPLOAD = CUTTING_PLAN / "secure_dxf_upload.js"
PLAN_SETTINGS_SERVICE = ROOT / "almdina_erp" / "services" / "plan_settings_edit_service.py"
DOCUMENT_CONTEXT = (
    ROOT
    / "public"
    / "js"
    / "door_cutting_order"
    / "core"
    / "door_cutting_order_document_context.js"
)
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

    # PlanControls keeps generic optimizer/recalculation policy. The final adapter
    # composes that with explicit PlanEditSession intent for these five fields and
    # uses Frappe v16's supported df.get_status/read_only extension points.
    assert "controls.applyOptimizerFieldAccess(frm)" in adapter
    assert "df.get_status = function almdinaFocusedPlanFieldStatus" in adapter
    assert 'STATUS_KEY = "__almdinaFocusedPlanStatus"' in adapter
    assert 'field.df[STATUS_KEY] = editingAllowed ? "Write" : "Read"' in adapter
    assert 'frm.set_df_property(fieldname, "read_only", desiredReadOnly)' in adapter
    assert 'this.hidden || this.hidden_due_to_dependency' in adapter
    assert "almdina_edit_session_changed(frm) { schedule(frm); }" in adapter
    assert "refresh_plan_controls(frm) { schedule(frm); }" in adapter

    # Never synthesize or mutate broad Door Cutting Order permissions in the UI.
    assert "frm.perm" not in adapter
    assert "AlmdinaPermissions" not in adapter
    assert "user_roles" not in adapter
    assert "ignore_permissions" not in adapter


def test_designer_plan_edit_capability_is_not_replaced_by_current_stage_role() -> None:
    session = source(PLAN_EDIT_SESSION)
    service = source(PLAN_SETTINGS_SERVICE)
    context = source(DOCUMENT_CONTEXT)

    # This focused edit surface is owned by edit_optimizer_settings. Production
    # lifecycle may be proven by a current-stage snapshot or by the authoritative
    # `At ...` order status. Neither path requires the current worker-stage role.
    assert 'can(frm, "edit_optimizer_settings")' in session
    assert "function hasActiveProductionStage(frm)" in session
    assert "function hasActiveRoutedLifecycle(frm)" in session
    assert "if (hasProductionRoute(frm))" in session
    assert "return hasActiveRoutedLifecycle(frm);" in session
    assert '"At Drawing"' in session
    assert "context.canTuneCuttingAlgorithm(frm)" not in session

    assert "Capability.EDIT_OPTIMIZER_SETTINGS" in service
    assert "require_stage_operational_access" not in service
    assert "SHOP_FLOOR_ORDER_STATUSES" in service
    assert "if _has_active_routed_lifecycle(doc):" in service
    assert "انتهى المسار الإنتاجي الحالي" in service

    # Recalculation/stage-scoped actions deliberately keep their separate role
    # policy. Fixing the edit button must not silently broaden those commands.
    assert "function canTuneCuttingAlgorithm" in context
    assert "canMutateCurrentStage(frm)" in context


def test_plan_edit_session_keeps_hard_lifecycle_locks() -> None:
    session = source(PLAN_EDIT_SESSION)
    service = source(PLAN_SETTINGS_SERVICE)

    assert "Number(frm.doc.docstatus || 0) !== 0" in session
    assert 'String(frm.doc.approved_plan || "").trim()' in session
    assert '(frm.doc.revision_state || "Current") === "Superseded"' in session
    assert 'DRAFT_LIKE.has(frm.doc.status || "Draft")' in session

    assert 'getattr(doc, "docstatus", 0)' in service
    assert 'getattr(doc, "approved_plan", None)' in service
    assert 'getattr(doc, "revision_state", "Current")' in service
    assert "DRAFT_LIKE_STATUSES" in service


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
