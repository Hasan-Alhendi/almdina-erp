from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "almdina_erp"
REPOSITORY = APP / "infrastructure" / "frappe" / "notes_repository.py"
DCO_NOTES_UX = ROOT / "public" / "js" / "door_cutting_order" / "notes" / "door_cutting_order_notes_ux.js"


def source(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_note_action_identity_uses_canonical_frappe_owner() -> None:
    repository = source(REPOSITORY)
    assert '"author_user": str(note.get("owner") or note.get("comment_email") or "").strip()' in repository
    assert 'note["comment_email"] = str(note.get("owner") or "").strip()' in repository
    assert "Frappe `owner` is the stable authenticated user identity" in repository


def test_toolbar_count_is_refreshed_for_each_order_identity() -> None:
    ux = source(DCO_NOTES_UX)
    assert "function orderIdentity(frm)" in ux
    assert "function resetIdentityState(frm, identity)" in ux
    assert "function refreshNotesSummary(frm)" in ux
    assert "_almdinaNotesOrderIdentity" in ux
    assert "_almdinaNotesSummaryGeneration" in ux
    assert "get_order_notes_context" in ux
    assert "Never paint the previous order's count" in ux


def test_toolbar_summary_is_stale_response_safe_and_dco_save_free() -> None:
    ux = source(DCO_NOTES_UX)
    assert "function isCurrentSummaryRequest(frm, identity, generation)" in ux
    assert "applyContextSnapshot(frm, context, identity, generation)" in ux
    assert "String(context.order || \"\") !== String(identity || \"\")" in ux
    assert "frm._almdinaNotesSummaryGeneration = Number(frm._almdinaNotesSummaryGeneration || 0) + 1" in ux
    assert "frm.save(" not in ux
    assert "frm.set_value" not in ux
    assert "frm.dirty" not in ux
