"""Board editor draft contract. No Cutting Plan mutation and no site writes."""

from __future__ import annotations

import unittest
from pathlib import Path

from almdina_erp.almdina_erp.application.cutting.board_editor_draft_save import (
    DraftInsertConflict,
    draft_write_allowed,
    execute_save,
)
from almdina_erp.almdina_erp.domain.cutting.board_editor_draft import (
    DraftLayoutError,
    catalog_from_projection,
    decide_draft_write,
    distribution_fingerprint,
    normalize_content_revision_token,
    normalize_layout,
)

APP = Path(__file__).resolve().parents[1] / "almdina_erp"


def catalog():
    return catalog_from_projection(
        {
            "pieces": [
                {
                    "piece_instance_id": "pi-a",
                    "piece_id": 1,
                    "allow_rotation": True,
                    "allow_rotation_proven": True,
                    "glass_host_piece_id": None,
                },
                {
                    "piece_instance_id": "pi-b",
                    "piece_id": 2,
                    "allow_rotation": False,
                    "allow_rotation_proven": True,
                    "glass_host_piece_id": 1,
                },
            ],
            "sheets": [{"sheet_no": 1}, {"sheet_no": 2}],
        }
    )


def layout(**overrides):
    document = {
        "schema": 1,
        "pieces": [
            piece("pi-a", sheet_no=1, x=10, y=20, rotation=15),
            piece("pi-b", sheet_no=1, x=40, y=50, host=1),
        ],
        "boards": [
            {"sheet_no": 1, "origin_x_mm": 0, "origin_y_mm": 36, "user_moved": False},
            {"sheet_no": 2, "origin_x_mm": 1300, "origin_y_mm": 36, "user_moved": False},
        ],
    }
    document.update(overrides)
    return document


def piece(instance, sheet_no=1, x=0, y=0, rotation=0, distribution="active", reason=None, host=None):
    return {
        "piece_instance_id": instance,
        "sheet_no": sheet_no,
        "local_x_mm": x,
        "local_y_mm": y,
        "rotation_deg": rotation,
        "distribution": distribution,
        "exclusion_reason": reason,
        "glass_host_piece_id": host,
    }


class MemoryStore:
    def __init__(self):
        self.rows = {}

    def lock(self, key):
        row = self.rows.get(key)
        return None if row is None else dict(row)

    def insert(self, row):
        if row["draft_key"] in self.rows:
            raise DraftInsertConflict
        self.rows[row["draft_key"]] = dict(row)
        return dict(row)

    def update_if_version(self, key, expected_version, changes):
        current = self.rows.get(key)
        if current is None or int(current["draft_version"]) != int(expected_version):
            return False
        current.update(changes)
        return True


def context(status="Draft", revision="rev-a"):
    return {
        "order_name": "ORD-1",
        "plan_name": "PLAN-1",
        "order_status": status,
        "source_input_fingerprint": "fp-a",
        "source_content_revision": revision,
        "catalog": catalog(),
    }


def request(document, version=0, revision="rev-a"):
    return {
        "order_name": "ORD-1",
        "plan_name": "PLAN-1",
        "expected_draft_version": version,
        "source_content_revision": revision,
        "layout": document,
    }


