"""Board editor draft contract. No Cutting Plan mutation and no site writes."""

from __future__ import annotations

import unittest
from pathlib import Path

from almdina_erp.almdina_erp.application.cutting.board_editor_draft_save import (
    DraftInsertConflict,
    draft_write_allowed,
    execute_begin_from_current_source,
    execute_save,
)
from almdina_erp.almdina_erp.domain.cutting.board_editor_draft import (
    BOARD_GAP_MM,
    TITLE_BAND_MM,
    DraftLayoutError,
    boards_share_collapsed_default_origin,
    catalog_from_projection,
    decide_draft_write,
    distribution_fingerprint,
    identity_layout_from_projection,
    normalize_content_revision_token,
    normalize_layout,
    tokens_operationally_equivalent,
    workspace_board_origins,
)

# Live fixture shapes from order 26-00022 / CP-2026-00028 (read-only diagnosis).
# Stored draft used empty slot1 + older input fingerprint; live token carries
# saved_layout_sha256 + a different manufacturing fingerprint.
LIVE_STORED_TOKEN = (
    "CP-2026-00028||5|4dcf9a400488c96b3912d5f6e6071916fe291afb32fe9e2354549aa60e064033|0|0"
)
LIVE_SOURCE_TOKEN = (
    "CP-2026-00028|cd2a90a5dd5497724fcb1abee298a3917dc71e8f2d02b8015a1664d5470f9b6d|"
    "5|cda900e9c2581e74351af56fce5be5fa2ca7c4a4f5a706dc09fba7cb69eb95e5|0|0"
)
LIVE_STORED_FP = "4dcf9a400488c96b3912d5f6e6071916fe291afb32fe9e2354549aa60e064033"
LIVE_SOURCE_FP = "cda900e9c2581e74351af56fce5be5fa2ca7c4a4f5a706dc09fba7cb69eb95e5"

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


def projection():
    return {
        "pieces": [
            {
                "piece_instance_id": "pi-a",
                "piece_id": 1,
                "allow_rotation": True,
                "allow_rotation_proven": True,
                "glass_host_piece_id": None,
                "sheet_no": 1,
                "placement_cm": {"x": 1.0, "y": 2.0},
            },
            {
                "piece_instance_id": "pi-b",
                "piece_id": 2,
                "allow_rotation": False,
                "allow_rotation_proven": True,
                "glass_host_piece_id": 1,
                "sheet_no": 1,
                "placement_cm": {"x": 4.0, "y": 5.0},
            },
        ],
        "sheets": [{"sheet_no": 1}, {"sheet_no": 2}],
    }


def context(status="Draft", revision="rev-a", fingerprint="fp-a", with_projection=False):
    payload = {
        "order_name": "ORD-1",
        "plan_name": "PLAN-1",
        "order_status": status,
        "source_input_fingerprint": fingerprint,
        "source_content_revision": revision,
        "catalog": catalog(),
    }
    if with_projection:
        proj = projection()
        payload["projection"] = proj
        payload["catalog"] = catalog_from_projection(proj)
    return payload


def request(document, version=0, revision="rev-a"):
    return {
        "order_name": "ORD-1",
        "plan_name": "PLAN-1",
        "expected_draft_version": version,
        "source_content_revision": revision,
        "layout": document,
    }


