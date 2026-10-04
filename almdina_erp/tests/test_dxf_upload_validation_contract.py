from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SERVICE = ROOT / "almdina_erp" / "services" / "shop_floor_dxf_service.py"
PRESENTER = ROOT / "almdina_erp" / "presentation" / "cutting" / "dxf_error_presenter.py"


def _source() -> str:
    return SERVICE.read_text(encoding="utf-8")


def test_upload_keeps_file_metadata_guards_and_private_attachment():
    src = _source()
    for token in [
        "MAX_DXF_FILE_SIZE = 10 * 1024 * 1024",
        '.endswith(".dxf")',
        '"File"',
        '"file_size"',
        '"is_private"',
        '"attached_to_doctype": "Cutting Plan"',
        '"attached_to_name": plan.name',
        '"attached_to_field": "dxf_file"',
    ]:
        assert token in src


def test_upload_keeps_role_capability_native_read_and_plan_lock_guards():
    src = _source()
    for token in [
        "required_upload_capability",
        'order.check_permission("read")',
        "require_cutting_plan_capability",
        "require_stage_assignment_access",
        'DrawingActionDenied("plan_already_approved")',
    ]:
        assert token in src


def test_upload_shows_actionable_arabic_validation_feedback():
    src = _source()
    presenter = PRESENTER.read_text(encoding="utf-8")
    for token in [
        "ملف DXF مطلوب",
        "ملف غير مدعوم",
        "الملف غير موجود",
        "ملف DXF كبير جدًا",
        "الملف مرتبط مسبقًا",
        "تعذر قبول ملف DXF",
        "render_error_cards_html",
    ]:
        assert token in src
    assert "صحح الرسم ثم أعد رفع الملف" in presenter
    assert "ما المشكلة؟" in presenter


def test_invalid_geometry_is_not_attached_as_the_production_file():
    src = _source()
    parse_pos = src.index("custom_snapshot = parse_production_dxf")
    attach_pos = src.index("_attach_validated_dxf_file(plan, file_row)")
    assert parse_pos < attach_pos
