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


def test_new_recovery_probe_starts_without_a_post_readiness_evaluate() -> None:
    source = DESK_RUNNER.read_text(encoding="utf-8")
    tree = ast.parse(source)
    probe_script = next(
        ast.literal_eval(node.value)
        for node in tree.body
        if isinstance(node, ast.Assign)
        and any(
            isinstance(target, ast.Name)
            and target.id == "NEW_RECOVERY_PROBE_INIT_SCRIPT"
            for target in node.targets
        )
    )
    probe = next(
        node for node in tree.body
        if isinstance(node, ast.FunctionDef)
        and node.name == "certify_new_recovery_discovery_probe"
    )
    calls = [
        node for node in ast.walk(probe)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "page"
    ]
    assert not [node for node in calls if node.func.attr == "evaluate"]
    assert any(node.func.attr == "wait_for_function" for node in calls)
    assert "startNewFormProbe" in probe_script
    assert "explicit_probe_started" in probe_script
    assert "explicit_probe_settled" in probe_script
    assert "Promise.resolve(promise).then" in probe_script
    assert "LocalDraftRepository.discover" in ast.unparse(probe)
    assert "NewRecovery.discover" in ast.unparse(probe)
    assert "LocalCheckpoint.initializeNewForm" in ast.unparse(probe)
    assert '"IndexedDB.transaction"' in source
