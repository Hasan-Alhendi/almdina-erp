"""Real Frappe persistence for connected sheet-perimeter path rows."""

from __future__ import annotations

from contextlib import contextmanager
from uuid import uuid4

import frappe
import pytest
from frappe.tests.utils import FrappeTestCase

from almdina_erp.almdina_erp.domain.cnc.operational_file import validate_operational_path_rows
from almdina_erp.almdina_erp.domain.cnc.perimeter import SHEET_PERIMETER_PATH_KEY
from almdina_erp.almdina_erp.infrastructure.frappe.cnc_operational_file_repository import (
    _sequence_json,
    save_sheet,
)


pytestmark = pytest.mark.skipif(
    not getattr(frappe.local, "site", None),
    reason="Requires a live Frappe site",
)


def _payload(*, sheet_no: int, join_mode: str, paths: list[dict], operations: list[dict] | None = None):
    token = uuid4().hex[:8]
    return {
        "door_cutting_order": f"_Test CNC Order {token}",
        "cutting_plan": f"_Test CNC Plan {token}",
        "plan_revision": 1,
        "plan_source_type": "System",
        "sheet_no": sheet_no,
        "sheet_key": f"sheet:{sheet_no}",
        "status": "Not Generated",
        "settings_fingerprint": f"fp-{token}",
        "cut_path_early_confirmed": 0,
        "perimeter_join_mode": join_mode,
        "cut_path_sequence": [SHEET_PERIMETER_PATH_KEY, "cut_path:internals"]
        if join_mode == "connected"
        else [],
        "perimeter_cut_early_confirmed": 0,
        "operations": operations
        or (
            [
                {
                    "operation_key": "sheet_perimeter",
                    "dxf_layer": "CUT_PATH",
                    "sequence": 1,
                    "tool_preset": "",
                    "preset_source": "Factory",
                },
                {
                    "operation_key": "cut_path",
                    "dxf_layer": "CUT_PATH",
                    "sequence": 2,
                    "tool_preset": "",
                    "preset_source": "Factory",
                },
            ]
            if join_mode == "connected"
            else [
                {
                    "operation_key": "cut_path",
                    "dxf_layer": "CUT_PATH",
                    "sequence": 1,
                    "tool_preset": "",
                    "preset_source": "Factory",
                }
            ]
        ),
        "paths": paths,
    }


@contextmanager
def _allow_missing_links():
    original_exists = frappe.db.exists

    def _exists(doctype, name=None, *args, **kwargs):
        if doctype in {"Door Cutting Order", "Cutting Plan"}:
            return True
        return original_exists(doctype, name, *args, **kwargs)

    frappe.db.exists = _exists  # type: ignore[method-assign]
    try:
        yield
    finally:
        frappe.db.exists = original_exists  # type: ignore[method-assign]


