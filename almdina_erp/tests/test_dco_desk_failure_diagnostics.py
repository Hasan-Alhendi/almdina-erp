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


def test_route_diagnostics_tolerate_frappe_returning_no_route() -> None:
    source = DESK_RUNNER.read_text(encoding="utf-8")

    assert "Array.isArray(value) ? value.map(String).join(\"/\") : \"\"" in source
    assert "user=_redact_text(user" not in source
    assert "user: window.frappe" not in source


def test_new_local_gate_uses_desk_interactions_without_recovery_instrumentation() -> None:
    source = DESK_RUNNER.read_text(encoding="utf-8")
    tree = ast.parse(source)
    certification = next(
        node for node in tree.body
        if isinstance(node, ast.FunctionDef)
        and node.name == "certify_actual_frappe_desk_new_recovery"
    )
    stress = next(
        node for node in tree.body
        if isinstance(node, ast.FunctionDef)
        and node.name == "certify_new_dco_recovery_stress"
    )
    arguments = certification.args.kwonlyargs
    assert arguments[0].arg == "piece_count"
    assert ast.literal_eval(certification.args.kw_defaults[0]) == 10
    assert "NEW_RECOVERY_PROBE_INIT_SCRIPT" not in source
    assert "Object.defineProperty(window, \"AlmdinaDcoRecovery\"" not in source
    assert "new Proxy(value" not in source
    assert "page.add_init_script" not in ast.unparse(certification)
    assert "page.evaluate" not in ast.unparse(certification)
    assert "tbody tr.dco-virtual-row" in ast.unparse(certification)
    assert "page.reload" in ast.unparse(certification)
    assert 'data-recovery-action="continue"' in ast.unparse(certification)
    assert "expect_response" in ast.unparse(certification)
    assert "canonical_record_count=len(canonical_rows)" in ast.unparse(certification)
    assert "recovery_creation_token" in ast.unparse(certification)
    assert 'data-recovery-state=\'COMPLETED\'' in ast.unparse(certification)
    assert "range(piece_count)" in ast.unparse(certification)
    assert "initializeNewForm(frm)" not in ast.unparse(certification)
    assert "piece_count not in {200, 500}" in ast.unparse(stress)
