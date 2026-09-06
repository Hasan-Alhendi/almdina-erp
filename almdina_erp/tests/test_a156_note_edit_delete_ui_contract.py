from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PANEL = ROOT / "public" / "js" / "notes" / "notes_panel.js"


def test_notes_panel_balanced_iife_and_mutation_methods() -> None:
    source = PANEL.read_text(encoding="utf-8")
    assert source.startswith("(() => {")
    assert source.rstrip().endswith("})();")
    assert "notes_service.edit_note" in source
    assert "notes_service.delete_note" in source
    assert "function beginEdit(" in source
    assert "function saveEdit(" in source
    assert "function deleteComment(" in source