class TestCncSheetPerimeterPathPersistence(FrappeTestCase):
    def setUp(self) -> None:
        super().setUp()
        frappe.set_user("Administrator")
        frappe.reload_doc("Almdina ERP", "doctype", "cnc_operational_path", force=True)
        frappe.reload_doc("Almdina ERP", "doctype", "cnc_operational_file", force=True)
        frappe.clear_cache(doctype="CNC Operational Path")
        frappe.clear_cache(doctype="CNC Operational File")
        self.created: list[str] = []

    def tearDown(self) -> None:
        frappe.set_user("Administrator")
        for name in self.created:
            if frappe.db.exists("CNC Operational File", name):
                frappe.delete_doc(
                    "CNC Operational File",
                    name,
                    force=True,
                    ignore_permissions=True,
                )
        super().tearDown()

    def _insert_payload(self, payload: dict) -> str:
        document = frappe.new_doc("CNC Operational File")
        for field, value in payload.items():
            if field in {"operations", "paths", "cut_path_sequence"}:
                continue
            document.set(field, value)
        document.set("cut_path_sequence", _sequence_json(payload.get("cut_path_sequence")))
        for row in payload.get("operations") or []:
            document.append("operations", row)
        for row in validate_operational_path_rows(list(payload.get("paths") or [])):
            document.append("paths", row)
        document.flags.ignore_permissions = True
        document.flags.ignore_links = True
        with _allow_missing_links():
            document.save()
        self.created.append(document.name)
        return str(document.name)

    def test_meta_piece_instance_id_is_optional_after_reload(self) -> None:
        meta = frappe.get_meta("CNC Operational Path")
        field = meta.get_field("piece_instance_id")
        self.assertIsNotNone(field)
        self.assertFalse(bool(field.reqd))

    def test_connected_perimeter_saves_and_reloads_empty_piece_id(self) -> None:
        name = self._insert_payload(
            _payload(
                sheet_no=1,
                join_mode="connected",
                paths=[
                    {
                        "path_key": SHEET_PERIMETER_PATH_KEY,
                        "operation_key": "sheet_perimeter",
                        "piece_instance_id": "",
                        "dxf_layer": "CUT_PATH",
                        "sequence": 1,
                        "tool_preset": "",
                    },
                    {
                        "path_key": "cut_path:piece-a:outer",
                        "operation_key": "cut_path",
                        "piece_instance_id": "piece-a",
                        "dxf_layer": "CUT_PATH",
                        "sequence": 2,
                        "tool_preset": "",
                    },
                ],
            )
        )
        reloaded = frappe.get_doc("CNC Operational File", name)
        peri = next(row for row in reloaded.paths if row.path_key == SHEET_PERIMETER_PATH_KEY)
        self.assertEqual(peri.operation_key, "sheet_perimeter")
        self.assertEqual(str(peri.piece_instance_id or ""), "")
        piece = next(row for row in reloaded.paths if row.path_key == "cut_path:piece-a:outer")
        self.assertEqual(piece.piece_instance_id, "piece-a")
        self.assertEqual(
            sum(1 for row in reloaded.paths if row.path_key == SHEET_PERIMETER_PATH_KEY),
            1,
        )
        self.assertEqual(reloaded.perimeter_join_mode, "connected")
        ops = [row.operation_key for row in reloaded.operations]
        self.assertEqual(ops, ["sheet_perimeter", "cut_path"])

    def test_separate_perimeter_saves_without_sheet_perimeter_row(self) -> None:
        name = self._insert_payload(
            _payload(
                sheet_no=2,
                join_mode="separate",
                paths=[
                    {
                        "path_key": "cut_path:piece-b:outer",
                        "operation_key": "cut_path",
                        "piece_instance_id": "piece-b",
                        "dxf_layer": "CUT_PATH",
                        "sequence": 1,
                        "tool_preset": "",
                    }
                ],
            )
        )
        reloaded = frappe.get_doc("CNC Operational File", name)
        self.assertEqual(reloaded.perimeter_join_mode, "separate")
        self.assertFalse(any(row.path_key == SHEET_PERIMETER_PATH_KEY for row in reloaded.paths))
        self.assertEqual(reloaded.paths[0].piece_instance_id, "piece-b")

    def test_piece_bound_path_without_piece_id_is_rejected(self) -> None:
        frappe.reload_doc("Almdina ERP", "doctype", "cnc_operational_file", force=True)
        document = frappe.new_doc("CNC Operational File")
        document.door_cutting_order = f"_Test CNC Order {uuid4().hex[:8]}"
        document.cutting_plan = f"_Test CNC Plan {uuid4().hex[:8]}"
        document.plan_revision = 1
        document.plan_source_type = "System"
        document.sheet_no = 3
        document.status = "Not Generated"
        document.perimeter_join_mode = "separate"
        document.append(
            "paths",
            {
                "path_key": "cut_path:piece-c:outer",
                "operation_key": "cut_path",
                "piece_instance_id": "",
                "dxf_layer": "CUT_PATH",
                "sequence": 1,
            },
        )
        document.flags.ignore_permissions = True
        document.flags.ignore_links = True
        with self.assertRaises(frappe.ValidationError):
            with _allow_missing_links():
                document.save()

    def test_perimeter_with_piece_id_is_rejected(self) -> None:
        frappe.reload_doc("Almdina ERP", "doctype", "cnc_operational_file", force=True)
        document = frappe.new_doc("CNC Operational File")
        document.door_cutting_order = f"_Test CNC Order {uuid4().hex[:8]}"
        document.cutting_plan = f"_Test CNC Plan {uuid4().hex[:8]}"
        document.plan_revision = 1
        document.plan_source_type = "System"
        document.sheet_no = 4
        document.status = "Not Generated"
        document.perimeter_join_mode = "connected"
        document.append(
            "paths",
            {
                "path_key": SHEET_PERIMETER_PATH_KEY,
                "operation_key": "sheet_perimeter",
                "piece_instance_id": "piece-a",
                "dxf_layer": "CUT_PATH",
                "sequence": 1,
            },
        )
        document.flags.ignore_permissions = True
        document.flags.ignore_links = True
        with self.assertRaises(frappe.ValidationError):
            with _allow_missing_links():
                document.save()

    def test_save_sheet_repository_round_trip_connected_perimeter(self) -> None:
        payload = _payload(
            sheet_no=5,
            join_mode="connected",
            paths=validate_operational_path_rows(
                [
                    {
                        "path_key": SHEET_PERIMETER_PATH_KEY,
                        "operation_key": "sheet_perimeter",
                        "piece_instance_id": "",
                        "dxf_layer": "CUT_PATH",
                        "sequence": 1,
                        "tool_preset": "",
                    },
                    {
                        "path_key": "cut_path:piece-d:outer",
                        "operation_key": "cut_path",
                        "piece_instance_id": "piece-d",
                        "dxf_layer": "CUT_PATH",
                        "sequence": 2,
                        "tool_preset": "",
                    },
                ]
            ),
        )
        with _allow_missing_links():
            name = save_sheet("", payload)
        self.created.append(name)
        saved = frappe.get_doc("CNC Operational File", name)
        peri = next(row for row in saved.paths if row.path_key == SHEET_PERIMETER_PATH_KEY)
        self.assertEqual(str(peri.piece_instance_id or ""), "")
        self.assertEqual(saved.perimeter_join_mode, "connected")
        # Failed save would not create a document; no orphan NC is attached here.
        self.assertFalse(bool(saved.generated_file))
