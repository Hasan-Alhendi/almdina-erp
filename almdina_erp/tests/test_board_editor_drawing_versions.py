"""Drawing version sets must match before a cutting-plan copy is frozen."""

from __future__ import annotations

import copy
import unittest
from pathlib import Path

from almdina_erp.almdina_erp.application.cutting.board_editor_drawing_save import (
    execute_archive_drawings_for_new_source,
    execute_save_drawing,
)
from almdina_erp.almdina_erp.application.cutting.board_editor_plan_create import (
    CreateBoardEditorPlanCommand,
    compile_saved_drawings,
    execute_create,
)
from almdina_erp.almdina_erp.services.board_editor_plan_create_service import _drawing_versions
from almdina_erp.tests.test_board_editor_drawing_persistence import (
    MemoryDrawingStore,
    _context,
    _document,
    _line,
    _request,
)
from almdina_erp.tests.test_board_editor_plan_materialize import (
    draft_payload,
    layout_rows,
    projection,
    projection_piece,
    source_snapshot,
)

ROOT = Path(__file__).resolve().parents[1]
STORE_SOURCE = (
    ROOT / "almdina_erp" / "infrastructure" / "frappe" / "board_editor_drawing_store.py"
).read_text(encoding="utf-8")


def _record(instance, version, marker, fingerprint="fp-1"):
    document = _document(instance, paths=[_line(x=marker)])
    return {
        "piece_instance_id": instance,
        "drawing_version": version,
        "source_input_fingerprint": fingerprint,
        "document": document,
        "drawing_json": document,
    }


