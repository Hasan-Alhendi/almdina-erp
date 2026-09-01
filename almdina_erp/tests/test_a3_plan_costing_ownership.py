from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import patch

import frappe

from almdina_erp.almdina_erp.application.costing.financial_documents import (
    build_customer_invoice_document,
)
from almdina_erp.almdina_erp.infrastructure.frappe import cutting_plan_costing_workspace as workspace
from almdina_erp.almdina_erp.services import cost_permission_service as cost_service
from almdina_erp.almdina_erp.services import cutting_plan_command_service as plan_commands
from almdina_erp.almdina_erp.services import cutting_plan_cost_command_service as cost_commands


class TestA3PlanCostingOwnership(unittest.TestCase):
    def test_plan_cost_formula_uses_plan_geometry_and_rates(self) -> None:
        plan = SimpleNamespace(
            required_boards=3,
            board_rate_usd=10,
            cutting_cost_per_board_usd=2,
            edge_cost_usd=5,
            mdf_cost_usd=0,
            cutting_cost_usd=0,
            total_cost_usd=0,
            cost_snapshot_version=0,
        )

        result = workspace.apply_plan_costs(plan)

        self.assertEqual(result["mdf_cost_usd"], 30)
        self.assertEqual(result["cutting_cost_usd"], 6)
        self.assertEqual(result["edge_cost_usd"], 5)
        self.assertEqual(result["total_cost_usd"], 41)
        self.assertEqual(plan.cost_snapshot_version, workspace.COST_SNAPSHOT_VERSION)

    def test_focused_cost_edit_preserves_geometry_and_freshness(self) -> None:
        plan = SimpleNamespace(
            name="CP-A3-001",
            source_type="System",
            status="Draft",
            required_boards=2,
            board_rate_usd=5,
            cutting_cost_per_board_usd=1,
            mdf_cost_usd=10,
            cutting_cost_usd=2,
            edge_cost_usd=3,
            total_cost_usd=15,
            cost_snapshot_version=1,
            snapshot_json='{"sheets":[{"sheet_no":1}]}',
            input_fingerprint="geometry-fingerprint",
            metadata_fingerprint="metadata-fingerprint",
            validation_status="Valid",
            plan_needs_recalculation=0,
        )
        order = SimpleNamespace(name="DCO-A3-001", cutting_plan_source="System")
        saved: list[SimpleNamespace] = []

        class FakeRepository:
            def __init__(self, capability: str):
                self.capability = capability

            def ensure_system_draft(self, _order):
                raise AssertionError("Cost settings must not create a system draft")

            def ensure_uploaded_dxf_draft(self, _order):
                raise AssertionError("System order must not create a DXF draft")

            def save_document(self, saved_plan):
                saved.append(saved_plan)
                return saved_plan

        with patch.object(cost_commands, "require_cutting_plan_capability"):
            with patch.object(cost_commands, "current_cost_plan", return_value=plan):
                with patch.object(cost_commands, "FrappeCuttingPlanCommandRepository", FakeRepository):
                    with patch.object(cost_commands, "initialize_draft_plan_cost_snapshot", return_value=False):
                        with patch.object(cost_commands, "refresh_order_commercial_totals"):
                            with patch.object(
                                cost_commands.frappe.db,
                                "get_value",
                                return_value={
                                    "board_rate_usd": 8,
                                    "cutting_cost_per_board_usd": 2,
                                },
                            ):
                                result = cost_commands.update_plan_cost_settings(
                                    order,
                                    board_rate_usd=8,
                                    cutting_cost_per_board_usd=2,
                                )

        self.assertEqual(len(saved), 1)
        self.assertEqual(plan.board_rate_usd, 8)
        self.assertEqual(plan.cutting_cost_per_board_usd, 2)
        self.assertEqual(plan.mdf_cost_usd, 16)
        self.assertEqual(plan.cutting_cost_usd, 4)
        self.assertEqual(plan.edge_cost_usd, 3)
        self.assertEqual(plan.total_cost_usd, 23)
        self.assertEqual(result["total_cost_usd"], 23)
        self.assertEqual(plan.snapshot_json, '{"sheets":[{"sheet_no":1}]}')
        self.assertEqual(plan.input_fingerprint, "geometry-fingerprint")
        self.assertEqual(plan.metadata_fingerprint, "metadata-fingerprint")
        self.assertEqual(plan.validation_status, "Valid")
        self.assertEqual(plan.plan_needs_recalculation, 0)

    def test_cost_edit_on_approved_plan_persists_rates_without_creating_a_draft(self) -> None:
        plan = SimpleNamespace(
            name="CP-A3-APPROVED",
            source_type="System",
            status="Approved",
            required_boards=2,
            board_rate_usd=5,
            cutting_cost_per_board_usd=1,
            mdf_cost_usd=10,
            cutting_cost_usd=2,
            edge_cost_usd=3,
            total_cost_usd=15,
            cost_snapshot_version=1,
            snapshot_json='{"sheets":[{"sheet_no":1}]}',
            input_fingerprint="geometry-fingerprint",
            metadata_fingerprint="metadata-fingerprint",
            validation_status="Valid",
            plan_needs_recalculation=0,
        )
        order = SimpleNamespace(name="DCO-A3-APPROVED")
        persisted: list[SimpleNamespace] = []
        fake_db = SimpleNamespace(
            get_value=lambda *_args, **_kwargs: {
                "board_rate_usd": 8,
                "cutting_cost_per_board_usd": 2,
            }
        )

        with patch.object(cost_commands, "_", lambda value: value):
            with patch.object(cost_commands.frappe, "db", fake_db):
                with patch.object(cost_commands, "require_cutting_plan_capability"):
                    with patch.object(cost_commands, "current_cost_plan", return_value=plan):
                        with patch.object(cost_commands, "FrappeCuttingPlanCommandRepository") as repository_cls:
                            with patch.object(cost_commands, "initialize_draft_plan_cost_snapshot", return_value=False):
                                with patch.object(
                                    cost_commands,
                                    "persist_plan_cost_snapshot",
                                    side_effect=lambda saved_plan: persisted.append(saved_plan) or {},
                                ):
                                    with patch.object(cost_commands, "refresh_order_commercial_totals"):
                                        result = cost_commands.update_plan_cost_settings(
                                            order,
                                            board_rate_usd=8,
                                            cutting_cost_per_board_usd=2,
                                        )

        repository_cls.assert_not_called()
        self.assertEqual(len(persisted), 1)
        self.assertEqual(plan.required_boards, 2)
        self.assertEqual(plan.board_rate_usd, 8)
        self.assertEqual(plan.cutting_cost_per_board_usd, 2)
        self.assertEqual(plan.mdf_cost_usd, 16)
        self.assertEqual(plan.cutting_cost_usd, 4)
        self.assertEqual(plan.total_cost_usd, 23)
        self.assertEqual(result["total_cost_usd"], 23)
        self.assertEqual(plan.snapshot_json, '{"sheets":[{"sheet_no":1}]}')
        self.assertEqual(plan.plan_needs_recalculation, 0)

    def test_current_cost_plan_prefers_draft_that_owns_boards(self) -> None:
        draft = SimpleNamespace(name="CP-DRAFT-BOARDS", status="Draft", required_boards=3)
        approved = SimpleNamespace(name="CP-APPROVED", status="Approved", required_boards=3)
        order = SimpleNamespace(name="DCO-COST-PLAN-1")

        def latest(_order_name, **filters):
            status = filters.get("status")
            if status == "Draft":
                return draft
            if status == "Approved":
                return approved
            return None

        with patch.object(workspace, "latest_plan", side_effect=latest):
            self.assertIs(workspace.current_cost_plan(order), draft)

    def test_current_cost_plan_ignores_empty_draft_when_approved_exists(self) -> None:
        draft = SimpleNamespace(name="CP-EMPTY-DRAFT", status="Draft", required_boards=0)
        approved = SimpleNamespace(name="CP-APPROVED", status="Approved", required_boards=4)
        order = SimpleNamespace(name="DCO-COST-PLAN-2")

        def latest(_order_name, **filters):
            status = filters.get("status")
            if status == "Draft":
                return draft
            if status == "Approved":
                return approved
            return None

        with patch.object(workspace, "latest_plan", side_effect=latest):
            self.assertIs(workspace.current_cost_plan(order), approved)

    def test_cost_edit_fails_closed_if_frappe_restores_old_permlevel_values(self) -> None:
        plan = SimpleNamespace(name="CP-A3-PERMLEVEL")

        with patch.object(
            cost_commands.frappe.db,
            "get_value",
            return_value={
                "board_rate_usd": 0,
                "cutting_cost_per_board_usd": 1,
            },
        ):
            with self.assertRaises(frappe.ValidationError):
                cost_commands._assert_cost_inputs_persisted(
                    plan,
                    board_rate_usd=22,
                    cutting_cost_per_board_usd=2.5,
                )

    def test_cost_save_response_uses_exact_saved_plan_revision(self) -> None:
        order = SimpleNamespace(
            name="DCO-A3-ROUNDTRIP",
            pieces=[],
            board_rate_usd=0,
            cutting_cost_per_board_usd=0,
            mdf_cost_usd=0,
            cutting_cost_usd=0,
            edge_cost_usd=0,
            total_cost_usd=0,
            special_shapes_baseline_cost_usd=0,
            special_shapes_estimated_total_usd=0,
            special_shapes_final_total_usd=0,
            customer_quote_total_usd=0,
            customer_quote_status="",
            material_variance_cost_usd=0,
            internal_loss_cost_usd=0,
            actual_cost_usd=0,
        )
        saved_plan = SimpleNamespace(
            name="CP-A3-SAVED",
            status="Draft",
            cost_snapshot_version=workspace.COST_SNAPSHOT_VERSION,
            required_boards=2,
            board_rate_usd=22,
            cutting_cost_per_board_usd=2.5,
            mdf_cost_usd=44,
            cutting_cost_usd=5,
            edge_cost_usd=3,
            total_cost_usd=52,
        )

        payload = cost_service._cost_snapshot(order, plan=saved_plan)

        self.assertEqual(payload["cutting_plan"], "CP-A3-SAVED")
        self.assertEqual(payload["order"]["board_rate_usd"], 22)
        self.assertEqual(payload["order"]["cutting_cost_per_board_usd"], 2.5)
        self.assertEqual(payload["order"]["required_boards"], 2)
        self.assertEqual(payload["order"]["total_cost_usd"], 52)

    def test_special_price_projection_is_persisted_and_used_by_customer_print(self) -> None:
        piece = SimpleNamespace(
            name="DCO-DETAIL-SPECIAL-1",
            piece_no=1,
            piece_type="Special",
            width_cm=40,
            length_cm=80,
            qty=2,
            area_m2=0.64,
            edge_type="2cm عادي",
            edge_meters=4,
            edge_rate_usd=0.5,
            edge_cost_usd=4,
            notes="",
            special_shape_estimated_unit_price_usd=0,
            special_shape_custom_unit_price_usd=25,
            special_shape_final_unit_price_usd=0,
            special_shape_price_status="Approved",
            special_shape_price_note="سعر معتمد",
            special_shape_price_approved_by="accounts@example.com",
            special_shape_price_approved_on="2026-08-24 12:00:00",
        )
        order = SimpleNamespace(
            name="DCO-A3-SPECIAL-PRINT",
            pieces=[piece],
            total_area_m2=0.64,
            board_rate_usd=0,
            cutting_cost_per_board_usd=0,
            mdf_cost_usd=0,
            cutting_cost_usd=0,
            edge_cost_usd=0,
            total_cost_usd=0,
            special_shapes_baseline_cost_usd=0,
            special_shapes_estimated_total_usd=0,
            special_shapes_final_total_usd=0,
            customer_quote_total_usd=0,
            customer_quote_status="Estimated",
        )
        plan = SimpleNamespace(
            status="Draft",
            cost_snapshot_version=workspace.COST_SNAPSHOT_VERSION,
            board_rate_usd=20,
            cutting_cost_per_board_usd=3,
            mdf_cost_usd=40,
            cutting_cost_usd=6,
            edge_cost_usd=4,
            total_cost_usd=50,
        )
        settings = SimpleNamespace(
            default_special_design_fee_usd=0,
            default_special_cnc_fee_usd=0,
            default_special_manual_edge_fee_usd=0,
            default_special_margin_percent=0,
        )

        with patch.object(workspace.frappe, "get_cached_doc", return_value=settings):
            with patch.object(workspace.frappe.db, "set_value") as set_value:
                totals = workspace.refresh_order_commercial_totals(order, plan)

        self.assertEqual(piece.special_shape_final_unit_price_usd, 25)
        self.assertEqual(piece.special_shape_price_status, "Approved")
        self.assertEqual(totals["special_shapes_final_total_usd"], 50)
        self.assertEqual(totals["customer_quote_total_usd"], 96)
        set_value.assert_any_call(
            "Door Cutting Order Detail",
            piece.name,
            {
                "special_shape_estimated_unit_price_usd": 2.0,
                "special_shape_final_unit_price_usd": 25.0,
                "special_shape_price_status": "Approved",
            },
            update_modified=False,
        )

        invoice = build_customer_invoice_document(
            {
                "name": order.name,
                "customer": "زبون",
                "order_date": "2026-08-24",
                "board_description": "MDF",
                "edge_color": "أبيض",
                "revision": 1,
                "required_boards": 0,
                "board_rate_usd": 0,
                "cutting_cost_per_board_usd": 0,
                "mdf_cost_usd": plan.mdf_cost_usd,
                "cutting_cost_usd": plan.cutting_cost_usd,
                "edge_cost_usd": plan.edge_cost_usd,
                "customer_quote_total_usd": totals["customer_quote_total_usd"],
                "customer_quote_status": totals["customer_quote_status"],
            },
            [
                {
                    "piece_no": piece.piece_no,
                    "piece_type": piece.piece_type,
                    "width_cm": piece.width_cm,
                    "length_cm": piece.length_cm,
                    "qty": piece.qty,
                    "edge_type": piece.edge_type,
                    "edge_meters": piece.edge_meters,
                    "edge_rate_usd": piece.edge_rate_usd,
                    "edge_cost_usd": piece.edge_cost_usd,
                    "special_shape_final_unit_price_usd": piece.special_shape_final_unit_price_usd,
                    "special_shape_price_note": piece.special_shape_price_note,
                }
            ],
        )
        special_line = next(line for line in invoice["lines"] if line["type"] == "special")
        self.assertEqual(special_line["rate_usd"], 25)
        self.assertEqual(special_line["amount_usd"], 50)

    def test_special_price_command_refreshes_projection_before_response(self) -> None:
        piece = SimpleNamespace(
            name="DCO-DETAIL-SPECIAL-COMMAND",
            piece_type="Special",
            special_shape_custom_unit_price_usd=0,
            special_shape_final_unit_price_usd=0,
            special_shape_price_status="Estimated",
            special_shape_price_note="",
            special_shape_price_approved_by="",
            special_shape_price_approved_on=None,
        )
        order = SimpleNamespace(
            name="DCO-A3-SPECIAL-COMMAND",
            modified="v1",
            pieces=[piece],
            flags=SimpleNamespace(),
            customer_quote_total_usd=0,
            customer_quote_status="Estimated",
        )

        def save(*, ignore_permissions: bool) -> None:
            self.assertTrue(ignore_permissions)
            order.modified = "v2"

        order.save = save

        def refresh(saved_order) -> dict[str, object]:
            self.assertIs(saved_order, order)
            piece.special_shape_final_unit_price_usd = piece.special_shape_custom_unit_price_usd
            saved_order.customer_quote_total_usd = 50
            saved_order.customer_quote_status = "Approved"
            return {
                "customer_quote_total_usd": 50,
                "customer_quote_status": "Approved",
            }

        with patch.object(cost_service, "_locked_order", return_value=order):
            with patch.object(cost_service, "_require_cost_visibility"):
                with patch.object(cost_service, "require_document_capability"):
                    with patch.object(cost_service, "_require_expected_document_version"):
                        with patch.object(cost_service, "assert_order_editable"):
                            with patch.object(cost_service, "refresh_order_commercial_totals", side_effect=refresh) as refresh_mock:
                                with patch.object(cost_service.frappe, "session", SimpleNamespace(user="accounts@example.com")):
                                    result = cost_service.approve_special_piece_price(
                                        order.name,
                                        piece.name,
                                        25,
                                        "سعر معتمد",
                                        expected_modified="v1",
                                    )

        refresh_mock.assert_called_once_with(order)
        self.assertEqual(result["unit_price_usd"], 25)
        self.assertEqual(result["customer_quote_total_usd"], 50)
        self.assertEqual(result["customer_quote_status"], "Approved")
        self.assertEqual(result["order_modified"], "v2")

    def test_legacy_draft_read_falls_back_without_mutating_it(self) -> None:
        order = SimpleNamespace(
            name="DCO-A3-002",
            board_rate_usd=12,
            cutting_cost_per_board_usd=3,
            mdf_cost_usd=24,
            cutting_cost_usd=6,
            edge_cost_usd=4,
            total_cost_usd=34,
        )
        legacy_draft = SimpleNamespace(
            status="Draft",
            cost_snapshot_version=0,
            board_rate_usd=0,
            cutting_cost_per_board_usd=0,
            mdf_cost_usd=0,
            cutting_cost_usd=0,
            edge_cost_usd=0,
            total_cost_usd=0,
        )

        values = workspace.authoritative_cost_values(order, plan=legacy_draft)

        self.assertEqual(values["board_rate_usd"], 12)
        self.assertEqual(values["total_cost_usd"], 34)
        self.assertEqual(legacy_draft.cost_snapshot_version, 0)

    def test_legacy_approved_snapshot_remains_historical_authority(self) -> None:
        order = SimpleNamespace(
            name="DCO-A3-003",
            board_rate_usd=99,
            cutting_cost_per_board_usd=99,
            mdf_cost_usd=99,
            cutting_cost_usd=99,
            edge_cost_usd=99,
            total_cost_usd=99,
        )
        approved = SimpleNamespace(
            status="Approved",
            cost_snapshot_version=0,
            board_rate_usd=7,
            cutting_cost_per_board_usd=1,
            mdf_cost_usd=14,
            cutting_cost_usd=2,
            edge_cost_usd=3,
            total_cost_usd=19,
        )

        values = workspace.authoritative_cost_values(order, plan=approved)

        self.assertEqual(values["board_rate_usd"], 7)
        self.assertEqual(values["total_cost_usd"], 19)

    def test_approval_rejects_pre_a3_draft_cost_snapshot(self) -> None:
        order = SimpleNamespace(name="DCO-A3-004")
        plan = SimpleNamespace(
            status="Draft",
            validation_status="Valid",
            snapshot_json='{"validation":{"is_valid":true},"sheets":[{"sheet_no":1}]}',
            plan_needs_recalculation=0,
            cost_snapshot_version=0,
        )

        with self.assertRaises(frappe.ValidationError):
            plan_commands._assert_plan_ready_for_approval(order, plan)

    def test_cost_settings_update_does_not_require_draft_order_status(self) -> None:
        order = SimpleNamespace(name="DCO-AT-CNC-001", status="At CNC")
        saved_plan = SimpleNamespace(name="CP-AT-CNC-001")
        snapshot = {"order_name": order.name, "cutting_plan": saved_plan.name}
        fake_db = SimpleNamespace(sql=lambda *args, **kwargs: None)

        with patch.object(cost_service.frappe, "db", fake_db):
            with patch.object(cost_service, "_", lambda value: value):
                with patch.object(cost_service, "_authorized_order", return_value=order):
                    with patch.object(cost_service, "_require_cost_visibility"):
                        with patch.object(
                            cost_service,
                            "_required_cost_input",
                            side_effect=lambda value, _label: float(value),
                        ):
                            with patch(
                                "almdina_erp.almdina_erp.services.cutting_plan_cost_command_service.update_plan_cost_settings",
                                return_value={"cutting_plan": saved_plan.name},
                            ) as save_settings:
                                with patch.object(
                                    cost_service.frappe,
                                    "get_doc",
                                    return_value=saved_plan,
                                ):
                                    with patch.object(
                                        cost_service,
                                        "_cost_snapshot",
                                        return_value=snapshot,
                                    ):
                                        result = cost_service.update_order_cost_settings(
                                            order.name,
                                            board_rate_usd=8,
                                            cutting_cost_per_board_usd=2,
                                        )

        save_settings.assert_called_once()
        self.assertIs(save_settings.call_args.args[0], order)
        self.assertEqual(save_settings.call_args.kwargs["board_rate_usd"], 8.0)
        self.assertEqual(save_settings.call_args.kwargs["cutting_cost_per_board_usd"], 2.0)
        self.assertEqual(result, snapshot)


if __name__ == "__main__":
    unittest.main()
