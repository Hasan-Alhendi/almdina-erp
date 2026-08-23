from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from almdina_erp.almdina_erp.services import cutting_plan_workspace_query_service as query_service


APP_ROOT = Path(__file__).resolve().parents[1]
PRESENTER = (
    APP_ROOT
    / "public"
    / "js"
    / "door_cutting_order"
    / "cutting_plan"
    / "door_cutting_order_plan_workspace_presenter_adapter.js"
)
PLAN_EDIT = (
    APP_ROOT
    / "public"
    / "js"
    / "door_cutting_order"
    / "cutting_plan"
    / "door_cutting_order_plan_edit_session_ux.js"
)
QUERY_SERVICE = (
    APP_ROOT
    / "almdina_erp"
    / "services"
    / "cutting_plan_workspace_query_service.py"
)


def _row(
    *,
    name: str,
    status: str,
    source_type: str,
    revision: int,
    optimization_mode: str,
    machine_type: str = "Auto",
    timeout: float = 10,
    kerf: float = 3,
    trim: float = 5,
) -> dict:
    return {
        "name": name,
        "status": status,
        "source_type": source_type,
        "revision": revision,
        "optimization_mode": optimization_mode,
        "machine_type": machine_type,
        "optimization_time_limit_sec": timeout,
        "kerf_mm": kerf,
        "trim_margin_mm": trim,
    }


def test_edit_seed_prefers_existing_system_draft_over_newer_other_source():
    rows = [
        _row(
            name="CP-UPLOADED-3",
            status="Draft",
            source_type="Uploaded DXF",
            revision=3,
            optimization_mode="Deep Search",
        ),
        _row(
            name="CP-SYSTEM-2",
            status="Draft",
            source_type="System",
            revision=2,
            optimization_mode="Auto Pro",
            kerf=4,
        ),
        _row(
            name="CP-APPROVED-1",
            status="Approved",
            source_type="System",
            revision=1,
            optimization_mode="Optimal Search",
        ),
    ]

    settings = query_service._editable_settings(rows)

    assert settings["packing_mode"] == "Auto Pro"
    assert settings["kerf_mm"] == 4


def test_edit_seed_inherits_latest_approved_when_system_draft_does_not_exist():
    rows = [
        _row(
            name="CP-APPROVED-4",
            status="Approved",
            source_type="Uploaded DXF",
            revision=4,
            optimization_mode="Optimal Search",
            trim=7,
        ),
        _row(
            name="CP-OLD-3",
            status="Superseded",
            source_type="System",
            revision=3,
            optimization_mode="Auto",
        ),
    ]

    settings = query_service._editable_settings(rows)

    assert settings["packing_mode"] == "Optimal Search"
    assert settings["trim_margin_mm"] == 7


def test_edit_seed_uses_factory_defaults_without_persisting_a_plan():
    defaults = SimpleNamespace(
        optimization_mode="Auto Pro",
        machine_type="Panel Saw",
        optimization_time_limit_sec=18,
        kerf_mm=3.2,
        trim_margin_mm=4.5,
    )
    with patch.object(query_service, "factory_default_plan_settings", return_value=defaults) as factory_defaults:
        settings = query_service._editable_settings([])

    factory_defaults.assert_called_once_with()
    assert settings == {
        "packing_mode": "Auto Pro",
        "cutting_machine_type": "Panel Saw",
        "optimization_time_limit_sec": 18.0,
        "kerf_mm": 3.2,
        "trim_margin_mm": 4.5,
    }


def test_workspace_exposes_edit_seed_only_to_optimizer_editors():
    source = QUERY_SERVICE.read_text(encoding="utf-8")

    assert '"editable_settings": _editable_settings(rows) if capabilities["edit_settings"] else None' in source
    assert "factory_default_plan_settings" in source
    assert "ensure_system_draft" not in source


def test_frontend_uses_editable_seed_before_requiring_an_existing_plan_row():
    presenter_source = PRESENTER.read_text(encoding="utf-8")
    edit_source = PLAN_EDIT.read_text(encoding="utf-8")

    assert "const editable = payload && payload.editable_settings" in presenter_source
    assert "if (editable) return { ...editable }" in presenter_source
    assert "const seed = activeSettings(frm);" in edit_source
    assert 'translate("لا توجد خطة قص قابلة لتعديل الإعدادات حاليًا.")' in edit_source