class BoardEditorDraftTests(unittest.TestCase):
    def test_round_trip_keeps_pose_host_exclusion_and_removed_board(self):
        document = layout()
        document["pieces"] = [
            piece("pi-a", sheet_no=None, x=400, y=20, rotation=15),
            piece(
                "pi-b",
                sheet_no=None,
                x=500,
                y=80,
                distribution="excluded",
                reason="removed_from_distribution",
                host=None,
            ),
        ]
        document["boards"] = [
            {"sheet_no": 1, "origin_x_mm": 12, "origin_y_mm": 36, "user_moved": True}
        ]
        normalized = normalize_layout(document, catalog())
        self.assertEqual(normalized["pieces"][0]["rotation_deg"], 15)
        self.assertIsNone(normalized["pieces"][0]["sheet_no"])
        self.assertEqual(normalized["pieces"][1]["distribution"], "excluded")
        self.assertEqual([board["sheet_no"] for board in normalized["boards"]], [1])
        self.assertNotIn("outline_mm", normalized["pieces"][0])

    def test_host_and_guest_survive_when_the_link_is_the_source_link(self):
        normalized = normalize_layout(layout(), catalog())
        guest = next(row for row in normalized["pieces"] if row["piece_instance_id"] == "pi-b")
        self.assertEqual(guest["glass_host_piece_id"], 1)

    def test_rejects_view_only_and_mismatched_order(self):
        self.assertFalse(
            draft_write_allowed(
                has_edit_capability=False,
                has_plan_view=True,
                order_status="Draft",
            )
        )
        self.assertTrue(
            draft_write_allowed(
                has_edit_capability=True,
                has_plan_view=True,
                order_status="Draft",
            )
        )
        store = MemoryStore()
        result = execute_save(
            request(layout()) | {"plan_name": "OTHER"},
            context(),
            store,
        )
        self.assertEqual(result["code"], "order_plan_mismatch")
        self.assertEqual(store.rows, {})

    def test_rejects_forged_identity_rotation_and_scale(self):
        forged = layout()
        forged["pieces"][0]["piece_instance_id"] = "forged"
        with self.assertRaises(DraftLayoutError) as unknown:
            normalize_layout(forged, catalog())
        self.assertEqual(unknown.exception.code, "unknown_piece")

        duplicated = layout()
        duplicated["pieces"].append(piece("pi-a"))
        with self.assertRaises(DraftLayoutError) as duplicate:
            normalize_layout(duplicated, catalog())
        self.assertEqual(duplicate.exception.code, "duplicate_piece")

        rotated = layout()
        rotated["pieces"][1]["rotation_deg"] = 20
        with self.assertRaises(DraftLayoutError) as rotation:
            normalize_layout(rotated, catalog())
        self.assertEqual(rotation.exception.code, "rotation_forbidden")

        scaled = layout()
        scaled["pieces"][0]["scale_x"] = 2
        with self.assertRaises(DraftLayoutError) as scale:
            normalize_layout(scaled, catalog())
        self.assertEqual(scale.exception.code, "forbidden_field")

        huge = layout()
        huge["pieces"][0]["local_x_mm"] = 10**12
        with self.assertRaises(DraftLayoutError) as unbounded:
            normalize_layout(huge, catalog())
        self.assertEqual(unbounded.exception.code, "unbounded")

        host = layout()
        host["pieces"][0]["glass_host_piece_id"] = 2
        with self.assertRaises(DraftLayoutError) as forged_host:
            normalize_layout(host, catalog())
        self.assertEqual(forged_host.exception.code, "forged_host")

    def test_two_tabs_and_source_change_do_not_overwrite(self):
        store = MemoryStore()
        first = execute_save(request(layout(), version=0), context(), store)
        self.assertTrue(first["ok"])
        self.assertEqual(first["draft_version"], 1)
        moved = layout()
        moved["pieces"][0]["local_x_mm"] = 80
        other = execute_save(request(moved, version=0), context(), store)
        self.assertEqual(other["code"], "version_conflict")
        self.assertEqual(other.get("current_draft_version"), 1)
        self.assertEqual(len(store.rows), 1)
        self.assertEqual(store.rows[next(iter(store.rows))]["draft_version"], 1)
        # Local layout from the losing tab must not replace the stored row.
        self.assertEqual(store.rows[next(iter(store.rows))]["layout_json"]["pieces"][0]["local_x_mm"], 10)

        stale = execute_save(request(moved, version=1, revision="rev-b"), context(revision="rev-a"), store)
        self.assertEqual(stale["code"], "source_conflict")
        self.assertEqual(stale.get("current_draft_version"), 1)
        self.assertEqual(store.rows[next(iter(store.rows))]["draft_version"], 1)

        changed_source = execute_save(request(moved, version=1, revision="rev-b"), context(revision="rev-b"), store)
        self.assertEqual(changed_source["code"], "source_conflict")
        self.assertEqual(store.rows[next(iter(store.rows))]["source_content_revision"], "rev-a")

    def test_open_edit_save_twice_then_reopen_save(self):
        store = MemoryStore()
        first = execute_save(request(layout(), version=0), context(), store)
        self.assertTrue(first["ok"])
        edited = layout()
        edited["pieces"][0]["local_x_mm"] = 55
        second = execute_save(request(edited, version=1), context(), store)
        self.assertTrue(second["ok"])
        self.assertEqual(second["draft_version"], 2)
        # Re-open with the saved version and save again without conflict.
        third = execute_save(request(edited, version=2), context(), store)
        self.assertTrue(third["ok"])
        self.assertEqual(third["draft_version"], 2)
        self.assertEqual(third["code"], "saved")
        again = layout()
        again["pieces"][0]["local_x_mm"] = 70
        fourth = execute_save(request(again, version=2), context(), store)
        self.assertTrue(fourth["ok"])
        self.assertEqual(fourth["draft_version"], 3)

    def test_legacy_job_status_token_is_not_a_source_conflict(self):
        base = "CP-1|2026-01-01|1|fp-a|0"
        legacy_idle = f"{base}|idle"
        legacy_done = f"{base}|completed"
        live = f"{base}|0"
        self.assertEqual(normalize_content_revision_token(legacy_idle), live)
        self.assertEqual(normalize_content_revision_token(legacy_done), live)
        self.assertEqual(normalize_content_revision_token(f"{base}|queued"), f"{base}|1")
        self.assertEqual(
            decide_draft_write(
                stored_version=3,
                stored_fingerprint="fp-layout",
                stored_source_revision=legacy_idle,
                expected_version=3,
                layout_fingerprint="fp-layout-2",
                live_source_revision=live,
                request_source_revision=live,
            ),
            "update",
        )
        # A real fingerprint/modified change must still conflict.
        self.assertEqual(
            decide_draft_write(
                stored_version=3,
                stored_fingerprint="fp-layout",
                stored_source_revision=legacy_idle,
                expected_version=3,
                layout_fingerprint="fp-layout-2",
                live_source_revision=f"CP-1|2026-01-02|1|fp-b|0|0",
                request_source_revision=f"CP-1|2026-01-02|1|fp-b|0|0",
            ),
            "source_conflict",
        )

        store = MemoryStore()
        first = execute_save(
            request(layout(), version=0, revision=legacy_idle),
            context(revision=legacy_idle),
            store,
        )
        self.assertTrue(first["ok"])
        moved = layout()
        moved["pieces"][0]["local_x_mm"] = 42
        # Client refreshed and now carries the stable bit; stored still has idle.
        next_save = execute_save(
            request(moved, version=1, revision=live),
            context(revision=live),
            store,
        )
        self.assertTrue(next_save["ok"], next_save)
        self.assertEqual(next_save["draft_version"], 2)
        self.assertEqual(
            store.rows[next(iter(store.rows))]["source_content_revision"],
            live,
        )

    def test_non_conflict_errors_are_not_version_or_source(self):
        store = MemoryStore()
        locked = execute_save(request(layout()), context(status="Delivered"), store)
        self.assertEqual(locked["code"], "order_locked")
        self.assertNotEqual(locked["code"], "version_conflict")
        self.assertNotEqual(locked["code"], "source_conflict")
        mismatch = execute_save(
            {**request(layout()), "order_name": "OTHER"},
            context(),
            store,
        )
        self.assertEqual(mismatch["code"], "order_plan_mismatch")
        self.assertNotIn(mismatch["code"], {"version_conflict", "source_conflict"})

    def test_first_save_is_not_duplicated(self):
        store = MemoryStore()
        document = layout()
        first = execute_save(request(document, version=0), context(), store)
        second = execute_save(request(document, version=0), context(), store)
        self.assertTrue(second["ok"])
        self.assertEqual(second["draft_version"], first["draft_version"])
        self.assertEqual(len(store.rows), 1)
        self.assertEqual(
            decide_draft_write(
                stored_version=1,
                stored_fingerprint=distribution_fingerprint(normalize_layout(document, catalog())),
                stored_source_revision="rev-a",
                expected_version=0,
                layout_fingerprint=distribution_fingerprint(normalize_layout(document, catalog())),
                live_source_revision="rev-a",
                request_source_revision="rev-a",
            ),
            "idempotent",
        )

    def test_locked_order_does_not_save(self):
        store = MemoryStore()
        result = execute_save(request(layout()), context(status="Delivered"), store)
        self.assertEqual(result["code"], "order_locked")
        self.assertEqual(store.rows, {})
        self.assertFalse(
            draft_write_allowed(
                has_edit_capability=True,
                has_plan_view=True,
                order_status="Cancelled",
            )
        )

    def test_service_does_not_mutate_the_cutting_plan(self):
        source = (APP / "services" / "board_editor_draft_service.py").read_text(encoding="utf-8")
        store = (APP / "infrastructure" / "frappe" / "board_editor_draft_store.py").read_text(encoding="utf-8")
        self.assertIn("Capability.EDIT_OPTIMIZER_SETTINGS", source)
        self.assertIn("frappe.PermissionError", source)
        self.assertIn('methods=["POST"]', source)
        self.assertNotIn("snapshot_json", source)
        self.assertNotIn(".save(", source)
        self.assertNotIn("snapshot_json", store)
        self.assertNotIn('get_doc("Cutting Plan"', store)


if __name__ == "__main__":
    unittest.main()
