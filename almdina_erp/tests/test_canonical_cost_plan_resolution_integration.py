from __future__ import annotations

import json
from collections.abc import Mapping

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import now_datetime

from almdina_erp.almdina_erp.domain.cutting.plan_lifecycle import (
    APPROVED,
    DRAFT,
    SYSTEM,
    UPLOADED_DXF,
)
from almdina_erp.almdina_erp.infrastructure.frappe.cutting_plan_runtime_repository import (
    resolve_canonical_cost_plan,
)
from almdina_erp.almdina_erp.services.cost_document_service import _document_context
from almdina_erp.almdina_erp.services.cost_permission_service import _cost_snapshot


class TestCanonicalCostPlanResolutionIntegration(FrappeTestCase):
    """Exercise resolver + cost/document projections against real Frappe tables."""

    def setUp(self) -> None:
        super().setUp()
        token = frappe.generate_hash(length=8)
        self.order_name = f"TEST-DCO-CANON-{token}"
        self._insert(
            "Door Cutting Order",
            {
                "name": self.order_name,
                **self._standard_columns(),
                "status": "Draft",
                "revision": 1,
                "board_description": "TEST MDF",
                "board_rate_usd": 999,
                "cutting_cost_per_board_usd": 99,
                "mdf_cost_usd": 999,
                "cutting_cost_usd": 99,
                "total_cost_usd": 1098,
            },
        )
        self.piece_name = f"TEST-DCO-ROW-{token}"
        self._insert(
            "Door Cutting Order Detail",
            {
                "name": self.piece_name,
                **self._standard_columns(),
                "parent": self.order_name,
                "parenttype": "Door Cutting Order",
                "parentfield": "pieces",
                "idx": 1,
                "piece_no": 1,
                "piece_type": "Regular",
                "qty": 2,
                "edge_meters": 4,
                "edge_cost_usd": 2,
            },
        )

    def tearDown(self) -> None:
        frappe.db.delete("Door Cutting Order Detail", {"parent": self.order_name})
        frappe.db.delete("Cutting Plan", {"door_cutting_order": self.order_name})
        frappe.db.delete("Door Cutting Order", {"name": self.order_name})
        super().tearDown()

    @staticmethod
    def _standard_columns() -> dict[str, object]:
        now = now_datetime()
        return {
            "owner": "Administrator",
            "creation": now,
            "modified": now,
            "modified_by": "Administrator",
            "docstatus": 0,
            "idx": 0,
        }

    @staticmethod
    def _insert(doctype: str, values: Mapping[str, object]) -> None:
        columns = list(values)
        quoted = ", ".join(f"`{column}`" for column in columns)
        placeholders = ", ".join(["%s"] * len(columns))
        frappe.db.sql(
            f"INSERT INTO `tab{doctype}` ({quoted}) VALUES ({placeholders})",
            tuple(values[column] for column in columns),
        )

    def _snapshot(
        self,
        *,
        full_boards: int,
        customer_offcut_copies: int = 0,
        factory_offcut_copies: int = 0,
    ) -> str:
        sheets: list[dict[str, object]] = []
        copy_no = 0
        for sheet_no in range(1, full_boards + 1):
            copy_no += 1
            sheets.append(
                {
                    "sheet_no": sheet_no,
                    "resource_kind": "FULL_BOARD",
                    "pieces": [
                        {
                            "piece_instance_id": f"piece:{copy_no}",
                            "source_piece_no": 1,
                            "resource_kind": "FULL_BOARD",
                        }
                    ],
                }
            )
        for _ in range(customer_offcut_copies):
            copy_no += 1
            sheets.append(
                {
                    "sheet_no": len(sheets) + 1,
                    "resource_kind": "OFFCUT",
                    "pieces": [
                        {
                            "piece_instance_id": f"piece:{copy_no}",
                            "source_piece_no": 1,
                            "resource_kind": "OFFCUT",
                            "offcut_source_party": "CUSTOMER",
                            "offcut_execution_party": "CUSTOMER",
                        }
                    ],
                }
            )
        for _ in range(factory_offcut_copies):
            copy_no += 1
            sheets.append(
                {
                    "sheet_no": len(sheets) + 1,
                    "resource_kind": "OFFCUT",
                    "pieces": [
                        {
                            "piece_instance_id": f"piece:{copy_no}",
                            "source_piece_no": 1,
                            "resource_kind": "OFFCUT",
                            "offcut_source_party": "FACTORY",
                            "offcut_execution_party": "FACTORY",
                        }
                    ],
                }
            )
        return json.dumps(
            {
                "physical_execution_contract": 1,
                "sheets": sheets,
            }
        )

    def _plan(
        self,
        name: str,
        *,
        revision: int,
        status: str,
        source_type: str,
        required_boards: int,
        mdf_cost_usd: float,
        cutting_cost_usd: float,
        snapshot_json: str,
        offcut_price_usd: float = 0,
        waste_area_m2: float = 0,
        waste_percent: float = 0,
    ) -> str:
        self._insert(
            "Cutting Plan",
            {
                "name": name,
                **self._standard_columns(),
                "door_cutting_order": self.order_name,
                "plan_kind": "Order",
                "revision": revision,
                "status": status,
                "source_type": source_type,
                "snapshot_json": snapshot_json,
                "required_boards": required_boards,
                "cost_snapshot_version": 1,
                "board_rate_usd": 22,
                "cutting_cost_per_board_usd": 2.5,
                "mdf_cost_usd": mdf_cost_usd,
                "cutting_cost_usd": cutting_cost_usd,
                "edge_cost_usd": 0,
                "total_cost_usd": mdf_cost_usd + cutting_cost_usd + offcut_price_usd,
                "offcut_price_usd": offcut_price_usd,
                "waste_area_m2": waste_area_m2,
                "waste_percent": waste_percent,
            },
        )
        return name

    def test_resolution_priority_is_system_then_uploaded_then_official_approved(self) -> None:
        system = self._plan(
            f"{self.order_name}-SYSTEM",
            revision=1,
            status=DRAFT,
            source_type=SYSTEM,
            required_boards=4,
            mdf_cost_usd=88,
            cutting_cost_usd=10,
            snapshot_json=self._snapshot(full_boards=4),
        )
        order = frappe.get_doc("Door Cutting Order", self.order_name)
        self.assertEqual(resolve_canonical_cost_plan(order).name, system)

        uploaded = self._plan(
            f"{self.order_name}-DXF",
            revision=2,
            status=DRAFT,
            source_type=UPLOADED_DXF,
            required_boards=3,
            mdf_cost_usd=66,
            cutting_cost_usd=7.5,
            snapshot_json=self._snapshot(full_boards=3),
        )
        self.assertEqual(resolve_canonical_cost_plan(order).name, uploaded)

        approved = self._plan(
            f"{self.order_name}-APPROVED",
            revision=3,
            status=APPROVED,
            source_type=UPLOADED_DXF,
            required_boards=2,
            mdf_cost_usd=44,
            cutting_cost_usd=5,
            snapshot_json=self._snapshot(full_boards=2),
        )
        frappe.db.set_value(
            "Door Cutting Order",
            self.order_name,
            "approved_plan",
            approved,
            update_modified=False,
        )
        order = frappe.get_doc("Door Cutting Order", self.order_name)

        self._plan(
            f"{self.order_name}-NEWER-SYSTEM",
            revision=10,
            status=DRAFT,
            source_type=SYSTEM,
            required_boards=9,
            mdf_cost_usd=198,
            cutting_cost_usd=22.5,
            snapshot_json=self._snapshot(full_boards=9),
        )
        self._plan(
            f"{self.order_name}-NEWER-DXF",
            revision=11,
            status=DRAFT,
            source_type=UPLOADED_DXF,
            required_boards=8,
            mdf_cost_usd=176,
            cutting_cost_usd=20,
            snapshot_json=self._snapshot(full_boards=8),
        )
        self.assertEqual(resolve_canonical_cost_plan(order).name, approved)

    def test_cost_workspace_and_document_context_share_exact_approved_plan(self) -> None:
        self._plan(
            f"{self.order_name}-SYSTEM",
            revision=8,
            status=DRAFT,
            source_type=SYSTEM,
            required_boards=9,
            mdf_cost_usd=198,
            cutting_cost_usd=22.5,
            snapshot_json=self._snapshot(full_boards=9),
            waste_area_m2=90,
            waste_percent=90,
        )
        self._plan(
            f"{self.order_name}-DXF",
            revision=9,
            status=DRAFT,
            source_type=UPLOADED_DXF,
            required_boards=7,
            mdf_cost_usd=154,
            cutting_cost_usd=17.5,
            snapshot_json=self._snapshot(full_boards=7),
            waste_area_m2=70,
            waste_percent=70,
        )
        approved = self._plan(
            f"{self.order_name}-APPROVED",
            revision=3,
            status=APPROVED,
            source_type=UPLOADED_DXF,
            required_boards=1,
            mdf_cost_usd=22,
            cutting_cost_usd=2.5,
            snapshot_json=self._snapshot(full_boards=1, customer_offcut_copies=1),
            waste_area_m2=1.25,
            waste_percent=12.5,
        )
        frappe.db.set_value(
            "Door Cutting Order",
            self.order_name,
            "approved_plan",
            approved,
            update_modified=False,
        )
        order = frappe.get_doc("Door Cutting Order", self.order_name)

        cost = _cost_snapshot(order)
        document_order, document_pieces = _document_context(order)

        self.assertEqual(cost["cutting_plan"], approved)
        self.assertEqual(cost["order"]["required_boards"], 1)
        self.assertEqual(cost["order"]["mdf_cost_usd"], 22)
        self.assertEqual(cost["order"]["waste_percent"], 12.5)
        self.assertEqual(cost["pieces"][0]["qty"], 2)
        self.assertEqual(cost["pieces"][0]["factory_execution_qty"], 1)

        self.assertEqual(document_order["required_boards"], 1)
        self.assertEqual(document_order["mdf_cost_usd"], 22)
        self.assertEqual(document_order["waste_percent"], 12.5)
        self.assertEqual(document_pieces[0]["qty"], 2)
        self.assertEqual(document_pieces[0]["factory_execution_qty"], 1)

    def test_factory_offcut_applicability_and_zero_new_board_count_share_plan(self) -> None:
        uploaded = self._plan(
            f"{self.order_name}-DXF",
            revision=2,
            status=DRAFT,
            source_type=UPLOADED_DXF,
            required_boards=0,
            mdf_cost_usd=0,
            cutting_cost_usd=0,
            offcut_price_usd=8.5,
            snapshot_json=self._snapshot(full_boards=0, factory_offcut_copies=1),
        )
        order = frappe.get_doc("Door Cutting Order", self.order_name)
        cost = _cost_snapshot(order)

        self.assertEqual(cost["cutting_plan"], uploaded)
        self.assertEqual(cost["order"]["required_boards"], 0)
        self.assertEqual(cost["order"]["mdf_cost_usd"], 0)
        self.assertTrue(cost["order"]["offcut_price_applicable"])
        self.assertEqual(cost["order"]["offcut_price_usd"], 8.5)
