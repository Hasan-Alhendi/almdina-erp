"""Drawing persistence without a site, a Cutting Plan write, or Drawing Mode UI."""

from __future__ import annotations

import copy
import unittest
from pathlib import Path
from unittest.mock import patch

from almdina_erp.almdina_erp.application.cutting.board_editor_draft_save import execute_save
from almdina_erp.almdina_erp.application.cutting.board_editor_drawing_save import (
    DrawingInsertConflict,
    execute_archive_drawings_for_new_source,
    execute_coordinated_editor_save,
    execute_get_drawing,
    execute_get_drawing_archive,
    execute_list_drawings,
    execute_save_drawing,
)
from almdina_erp.almdina_erp.domain.cutting.board_editor_draft import (
    FORBIDDEN_FIELDS,
    DraftLayoutError,
    normalize_layout,
)
from almdina_erp.almdina_erp.domain.cutting.board_editor_drawing import (
    SCHEMA,
    document_fingerprint,
    normalize_document,
)
from almdina_erp.almdina_erp.domain.cutting.board_editor_drawing_persistence import (
    drawing_catalog_from_pieces,
    drawing_key,
)
from almdina_erp.almdina_erp.domain.cutting.dxf_geometry_snapshot import (
    GEOMETRY_COORDINATE_SPACE,
    GEOMETRY_SCHEMA_VERSION,
    GEOMETRY_UNIT,
)
from almdina_erp.almdina_erp.domain.cutting import board_editor_drawing_persistence as persistence
from almdina_erp.tests.test_board_editor_draft import (
    MemoryStore as DraftMemoryStore,
    catalog as draft_catalog,
    context as draft_context,
    layout,
    request as draft_request,
)

APP = Path(__file__).resolve().parents[1] / "almdina_erp"
ROOT = Path(__file__).resolve().parents[1]


class MemoryDrawingStore:
    def __init__(self):
        self.rows = {}

    def lock(self, key):
        row = self.rows.get(key)
        return None if row is None else copy.deepcopy(row)

    def read(self, key):
        return self.lock(key)

    def read_for_plan(self, order_name, plan_name):
        return [
            copy.deepcopy(row)
            for row in self.rows.values()
            if row.get("door_cutting_order") == order_name and row.get("source_plan") == plan_name
        ]

    def insert(self, row):
        if row["drawing_key"] in self.rows:
            raise DrawingInsertConflict
        self.rows[row["drawing_key"]] = copy.deepcopy(row)
        return copy.deepcopy(row)

    def update_if_version(self, key, expected_version, changes):
        current = self.rows.get(key)
        if current is None or int(current["drawing_version"]) != int(expected_version):
            return False
        current.update(copy.deepcopy(dict(changes)))
        return True

    def archive_many(self, updates):
        for update in updates:
            row = self.rows.get(update["drawing_key"])
            if row is None or int(row["drawing_version"]) != int(update["expected_version"]):
                return False
        for update in updates:
            self.rows[update["drawing_key"]].update(copy.deepcopy(dict(update["changes"])))
        return True


def _document(piece_id="piece:a", paths=None, shapes=None, references=None, width=600, length=2100):
    return {
        "schema": SCHEMA,
        "version": 1,
        "units": "mm",
        "coordinate_space": "door_local",
        "piece_instance_id": piece_id,
        "blank": {"width_mm": width, "length_mm": length},
        "paths": list(paths or []),
        "shapes": list(shapes or []),
        "references": list(references or []),
    }


def _line(path_id="path-1", x=350, role="manufacturing_outer"):
    return {
        "id": path_id,
        "role": role,
        "closed": False,
        "source_shape_id": None,
        "nodes": [
            {"id": "n1", "x_mm": 0, "y_mm": 0},
            {"id": "n2", "x_mm": x, "y_mm": 0},
        ],
        "segments": [
            {"id": "s1", "kind": "line", "from_node": "n1", "to_node": "n2"},
        ],
    }


def _curve():
    return {
        "id": "path-curve",
        "role": "annotation",
        "closed": False,
        "source_shape_id": None,
        "nodes": [
            {"id": "n1", "x_mm": 0, "y_mm": 0},
            {"id": "n2", "x_mm": 100, "y_mm": 0},
        ],
        "segments": [
            {
                "id": "s-curve",
                "kind": "bezier",
                "from_node": "n1",
                "to_node": "n2",
                "controls": [
                    {"x_mm": 20, "y_mm": 40},
                    {"x_mm": 80, "y_mm": -10},
                ],
            }
        ],
    }


