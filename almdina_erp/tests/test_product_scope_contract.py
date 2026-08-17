from __future__ import annotations

import json
import runpy
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class TestProductScopeContract(unittest.TestCase):
    def test_invoice_costing_and_printing_remain_active(self) -> None:
        order_meta = json.loads(
            (
                ROOT
                / "almdina_erp"
                / "doctype"
                / "door_cutting_order"
                / "door_cutting_order.json"
            ).read_text(encoding="utf-8")
        )
        fields = {row["fieldname"]: row for row in order_meta["fields"]}
        for fieldname in (
            "board_rate_usd",
            "cutting_cost_per_board_usd",
            "mdf_cost_usd",
            "cutting_cost_usd",
            "edge_cost_usd",
            "total_cost_usd",
            "customer_quote_total_usd",
            "order_cost_invoice_html",
        ):
            self.assertIn(fieldname, fields)

        hooks = runpy.run_path(str(ROOT / "hooks.py"))
        scripts = hooks["doctype_js"]["Door Cutting Order"]
        for script in (
            "public/js/door_cutting_order/printing/door_cutting_order_document_print_theme.js",
            "public/js/door_cutting_order/printing/door_cutting_order_document_print_presenter.js",
            "public/js/door_cutting_order/costing/door_cutting_order_multi_edge_documents_ux.js",
            "public/js/door_cutting_order/costing/door_cutting_order_cost_permissions_ux.js",
            "public/js/door_cutting_order/costing/door_cutting_order_financial_documents_ux.js",
        ):
            self.assertIn(script, scripts)
        self.assertNotIn(
            "public/js/door_cutting_order_cost_invoice_ux.js",
            scripts,
        )

    def test_stock_features_are_not_active_ui_or_approval_dependencies(self) -> None:
        hooks = runpy.run_path(str(ROOT / "hooks.py"))
        self.assertNotIn("Material Consumption Log", hooks.get("doc_events", {}))

        retired = (
            "almdina_erp.almdina_erp.services.legacy_endpoint_service."
            "retired_product_endpoint"
        )
        overrides = hooks["override_whitelisted_methods"]
        for endpoint in (
            "almdina_erp.almdina_erp.services.actual_consumption_reversal.reverse_actual_consumption",
            "almdina_erp.almdina_erp.services.actual_consumption_service.record_actual_consumption",
            "almdina_erp.almdina_erp.services.remnant_service.generate_order_remnants",
            "almdina_erp.almdina_erp.services.settings_access_service.get_stock_settings",
            "almdina_erp.almdina_erp.services.settings_access_service.update_stock_settings",
            "almdina_erp.almdina_erp.services.stock_availability_service.check_order_stock",
            "almdina_erp.almdina_erp.services.stock_service.check_order_stock",
            "almdina_erp.almdina_erp.services.stock_service.consume_order_materials",
        ):
            with self.subTest(endpoint=endpoint):
                self.assertEqual(overrides.get(endpoint), retired)

        approval_source = (
            ROOT
            / "almdina_erp"
            / "services"
            / "cutting_plan_snapshot_service.py"
        ).read_text(encoding="utf-8")
        self.assertNotIn("services.stock_service", approval_source)
        self.assertNotIn("services.remnant_planning", approval_source)
        self.assertIn("frappe.parse_json(order.cutting_plan_json", approval_source)

        order_scripts = hooks["doctype_js"]["Door Cutting Order"]
        retired_workflow = ROOT / "public" / "js" / "door_cutting_order_workflow.js"
        self.assertFalse(retired_workflow.exists())
        self.assertNotIn(
            "public/js/door_cutting_order_workflow.js",
            order_scripts,
        )
        for script in order_scripts:
            source = (ROOT / script).read_text(encoding="utf-8")
            for token in ("stock_service", "Stock Manager", "فحص توفر المواد"):
                with self.subTest(script=script, token=token):
                    self.assertNotIn(token, source)

        commands_source = (
            ROOT / "almdina_erp" / "application" / "shop_floor" / "commands.py"
        ).read_text(encoding="utf-8")
        repository_source = (
            ROOT
            / "almdina_erp"
            / "infrastructure"
            / "frappe"
            / "shop_floor_command_repository.py"
        ).read_text(encoding="utf-8")
        compatibility_service_source = (
            ROOT / "almdina_erp" / "services" / "shop_floor_service.py"
        ).read_text(encoding="utf-8")
        compatibility_gateway_source = (
            ROOT
            / "almdina_erp"
            / "infrastructure"
            / "frappe"
            / "shop_floor_gateway.py"
        ).read_text(encoding="utf-8")
        for source in (
            commands_source,
            repository_source,
            compatibility_service_source,
            compatibility_gateway_source,
        ):
            self.assertNotIn("consume_stock", source)
            self.assertNotIn("register_remnants", source)

        for relative in (
            "infrastructure/frappe/replacements/snapshot_adapter.py",
            "services/replacement_service.py",
            "services/replacement_creation_service.py",
            "services/replacement_approval.py",
            "services/replacement_execution.py",
            "services/replacement_completion.py",
            "services/replacement_plan_service.py",
            "services/replacement_status_service.py",
            "services/order_lifecycle_service.py",
        ):
            source = (ROOT / "almdina_erp" / relative).read_text(encoding="utf-8")
            for token in (
                "Material Reservation",
                "Material Consumption Log",
                "Stock Entry",
                "stock_service",
                "Board Remnant",
            ):
                with self.subTest(module=relative, token=token):
                    self.assertNotIn(token, source)

    def test_replacement_facade_and_domain_have_clean_boundaries(self) -> None:
        facade = (
            ROOT / "almdina_erp" / "services" / "replacement_service.py"
        ).read_text(encoding="utf-8")
        domain = (
            ROOT
            / "almdina_erp"
            / "domain"
            / "replacements"
            / "planning.py"
        ).read_text(encoding="utf-8")
        hooks = (ROOT / "hooks.py").read_text(encoding="utf-8")

        self.assertLess(len(facade.splitlines()), 100)
        self.assertIn("Backward-compatible replacement API facade", facade)
        self.assertNotIn("frappe.db.", facade)
        self.assertNotIn("frappe.get_doc", facade)
        self.assertNotIn("import frappe", domain)
        self.assertNotIn("from frappe", domain)
        self.assertNotIn(
            '"almdina_erp.almdina_erp.services.replacement_service.'
            'approve_replacement":',
            hooks,
        )

    def test_replacements_use_the_same_free_text_board_identity(self) -> None:
        payload = json.loads(
            (
                ROOT
                / "almdina_erp"
                / "doctype"
                / "replacement_piece"
                / "replacement_piece.json"
            ).read_text(encoding="utf-8")
        )
        fields = {row["fieldname"]: row for row in payload["fields"]}
        self.assertEqual(fields["board_description"].get("reqd"), 1)
        self.assertNotEqual(fields["board_item"].get("reqd"), 1)
        self.assertEqual(fields["board_item"].get("hidden"), 1)
        for fieldname in (
            "source_preference",
            "selected_remnant",
            "stock_entry",
            "generated_remnant",
        ):
            self.assertEqual(fields[fieldname].get("hidden"), 1)

    def test_zero_replacement_loss_is_preserved_by_the_ui(self) -> None:
        source = (
            ROOT / "public" / "js" / "replacement_piece.js"
        ).read_text(encoding="utf-8")
        self.assertNotIn(
            "internal_loss_cost_usd: values.internal_loss_cost_usd || null",
            source,
        )
        self.assertIn(
            'values.internal_loss_cost_usd === ""',
            source,
        )

    def test_primary_workspaces_do_not_expose_inventory(self) -> None:
        banned_targets = (
            '"link_to":"Warehouse"',
            '"link_to":"Stock Reconciliation"',
            '"link_to":"Board Remnant"',
            '"link_to":"Material Reservation"',
            '"link_to":"Material Consumption Log"',
            '"link_to":"Order Stock Availability"',
            '"link_to":"Remnant Inventory"',
            '"link_to":"factory-stock-settings"',
        )
        workspace_root = ROOT / "almdina_erp" / "workspace"
        for name in (
            "almdina_erp/almdina_erp.json",
            "almdina_reports/almdina_reports.json",
            "almdina_settings/almdina_settings.json",
            "almdina_control_center/almdina_control_center.json",
            "almdina_go_live/almdina_go_live.json",
        ):
            source = (workspace_root / name).read_text(encoding="utf-8")
            for target in banned_targets:
                with self.subTest(workspace=name, target=target):
                    self.assertNotIn(target, source)

    def test_new_install_does_not_create_stock_item_customizations(self) -> None:
        source = (ROOT / "install.py").read_text(encoding="utf-8")
        for token in (
            "create_custom_fields",
            "ITEM_CUSTOM_FIELDS",
            "seed_required_uoms",
            "seed_edge_banding_items",
            "custom_is_mdf",
        ):
            self.assertNotIn(token, source)
        self.assertIn("sync_order_board_descriptions()", source)
        self.assertIn("sync_plan_board_descriptions()", source)
        self.assertIn("sync_replacement_board_descriptions()", source)
        self.assertIn(
            "set source.board_description = plan.board_description",
            source,
        )
        self.assertIn(
            "set replacement.board_description = order_doc.board_description",
            source,
        )

    def test_edge_banding_seed_has_no_inventory_defaults(self) -> None:
        payload = json.loads(
            (
                ROOT
                / "almdina_erp"
                / "doctype"
                / "edge_banding_type"
                / "edge_banding_type.json"
            ).read_text(encoding="utf-8")
        )
        fields = {row["fieldname"]: row for row in payload["fields"]}
        for fieldname in ("consumption_uom", "item_code", "stock_uom"):
            self.assertEqual(fields[fieldname].get("hidden"), 1)
            self.assertNotIn("default", fields[fieldname])

    def test_stock_settings_are_hidden_and_forced_off(self) -> None:
        payload = json.loads(
            (
                ROOT
                / "almdina_erp"
                / "doctype"
                / "almdina_erp_settings"
                / "almdina_erp_settings.json"
            ).read_text(encoding="utf-8")
        )
        fields = {row["fieldname"]: row for row in payload["fields"]}
        for fieldname in (
            "enforce_stock_control",
            "default_warehouse",
            "reserve_stock_on_approval",
            "prefer_remnants_before_full_boards",
        ):
            self.assertEqual(fields[fieldname].get("hidden"), 1)
        self.assertEqual(fields["enforce_stock_control"].get("default"), "0")
        self.assertEqual(
            fields["prefer_remnants_before_full_boards"].get("default"),
            "0",
        )

    def test_operational_reports_use_free_text_board_identity(self) -> None:
        report_root = ROOT / "almdina_erp" / "report"
        for relative in (
            "factory_order_analysis/factory_order_analysis.py",
            "piece_size_usage_analysis/piece_size_usage_analysis.py",
            "board_usage_analysis/board_usage_analysis.py",
        ):
            source = (report_root / relative).read_text(encoding="utf-8")
            self.assertIn("board_description", source)
            for stale in (
                "o.board_material",
                "o.board_color",
                "o.board_thickness_mm",
                "src.material",
                "src.color",
                "src.thickness_mm",
            ):
                with self.subTest(report=relative, stale=stale):
                    self.assertNotIn(stale, source)

    def test_factory_operations_date_filter_uses_a_declared_order_alias(self) -> None:
        source = (
            ROOT
            / "almdina_erp"
            / "report"
            / "factory_operations_summary"
            / "factory_operations_summary.py"
        ).read_text(encoding="utf-8")
        self.assertIn("from `tabDoor Cutting Order` o", source)
        self.assertIn("o.order_date >= %(from_date)s", source)
        self.assertIn("o.order_date <= %(to_date)s", source)


if __name__ == "__main__":
    unittest.main()
