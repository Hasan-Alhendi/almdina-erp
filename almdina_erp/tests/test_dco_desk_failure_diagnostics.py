from __future__ import annotations

import ast
from pathlib import Path


APP_ROOT = Path(__file__).resolve().parents[1]
DESK_RUNNER = APP_ROOT / "ci" / "dco_frappe_desk_recovery.py"
WORKFLOW = APP_ROOT.parent / ".github" / "workflows" / "frappe-v16-integration.yml"


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
    local_gate = next(
        node for node in tree.body
        if isinstance(node, ast.FunctionDef)
        and node.name == "certify_new_dco_local_gate"
    )
    smoke = next(
        node for node in tree.body
        if isinstance(node, ast.FunctionDef)
        and node.name == "certify_new_dco_form_smoke"
    )
    transition = next(
        node for node in tree.body
        if isinstance(node, ast.FunctionDef)
        and node.name == "certify_edit_to_new_transition"
    )
    form_loader = next(
        node for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "active_form_page"
    )
    edit_certification = next(
        node for node in tree.body
        if isinstance(node, ast.FunctionDef)
        and node.name == "certify_actual_frappe_desk_edit_recovery"
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
    assert [argument.arg for argument in local_gate.args.args] == ["browser"]
    assert "browser.new_context()" in ast.unparse(local_gate)
    assert "cur_frm" not in ast.unparse(certification)
    assert "cur_frm" not in ast.unparse(smoke)
    assert "open_new_dco_form" in ast.unparse(certification)
    assert "form-page:visible" in ast.unparse(form_loader)
    assert "wait_for_customer_interactive" in ast.unparse(certification)
    assert "step_started" in source
    assert "certify_edit_to_new_transition(page)" in ast.unparse(edit_certification)
    assert "certify_new_dco_local_gate(browser)" in ast.unparse(edit_certification)
    assert "browser.new_context()" in ast.unparse(local_gate)
    assert "open_new_dco_form" in ast.unparse(transition)
    assert "wait_for_customer_interactive" in ast.unparse(transition)


def test_page_failure_diagnostics_respect_page_lifecycle_and_trace_ui_steps() -> None:
    source = DESK_RUNNER.read_text(encoding="utf-8")
    tree = ast.parse(source)
    ui_step = next(
        node for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "ui_step"
    )
    safe_url = next(
        node for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "_safe_page_url"
    )
    attach = next(
        node for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "attach_browser_diagnostics"
    )
    dom_capture = next(
        node for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "capture_new_form_dom_evidence"
    )
    document_capture = next(
        node for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "capture_page_document_state"
    )
    navigation_handler = next(
        node for node in ast.walk(attach)
        if isinstance(node, ast.FunctionDef) and node.name == "on_frame_navigated"
    )
    state_reader = next(
        node for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "read_page_state"
    )

    ui_step_source = ast.unparse(ui_step)
    assert ui_step_source.index("step_started") < ui_step_source.index("result = action()")
    assert 'page.on("close"' in source
    assert 'page.on("crash"' in source
    assert 'page.on("framenavigated"' in source
    assert "page.url" not in ast.unparse(state_reader)
    assert "page.evaluate" not in ast.unparse(state_reader)
    assert "page.url" not in ast.unparse(safe_url)
    assert "lifecycle['url'] = frame.url" in ast.unparse(navigation_handler)
    assert "screenshot_skipped_after_failure" in source
    assert "page.screenshot" not in source
    assert "diagnostic_page = LAST_ACTIVE_PAGE or page" in source
    assert "page.evaluate" not in ast.unparse(dom_capture)
    assert "page.evaluate" not in ast.unparse(document_capture)
    assert "form_page.evaluate" not in ast.unparse(dom_capture)
    assert "timeout=5000" in ast.unparse(dom_capture)
    assert "timeout=5000" in ast.unparse(document_capture)
    assert "page.evaluate" not in ast.unparse(attach)


def test_customer_field_smoke_is_independent_of_recovery_and_has_dispatch_input() -> None:
    source = DESK_RUNNER.read_text(encoding="utf-8")
    tree = ast.parse(source)
    field_smoke = next(
        node for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "certify_new_customer_field_smoke"
    )
    main = next(
        node for node in tree.body
        if isinstance(node, ast.If) and isinstance(node.test, ast.Compare)
        and isinstance(node.test.left, ast.Name) and node.test.left.id == "__name__"
    )
    workflow = WORKFLOW.read_text(encoding="utf-8")
    field_smoke_source = ast.unparse(field_smoke)

    assert "wait_for_new_form_loaded" in field_smoke_source
    assert "wait_for_customer_interactive" in field_smoke_source
    assert "to_have_value(customer_name)" in field_smoke_source
    assert ".awesomplete li" in field_smoke_source
    assert "Recovery" not in field_smoke_source
    assert "DCO_DESK_NEW_CUSTOMER_FIELD_SMOKE_ONLY" in ast.unparse(main)
    assert ast.unparse(main).index("certify_new_dco_form_smoke(page)") < ast.unparse(main).index("certify_new_customer_field_smoke(page)")
    assert "new_customer_field_smoke_only:" in workflow
    assert "inputs.new_customer_field_smoke_only != true" in workflow
    assert "DCO_DESK_NEW_CUSTOMER_FIELD_SMOKE_ONLY:" in workflow


def test_interrupt_trace_records_active_or_last_failed_step() -> None:
    source = DESK_RUNNER.read_text(encoding="utf-8")
    assert 'step=ACTIVE_STEP or LAST_FAILED_STEP' in source
