from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
UX = (
    ROOT
    / "public"
    / "js"
    / "door_cutting_order"
    / "production"
    / "door_cutting_order_intake_planning_ux.js"
)


def test_intake_planning_ux_uses_server_plan_without_starting_production() -> None:
    source = UX.read_text(encoding="utf-8")

    assert source.startswith("(() => {")
    assert source.rstrip().endswith("})();")
    assert "order_intake_service.get_finish_data_entry_options" in source
    assert "order_intake_service.finish_data_entry" in source
    assert '__("إنهاء إدخال البيانات")' in source
    assert '__("تعديل خطة الإرسال")' in source
    assert "dispatch_order" not in source
    assert "Production Stage" not in source
    assert "setTimeout(" not in source


def test_intake_planning_ux_retires_legacy_dispatch_button_during_intake() -> None:
    source = UX.read_text(encoding="utf-8")

    assert 'frm.remove_custom_button(__("إرسال للإنتاج"))' in source
    assert 'stage === DATA_ENTRY' in source
    assert 'stage === READY_TO_DISPATCH' in source


def test_intake_planning_ux_blocks_unsaved_form_state_before_server_mutation() -> None:
    source = UX.read_text(encoding="utf-8")

    assert 'typeof frm.is_dirty === "function" && frm.is_dirty()' in source
    assert "Boolean(frm.doc.__unsaved)" in source
    assert "if (!requirePersistedFormState(frm)) return null;" in source
    assert "if (!requirePersistedFormState(frm)) return;" in source
    assert "if (hasUnsavedChanges(frm))" in source


def test_intake_planning_ux_rejects_stale_async_completions() -> None:
    source = UX.read_text(encoding="utf-8")

    assert "window.AlmdinaDocumentContext" in source
    assert "context.capture(frm)" in source
    assert "context.isCurrent(frm, token)" in source
    assert "const optionsToken = captureDocumentContext(frm);" in source
    assert "const mutationToken = captureDocumentContext(frm);" in source
    assert "if (!isCurrentDocumentContext(frm, optionsToken)) return;" in source
    assert "if (!isCurrentDocumentContext(frm, mutationToken)) return;" in source
