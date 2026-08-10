from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PLAN_SERVICE = ROOT / "almdina_erp" / "services" / "cutting_plan_service.py"
ORDER_JSON = ROOT / "almdina_erp" / "doctype" / "door_cutting_order" / "door_cutting_order.json"
CUTTING_PLAN_JSON = ROOT / "almdina_erp" / "doctype" / "cutting_plan" / "cutting_plan.json"
SHOP_FLOOR = ROOT / "almdina_erp" / "services" / "shop_floor_service.py"
TABS_UX = ROOT / "public" / "js" / "door_cutting_order_plan_tabs_ux.js"


def _source(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_dual_plan_fields_exist_on_order():
    import json

    doc = json.loads(ORDER_JSON.read_text(encoding="utf-8"))
    fields = {row["fieldname"]: row for row in doc["fields"]}
    assert fields["system_plan_json"]["fieldtype"] == "Long Text"
    assert fields["custom_plan_json"]["fieldtype"] == "Long Text"
    assert fields["approved_plan_source"]["options"] == "System\nCustom"


def test_cutting_plan_supports_custom_dxf_kind():
    import json

    doc = json.loads(CUTTING_PLAN_JSON.read_text(encoding="utf-8"))
    plan_kind = next(row for row in doc["fields"] if row["fieldname"] == "plan_kind")
    assert "Custom DXF" in plan_kind["options"]


def test_lock_cutting_plan_accepts_plan_source():
    src = _source(PLAN_SERVICE)
    lock_block = src.split("def lock_cutting_plan", 1)[1].split("def _lock_order_for_production", 1)[0]
    lock_impl = src.split("def _lock_order_for_production", 1)[1].split("@frappe.whitelist()", 1)[0]
    assert 'plan_source: str = "System"' in lock_block
    assert 'plan_source == "Custom"' in lock_impl
    assert 'plan_kind = "Custom DXF"' in lock_impl
    assert '"approved_plan_source": plan_source' in lock_impl


def test_upload_parses_dxf_into_custom_plan_json():
    src = _source(SHOP_FLOOR)
    upload = src.split("def upload_production_dxf", 1)[1].split("@frappe.whitelist()", 1)[0]
    assert "parse_production_dxf" in upload
    assert "custom_plan_json" in upload
    assert "validate_imported_plan" in upload


def test_dxf_export_uses_stored_system_plan_before_approval():
    src = _source(ROOT / "almdina_erp" / "services" / "export_validation_service.py")
    assert "def _stored_order_export_snapshot" in src
    assert "get_system_plan_json" in src
    block = src.split("def get_validated_dxf_plan", 1)[1]
    assert "_stored_order_export_snapshot(order)" in block


def test_dual_tabs_ux_exposes_system_custom_and_approved_tabs():
    src = _source(TABS_UX)
    assert "خطة النظام" in src
    assert "الخطة المرفوعة" in src
    assert "الخطة المعتمدة" in src
    assert "view_system_cutting_plan" in src
    assert "view_uploaded_cutting_plan" in src
    assert "view_approved_cutting_plan" in src
    assert "shouldShowPlanTabs" in src
    assert "لا يوجد خطة مرفوعة" in src


def test_custom_plan_snapshot_does_not_fall_back_to_system_plan():
    src = _source(SHOP_FLOOR)
    block = src.split('if plan_source == "Custom":', 1)[1].split("\n\n\tsnapshot = None", 1)[0]
    assert "return {}" in block
    assert "cutting_plan_json" not in block
