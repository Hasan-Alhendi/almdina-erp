from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase


EXPECTED_EDGE_RATES = {
    "قشاط 2سم عادي": 0.5,
    "قشاط 4سم عادي": 1.0,
    "قشاط 2سم لميع": 1.0,
    "قشاط 4سم لميع": 2.0,
    "قشاط 2سم عادي يدوي": 1.0,
    "قشاط 4سم عادي يدوي": 2.0,
    "قشاط 2سم ذهبي": 1.25,
    "قشاط 4سم ذهبي": 2.5,
    "قشاط 2سم ذهبي يدوي": 2.5,
    "قشاط 4سم ذهبي يدوي": 5.0,
    "قشاط 2سم لميع يدوي": 2.0,
    "قشاط 4سم لميع يدوي": 4.0,
}


class TestAlmdinaSchemaInstall(FrappeTestCase):
    def test_required_doctypes_exist(self):
        required = {
            "Door Cutting Order",
            "Door Cutting Order Detail",
            "Edge Banding Type",
            "Cutting Plan",
            "Cutting Plan Source",
            "Cutting Plan Piece",
            "Board Remnant",
            "Production Routing",
            "Production Stage",
            "Production Stage Event",
            "Production Incident",
            "Replacement Piece",
            "Material Reservation",
            "Material Consumption Log",
            "Almdina ERP Settings",
        }
        missing = sorted(name for name in required if not frappe.db.exists("DocType", name))
        self.assertEqual(missing, [])

    def test_required_pages_exist(self):
        required = {
            "factory-stock-settings",
            "factory-production-settings",
            "factory-approval-queue",
            "factory-plan-archive",
            "factory-system-preflight",
            "factory-performance-benchmark",
        }
        missing = sorted(name for name in required if not frappe.db.exists("Page", name))
        self.assertEqual(missing, [])

    def test_required_workspaces_exist(self):
        required = {
            "Almdina ERP",
            "Almdina Reports",
            "Almdina Settings",
            "Almdina Control Center",
            "Almdina Go-Live",
        }
        missing = sorted(name for name in required if not frappe.db.exists("Workspace", name))
        self.assertEqual(missing, [])

    def test_required_reports_exist(self):
        required = {
            "Factory Order Analysis",
            "Production Stage Performance",
            "Remnant Inventory",
            "Production Incidents and Replacements",
            "Order Stock Availability",
            "Board Usage Analysis",
            "Piece Size Usage Analysis",
            "Factory Operations Summary",
        }
        missing = sorted(name for name in required if not frappe.db.exists("Report", name))
        self.assertEqual(missing, [])

    def test_required_print_formats_exist(self):
        required = {
            "Door Cutting Measurements",
            "Door Cutting Plan Official",
            "Door Cutting Plan Production A4",
        }
        missing = sorted(name for name in required if not frappe.db.exists("Print Format", name))
        self.assertEqual(missing, [])

    def test_exact_baseline_edge_types_exist_on_fresh_install(self):
        for edge_name, expected_rate in EXPECTED_EDGE_RATES.items():
            row = frappe.db.get_value(
                "Edge Banding Type",
                edge_name,
                ["rate_usd_per_meter", "width_cm", "finish_type", "application_method"],
                as_dict=True,
            )
            self.assertIsNotNone(row, edge_name)
            self.assertEqual(float(row.rate_usd_per_meter), expected_rate, edge_name)
            self.assertGreater(float(row.width_cm or 0), 0, edge_name)
            self.assertTrue(row.finish_type, edge_name)
            self.assertTrue(row.application_method, edge_name)

    def test_default_routing_contains_v1_core_sequence(self):
        settings = frappe.get_single("Almdina ERP Settings")
        self.assertTrue(settings.default_production_routing)
        rows = frappe.get_all(
            "Production Routing Stage",
            filters={
                "parent": settings.default_production_routing,
                "parenttype": "Production Routing",
            },
            fields=["sequence", "stage_type", "required"],
            order_by="sequence asc",
        )
        core = [row.stage_type for row in rows if row.required]
        self.assertEqual(core[:3], ["Review / Preparation", "Cutting", "Edge Banding"])

    def test_order_meta_has_no_stale_factory_defaults(self):
        meta = frappe.get_meta("Door Cutting Order")
        for fieldname in (
            "kerf_mm",
            "trim_margin_mm",
            "cutting_cost_per_board_usd",
            "packing_mode",
        ):
            field = meta.get_field(fieldname)
            self.assertIsNotNone(field)
            self.assertIn(field.default, (None, ""), f"{fieldname} still has stale static default {field.default!r}")

    def test_unplaced_approval_flag_is_off_in_v1(self):
        settings = frappe.get_single("Almdina ERP Settings")
        self.assertFalse(bool(settings.allow_unplaced_approval))