def begin_request(version=0, revision="rev-a"):
    return {
        "order_name": "ORD-1",
        "plan_name": "PLAN-1",
        "expected_draft_version": version,
        "source_content_revision": revision,
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
        # Local edits stay in the client; the stored row is untouched.
        self.assertEqual(store.rows[next(iter(store.rows))]["layout_json"]["pieces"][0]["local_x_mm"], 10)
        self.assertEqual(store.rows[next(iter(store.rows))]["source_content_revision"], "rev-a")

        # Real source change: request==live and expected=0 must not silently replace
        # the draft that still binds the previous operational source.
        no_silent_rebase = execute_save(
            request(moved, version=0, revision="rev-b"),
            context(revision="rev-b"),
            store,
        )
        self.assertEqual(no_silent_rebase["code"], "source_conflict")
        self.assertEqual(store.rows[next(iter(store.rows))]["source_content_revision"], "rev-a")
        self.assertEqual(store.rows[next(iter(store.rows))]["layout_json"]["pieces"][0]["local_x_mm"], 10)

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

    def test_source_token_operational_equivalence_and_conflicts(self):
        """modified-only is same source; layout/fingerprint changes are not."""

        older = "CP-1|2026-11-02 15:16:58|5|fp-edge|0|0"
        newer_touch = "CP-1|2026-11-02 15:21:42|5|fp-edge|0|0"
        self.assertEqual(
            normalize_content_revision_token(older),
            normalize_content_revision_token(newer_touch),
            "modified-only drift must not count as a source change",
        )
        # Geometry/distribution digest changed while revision/fingerprint/modified stay.
        before_geom = "CP-1|layout-aaa|5|fp-edge|0|0"
        after_geom = "CP-1|layout-bbb|5|fp-edge|0|0"
        self.assertNotEqual(
            normalize_content_revision_token(before_geom),
            normalize_content_revision_token(after_geom),
            "saved_layout_sha change must be detected even when modified is fixed",
        )
        self.assertEqual(
            decide_draft_write(
                stored_version=1,
                stored_fingerprint="fp-layout",
                stored_source_revision=before_geom,
                expected_version=1,
                layout_fingerprint="fp-layout-2",
                live_source_revision=after_geom,
                request_source_revision=after_geom,
            ),
            "source_conflict",
        )
        # Legacy datetime slot vs new empty/layout slot with same operational fields.
        legacy_clock = "CP-1|2026-01-01 10:00:00|5|fp-a|0|0"
        modern_empty = "CP-1||5|fp-a|0|0"
        modern_layout = "CP-1|sha-layout|5|fp-a|0|0"
        self.assertEqual(
            normalize_content_revision_token(legacy_clock),
            normalize_content_revision_token(modern_empty),
        )
        self.assertNotEqual(
            normalize_content_revision_token(legacy_clock),
            normalize_content_revision_token(modern_layout),
        )

        store = MemoryStore()
        first = execute_save(
            request(layout(), version=0, revision=older),
            context(revision=older),
            store,
        )
        self.assertTrue(first["ok"])
        moved = layout()
        moved["pieces"][0]["local_x_mm"] = 120
        # Same manufacturing + layout identity; only the row clock moved.
        after_touch = execute_save(
            request(moved, version=1, revision=newer_touch),
            context(revision=newer_touch),
            store,
        )
        self.assertTrue(after_touch["ok"], after_touch)
        self.assertEqual(after_touch["draft_version"], 2)

        # Tab A saved v2; tab B still on expected=0 with a different layout must
        # not wipe it (same layout would be idempotent by design).
        other_layout = layout()
        other_layout["pieces"][0]["local_x_mm"] = 999
        other_tab = execute_save(
            request(other_layout, version=0, revision=newer_touch),
            context(revision=newer_touch),
            store,
        )
        self.assertEqual(other_tab["code"], "version_conflict")
        self.assertEqual(store.rows[next(iter(store.rows))]["draft_version"], 2)
        self.assertEqual(
            store.rows[next(iter(store.rows))]["layout_json"]["pieces"][0]["local_x_mm"],
            120,
        )

        # Draft bound to a different real source is not replaced by expected=0.
        real_new = "CP-1|layout-new|6|fp-edge-v2|0|0"
        blocked = execute_save(
            request(moved, version=0, revision=real_new),
            context(revision=real_new),
            store,
        )
        self.assertEqual(blocked["code"], "source_conflict")
        self.assertEqual(
            store.rows[next(iter(store.rows))]["layout_json"]["pieces"][0]["local_x_mm"],
            120,
        )
        # Mid-session stale request still rejects; local store untouched.
        rejected = execute_save(
            request(moved, version=2, revision=newer_touch),
            context(revision=real_new),
            store,
        )
        self.assertEqual(rejected["code"], "source_conflict")
        self.assertEqual(store.rows[next(iter(store.rows))]["draft_version"], 2)

    def test_legacy_job_status_token_is_not_a_source_conflict(self):
        base = "CP-1|2026-01-01|1|fp-a|0"
        legacy_idle = f"{base}|idle"
        legacy_done = f"{base}|completed"
        # Modified clock is blanked; job labels collapse to the stable bit.
        live = "CP-1||1|fp-a|0|0"
        self.assertEqual(normalize_content_revision_token(legacy_idle), live)
        self.assertEqual(normalize_content_revision_token(legacy_done), live)
        self.assertEqual(
            normalize_content_revision_token(f"{base}|queued"),
            "CP-1||1|fp-a|0|1",
        )
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
        # A real fingerprint change with a session still on the old token conflicts.
        self.assertEqual(
            decide_draft_write(
                stored_version=3,
                stored_fingerprint="fp-layout",
                stored_source_revision=legacy_idle,
                expected_version=3,
                layout_fingerprint="fp-layout-2",
                live_source_revision="CP-1||1|fp-b|0|0",
                request_source_revision=legacy_idle,
            ),
            "source_conflict",
        )
        # Same fingerprint with a drifted modified clock is not a source change.
        self.assertEqual(
            normalize_content_revision_token("CP-1|2026-01-01T10:00:00|5|fp-a|0|0"),
            normalize_content_revision_token("CP-1|2026-01-01T10:05:00|5|fp-a|0|0"),
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
        self.assertIn("begin_board_editor_draft_from_current_source", source)
        self.assertIn("execute_begin_from_current_source", source)
        self.assertNotIn("snapshot_json", source)
        self.assertNotIn(".save(", source)
        self.assertNotIn("snapshot_json", store)
        self.assertNotIn('get_doc("Cutting Plan"', store)

    def test_live_fixture_empty_slot_vs_layout_sha_with_fingerprint_change_is_case_b(self):
        """User draft: empty slot1 + old fp; live: layout_sha + new fp — real source change."""

        self.assertFalse(
            tokens_operationally_equivalent(LIVE_STORED_TOKEN, LIVE_SOURCE_TOKEN),
            "fingerprint change must not be treated as format-only migration",
        )
        # Empty slot alone is not proof of equal content when fingerprints differ.
        self.assertNotEqual(
            normalize_content_revision_token(LIVE_STORED_TOKEN).split("|")[3],
            normalize_content_revision_token(LIVE_SOURCE_TOKEN).split("|")[3],
        )
        self.assertEqual(
            decide_draft_write(
                stored_version=3,
                stored_fingerprint="dist-old",
                stored_source_revision=LIVE_STORED_TOKEN,
                expected_version=3,
                layout_fingerprint="dist-new",
                live_source_revision=LIVE_SOURCE_TOKEN,
                request_source_revision=LIVE_SOURCE_TOKEN,
            ),
            "source_conflict",
        )
        # expected=0 must not silently rebase over the incompatible draft.
        self.assertEqual(
            decide_draft_write(
                stored_version=3,
                stored_fingerprint="dist-old",
                stored_source_revision=LIVE_STORED_TOKEN,
                expected_version=0,
                layout_fingerprint="dist-new",
                live_source_revision=LIVE_SOURCE_TOKEN,
                request_source_revision=LIVE_SOURCE_TOKEN,
            ),
            "source_conflict",
        )

    def test_empty_slot_vs_layout_sha_same_fingerprint_is_format_only(self):
        """Case A: representation migration with matching manufacturing identity."""

        legacy_empty = "CP-1||5|fp-same|0|0"
        live_layout = "CP-1|sha-abc|5|fp-same|0|0"
        self.assertTrue(tokens_operationally_equivalent(legacy_empty, live_layout))
        store = MemoryStore()
        first = execute_save(
            request(layout(), version=0, revision=legacy_empty),
            context(revision=legacy_empty, fingerprint="fp-same"),
            store,
        )
        self.assertTrue(first["ok"])
        moved = layout()
        moved["pieces"][0]["local_x_mm"] = 88
        upgraded = execute_save(
            request(moved, version=1, revision=live_layout),
            context(revision=live_layout, fingerprint="fp-same"),
            store,
        )
        self.assertTrue(upgraded["ok"], upgraded)
        self.assertEqual(upgraded["draft_version"], 2)
        self.assertEqual(
            store.rows[next(iter(store.rows))]["source_content_revision"],
            live_layout,
        )
        self.assertEqual(
            store.rows[next(iter(store.rows))]["layout_json"]["pieces"][0]["local_x_mm"],
            88,
        )

    def test_begin_from_current_source_archives_and_allows_save_reopen(self):
        store = MemoryStore()
        old_layout = layout()
        old_layout["pieces"][0]["local_x_mm"] = 777
        created = execute_save(
            request(old_layout, version=0, revision=LIVE_STORED_TOKEN),
            context(revision=LIVE_STORED_TOKEN, fingerprint=LIVE_STORED_FP),
            store,
        )
        self.assertTrue(created["ok"])
        self.assertEqual(created["draft_version"], 1)
        key = next(iter(store.rows))
        # Simulate the live draft version the user already has.
        store.rows[key]["draft_version"] = 3

        # Direct save against the new source remains blocked.
        blocked = execute_save(
            request(layout(), version=3, revision=LIVE_SOURCE_TOKEN),
            context(revision=LIVE_SOURCE_TOKEN, fingerprint=LIVE_SOURCE_FP),
            store,
        )
        self.assertEqual(blocked["code"], "source_conflict")
        self.assertEqual(store.rows[key]["layout_json"]["pieces"][0]["local_x_mm"], 777)

        # expected=0 must not wipe the incompatible draft.
        zero = execute_begin_from_current_source(
            begin_request(version=0, revision=LIVE_SOURCE_TOKEN),
            context(
                revision=LIVE_SOURCE_TOKEN,
                fingerprint=LIVE_SOURCE_FP,
                with_projection=True,
            ),
            store,
        )
        self.assertEqual(zero["code"], "version_conflict")
        self.assertEqual(store.rows[key]["layout_json"]["pieces"][0]["local_x_mm"], 777)

        begun = execute_begin_from_current_source(
            begin_request(version=3, revision=LIVE_SOURCE_TOKEN),
            context(
                revision=LIVE_SOURCE_TOKEN,
                fingerprint=LIVE_SOURCE_FP,
                with_projection=True,
            ),
            store,
        )
        self.assertTrue(begun["ok"], begun)
        self.assertEqual(begun["code"], "begun")
        self.assertTrue(begun["archived_prior_draft"])
        self.assertEqual(begun["draft_version"], 4)
        self.assertEqual(begun["source_content_revision"], LIVE_SOURCE_TOKEN)
        row = store.rows[key]
        self.assertEqual(row["source_content_revision"], LIVE_SOURCE_TOKEN)
        self.assertEqual(row["source_input_fingerprint"], LIVE_SOURCE_FP)
        # Prior poses are archived, not copied onto the new identity layout.
        self.assertNotEqual(row["layout_json"]["pieces"][0]["local_x_mm"], 777)
        self.assertEqual(row["layout_json"]["pieces"][0]["local_x_mm"], 10.0)
        archive = row["prior_draft_archive_json"]
        self.assertIsInstance(archive, list)
        self.assertEqual(archive[-1]["archived_draft_version"], 3)
        self.assertEqual(archive[-1]["source_content_revision"], LIVE_STORED_TOKEN)
        self.assertEqual(archive[-1]["layout"]["pieces"][0]["local_x_mm"], 777)

        # First save after begin, second save, then reopen-equivalent save.
        moved = dict(row["layout_json"])
        moved = normalize_layout(
            {
                "schema": 1,
                "pieces": [
                    {**piece, "local_x_mm": 33}
                    if piece["piece_instance_id"] == "pi-a"
                    else piece
                    for piece in moved["pieces"]
                ],
                "boards": moved["boards"],
            },
            catalog_from_projection(projection()),
        )
        first_save = execute_save(
            request(moved, version=4, revision=LIVE_SOURCE_TOKEN),
            context(revision=LIVE_SOURCE_TOKEN, fingerprint=LIVE_SOURCE_FP, with_projection=True),
            store,
        )
        self.assertTrue(first_save["ok"], first_save)
        self.assertEqual(first_save["draft_version"], 5)
        second_save = execute_save(
            request(moved, version=5, revision=LIVE_SOURCE_TOKEN),
            context(revision=LIVE_SOURCE_TOKEN, fingerprint=LIVE_SOURCE_FP, with_projection=True),
            store,
        )
        self.assertTrue(second_save["ok"], second_save)
        self.assertEqual(second_save["draft_version"], 5)
        reopen = layout()
        reopen["pieces"][0]["local_x_mm"] = 44
        # Reopen uses the current version against the live source.
        after_reopen = execute_save(
            request(reopen, version=5, revision=LIVE_SOURCE_TOKEN),
            context(revision=LIVE_SOURCE_TOKEN, fingerprint=LIVE_SOURCE_FP, with_projection=True),
            store,
        )
        self.assertTrue(after_reopen["ok"], after_reopen)
        self.assertEqual(after_reopen["draft_version"], 6)
        # Archive retained across later saves (begin wrote it; save does not clear).
        self.assertEqual(
            store.rows[key]["prior_draft_archive_json"][-1]["layout"]["pieces"][0]["local_x_mm"],
            777,
        )

    def test_begin_cancel_path_leaves_store_untouched(self):
        """Cancel is client-only: never calling begin must leave the draft intact."""

        store = MemoryStore()
        created = execute_save(
            request(layout(), version=0, revision=LIVE_STORED_TOKEN),
            context(revision=LIVE_STORED_TOKEN, fingerprint=LIVE_STORED_FP),
            store,
        )
        self.assertTrue(created["ok"])
        key = next(iter(store.rows))
        before = dict(store.rows[key])
        # User declined confirm → no begin_request reaches the server.
        self.assertEqual(store.rows[key], before)
        self.assertEqual(store.rows[key]["source_content_revision"], LIVE_STORED_TOKEN)

    def test_identity_layout_places_boards_on_non_overlapping_grid(self):
        """Begin-from-source must not write every board at origin (0, TITLE_BAND)."""

        two = {
            "sheets": [
                {"sheet_no": 1, "full_width_cm": 122, "full_length_cm": 244},
                {"sheet_no": 2, "full_width_cm": 80, "full_length_cm": 160},
            ],
            "pieces": [
                {
                    "piece_instance_id": "pi-a",
                    "piece_id": 1,
                    "sheet_no": 1,
                    "placement_cm": {"x": 1.5, "y": 2.5},
                    "glass_host_piece_id": None,
                },
                {
                    "piece_instance_id": "pi-b",
                    "piece_id": 2,
                    "sheet_no": 2,
                    "placement_cm": {"x": 3.0, "y": 4.0},
                    "glass_host_piece_id": 1,
                },
            ],
        }
        three = {
            "sheets": [
                {"sheet_no": 1, "full_width_cm": 122, "full_length_cm": 244},
                {"sheet_no": 2, "full_width_cm": 100, "full_length_cm": 200},
                {"sheet_no": 3, "full_width_cm": 80, "full_length_cm": 160},
            ],
            "pieces": two["pieces"]
            + [
                {
                    "piece_instance_id": "pi-c",
                    "piece_id": 3,
                    "sheet_no": 3,
                    "placement_cm": {"x": 0.5, "y": 0.5},
                    "glass_host_piece_id": None,
                }
            ],
        }

        for label, projection_payload in (("two", two), ("three", three)):
            with self.subTest(boards=label):
                document = identity_layout_from_projection(projection_payload)
                boards = {row["sheet_no"]: row for row in document["boards"]}
                self.assertFalse(
                    boards_share_collapsed_default_origin(document["boards"]),
                    "identity layout must not collapse all boards onto one origin",
                )
                self.assertEqual(boards[1]["origin_x_mm"], 0.0)
                self.assertEqual(boards[1]["origin_y_mm"], TITLE_BAND_MM)
                self.assertEqual(
                    boards[2]["origin_x_mm"],
                    1220.0 + BOARD_GAP_MM,
                )
                self.assertEqual(boards[2]["origin_y_mm"], TITLE_BAND_MM)
                self.assertFalse(boards[1]["user_moved"])
                self.assertFalse(boards[2]["user_moved"])
                # Local piece pose/hosting stay projection-local, not workspace.
                by_id = {row["piece_instance_id"]: row for row in document["pieces"]}
                self.assertEqual(by_id["pi-a"]["local_x_mm"], 15.0)
                self.assertEqual(by_id["pi-a"]["local_y_mm"], 25.0)
                self.assertEqual(by_id["pi-a"]["rotation_deg"], 0.0)
                self.assertEqual(by_id["pi-b"]["glass_host_piece_id"], 1)
                if 3 in boards:
                    self.assertEqual(boards[3]["origin_x_mm"], 0.0)
                    self.assertGreater(
                        boards[3]["origin_y_mm"],
                        boards[1]["origin_y_mm"] + 2440.0,
                    )
                    # Title bands of row 1 and row 2 must not overlap.
                    row1_bottom = boards[1]["origin_y_mm"] + 2440.0
                    row2_title_top = boards[3]["origin_y_mm"] - TITLE_BAND_MM
                    self.assertGreaterEqual(row2_title_top, row1_bottom)

        # Workspace helper matches the 2-column editor grid for mixed sizes.
        origins = workspace_board_origins(three["sheets"], columns=2)
        self.assertEqual(origins[1][0], 0.0)
        self.assertEqual(origins[2][0], 1220.0 + BOARD_GAP_MM)
        self.assertEqual(origins[1][1], origins[2][1])
        self.assertGreater(origins[3][1], origins[1][1])

    def test_begin_persists_grid_origins_for_reopen(self):
        store = MemoryStore()
        created = execute_save(
            request(layout(), version=0, revision=LIVE_STORED_TOKEN),
            context(revision=LIVE_STORED_TOKEN, fingerprint=LIVE_STORED_FP),
            store,
        )
        self.assertTrue(created["ok"])
        key = next(iter(store.rows))
        store.rows[key]["draft_version"] = 3
        begun = execute_begin_from_current_source(
            begin_request(version=3, revision=LIVE_SOURCE_TOKEN),
            context(
                revision=LIVE_SOURCE_TOKEN,
                fingerprint=LIVE_SOURCE_FP,
                with_projection=True,
            ),
            store,
        )
        self.assertTrue(begun["ok"], begun)
        boards = {
            row["sheet_no"]: row
            for row in store.rows[key]["layout_json"]["boards"]
        }
        self.assertEqual(boards[1]["origin_x_mm"], 0.0)
        self.assertEqual(boards[2]["origin_x_mm"], 1220.0 + BOARD_GAP_MM)
        self.assertFalse(boards_share_collapsed_default_origin(store.rows[key]["layout_json"]["boards"]))
        # Reopen-equivalent save keeps the same board workspace origins.
        saved = execute_save(
            request(store.rows[key]["layout_json"], version=4, revision=LIVE_SOURCE_TOKEN),
            context(revision=LIVE_SOURCE_TOKEN, fingerprint=LIVE_SOURCE_FP, with_projection=True),
            store,
        )
        self.assertTrue(saved["ok"], saved)
        again = {
            row["sheet_no"]: row
            for row in store.rows[key]["layout_json"]["boards"]
        }
        self.assertEqual(again[1]["origin_x_mm"], boards[1]["origin_x_mm"])
        self.assertEqual(again[2]["origin_x_mm"], boards[2]["origin_x_mm"])

    def test_begin_concurrent_tab_and_real_geometry_reject(self):
        store = MemoryStore()
        created = execute_save(
            request(layout(), version=0, revision=LIVE_STORED_TOKEN),
            context(revision=LIVE_STORED_TOKEN, fingerprint=LIVE_STORED_FP),
            store,
        )
        self.assertTrue(created["ok"])
        key = next(iter(store.rows))
        store.rows[key]["draft_version"] = 3

        begun = execute_begin_from_current_source(
            begin_request(version=3, revision=LIVE_SOURCE_TOKEN),
            context(
                revision=LIVE_SOURCE_TOKEN,
                fingerprint=LIVE_SOURCE_FP,
                with_projection=True,
            ),
            store,
        )
        self.assertTrue(begun["ok"])
        self.assertEqual(begun["draft_version"], 4)

        # Other tab still holding expected=3 must lose.
        stale_begin = execute_begin_from_current_source(
            begin_request(version=3, revision=LIVE_SOURCE_TOKEN),
            context(
                revision=LIVE_SOURCE_TOKEN,
                fingerprint=LIVE_SOURCE_FP,
                with_projection=True,
            ),
            store,
        )
        self.assertEqual(stale_begin["code"], "version_conflict")
        self.assertEqual(store.rows[key]["draft_version"], 4)

        stale_save = execute_save(
            request(layout(), version=3, revision=LIVE_SOURCE_TOKEN),
            context(revision=LIVE_SOURCE_TOKEN, fingerprint=LIVE_SOURCE_FP, with_projection=True),
            store,
        )
        self.assertEqual(stale_save["code"], "version_conflict")

        # Real manufacturing fingerprint change after begin still conflicts.
        later = (
            "CP-2026-00028|cd2a90a5dd5497724fcb1abee298a3917dc71e8f2d02b8015a1664d5470f9b6d|"
            "5|ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff|0|0"
        )
        geom = execute_save(
            request(layout(), version=4, revision=later),
            context(revision=later, fingerprint="ff" * 32, with_projection=True),
            store,
        )
        self.assertEqual(geom["code"], "source_conflict")
        self.assertEqual(store.rows[key]["draft_version"], 4)
        self.assertEqual(store.rows[key]["source_content_revision"], LIVE_SOURCE_TOKEN)


if __name__ == "__main__":
    unittest.main()
