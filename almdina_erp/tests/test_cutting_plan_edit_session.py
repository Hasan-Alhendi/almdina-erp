from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch

import frappe

from almdina_erp.almdina_erp.services import plan_settings_edit_service as service


ROOT = Path(__file__).resolve().parents[1]
CUTTING_PLAN = ROOT / "public" / "js" / "door_cutting_order" / "cutting_plan"
EDIT_SESSION = CUTTING_PLAN / "door_cutting_order_plan_edit_session_ux.js"
FIELD_ACCESS = CUTTING_PLAN / "door_cutting_order_plan_field_access_adapter.js"
MANIFEST = ROOT / "frontend_assets.py"
SERVICE = ROOT / "almdina_erp" / "services" / "plan_settings_edit_service.py"


def source(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _door_cutting_order_assets(manifest: str) -> str:
    return manifest.split('"Door Cutting Order": [', 1)[1].split(
        '],\n    "Edge Banding Type"', 1
    )[0]


def _field(label: str, options: str = "") -> SimpleNamespace:
    return SimpleNamespace(label=label, options=options)


class FakeOrder:
    def __init__(self, **overrides):
        values = {
            "name": "DCO-TEST-PLAN-EDIT",
            "docstatus": 0,
            "approved_plan": 0,
            "revision_state": "Current",
            "status": "Draft",
            "current_production_stage": None,
            "production_path": None,
            "packing_mode": "Auto",
            "cutting_machine_type": "Panel Saw",
            "kerf_mm": 5.0,
            "trim_margin_mm": 5.0,
            "optimization_time_limit_sec": 10.0,
            "plan_needs_recalculation": 0,
        }
        values.update(overrides)
        for key, value in values.items():
            setattr(self, key, value)

        fields = {
            "packing_mode": _field(
                "طريقة ترتيب القطع",
                "Auto\nSkyline\nGuillotine\nGrid\nAuto Pro\nDeep Search\nOptimal Search",
            ),
            "cutting_machine_type": _field(
                "نوع آلة القص",
                "Panel Saw\nBeam Saw\nCNC Router",
            ),
            "kerf_mm": _field("سماكة خط المنشار"),
            "trim_margin_mm": _field("هامش تسوية الحواف"),
            "optimization_time_limit_sec": _field("مهلة البحث"),
        }
        self.meta = SimpleNamespace(get_field=lambda fieldname: fields.get(fieldname))
        self.checked_permissions: list[str] = []

    def get(self, fieldname: str):
        return getattr(self, fieldname, None)

    def check_permission(self, permission_type: str) -> None:
        self.checked_permissions.append(permission_type)


def test_plan_settings_are_read_only_until_explicit_edit_button() -> None:
    edit_session = source(EDIT_SESSION)
    adapter = source(FIELD_ACCESS)

    assert 'const EDITING_KEY = "__almdina_plan_settings_editing"' in edit_session
    assert "function planSettingsMayWrite(frm)" in edit_session
    assert "isEditing(frm) && canEditPlanSettings(frm)" in edit_session
    assert 'can(frm, "edit_optimizer_settings")' in edit_session
    assert "context.canTuneCuttingAlgorithm(frm)" in edit_session

    assert "dco-plan-settings-edit" in edit_session
    assert "dco-plan-settings-save" in edit_session
    assert "dco-plan-settings-cancel" in edit_session
    assert '${__("تعديل")}' in edit_session
    assert '${__("حفظ")}' in edit_session
    assert '${__("إلغاء")}' in edit_session

    assert "window.AlmdinaPlanEditSessionUX" in adapter
    assert "editor.planSettingsMayWrite(frm)" in adapter
    assert "!editor.planSettingsMayWrite(frm)" in adapter
    assert 'return "Read";' in adapter


def test_edit_session_loads_immediately_before_final_field_status_owner() -> None:
    dco_assets = _door_cutting_order_assets(source(MANIFEST))
    edit_session = (
        '"public/js/door_cutting_order/cutting_plan/door_cutting_order_plan_edit_session_ux.js"'
    )
    adapter = (
        '"public/js/door_cutting_order/cutting_plan/door_cutting_order_plan_field_access_adapter.js"'
    )

    assert dco_assets.count(edit_session) == 1
    assert dco_assets.count(adapter) == 1
    assert dco_assets.index(edit_session) < dco_assets.index(adapter)
    assert dco_assets.rstrip().endswith(adapter + ",")


def test_focused_save_contract_never_uses_broad_order_save_or_permission_bypass() -> None:
    backend = source(SERVICE)
    frontend = source(EDIT_SESSION)

    assert "plan_settings_edit_service.save_plan_settings" in frontend
    assert "require_document_capability(" in backend
    assert "Capability.EDIT_OPTIMIZER_SETTINGS" in backend
    assert "require_stage_operational_access(doc)" in backend
    assert 'frappe.db.set_value(' in backend
    assert '"plan_needs_recalculation"' in backend
    assert "ignore_permissions" not in backend
    assert "doc.save(" not in backend
    assert "order.save(" not in backend


class TestPlanSettingsEditService(TestCase):
    def test_routed_order_requires_current_stage_operational_access(self) -> None:
        doc = FakeOrder(
            status="In Production",
            current_production_stage="STAGE-001",
            production_path="ROUTE-001",
        )

        with patch.object(service, "require_stage_operational_access") as stage_gate:
            service._assert_edit_lifecycle(doc)

        stage_gate.assert_called_once_with(doc)

    def test_handed_off_order_fails_closed_when_stage_access_is_denied(self) -> None:
        doc = FakeOrder(
            status="Completed",
            current_production_stage=None,
            production_path="ROUTE-001",
        )

        with patch.object(
            service,
            "require_stage_operational_access",
            side_effect=frappe.PermissionError("not current stage actor"),
        ):
            with self.assertRaises(frappe.PermissionError):
                service._assert_edit_lifecycle(doc)

    def test_save_persists_only_changed_plan_settings_and_marks_plan_stale(self) -> None:
        doc = FakeOrder()

        with (
            patch.object(service.frappe.db, "sql") as lock_row,
            patch.object(service.frappe, "get_doc", return_value=doc),
            patch.object(service, "require_document_capability") as capability_gate,
            patch.object(service.frappe.db, "set_value") as set_value,
        ):
            result = service.save_plan_settings(
                order_name=doc.name,
                packing_mode="Auto Pro",
                cutting_machine_type="Panel Saw",
                kerf_mm=4,
                trim_margin_mm=5,
                optimization_time_limit_sec=10,
            )

        lock_row.assert_called_once()
        self.assertEqual(doc.checked_permissions, ["read"])
        capability_gate.assert_called_once()
        set_value.assert_called_once_with(
            "Door Cutting Order",
            doc.name,
            {
                "packing_mode": "Auto Pro",
                "kerf_mm": 4.0,
                "plan_needs_recalculation": 1,
            },
            update_modified=True,
        )
        self.assertEqual(result["changed_fields"], ["packing_mode", "kerf_mm"])
        self.assertEqual(result["plan_needs_recalculation"], 1)

    def test_negative_plan_setting_is_rejected_before_persistence(self) -> None:
        doc = FakeOrder()

        with self.assertRaises(frappe.ValidationError):
            service._normalize_updates(doc, {"kerf_mm": -1})
