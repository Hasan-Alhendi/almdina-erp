from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch

import frappe

from almdina_erp.almdina_erp.services import (
    cutting_plan_command_service as command_service,
)
from almdina_erp.almdina_erp.services import plan_settings_edit_service as service


ROOT = Path(__file__).resolve().parents[1]
CUTTING_PLAN = ROOT / "public" / "js" / "door_cutting_order" / "cutting_plan"
EDIT_SESSION = CUTTING_PLAN / "door_cutting_order_plan_edit_session_ux.js"
FIELD_ACCESS = CUTTING_PLAN / "door_cutting_order_plan_field_access_adapter.js"
MANIFEST = ROOT / "frontend_assets.py"
SERVICE = ROOT / "almdina_erp" / "services" / "plan_settings_edit_service.py"
COMMAND_SERVICE = ROOT / "almdina_erp" / "services" / "cutting_plan_command_service.py"


def source(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _door_cutting_order_assets(manifest: str) -> str:
    return manifest.split('"Door Cutting Order": [', 1)[1].split(
        '],\n    "Edge Banding Type"', 1
    )[0]


def _field(label: str, options: str = "") -> SimpleNamespace:
    return SimpleNamespace(label=label, options=options)


def _cutting_plan_meta() -> SimpleNamespace:
    fields = {
        "optimization_mode": _field(
            "Optimization Mode",
            "Auto\nAuto Pro\nDeep Search\nOptimal Search\nMaxRects Best Short Side\nMaxRects Best Area\nMaxRects Bottom Left\nMaxRects Contact Point\nMaxRects Width\nMaxRects Length\nShelf Horizontal\nShelf Vertical\nShelf First Fit\nShelf Next Fit\nGuillotine Short Axis\nGuillotine Long Axis\nGuillotine Best Area Fit\nGuillotine Best Short Side Fit\nGuillotine Best Long Side Fit\nSkyline Bottom Left\nSkyline Best Fit",
        ),
        "machine_type": _field(
            "Cutting Machine Type",
            "Auto\nCNC Router\nPanel Saw",
        ),
        "kerf_mm": _field("Kerf MM"),
        "trim_margin_mm": _field("Trim Margin MM"),
        "optimization_time_limit_sec": _field("Optimization Time Limit Sec"),
    }
    return SimpleNamespace(get_field=lambda fieldname: fields.get(fieldname))


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
    assert "context.canTuneCuttingAlgorithm(frm)" not in edit_session
    assert "function lifecycleAllowsEdit(frm)" in edit_session
    assert "function hasActiveRoutedLifecycle(frm)" in edit_session
    assert '"At Drawing"' in edit_session

    assert "dco-plan-settings-edit" in edit_session
    assert "dco-plan-settings-save" in edit_session
    assert "dco-plan-settings-cancel" in edit_session
    assert '${__("تعديل")}' in edit_session
    assert '${__("حفظ")}' in edit_session
    assert '${__("إلغاء")}' in edit_session

    assert "window.AlmdinaPlanEditSessionUX" in adapter
    assert "editor.planSettingsMayWrite(frm)" in adapter
    assert 'field.df[STATUS_KEY] = editingAllowed ? "Write" : "Read"' in adapter
    assert 'frm.set_df_property(fieldname, "read_only", desiredReadOnly)' in adapter
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


def test_focused_save_contract_delegates_persistence_to_plan_command_owner() -> None:
    backend = source(SERVICE)
    command_backend = source(COMMAND_SERVICE)
    frontend = source(EDIT_SESSION)

    assert "plan_settings_edit_service.save_plan_settings" in frontend
    assert "require_cutting_plan_capability(" in backend
    assert "Capability.EDIT_OPTIMIZER_SETTINGS" in backend
    assert "require_stage_operational_access" not in backend
    assert "SHOP_FLOOR_ORDER_STATUSES" in backend
    assert "save_system_plan_settings" in backend
    assert "frappe.db.set_value(" not in backend
    assert "ignore_permissions" not in backend
    assert "doc.save(" not in backend
    assert "order.save(" not in backend

    assert "FrappeCuttingPlanCommandRepository" in command_backend
    assert "require_cutting_plan_capability(" in command_backend
    assert '"plan_needs_recalculation"' in command_backend
    assert "ignore_permissions" not in command_backend
    assert "order.save(" not in command_backend


class TestPlanSettingsEditService(TestCase):
    def test_routed_order_with_active_stage_uses_focused_capability_not_stage_role(self) -> None:
        doc = FakeOrder(
            status="In Production",
            current_production_stage="STAGE-001",
            production_path="ROUTE-001",
        )

        # The whitelist command has already required EDIT_OPTIMIZER_SETTINGS.
        # Lifecycle validation must not add a second current-worker role gate.
        service.assert_plan_settings_edit_lifecycle(doc)

    def test_routed_order_at_drawing_allows_edit_without_stage_snapshot(self) -> None:
        doc = FakeOrder(
            status="At Drawing",
            current_production_stage=None,
            production_path="ROUTE-DRAWING",
        )

        service.assert_plan_settings_edit_lifecycle(doc)

    def test_finished_routed_order_without_active_stage_fails_closed(self) -> None:
        doc = FakeOrder(
            status="Completed",
            current_production_stage=None,
            production_path="ROUTE-001",
        )

        with self.assertRaises(frappe.PermissionError):
            service.assert_plan_settings_edit_lifecycle(doc)

    def test_save_delegates_normalized_settings_to_plan_command_owner(self) -> None:
        doc = FakeOrder()
        expected = {
            "changed_fields": ["packing_mode", "kerf_mm"],
            "plan_needs_recalculation": 1,
        }

        with (
            patch.object(service.frappe.db, "sql") as lock_row,
            patch.object(service.frappe, "get_doc", return_value=doc),
            patch.object(service.frappe, "get_meta", return_value=_cutting_plan_meta()),
            patch.object(service, "require_cutting_plan_capability") as capability_gate,
            patch.object(
                command_service,
                "save_system_plan_settings",
                return_value=expected,
            ) as save_command,
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
        save_command.assert_called_once_with(
            doc,
            {
                "packing_mode": "Auto Pro",
                "cutting_machine_type": "Panel Saw",
                "kerf_mm": 4.0,
                "trim_margin_mm": 5.0,
                "optimization_time_limit_sec": 10.0,
            },
        )
        self.assertEqual(result, expected)

    def test_save_at_drawing_without_stage_snapshot_uses_focused_capability(self) -> None:
        doc = FakeOrder(
            status="At Drawing",
            current_production_stage=None,
            production_path="ROUTE-DRAWING",
        )
        expected = {
            "changed_fields": ["kerf_mm"],
            "plan_needs_recalculation": 1,
        }

        with (
            patch.object(service.frappe.db, "sql"),
            patch.object(service.frappe, "get_doc", return_value=doc),
            patch.object(service.frappe, "get_meta", return_value=_cutting_plan_meta()),
            patch.object(service, "require_cutting_plan_capability") as capability_gate,
            patch.object(
                command_service,
                "save_system_plan_settings",
                return_value=expected,
            ) as save_command,
        ):
            result = service.save_plan_settings(
                order_name=doc.name,
                kerf_mm=4,
            )

        capability_gate.assert_called_once()
        save_command.assert_called_once_with(doc, {"kerf_mm": 4.0})
        self.assertEqual(result, expected)

    def test_negative_plan_setting_is_rejected_before_persistence(self) -> None:
        with (
            patch.object(service.frappe, "get_meta", return_value=_cutting_plan_meta()),
            self.assertRaises(frappe.ValidationError),
        ):
            service.normalize_plan_settings_updates({"kerf_mm": -1})
