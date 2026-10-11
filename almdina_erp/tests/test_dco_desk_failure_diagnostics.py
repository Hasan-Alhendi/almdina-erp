from __future__ import annotations

import ast
from pathlib import Path


APP_ROOT = Path(__file__).resolve().parents[1]
DESK_RUNNER = APP_ROOT / "ci" / "dco_frappe_desk_recovery.py"


def test_desk_timeout_diagnostics_use_cached_state_without_reentering_browser() -> None:
    tree = ast.parse(DESK_RUNNER.read_text(encoding="utf-8"))
    reader = next(
        node for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "read_page_state"
    )
    browser_calls = {
        node.func.attr
        for node in ast.walk(reader)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "page"
    }

    assert "evaluate" not in browser_calls
    assert "wait_for_load_state" not in browser_calls
    assert "wait_for_timeout" not in browser_calls
    assert "LAST_PAGE_STATE" in ast.unparse(reader)