class DrawingVersionSetTests(unittest.TestCase):
    def test_a_plan_without_drawings_can_be_copied(self):
        pieces = {"A": {"piece_type": "Special", "original_w": 20, "original_h": 20}}
        self.assertEqual(compile_saved_drawings([], pieces, None)["ok"], True)
        self.assertEqual(compile_saved_drawings([], pieces, {})["adopted"], {})

    def test_matching_saved_drawing_is_accepted(self):
        result = compile_saved_drawings(
            [_record("A", 2, 40)],
            {"A": {"piece_type": "Regular"}},
            {"A": 2},
        )
        self.assertTrue(result["ok"])
        self.assertEqual(result["adopted"], {})

    def test_changed_version_new_drawing_and_unopened_drawing_are_conflicts(self):
        stored = [_record("A", 2, 40), _record("B", 1, 80)]
        pieces = {"A": {"piece_type": "Regular"}, "B": {"piece_type": "Regular"}}
        changed = compile_saved_drawings(stored, pieces, {"A": 1, "B": 1})
        self.assertEqual(changed["code"], "drawing_version_conflict")
        created = compile_saved_drawings(stored, pieces, {"A": 2})
        self.assertEqual(created["code"], "drawing_version_conflict")
        opened_only = compile_saved_drawings([_record("hidden", 4, 10)], {}, {"opened": 4})
        self.assertEqual(opened_only["code"], "drawing_version_conflict")

    def test_a_removed_expected_drawing_is_a_conflict(self):
        result = compile_saved_drawings(
            [_record("A", 1, 10)],
            {},
            {"A": 1, "B": 1},
        )
        self.assertEqual(result["code"], "drawing_version_conflict")

    def test_empty_and_missing_versions_do_not_pass_while_drawings_exist(self):
        # Before this fix both calls returned ok and the unseen drawing was copied.
        record = [_record("A", 1, 10)]
        self.assertEqual(compile_saved_drawings(record, {}, {})["code"], "drawing_version_conflict")
        self.assertEqual(compile_saved_drawings(record, {}, None)["code"], "drawing_versions_missing")

    def test_invalid_version_payloads_are_distinct_from_a_real_empty_set(self):
        record = [_record("A", 1, 10)]
        for payload in (["A"], {"A": "nope"}, {"A": -1}, {"A": True}, {"": 1}, ()):
            result = compile_saved_drawings(record, {}, payload)
            self.assertEqual(result["code"], "drawing_versions_invalid", payload)
        self.assertEqual(_drawing_versions(""), None)
        self.assertEqual(_drawing_versions("[]"), ())
        self.assertEqual(_drawing_versions("null"), ())
        self.assertEqual(_drawing_versions("{"), ())
        self.assertEqual(_drawing_versions('{"A": 1}'), {"A": 1})

    def test_this_users_saved_version_is_not_a_false_conflict(self):
        store = MemoryDrawingStore()
        first = execute_save_drawing(_request(_document(paths=[_line()])), _context(), store)
        second = execute_save_drawing(
            _request(_document(paths=[_line(x=80)]), version=first["drawing_version"]),
            _context(),
            store,
        )
        self.assertEqual(second["drawing_version"], 2)
        result = compile_saved_drawings(
            store.read_for_plan("ORD-1", "PLAN-1"),
            {"piece:a": {"piece_type": "Regular"}},
            {"piece:a": 2},
        )
        self.assertTrue(result["ok"])

    def test_two_drawings_on_one_plan_need_the_full_set(self):
        store = MemoryDrawingStore()
        execute_save_drawing(_request(_document(paths=[_line()])), _context(), store)
        execute_save_drawing(
            _request(
                _document("piece:b", paths=[_line(x=80)], width=400, length=800),
                piece_id="piece:b",
            ),
            _context(),
            store,
        )
        rows = store.read_for_plan("ORD-1", "PLAN-1")
        self.assertEqual(
            compile_saved_drawings(rows, {}, {"piece:a": 1})["code"],
            "drawing_version_conflict",
        )
        self.assertTrue(compile_saved_drawings(rows, {}, {"piece:a": 1, "piece:b": 1})["ok"])

    def test_source_fingerprint_change_is_still_rejected_when_versions_match(self):
        result = compile_saved_drawings(
            [_record("A", 1, 10, fingerprint="old")],
            {"A": {"piece_type": "Special", "original_w": 60, "original_h": 210}},
            {"A": 1},
            source_input_fingerprint="new",
        )
        self.assertEqual(result["code"], "source_changed")

    def test_copy_uses_the_locked_set_and_drops_a_stale_snapshot(self):
        fresh = _record("A", 4, 111)
        stale = _record("A", 4, 222)
        copied = _run_copy(expected={"A": 4}, locked=[fresh], stale=[stale])
        self.assertTrue(copied["result"]["ok"], copied["result"])
        stored = next(iter(copied["drawings"].rows.values()))
        self.assertEqual(stored["drawing_json"]["paths"][0]["nodes"][1]["x_mm"], 111.0)
        self.assertEqual(copied["port"].created_names, ["CP-NEW"])

    def test_a_drawing_created_during_copy_stops_the_copy(self):
        seen = _record("A", 1, 10)
        unseen = _record("B", 1, 20)
        copied = _run_copy(expected={"A": 1}, locked=[seen, unseen], stale=[seen])
        self.assertEqual(copied["result"]["code"], "drawing_version_conflict")
        self.assertEqual(copied["port"].created_names, [])
        self.assertEqual(copied["drawings"].rows, {})

    def test_first_insert_takes_the_plan_lock_before_the_row_is_written(self):
        store = _RecordingStore()
        saved = execute_save_drawing(_request(_document(paths=[_line()])), _context(), store)
        self.assertTrue(saved["ok"])
        self.assertEqual(
            [name for name, *_rest in store.calls],
            ["scope", "lock", "scope", "insert"],
        )

    def test_archive_locks_the_plan_before_the_drawing_rows(self):
        store = _RecordingStore()
        execute_save_drawing(_request(_document(paths=[_line()])), _context(), store)
        store.calls.clear()
        archived = execute_archive_drawings_for_new_source(
            _request(None, revision="rev-b"),
            _context(source_content_revision="rev-b", source_input_fingerprint="fp-b"),
            store,
        )
        self.assertEqual(archived["code"], "archived")
        self.assertEqual([name for name, *_rest in store.calls[:2]], ["scope", "drawings"])

    def test_replaying_the_same_copy_request_does_not_create_another_plan(self):
        fresh = _record("A", 1, 10)
        first = _run_copy(expected={"A": 1}, locked=[fresh], request_id="req-once")
        self.assertTrue(first["result"]["ok"])
        first["drawings"].lock_calls = 0
        second = execute_create(
            _command("req-once"),
            order_status="Draft",
            projection=first["projection"],
            machine_type="CNC Router",
            draft_store=first["drafts"],
            plan_port=first["port"],
            drawing_records=[_record("A", 9, 999)],
            expected_drawing_versions={"A": 9},
            drawing_store=first["drawings"],
        )
        self.assertTrue(second["ok"])
        self.assertTrue(second["idempotent"])
        self.assertEqual(second["plan_name"], "CP-NEW")
        self.assertEqual(first["drawings"].lock_calls, 0)
        self.assertEqual(first["port"].created_names, ["CP-NEW"])

    def test_version_failure_leaves_no_plan_and_does_not_change_the_source(self):
        source_before = {"marker": "source"}
        copied = _run_copy(expected={}, locked=[_record("A", 1, 10)])
        self.assertEqual(copied["result"]["code"], "drawing_version_conflict")
        self.assertEqual(copied["port"].created_names, [])
        self.assertEqual(copied["drafts"].row["last_created_plan"], "")
        self.assertEqual(source_before, {"marker": "source"})

    def test_store_locks_only_the_requested_order_and_plan(self):
        locking = STORE_SOURCE.split("def lock_for_plan", 1)[1].split("def _rows_for_plan", 1)[0]
        rows = STORE_SOURCE.split("def _rows_for_plan", 1)[1].split("def insert", 1)[0]
        scope = STORE_SOURCE.split("def lock_scope", 1)[1].split("def lock(", 1)[0]
        self.assertIn("draft_key", scope)
        self.assertIn("FOR UPDATE", scope)
        self.assertIn("door_cutting_order=%s AND source_plan=%s", rows)
        self.assertIn("ORDER BY drawing_key", rows)
        self.assertIn("FOR UPDATE", rows)
        self.assertIn("lock=True", locking)


