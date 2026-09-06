from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SERVICE = ROOT / "almdina_erp" / "services" / "notes_service.py"
REPOSITORY = ROOT / "almdina_erp" / "infrastructure" / "frappe" / "notes_repository.py"


def test_note_mutation_python_sources_compile() -> None:
    ast.parse(SERVICE.read_text(encoding="utf-8"))
    ast.parse(REPOSITORY.read_text(encoding="utf-8"))
