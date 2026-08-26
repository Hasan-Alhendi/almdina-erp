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

RETIRED_STANDARD_PAGES = {
    "factory-stock-settings": "Factory Stock Settings",
    "factory-system-preflight": "Factory System Preflight",
    "factory-performance-benchmark": "Factory Performance Benchmark",
    "factory-approval-queue": "Factory Approval Queue",
}
RETIRED_STANDARD_REPORTS = (
    "Order Stock Availability",
    "Remnant Inventory",
)


def assert_retired_standard_pages_absent() -> None:
    existing = sorted(
        page_name
        for page_name in RETIRED_STANDARD_PAGES
        if frappe.db.exists("Page", page_name)
    )
    if existing:
        raise AssertionError(f"Retired Standard Pages still exist: {existing}")


def seed_retired_standard_pages() -> None:
    assert_retired_standard_pages_absent()
    for page_name, title in RETIRED_STANDARD_PAGES.items():
        page = frappe.get_doc(
            {
                "doctype": "Page",
                "name": page_name,
                "page_name": page_name,
                "module": "Almdina ERP",
                "standard": "Yes",
                "title": title,
            }
        )
        page.db_insert()
    frappe.db.commit()
    missing = sorted(
        page_name
        for page_name in RETIRED_STANDARD_PAGES
        if not frappe.db.exists("Page", page_name)
    )
    if missing:
        raise AssertionError(f"Failed to seed retired Standard Page fixtures: {missing}")


def assert_retired_standard_reports_absent() -> None:
    existing = sorted(
        report_name
        for report_name in RETIRED_STANDARD_REPORTS
        if frappe.db.exists("Report", report_name)
    )
    if existing:
        raise AssertionError(f"Retired Standard Reports still exist: {existing}")


def seed_retired_standard_reports() -> None:
    assert_retired_standard_reports_absent()
    for report_name in RETIRED_STANDARD_REPORTS:
        report = frappe.get_doc(
            {
                "doctype": "Report",
                "name": report_name,
                "report_name": report_name,
                "module": "Almdina ERP",
                "ref_doctype": "Door Cutting Order",
                "report_type": "Script Report",
                "is_standard": "Yes",
            }
        )
        report.db_insert()
    frappe.db.commit()
    missing = sorted(
        report_name
        for report_name in RETIRED_STANDARD_REPORTS
        if not frappe.db.exists("Report", report_name)
    )
    if missing:
        raise AssertionError(f"Failed to seed retired Standard Report fixtures: {missing}")


class TestAlmdinaSchemaInstall(FrappeTestCase):
    def test_required_doctypes_exist(self):
        required = {
            "Door Cutting Order",
            "Door Cutting Order Detail",
            "Edge Banding Type",
            "Cutting Plan",
            "Cutting Plan Source",
            "Cutting Plan Piece",
            "Production Routing",
            "Production Stage",
            "Production Stage Event",
            "Production Incident",
            "Replacement Piece",
            "Almdina ERP Settings",
        }
        missing = sorted(name for name in required if not frappe.db.exists("DocType", name))
        self.assertEqual(missing, [])

    def test_required_pages_exist(self):
        required = {
            "factory-production-settings",
            "factory-plan-archive",
        }
        missing = sorted(name for name in required if not frappe.db.exists("Page", name))
        self.assertEqual(missing, [])

    def test_retired_standard_pages_are_absent(self):
        assert_retired_standard_pages_absent()

    def test_retired_standard_reports_are_absent(self):
        assert_retired_standard_reports_absent()

    def test_retired_approval_endpoints_fail_closed(self):
        from almdina_erp.almdina_erp.services import (
            approval_queue_service,
            order_review_service,
        )

        calls = (
            approval_queue_service.get_approval_queue_context,
            approval_queue_service.get_pending_review_orders,
            lambda: approval_queue_service.approve_order_safely("DCO-RETIRED"),
            lambda: approval_queue_service.reject_order_safely(
                "DCO-RETIRED",
                "retired",
            ),
            lambda: order_review_service.reject_order("DCO-RETIRED", "retired"),
        )
        for call in calls:
            with self.subTest(endpoint=getattr(call, "__name__", repr(call))):
                with self.assertRaises(frappe.ValidationError):
                    call()

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
            "Production Incidents and Replacements",
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
                ["rate_usd_per_meter", "width_cm"],
                as_dict=True,
            )
            self.assertIsNotNone(row, edge_name)
            self.assertEqual(float(row.rate_usd_per_meter), expected_rate, edge_name)
            self.assertGreater(float(row.width_cm or 0), 0, edge_name)

    def test_fresh_install_does_not_seed_production_routing_policy(self):
        settings = frappe.get_single("Almdina ERP Settings")
        self.assertFalse(settings.default_production_routing)
        self.assertEqual(
            frappe.get_all("Production Routing", pluck="name"),
            [],
            "Production routings must be created explicitly by an administrator.",
        )

    def test_order_meta_has_no_stale_factory_defaults(self):
        order_meta = frappe.get_meta("Door Cutting Order")
        for fieldname in ("kerf_mm", "trim_margin_mm", "packing_mode"):
            self.assertIsNone(
                order_meta.get_field(fieldname),
                f"{fieldname} must no longer be owned by Door Cutting Order",
            )

        cutting_cost = order_meta.get_field("cutting_cost_per_board_usd")
        self.assertIsNotNone(cutting_cost)
        self.assertIn(
            cutting_cost.default,
            (None, ""),
            f"cutting_cost_per_board_usd still has stale static default {cutting_cost.default!r}",
        )

        plan_meta = frappe.get_meta("Cutting Plan")
        for fieldname in ("optimization_mode", "kerf_mm", "trim_margin_mm"):
            field = plan_meta.get_field(fieldname)
            self.assertIsNotNone(field, f"Cutting Plan must own {fieldname}")
            self.assertTrue(field.read_only, f"{fieldname} must remain command-owned/read-only")

    def test_unplaced_approval_flag_is_off_in_v1(self):
        settings = frappe.get_single("Almdina ERP Settings")
        self.assertFalse(bool(settings.allow_unplaced_approval))
