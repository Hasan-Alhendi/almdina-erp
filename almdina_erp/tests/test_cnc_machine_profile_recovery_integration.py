"""Site-backed proof that a missing machine profile does not return HTTP 500."""

from __future__ import annotations

import frappe
import pytest
from frappe.tests.utils import FrappeTestCase

from almdina_erp.almdina_erp.domain.cnc.machine_profile import SAMPLE_MACHINE_PROFILE
from almdina_erp.almdina_erp.infrastructure.frappe.cnc_operational_file_repository import (
    machine_profile_view,
)
from almdina_erp.patches.v1_0.repair_missing_cnc_machine_profile_fields import execute


pytestmark = pytest.mark.skipif(
    not getattr(frappe.local, "site", None),
    reason="Requires a live Frappe site",
)

_SETTINGS = "Almdina ERP Settings"
_ORDER = "26-00132"


def _clear_value_cache() -> None:
    frappe.clear_document_cache(_SETTINGS, _SETTINGS)


class TestCncMachineProfileRecovery(FrappeTestCase):
    def setUp(self) -> None:
        super().setUp()
        frappe.set_user("Administrator")
        self.backup = frappe.db.sql(
            """
            select field, value
              from `tabSingles`
             where doctype = %s
               and field in %s
            """,
            (_SETTINGS, tuple(SAMPLE_MACHINE_PROFILE)),
            as_dict=True,
        )
        self.operational_files = frappe.db.count("CNC Operational File")

    def tearDown(self) -> None:
        frappe.set_user("Administrator")
        frappe.db.sql(
            "delete from `tabSingles` where doctype = %s and field in %s",
            (_SETTINGS, tuple(SAMPLE_MACHINE_PROFILE)),
        )
        for row in self.backup:
            frappe.db.sql(
                """
                insert into `tabSingles` (doctype, field, value)
                values (%s, %s, %s)
                """,
                (_SETTINGS, row.field, row.value),
            )
        _clear_value_cache()
        super().tearDown()

    def _stored(self) -> dict[str, str]:
        rows = frappe.db.sql(
            """
            select field, value
              from `tabSingles`
             where doctype = %s
               and field in %s
            """,
            (_SETTINGS, tuple(SAMPLE_MACHINE_PROFILE)),
            as_dict=True,
        )
        return {row.field: "" if row.value is None else str(row.value) for row in rows}

    def _replace_profile(self, values: dict[str, str]) -> None:
        frappe.db.sql(
            "delete from `tabSingles` where doctype = %s and field in %s",
            (_SETTINGS, tuple(SAMPLE_MACHINE_PROFILE)),
        )
        for field, value in values.items():
            frappe.db.sql(
                """
                insert into `tabSingles` (doctype, field, value)
                values (%s, %s, %s)
                """,
                (_SETTINGS, field, value),
            )
        _clear_value_cache()

    def test_incomplete_profile_opens_order_workspace_without_server_error(self) -> None:
        if not frappe.db.exists("Door Cutting Order", _ORDER):
            self.skipTest(f"Door Cutting Order {_ORDER} is not on this site")
        self._replace_profile({})
        view = machine_profile_view()
        self.assertFalse(view["production_approved"])
        self.assertEqual(view["fingerprint_payload"], {})

        from almdina_erp.almdina_erp.services.cnc_operational_file_service import (
            get_cnc_operational_workspace,
        )

        workspace = get_cnc_operational_workspace(_ORDER)
        self.assertIsInstance(workspace, dict)
        self.assertEqual(workspace.get("order_name"), _ORDER)
        if "machine_profile_production_approved" in workspace:
            self.assertFalse(workspace["machine_profile_production_approved"])
        self.assertEqual(frappe.db.count("CNC Operational File"), self.operational_files)

    def test_repair_patch_fills_gaps_without_replacing_user_values_or_approval(self) -> None:
        self._replace_profile(
            {
                "cnc_machine_tool_number": "T4",
                "cnc_machine_cutting_feed_mm_min": "4000",
                "cnc_machine_profile_production_approved": "1",
            }
        )
        execute()
        stored = self._stored()
        self.assertEqual(stored["cnc_machine_tool_number"], "T4")
        self.assertEqual(stored["cnc_machine_cutting_feed_mm_min"], "4000")
        self.assertEqual(stored["cnc_machine_profile_production_approved"], "1")
        self.assertEqual(stored["cnc_machine_spindle_speed_rpm"], "15000")
        self.assertEqual(stored["cnc_machine_distance_mode"], "G90")
        self.assertEqual(stored["cnc_machine_work_offset"], "G54")
        self.assertEqual(
            stored["cnc_machine_profile_source"],
            SAMPLE_MACHINE_PROFILE["cnc_machine_profile_source"],
        )
        self.assertEqual(float(stored["cnc_machine_plunge_feed_mm_min"]), 1800.0)
        self.assertEqual(float(stored["cnc_machine_example_depth_b_mm"]), 18.5)

        execute()
        self.assertEqual(self._stored(), stored)
        self.assertEqual(frappe.db.count("CNC Operational File"), self.operational_files)

    def test_repair_patch_leaves_approval_unchecked_when_the_row_is_missing(self) -> None:
        self._replace_profile({})
        execute()
        stored = self._stored()
        self.assertEqual(stored["cnc_machine_tool_number"], "T9")
        self.assertEqual(stored["cnc_machine_profile_production_approved"], "0")
        execute()
        self.assertEqual(self._stored(), stored)
