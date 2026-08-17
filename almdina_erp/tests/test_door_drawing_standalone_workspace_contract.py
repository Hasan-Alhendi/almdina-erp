from __future__ import annotations

import json
from pathlib import Path


APP_ROOT = Path(__file__).resolve().parents[1]


def _read(relative_path: str) -> str:
    return (APP_ROOT / relative_path).read_text(encoding="utf-8")


def test_standalone_drawing_page_is_unrestricted_by_fixed_frappe_roles() -> None:
    payload = json.loads(
        _read("almdina_erp/page/door_drawing/door_drawing.json")
    )
    assert payload["name"] == "door-drawing"
    assert payload["page_name"] == "door-drawing"
    assert payload["roles"] == []


def test_special_shape_facade_routes_to_workspace_instead_of_opening_dialog() -> None:
    source = _read(
        "public/js/door_cutting_order/drawing/special_shape_facade.js"
    )
    assert 'const WORKSPACE_ROUTE = "door-drawing"' in source
    assert "frappe.set_route(WORKSPACE_ROUTE" in source
    assert "frm.save()" in source
    assert "frappe.ui.Dialog" not in source


def test_workspace_server_endpoint_keeps_capability_and_geometry_boundaries() -> None:
    source = _read(
        "almdina_erp/services/special_shape_workspace_service.py"
    )
    assert "Capability.VIEW_DRAWING_WORKSPACE" in source
    assert "Capability.EDIT_SPECIAL_DRAWING" in source
    assert "require_stage_operational_access(order)" in source
    assert "validate_special_shape_drawing" in source
    assert "validate_special_shape_geometry" in source
    assert "order.flags.allow_approved_edit = True" in source
    assert "order.save(ignore_permissions=True)" in source


def test_workspace_uses_existing_v4_runtime_instead_of_forking_geometry() -> None:
    page = _read("almdina_erp/page/door_drawing/door_drawing.js")
    session = _read(
        "public/js/door_drawing_v4/workspace/session_controller.js"
    )
    bootstrap = _read("public/js/door_drawing_v4/bootstrap.js")

    assert "/assets/almdina_erp/js/door_drawing_v4/bootstrap.js" in page
    assert "runtime.PersistenceAdapter.fromStored" in session
    assert "runtime.EditorController.create" in session
    assert "runtime.ManufacturingProjection.project" in session
    assert "/door_drawing_v4/domain/document.js" in bootstrap
    assert "/door_drawing_v4/application/constraint_solver.js" in bootstrap
    assert "/door_drawing_v4/application/snap_resolver.js" in bootstrap


def test_workspace_has_explicit_session_cleanup_and_unsaved_state() -> None:
    page = _read("almdina_erp/page/door_drawing/door_drawing.js")
    session = _read(
        "public/js/door_drawing_v4/workspace/session_controller.js"
    )
    assert "session.destroy()" in page
    assert 'shell.setSaveState("dirty", "غير محفوظ")' in session
    assert "editor.destroy()" in session
    assert "لديك تعديلات غير محفوظة" in session
