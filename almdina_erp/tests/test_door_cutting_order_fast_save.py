from pathlib import Path
import json


ROOT = Path(__file__).resolve().parents[1]
ORDER_PY = ROOT / "almdina_erp" / "doctype" / "door_cutting_order" / "door_cutting_order.py"
ORDER_JSON = ROOT / "almdina_erp" / "doctype" / "door_cutting_order" / "door_cutting_order.json"
PLAN_SERVICE = ROOT / "almdina_erp" / "services" / "cutting_plan_service.py"
PREVIEW_API = ROOT / "almdina_erp" / "api.py"
FAST_SAVE_JS = ROOT / "public" / "js" / "door_cutting_order_fast_save_ux.js"
HOOKS = ROOT / "hooks.py"


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_normal_validate_decouples_optimizer_from_ordinary_save():
    source = _text(ORDER_PY)
    validate_block = source.split("    def validate(self) -> None:", 1)[1].split("    def _get_old_doc", 1)[0]
    assert 'self.flags.get("force_cutting_plan_recalculation")' in validate_block
    assert "self._can_reuse_current_plan" in validate_block
    assert "self._mark_plan_for_recalculation" in validate_block
    assert validate_block.count("self._calculate_cutting_plan") == 1


def test_explicit_recalculation_sets_force_flag_before_save():
    source = _text(ORDER_PY)
    recalculate = source.split("def recalculate_order(order_name: str)", 1)[1]
    assert "doc.flags.force_cutting_plan_recalculation = True" in recalculate
    assert "doc.save()" in recalculate


def test_preview_api_uses_new_explicit_plan_calculation_contract():
    source = _text(PREVIEW_API)
    preview = source.split("def preview_door_cutting_order", 1)[1].split(
        "@frappe.whitelist()\ndef get_approved_cutting_plan_snapshot", 1
    )[0]
    assert "settings = preview._get_settings()" in preview
    assert "input_fingerprint = preview._plan_input_fingerprint(settings)" in preview
    assert "preview._calculate_cutting_plan(settings, input_fingerprint)" in preview
    assert "preview._calculate_cutting_plan()" not in preview


def test_edge_rates_are_loaded_in_one_batch_query():
    source = _text(ORDER_PY)
    assert "def _get_edge_rate_map" in source
    assert 'frappe.get_all(' in source
    assert 'filters={"name": ["in", sorted(names)]}' in source
    calculate_rows = source.split("    def _calculate_piece_rows", 1)[1].split("    @staticmethod\n    def _normalized_number", 1)[0]
    assert "rates = self._get_edge_rate_map()" in calculate_rows
    assert "frappe.db.get_value" not in calculate_rows


def test_plan_fingerprint_and_stale_fields_exist():
    doc = json.loads(ORDER_JSON.read_text(encoding="utf-8"))
    fields = {row["fieldname"]: row for row in doc["fields"]}
    assert fields["plan_needs_recalculation"]["fieldtype"] == "Check"
    assert fields["calculated_plan_input_hash"]["fieldtype"] == "Data"
    source = _text(ORDER_PY)
    assert "def _plan_input_fingerprint" in source
    assert "hashlib.sha256" in source
    assert 'snapshot["input_fingerprint"] = input_fingerprint' in source


def test_plan_button_uses_dedicated_recalculation_endpoint():
    source = _text(FAST_SAVE_JS)
    assert "event.stopImmediatePropagation()" in source
    assert "await frm.save()" in source
    assert "door_cutting_order.recalculate_order" in source
    assert "await frm.reload_doc()" in source
    assert "تم حفظ التعديلات دون تشغيل محرك القص الثقيل" in source


def test_invoice_print_is_blocked_while_plan_is_stale():
    source = _text(FAST_SAVE_JS)
    assert 'event.target.closest(".dco-print-customer-invoice")' in source
    assert "planIsStale(frm)" in source
    assert "أعد حساب خطة القص أولًا" in source


def test_review_workflow_recalculates_only_when_required():
    source = _text(PLAN_SERVICE)
    submit = source.split("def submit_order_for_review", 1)[1].split("@frappe.whitelist()\ndef approve_order", 1)[0]
    assert "if cint(order.plan_needs_recalculation) or not order.cutting_plan_json" in submit
    assert "order.flags.force_cutting_plan_recalculation = True" in submit


def test_fast_save_script_is_loaded_after_plan_controls():
    hooks = _text(HOOKS)
    assert '"public/js/door_cutting_order_plan_ux.js"' in hooks
    assert '"public/js/door_cutting_order_fast_save_ux.js"' in hooks
    assert hooks.index('"public/js/door_cutting_order_plan_ux.js"') < hooks.index(
        '"public/js/door_cutting_order_fast_save_ux.js"'
    )