class _RecordingStore(MemoryDrawingStore):
    def __init__(self):
        super().__init__()
        self.calls = []
        self.lock_calls = 0

    def lock_scope(self, order_name, plan_name):
        self.calls.append(("scope", order_name, plan_name))

    def lock(self, key):
        self.calls.append(("lock", key))
        return super().lock(key)

    def lock_for_plan(self, order_name, plan_name):
        self.calls.append(("drawings", order_name, plan_name))
        self.lock_calls += 1
        return self.read_for_plan(order_name, plan_name)

    def insert(self, row):
        self.calls.append(("insert", row.get("piece_instance_id")))
        return super().insert(row)


def _command(request_id="req-copy"):
    return CreateBoardEditorPlanCommand(
        order_name="ORD-1",
        source_plan_name="PLAN-SRC",
        expected_draft_version=1,
        source_content_revision="rev-1",
        source_input_fingerprint="fp-1",
        create_request_id=request_id,
        draft_name="DRAFT-1",
    )


def _run_copy(*, expected, locked, stale=None, request_id="req-copy"):
    pieces = [projection_piece("A", 1, 0, 0, 600, 2100)]
    proj = projection(pieces)
    source = source_snapshot(pieces)
    draft = draft_payload(layout_rows(pieces))

    class DraftStore:
        def __init__(self):
            self.row = {
                "name": "DRAFT-1",
                "draft_version": 1,
                "source_content_revision": "rev-1",
                "source_input_fingerprint": "fp-1",
                "distribution_fingerprint": draft["distribution_fingerprint"],
                "layout_json": draft["layout"],
                "last_create_request_id": "",
                "last_created_plan": "",
                "last_created_draft_version": 0,
            }

        def lock_draft(self, order_name, plan_name):
            return dict(self.row)

        def record_create(self, **kwargs):
            self.row["last_create_request_id"] = kwargs["request_id"]
            self.row["last_created_plan"] = kwargs["plan_name"]
            self.row["last_created_draft_version"] = kwargs["draft_version"]

    class PlanPort:
        def __init__(self):
            self.created_names = []

        def existing_revisions(self, order_name):
            return [1]

        def create_board_editor_draft(self, **kwargs):
            self.created_names.append("CP-NEW")
            return {"name": "CP-NEW", "revision": 2, "status": "Draft"}

        def apply_snapshot(self, **kwargs):
            return {
                "name": kwargs["plan_name"],
                "revision": 2,
                "status": "Draft",
                "input_fingerprint": "fp-new",
                "content_revision_token": "CP-NEW|sha|2|fp-new|0|0",
            }

        def discard_incomplete_plan(self, plan_name):
            self.created_names.append(("discard", plan_name))

        def load_source_plan(self, order_name, plan_name):
            return {
                "name": plan_name,
                "order_name": order_name,
                "snapshot": source,
                "machine_type": "CNC Router",
            }

    class Drawings(_RecordingStore):
        def lock_for_plan(self, order_name, plan_name):
            self.lock_calls += 1
            return copy.deepcopy(locked)

    drawings = Drawings()
    drafts = DraftStore()
    port = PlanPort()
    result = execute_create(
        _command(request_id),
        order_status="Draft",
        projection=proj,
        machine_type="CNC Router",
        draft_store=drafts,
        plan_port=port,
        drawing_records=list(stale or []),
        expected_drawing_versions=expected,
        drawing_store=drawings,
    )
    return {
        "result": result,
        "drawings": drawings,
        "drafts": drafts,
        "port": port,
        "projection": proj,
    }