def _rectangle():
    return {
        "id": "shape-rect",
        "kind": "rectangle",
        "exploded": False,
        "path_id": None,
        "params": {"x_mm": 0, "y_mm": 0, "width_mm": 600, "height_mm": 400, "rotation_deg": 0},
    }


def _reference(file_id="FILE-PRIVATE-1"):
    return {
        "id": "ref-1",
        "file_id": file_id,
        "x_mm": 0,
        "y_mm": 0,
        "width_mm": 600,
        "height_mm": 2100,
        "rotation_deg": 0,
        "opacity": 0.45,
        "locked": True,
        "hidden": False,
        "calibration": None,
    }


def _context(**overrides):
    payload = {
        "order_name": "ORD-1",
        "plan_name": "PLAN-1",
        "order_status": "Draft",
        "has_edit_capability": True,
        "has_plan_view": True,
        "source_input_fingerprint": "fp-a",
        "source_content_revision": "rev-a",
        "catalog": {
            "piece:a": {"piece_type": "Special", "blank_width_mm": 600.0, "blank_length_mm": 2100.0},
            "piece:b": {"piece_type": "Special", "blank_width_mm": 400.0, "blank_length_mm": 800.0},
            "piece:regular": {"piece_type": "Regular", "blank_width_mm": 500.0, "blank_length_mm": 700.0},
            "piece:unproven": {"piece_type": "Special", "blank_width_mm": None, "blank_length_mm": None},
        },
        "trusted_file_ids": (),
    }
    payload.update(overrides)
    return payload


def _request(document, piece_id="piece:a", version=0, revision="rev-a", **overrides):
    payload = {
        "order_name": "ORD-1",
        "plan_name": "PLAN-1",
        "piece_instance_id": piece_id,
        "expected_drawing_version": version,
        "source_content_revision": revision,
        "drawing": document,
    }
    payload.update(overrides)
    return payload


