from __future__ import annotations

import unittest
from pathlib import Path

from almdina_erp.almdina_erp.application.security.permission_transfer import (
    MAX_TRANSFER_ROLES,
    PERMISSION_TRANSFER_SCHEMA,
    PERMISSION_TRANSFER_VERSION,
    build_permission_bundle,
    build_permission_export,
    parse_permission_bundle,
    parse_permission_export,
    preview_permission_bundle,
)
from almdina_erp.almdina_erp.domain.security.authorization import Capability


ROOT = Path(__file__).resolve().parents[1]
TRANSFER = (
    ROOT
    / "almdina_erp"
    / "application"
    / "security"
    / "permission_transfer.py"
)


class TestPermissionTransfer(unittest.TestCase):
    def test_policy_is_framework_independent_and_template_free(self) -> None:
        source = TRANSFER.read_text(encoding="utf-8")
        self.assertNotIn("import frappe", source)
        self.assertNotIn("from frappe", source)
        self.assertNotIn("PermissionTemplate", source)
        self.assertNotIn("template_state", source)

    def test_single_role_export_round_trip_preserves_capabilities(self) -> None:
        state = {
            Capability.CREATE_ORDER: True,
            Capability.SUBMIT_ORDER: True,
            Capability.VIEW_COSTS: False,
        }
        document = build_permission_export(role="Entry Test", state=state)
        self.assertEqual(document["schema"], PERMISSION_TRANSFER_SCHEMA)
        self.assertEqual(document["version"], PERMISSION_TRANSFER_VERSION)
        self.assertEqual(document["role"], "Entry Test")
        self.assertTrue(document["checksum"])

        parsed = parse_permission_export(document)
        self.assertEqual(parsed["source_role"], "Entry Test")
        self.assertTrue(parsed["capabilities"][Capability.CREATE_ORDER])
        self.assertTrue(parsed["capabilities"][Capability.SUBMIT_ORDER])
        self.assertFalse(parsed["capabilities"][Capability.VIEW_COSTS])

    def test_export_can_be_previewed_for_another_target_role(self) -> None:
        document = build_permission_export(
            role="Source Role",
            state={Capability.START_ASSIGNED_STAGE: True},
        )
        parsed = parse_permission_export(document)
        self.assertEqual(parsed["source_role"], "Source Role")
        self.assertTrue(
            parsed["capabilities"][Capability.START_ASSIGNED_STAGE]
        )

    def test_matrix_bundle_round_trip_and_preview(self) -> None:
        original = {
            "Entry Role": {
                Capability.CREATE_ORDER: True,
                Capability.SUBMIT_ORDER: True,
            },
            "Operator Role": {
                Capability.START_ASSIGNED_STAGE: True,
                Capability.HANDOFF_ASSIGNED_STAGE: True,
            },
        }
        bundle = build_permission_bundle(
            original,
            exported_by="admin@example.com",
            exported_at="2026-08-07 10:00:00",
            app_version="1.0.0-dev",
        )
        self.assertEqual(bundle["kind"], "role_matrix")
        self.assertEqual(len(bundle["roles"]), 2)
        self.assertNotIn("users", bundle)
        self.assertNotIn("passwords", bundle)
        self.assertNotIn("audit", bundle)

        parsed = parse_permission_bundle(bundle)
        self.assertTrue(parsed["Entry Role"][Capability.CREATE_ORDER])
        self.assertTrue(
            parsed["Operator Role"][Capability.START_ASSIGNED_STAGE]
        )

        current = {
            "Entry Role": {Capability.CREATE_ORDER: False},
            "Operator Role": {
                Capability.START_ASSIGNED_STAGE: True,
                Capability.HANDOFF_ASSIGNED_STAGE: True,
            },
        }
        preview = preview_permission_bundle(current, parsed)
        self.assertEqual(preview["summary"]["role_count"], 2)
        self.assertGreaterEqual(preview["summary"]["changed_role_count"], 1)
        self.assertGreater(preview["summary"]["change_count"], 0)

    def test_bundle_rejects_tampering_duplicates_and_excess_roles(self) -> None:
        bundle = build_permission_bundle(
            {"Source Role": {Capability.CREATE_ORDER: True}},
            exported_by="Administrator",
            exported_at="2026-08-07 10:00:00",
            app_version="1.0.0-dev",
        )
        tampered = dict(bundle)
        tampered["roles"] = [dict(bundle["roles"][0])]
        tampered["roles"][0]["capabilities"] = list(
            tampered["roles"][0]["capabilities"]
        ) + [Capability.APPROVE_ORDER]
        with self.assertRaisesRegex(ValueError, "checksum"):
            parse_permission_bundle(tampered)

        duplicate = dict(bundle)
        duplicate["roles"] = [bundle["roles"][0], bundle["roles"][0]]
        with self.assertRaisesRegex(ValueError, "duplicate role"):
            parse_permission_bundle(duplicate)

        excessive = {
            f"Role {index}": {}
            for index in range(MAX_TRANSFER_ROLES + 1)
        }
        with self.assertRaisesRegex(ValueError, "more than"):
            build_permission_bundle(
                excessive,
                exported_by="Administrator",
                exported_at="2026-08-07 10:00:00",
                app_version="1.0.0-dev",
            )

    def test_tampering_and_future_versions_fail_closed(self) -> None:
        document = build_permission_export(
            role="Source Role",
            state={Capability.CREATE_ORDER: True},
        )
        tampered = dict(document)
        tampered["capabilities"] = list(document["capabilities"]) + [
            Capability.APPROVE_ORDER
        ]
        with self.assertRaisesRegex(ValueError, "checksum"):
            parse_permission_export(tampered)

        future = dict(document)
        future["version"] = PERMISSION_TRANSFER_VERSION + 1
        with self.assertRaisesRegex(ValueError, "version"):
            parse_permission_export(future)


if __name__ == "__main__":
    unittest.main()
