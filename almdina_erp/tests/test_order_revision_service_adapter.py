from __future__ import annotations

import copy
import importlib.util
import sys
import types
import unittest
from pathlib import Path
from types import SimpleNamespace
from typing import Any


SERVICE_PATH = (
    Path(__file__).resolve().parents[1]
    / "almdina_erp"
    / "services"
    / "order_revision_service.py"
)
GATEWAY_MODULE = (
    "almdina_erp.almdina_erp.infrastructure.frappe.authorization_gateway"
)


class FakeOrder(SimpleNamespace):
    def __init__(self, **values: Any) -> None:
        super().__init__(**values)
        self.flags = SimpleNamespace()
        self.comments: list[str] = []
        self.inserted = False

    def check_permission(self, permission: str) -> None:
        self.checked_permission = permission

    def set(self, fieldname: str, value: Any) -> None:
        setattr(self, fieldname, value)

    def insert(self, ignore_permissions: bool = False) -> None:
        self.inserted = True
        self.ignore_permissions = ignore_permissions
        self.name = "DCO-REVISION-00002"

    def add_comment(self, comment_type: str, text: str) -> None:
        self.comments.append(text)


class FakeDatabase:
    def __init__(self) -> None:
        self.sql_calls: list[tuple[str, tuple[Any, ...]]] = []
        self.set_calls: list[tuple[Any, ...]] = []

    def sql(self, query: str, values: tuple[Any, ...]) -> list[Any]:
        self.sql_calls.append((query, values))
        return []

    def get_value(self, *args: Any, **kwargs: Any) -> Any:
        return None

    def set_value(self, *args: Any, **kwargs: Any) -> None:
        self.set_calls.append(args)


class RevisionHarness:
    def __init__(self) -> None:
        self.db = FakeDatabase()
        self.source = FakeOrder(
            name="DCO-ORIGINAL-00001",
            status="Approved",
            revision=3,
            revision_root=None,
            superseded_by=None,
            approved_plan="CUT-PLAN-00001",
            approved_plan_source="System",
            production_path=None,
            current_department=None,
            current_assignee=None,
            department_status=None,
            current_production_stage=None,
            production_dxf=None,
            drawing_dxf_status="None",
            packing_method="MaxRects",
            packing_score="score",
            engine_version="2.1",
            cutting_plan_json='{"sheets": [{}]}',
            system_plan_json='{"sheets": [{}]}',
            custom_plan_json="",
            calculated_plan_input_hash="input",
            calculated_plan_metadata_hash="metadata",
            plan_needs_recalculation=0,
            material_variance_cost_usd=5,
            internal_loss_cost_usd=2,
            actual_cost_usd=100,
            pieces=[
                SimpleNamespace(
                    piece_type="Special",
                    special_shape_custom_unit_price_usd=20,
                    special_shape_price_status="Approved",
                    special_shape_price_note="approved",
                    special_shape_price_approved_by="accounts@example.com",
                    special_shape_price_approved_on="2026-01-01",
                )
            ],
        )
        self.revised: FakeOrder | None = None

    def load(self):
        fake_frappe = types.ModuleType("frappe")
        fake_frappe.db = self.db
        fake_frappe.PermissionError = RuntimeError
        fake_frappe._ = lambda message: message
        fake_frappe.whitelist = lambda *args, **kwargs: (lambda fn: fn)
        fake_frappe.get_doc = lambda doctype, name: self.source

        def copy_doc(source: FakeOrder) -> FakeOrder:
            revised = copy.deepcopy(source)
            revised.comments = []
            revised.inserted = False
            self.revised = revised
            return revised

        fake_frappe.copy_doc = copy_doc

        def throw(message: str, *args: Any, **kwargs: Any) -> None:
            raise RuntimeError(message)

        fake_frappe.throw = throw

        fake_gateway = types.ModuleType(GATEWAY_MODULE)
        fake_gateway.doctype_has_capability = lambda *args, **kwargs: True

        previous_frappe = sys.modules.get("frappe")
        previous_gateway = sys.modules.get(GATEWAY_MODULE)
        sys.modules["frappe"] = fake_frappe
        sys.modules[GATEWAY_MODULE] = fake_gateway
        try:
            spec = importlib.util.spec_from_file_location(
                "_almdina_order_revision_service_adapter_test",
                SERVICE_PATH,
            )
            if spec is None or spec.loader is None:
                raise RuntimeError("Could not load order revision service")
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            return module
        finally:
            if previous_frappe is None:
                sys.modules.pop("frappe", None)
            else:
                sys.modules["frappe"] = previous_frappe
            if previous_gateway is None:
                sys.modules.pop(GATEWAY_MODULE, None)
            else:
                sys.modules[GATEWAY_MODULE] = previous_gateway


class TestOrderRevisionServiceAdapter(unittest.TestCase):
    def test_revision_preserves_original_and_resets_only_the_new_copy(self) -> None:
        harness = RevisionHarness()
        service = harness.load()

        result = service.create_order_revision(
            "DCO-ORIGINAL-00001",
            "Customer changed the measurements",
        )

        revised = harness.revised
        self.assertIsNotNone(revised)
        assert revised is not None

        self.assertEqual(harness.source.status, "Approved")
        self.assertEqual(harness.source.approved_plan, "CUT-PLAN-00001")
        self.assertEqual(revised.status, "Draft")
        self.assertIsNone(revised.approved_plan)
        self.assertEqual(revised.revision, 4)
        self.assertEqual(revised.revision_of, harness.source.name)
        self.assertEqual(revised.revision_root, harness.source.name)
        self.assertEqual(revised.revision_reason, "Customer changed the measurements")
        self.assertEqual(revised.plan_needs_recalculation, 1)
        self.assertTrue(revised.inserted)
        self.assertEqual(revised.pieces[0].special_shape_price_status, "Estimated")
        self.assertEqual(revised.pieces[0].special_shape_custom_unit_price_usd, 0)

        self.assertEqual(result["name"], "DCO-REVISION-00002")
        self.assertFalse(result["already_exists"])
        self.assertTrue(
            any(
                call[2:] == ("superseded_by", "DCO-REVISION-00002")
                for call in harness.db.set_calls
            )
        )
        self.assertIn(
            "Reason: Customer changed the measurements",
            harness.source.comments[0],
        )

    def test_revision_can_be_created_without_a_reason(self) -> None:
        harness = RevisionHarness()
        service = harness.load()

        result = service.create_order_revision("DCO-ORIGINAL-00001")

        revised = harness.revised
        self.assertIsNotNone(revised)
        assert revised is not None
        self.assertEqual(revised.revision_reason, "")
        self.assertTrue(revised.inserted)
        self.assertEqual(result["name"], "DCO-REVISION-00002")
        self.assertFalse(result["already_exists"])
        self.assertEqual(
            harness.source.comments,
            ["Controlled revision DCO-REVISION-00002 created."],
        )


if __name__ == "__main__":
    unittest.main()