class BoardEditorDrawingPersistenceTests(unittest.TestCase):
    def test_save_and_reload_keeps_the_same_geometry(self):
        store = MemoryDrawingStore()
        document = _document(paths=[_line()])
        saved = execute_save_drawing(_request(document), _context(), store)
        self.assertTrue(saved["ok"])
        self.assertEqual(saved["drawing_version"], 1)
        loaded = execute_get_drawing(_request(None), _context(), store)
        self.assertEqual(loaded["drawing"]["paths"], normalize_document(document)["paths"])
        self.assertEqual(loaded["document_fingerprint"], saved["document_fingerprint"])
        self.assertTrue(loaded["active"])
        self.assertTrue(loaded["compatible"])

    def test_several_special_pieces_keep_separate_documents(self):
        store = MemoryDrawingStore()
        first = execute_save_drawing(_request(_document(paths=[_line(x=350)])), _context(), store)
        second = execute_save_drawing(
            _request(_document("piece:b", paths=[_line(x=120)], width=400, length=800), piece_id="piece:b"),
            _context(),
            store,
        )
        self.assertTrue(first["ok"] and second["ok"])
        self.assertNotEqual(first["document_fingerprint"], second["document_fingerprint"])
        self.assertNotEqual(
            drawing_key("ORD-1", "PLAN-1", "piece:a"),
            drawing_key("ORD-1", "PLAN-1", "piece:b"),
        )
        loaded_a = execute_get_drawing(_request(None), _context(), store)
        loaded_b = execute_get_drawing(_request(None, piece_id="piece:b"), _context(), store)
        self.assertEqual(loaded_a["drawing"]["paths"][0]["nodes"][1]["x_mm"], 350.0)
        self.assertEqual(loaded_b["drawing"]["paths"][0]["nodes"][1]["x_mm"], 120.0)
        listed = execute_list_drawings(_request(None), _context(), store)
        self.assertTrue(all("drawing" not in row for row in listed["drawings"]))
        self.assertNotIn("paths", str(listed["drawings"]))

    def test_unknown_piece_is_rejected(self):
        store = MemoryDrawingStore()
        result = execute_save_drawing(
            _request(_document("piece:missing"), piece_id="piece:missing"),
            _context(),
            store,
        )
        self.assertEqual(result["code"], "unknown_piece")
        self.assertEqual(store.rows, {})
        loaded = execute_get_drawing(_request(None, piece_id="piece:missing"), _context(), store)
        self.assertEqual(loaded["code"], "unknown_piece")

    def test_document_piece_id_cannot_redirect_the_write(self):
        store = MemoryDrawingStore()
        result = execute_save_drawing(
            _request(_document("piece:b", width=400, length=800), piece_id="piece:a"),
            _context(),
            store,
        )
        self.assertEqual(result["code"], "piece_mismatch")
        self.assertEqual(store.rows, {})

    def test_plan_from_another_order_is_rejected(self):
        store = MemoryDrawingStore()
        result = execute_save_drawing(
            _request(_document(), plan_name="PLAN-OTHER"),
            _context(),
            store,
        )
        self.assertEqual(result["code"], "order_plan_mismatch")
        self.assertEqual(store.rows, {})

    def test_save_requires_board_editor_capability(self):
        store = MemoryDrawingStore()
        result = execute_save_drawing(
            _request(_document()),
            _context(has_edit_capability=False),
            store,
        )
        self.assertEqual(result["code"], "permission_denied")
        self.assertEqual(store.rows, {})
        hidden = execute_get_drawing(_request(None), _context(has_plan_view=False), store)
        self.assertEqual(hidden["code"], "permission_denied")

    def test_locked_order_rejects_save_and_still_allows_scoped_read(self):
        store = MemoryDrawingStore()
        execute_save_drawing(_request(_document(paths=[_line()])), _context(), store)
        denied = execute_save_drawing(
            _request(_document(paths=[_line(x=10)]), version=1),
            _context(order_status="Delivered"),
            store,
        )
        self.assertEqual(denied["code"], "order_locked")
        loaded = execute_get_drawing(_request(None), _context(order_status="Cancelled"), store)
        self.assertTrue(loaded["ok"])
        self.assertFalse(loaded["can_edit"])
        self.assertEqual(loaded["drawing"]["paths"][0]["nodes"][1]["x_mm"], 350.0)

    def test_blank_must_match_the_trusted_piece(self):
        store = MemoryDrawingStore()
        result = execute_save_drawing(
            _request(_document(width=600.1)),
            _context(),
            store,
        )
        self.assertEqual(result["code"], "blank_mismatch")
        self.assertEqual(store.rows, {})
        unproven = execute_save_drawing(
            _request(_document("piece:unproven"), piece_id="piece:unproven"),
            _context(),
            store,
        )
        self.assertEqual(unproven["code"], "blank_unproven")

    def test_open_path_empty_curve_and_parametric_documents_save(self):
        store = MemoryDrawingStore()
        cases = [
            _document(),
            _document(paths=[_line(role="manufacturing_outer")]),
            _document(paths=[_curve()]),
            _document(shapes=[_rectangle()]),
            _document(paths=[_line(role="annotation")]),
        ]
        version = 0
        for document in cases:
            result = execute_save_drawing(_request(document, version=version), _context(), store)
            self.assertTrue(result["ok"], result)
            self.assertEqual(result["drawing"]["paths"], normalize_document(document)["paths"])
            version = result["drawing_version"]
        self.assertEqual(version, 5)

    def test_second_save_increments_version_and_same_content_does_not(self):
        store = MemoryDrawingStore()
        first = execute_save_drawing(_request(_document(paths=[_line()])), _context(), store)
        repeat = execute_save_drawing(
            _request(_document(paths=[_line()]), version=first["drawing_version"]),
            _context(),
            store,
        )
        self.assertTrue(repeat["idempotent"])
        self.assertEqual(repeat["drawing_version"], 1)
        again = execute_save_drawing(_request(_document(paths=[_line()]), version=0), _context(), store)
        self.assertTrue(again["idempotent"])
        self.assertEqual(again["drawing_version"], 1)
        changed = execute_save_drawing(
            _request(_document(paths=[_line(x=120)]), version=1),
            _context(),
            store,
        )
        self.assertEqual(changed["drawing_version"], 2)
        self.assertFalse(changed["idempotent"])

    def test_version_conflict_keeps_the_newer_document(self):
        store = MemoryDrawingStore()
        execute_save_drawing(_request(_document(paths=[_line(x=100)])), _context(), store)
        newer = execute_save_drawing(
            _request(_document(paths=[_line(x=200)]), version=1),
            _context(),
            store,
        )
        stale = execute_save_drawing(
            _request(_document(paths=[_line(x=300)]), version=1),
            _context(),
            store,
        )
        self.assertEqual(stale["code"], "version_conflict")
        self.assertEqual(stale["current_drawing_version"], 2)
        loaded = execute_get_drawing(_request(None), _context(), store)
        self.assertEqual(loaded["drawing_version"], 2)
        self.assertEqual(loaded["document_fingerprint"], newer["document_fingerprint"])

    def test_source_change_is_rejected_and_the_old_drawing_stays(self):
        store = MemoryDrawingStore()
        saved = execute_save_drawing(_request(_document(paths=[_line()])), _context(), store)
        rejected = execute_save_drawing(
            _request(_document(paths=[_line(x=10)]), version=1, revision="rev-b"),
            _context(source_content_revision="rev-b", source_input_fingerprint="fp-b"),
            store,
        )
        self.assertEqual(rejected["code"], "source_conflict")
        row = next(iter(store.rows.values()))
        self.assertEqual(row["source_content_revision"], "rev-a")
        self.assertEqual(row["document_fingerprint"], saved["document_fingerprint"])
        hidden = execute_get_drawing(
            _request(None),
            _context(source_content_revision="rev-b"),
            store,
        )
        self.assertEqual(hidden["conflict"], "source")
        self.assertIsNone(hidden["drawing"])
        self.assertFalse(hidden["active"])
        self.assertEqual(hidden["drawing_version"], 1)

    def test_distribution_save_does_not_change_or_clear_a_drawing(self):
        drawings = MemoryDrawingStore()
        drafts = DraftMemoryStore()
        execute_save_drawing(_request(_document(paths=[_line()])), _context(), drawings)
        before = execute_save(draft_request(layout()), draft_context(), drafts)
        fingerprint = before["distribution_fingerprint"]
        changed = execute_save_drawing(
            _request(_document(paths=[_line(x=80)]), version=1),
            _context(),
            drawings,
        )
        self.assertEqual(changed["drawing_version"], 2)
        self.assertEqual(next(iter(drafts.rows.values()))["distribution_fingerprint"], fingerprint)
        moved = layout()
        moved["pieces"][0]["local_x_mm"] = 80
        after = execute_save(draft_request(moved, version=1), draft_context(), drafts)
        self.assertNotEqual(after["distribution_fingerprint"], fingerprint)
        loaded = execute_get_drawing(_request(None), _context(), drawings)
        self.assertEqual(loaded["drawing_version"], 2)
        self.assertEqual(loaded["drawing"]["paths"][0]["nodes"][1]["x_mm"], 80.0)

    def test_archive_starts_an_empty_drawing_and_retains_the_old_one(self):
        store = MemoryDrawingStore()
        execute_save_drawing(_request(_document(paths=[_line()])), _context(), store)
        live = _context(source_content_revision="rev-b", source_input_fingerprint="fp-b")
        archived = execute_archive_drawings_for_new_source(
            _request(None, revision="rev-b"),
            live,
            store,
        )
        self.assertEqual(archived["code"], "archived")
        self.assertEqual(archived["archived_count"], 1)
        loaded = execute_get_drawing(_request(None), live, store)
        self.assertTrue(loaded["active"])
        self.assertEqual(loaded["drawing"]["paths"], [])
        self.assertEqual(loaded["drawing_version"], 2)
        self.assertEqual(loaded["drawing"]["piece_instance_id"], "piece:a")
        history = execute_get_drawing_archive(_request(None), live, store)
        self.assertEqual(history["entries"][0]["drawing"]["paths"][0]["nodes"][1]["x_mm"], 350.0)
        self.assertEqual(history["entries"][0]["source_content_revision"], "rev-a")
        self.assertFalse(history["active"])
        second = execute_archive_drawings_for_new_source(_request(None, revision="rev-b"), live, store)
        self.assertEqual(second["code"], "unchanged")
        self.assertEqual(len(execute_get_drawing_archive(_request(None), live, store)["entries"]), 1)
        stale_view = execute_get_drawing(_request(None), _context(), store)
        self.assertEqual(stale_view["conflict"], "source")
        self.assertIsNone(stale_view["drawing"])

    def test_archive_does_not_rebind_a_piece_outside_the_current_catalog(self):
        store = MemoryDrawingStore()
        execute_save_drawing(_request(_document(paths=[_line()])), _context(), store)
        orphan_document = normalize_document(_document("piece:gone", paths=[_line(x=42)]))
        orphan_key = drawing_key("ORD-1", "PLAN-1", "piece:gone")
        store.rows[orphan_key] = {
            "drawing_key": orphan_key,
            "door_cutting_order": "ORD-1",
            "source_plan": "PLAN-1",
            "piece_instance_id": "piece:gone",
            "source_input_fingerprint": "fp-a",
            "source_content_revision": "rev-a",
            "drawing_version": 4,
            "document_fingerprint": document_fingerprint(orphan_document),
            "drawing_json": orphan_document,
            "prior_drawing_archive_json": [],
        }
        result = execute_archive_drawings_for_new_source(
            _request(None, revision="rev-b"),
            _context(source_content_revision="rev-b", source_input_fingerprint="fp-b"),
            store,
        )
        self.assertEqual(result["archived_count"], 1)
        orphan = store.rows[orphan_key]
        self.assertEqual(orphan["source_content_revision"], "rev-a")
        self.assertEqual(orphan["drawing_version"], 4)
        self.assertEqual(orphan["drawing_json"]["paths"][0]["nodes"][1]["x_mm"], 42.0)
        self.assertEqual(
            execute_get_drawing(_request(None, piece_id="piece:gone"), _context(), store)["code"],
            "unknown_piece",
        )

    def test_archive_limit_keeps_every_existing_row(self):
        store = MemoryDrawingStore()
        execute_save_drawing(_request(_document(paths=[_line()])), _context(), store)
        execute_save_drawing(
            _request(_document("piece:b", paths=[_line(x=80)], width=400, length=800), piece_id="piece:b"),
            _context(),
            store,
        )
        with patch.object(persistence, "MAX_DRAWING_ARCHIVES", 0):
            result = execute_archive_drawings_for_new_source(
                _request(None, revision="rev-b"),
                _context(source_content_revision="rev-b"),
                store,
            )
        self.assertEqual(result["code"], "archive_limit")
        self.assertTrue(all(row["source_content_revision"] == "rev-a" for row in store.rows.values()))
        self.assertTrue(all(row["prior_drawing_archive_json"] == [] for row in store.rows.values()))
        self.assertTrue(all(row["drawing_json"]["paths"] for row in store.rows.values()))

    def test_untrusted_reference_is_rejected_until_a_proven_file_id_is_supplied(self):
        store = MemoryDrawingStore()
        rejected = execute_save_drawing(
            _request(_document(references=[_reference()])),
            _context(),
            store,
        )
        self.assertEqual(rejected["code"], "untrusted_reference")
        self.assertEqual(store.rows, {})
        accepted = execute_save_drawing(
            _request(_document(references=[_reference("FILE-PROVEN")])),
            _context(trusted_file_ids=("FILE-PROVEN",)),
            store,
        )
        self.assertTrue(accepted["ok"])
        self.assertEqual(accepted["drawing"]["references"][0]["file_id"], "FILE-PROVEN")

    def test_conditional_update_failure_does_not_replace_the_row(self):
        store = MemoryDrawingStore()
        execute_save_drawing(_request(_document(paths=[_line()])), _context(), store)

        def refuse(key, expected_version, changes):
            return False

        store.update_if_version = refuse
        result = execute_save_drawing(
            _request(_document(paths=[_line(x=20)]), version=1),
            _context(),
            store,
        )
        self.assertEqual(result["code"], "version_conflict")
        self.assertEqual(next(iter(store.rows.values()))["drawing_json"]["paths"][0]["nodes"][1]["x_mm"], 350.0)

    def test_coordinated_save_keeps_distribution_when_a_drawing_conflicts(self):
        drafts = DraftMemoryStore()
        drawings = MemoryDrawingStore()
        blocked = execute_coordinated_editor_save(
            draft_request(layout(), version=4),
            [_request(_document())],
            draft_context(),
            _context(),
            drafts,
            drawings,
        )
        self.assertFalse(blocked["ok"])
        self.assertEqual(drawings.rows, {})
        self.assertEqual(drafts.rows, {})
        saved = execute_coordinated_editor_save(
            draft_request(layout()),
            [_request(_document(paths=[_line()]), version=3)],
            draft_context(),
            _context(),
            drafts,
            drawings,
        )
        self.assertEqual(saved["code"], "partial")
        self.assertEqual(saved["distribution"]["draft_version"], 1)
        self.assertEqual(drawings.rows, {})
        fingerprint = saved["distribution"]["distribution_fingerprint"]
        self.assertEqual(next(iter(drafts.rows.values()))["distribution_fingerprint"], fingerprint)

    def test_catalog_converts_trusted_centimetres_and_only_special_pieces_are_drawable(self):
        catalog = drawing_catalog_from_pieces(
            [
                {"piece_instance_id": "piece:a", "piece_type": "Special", "original_w": 60, "original_h": 210},
                {"piece_instance_id": "piece:regular", "piece_type": "Regular", "width_cm": 50, "length_cm": 70},
            ]
        )
        self.assertEqual(catalog["piece:a"]["blank_width_mm"], 600.0)
        self.assertEqual(catalog["piece:a"]["blank_length_mm"], 2100.0)
        store = MemoryDrawingStore()
        result = execute_save_drawing(
            _request(_document("piece:regular", width=500, length=700), piece_id="piece:regular"),
            _context(),
            store,
        )
        self.assertEqual(result["code"], "piece_not_drawable")

    def test_manufacturing_contracts_and_layout_geometry_stay_closed(self):
        self.assertEqual(GEOMETRY_SCHEMA_VERSION, 1)
        self.assertEqual(GEOMETRY_UNIT, "mm")
        self.assertEqual(GEOMETRY_COORDINATE_SPACE, "usable_sheet")
        self.assertIn("geometry", FORBIDDEN_FIELDS)
        with self.assertRaises(DraftLayoutError):
            normalize_layout(_document(), draft_catalog())
        drawing_source = (APP / "domain" / "cutting" / "board_editor_drawing.py").read_text(encoding="utf-8")
        persistence_source = (
            APP / "domain" / "cutting" / "board_editor_drawing_persistence.py"
        ).read_text(encoding="utf-8")
        application_source = (
            APP / "application" / "cutting" / "board_editor_drawing_save.py"
        ).read_text(encoding="utf-8")
        service_source = (APP / "services" / "board_editor_drawing_service.py").read_text(encoding="utf-8")
        store_source = (
            APP / "infrastructure" / "frappe" / "board_editor_drawing_store.py"
        ).read_text(encoding="utf-8")
        draft_service = (APP / "services" / "board_editor_draft_service.py").read_text(encoding="utf-8")
        draft_save = (APP / "application" / "cutting" / "board_editor_draft_save.py").read_text(encoding="utf-8")
        query_source = (APP / "services" / "board_editor_query_service.py").read_text(encoding="utf-8")
        self.assertNotIn("import frappe", drawing_source)
        self.assertNotIn("import frappe", persistence_source)
        self.assertNotIn("import frappe", application_source)
        self.assertNotIn("geometry_fingerprint", application_source)
        self.assertNotIn("board_editor_drawing", draft_save)
        self.assertNotIn("drawing_json", query_source)
        for source in (service_source, store_source, draft_service):
            self.assertNotIn("snapshot_json", source)
            self.assertNotIn(".save(", source)
            self.assertNotIn("special_shape_geometry_json", source)
            self.assertNotIn("plan_needs_recalculation", source)
        self.assertNotIn("EDIT_SPECIAL_DRAWING", service_source)
        self.assertIn("proven_reference_file_ids", service_source)
        self.assertNotIn("request.get(\"trusted_file_ids\")", service_source)
        self.assertNotIn("drawing.get(\"references\")", service_source)
        self.assertIn("archive_drawings_after_source_begin", draft_service)
        self.assertIn("frappe.db.rollback()", service_source)
        self.assertNotIn('get_doc("Cutting Plan"', store_source)
        catalog = (ROOT / "translations" / "ar.csv").read_text(encoding="utf-8")
        self.assertIn("You do not have permission to save this board editor drawing.", catalog)
        contracts = (ROOT / "tests" / "security_endpoint_contracts.py").read_text(encoding="utf-8")
        for name in (
            "get_board_editor_drawing",
            "list_board_editor_drawings",
            "save_board_editor_drawing",
            "get_board_editor_drawing_archive",
            "upload_board_editor_reference_image",
            "get_board_editor_reference_image",
        ):
            self.assertIn(name, contracts)

    def test_construction_polyline_reloads_without_touching_distribution(self):
        path = {
            "id": "p1",
            "role": "construction",
            "closed": False,
            "source_shape_id": None,
            "nodes": [
                {"id": "n1", "x_mm": 0, "y_mm": 0},
                {"id": "n2", "x_mm": 350, "y_mm": 0},
                {"id": "n3", "x_mm": 350, "y_mm": 120},
            ],
            "segments": [
                {"id": "s1", "kind": "line", "from_node": "n1", "to_node": "n2"},
                {"id": "s2", "kind": "line", "from_node": "n2", "to_node": "n3"},
            ],
        }
        document = _document(paths=[path])
        normalized = normalize_document(document)
        self.assertEqual(normalized["paths"][0]["role"], "construction")
        self.assertEqual(len(normalized["paths"][0]["nodes"]), 3)
        self.assertEqual(normalized["paths"][0]["segments"][0]["to_node"], "n2")
        self.assertEqual(normalized["paths"][0]["segments"][1]["from_node"], "n2")
        self.assertNotIn("length_mm", normalized["paths"][0]["segments"][0])
        store = MemoryDrawingStore()
        saved = execute_save_drawing(_request(document), _context(), store)
        self.assertTrue(saved["ok"])
        self.assertNotIn("distribution_fingerprint", saved)
        loaded = execute_get_drawing(_request(None), _context(), store)
        self.assertEqual(loaded["drawing"]["paths"][0]["nodes"][1]["x_mm"], 350.0)
        self.assertEqual(loaded["drawing"]["paths"][0]["nodes"][2]["y_mm"], 120.0)
        other = execute_save_drawing(
            _request(_document("piece:b", paths=[_line(x=80)], width=400, length=800), piece_id="piece:b"),
            _context(),
            store,
        )
        self.assertTrue(other["ok"])
        reloaded = execute_get_drawing(_request(None), _context(), store)
        self.assertEqual(reloaded["drawing"]["paths"][0]["nodes"][1]["x_mm"], 350.0)
        changed = _document(paths=[{
            **path,
            "nodes": [
                {"id": "n1", "x_mm": 0, "y_mm": 0},
                {"id": "n2", "x_mm": 360, "y_mm": 0},
                {"id": "n3", "x_mm": 360, "y_mm": 120},
            ],
        }])
        conflict = execute_save_drawing(_request(changed, version=0), _context(), store)
        self.assertEqual(conflict["code"], "version_conflict")
        self.assertEqual(store.rows[drawing_key("ORD-1", "PLAN-1", "piece:a")]["drawing_json"]["paths"][0]["nodes"][1]["x_mm"], 350.0)
        source = execute_save_drawing(_request(document, version=1, revision="rev-old"), _context(), store)
        self.assertEqual(source["code"], "source_conflict")
        self.assertNotIn("special_shape_geometry_json", saved)
        self.assertNotIn("snapshot_json", saved)

    def test_missing_draft_restores_only_the_stored_polygon(self):
        context = _context()
        context["catalog"]["piece:a"]["editable_outline_mm"] = [
            [0.0, 0.0], [600.0, 0.0], [600.0, 2100.0], [0.0, 2100.0],
        ]
        loaded = execute_get_drawing(_request(None), context, MemoryDrawingStore())
        self.assertTrue(loaded["reconstructed"])
        self.assertFalse(loaded["present"])
        self.assertEqual(loaded["drawing_version"], 0)
        path = loaded["drawing"]["paths"][0]
        self.assertEqual(path["role"], "manufacturing_outer")
        self.assertTrue(all(segment["kind"] == "line" for segment in path["segments"]))
        self.assertEqual(loaded["drawing"]["references"], [])
        self.assertEqual(loaded["drawing"]["shapes"], [])
        saved = execute_save_drawing(_request(_document()), _context(), MemoryDrawingStore())
        self.assertTrue(saved["ok"])
        store = MemoryDrawingStore()
        execute_save_drawing(_request(_document()), context, store)
        again = execute_get_drawing(_request(None), context, store)
        self.assertNotIn("reconstructed", again)
        self.assertEqual(again["drawing"]["paths"], [])


if __name__ == "__main__":
    unittest.main()
