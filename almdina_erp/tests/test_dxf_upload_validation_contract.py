from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SERVICE = ROOT / "almdina_erp" / "services" / "shop_floor_dxf_service.py"


def _source() -> str:
    return SERVICE.read_text(encoding="utf-8")


def test_upload_keeps_file_metadata_guards_and_private_attachment():
    src = _source()
    for token in [
        "MAX_DXF_FILE_SIZE = 10 * 1024 * 1024",
        '.endswith(".dxf")',
        '"File"',
        '"file_size"',
        '"is_private": 1',
        '"attached_to_doctype": order.doctype',
        '"attached_to_name": order.name',
        '"attached_to_field": "production_dxf"',
    ]:
        assert token in src


def test_upload_keeps_role_capability_native_read_and_plan_lock_guards():
    src = _source()
    for token in [
        "required_upload_capability",
        'order.check_permission("read")',
        "require_document_capability(order, capability)",
        "require_stage_operational_access(order)",
        'DrawingActionDenied("plan_already_approved")',
    ]:
        assert token in src


def test_upload_shows_actionable_arabic_validation_feedback():
    src = _source()
    for token in [
        "ملف DXF مطلوب",
        "ملف غير مدعوم",
        "الملف غير موجود",
        "ملف DXF كبير جدًا",
        "الملف مرتبط بمستند آخر",
        "تعذر قبول ملف DXF",
        "صحح الرسم ثم أعد رفع الملف",
    ]:
        assert token in src


def test_invalid_geometry_is_not_attached_as_the_production_file():
    src = _source()
    parse_pos = src.index("custom_snapshot = parse_production_dxf")
    attach_pos = src.index("_attach_validated_dxf_file(order, file_row)")
    assert parse_pos < attach_pos
