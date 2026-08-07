from __future__ import annotations

import unittest
from pathlib import Path

from almdina_erp.almdina_erp.application.security.permission_matrix import validate_capability_dependencies
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
POLICY = ROOT / "almdina_erp" / "application" / "security" / "permission_transfer.py"


def state(*capabilities: str) -> dict[str, bool]:
    return validate_capability_dependencies(
        {capability: True for capability in capabilities}
    )


class TestPermissionTransfer(unittest.TestCase):
    def test_policy_is_framework_independent_and_template_free(self) -> None:
        source = POLICY.read_text(encoding="utf-8")
        self.assertNotIn("import frappe", source)
        self.assertNotIn("from frappe", source)
        self.assertNotIn("PermissionTemplate", source)
        self.assertNotIn("template_state", source)
        self.assertNotIn("PERMISSION_TEMPLATES", source)

    def test_export_round_trip_preserves_manual_capabilities(self) -> None:
        source = state(
            Capability.VIEW_ORDERS,
            Capability.VIEW_CUTTING_PLAN,
            Capability.VIEW_DRAWING_WORKSPACE,
            Capability.UPLOAD_DXF,
        )
        document = build_permission_export(role="Designer Test", state=source)
        self.assertEqual(document["schema"], PERMISSION_TRANSFER_SCHEMA)
        self.assertEqual(document["version"], PERMISSION_TRANSFER_VERSION)
        self.assertEqual(document["role"], "Designer Test")
        self.assertTrue(document["checksum"])
        parsed = parse_permission_export(document)
        self.assertEqual(parsed["source_role"], "Designer Test")
        self.assertEqual(parsed["capabilities"], source)

    def test_export_can_be_previewed_for_another_existing_role(self) -> None:
        document = build_permission_export(
            role="Source Role",
            state=state(
                Capability.VIEW_ORDERS,
                Capability.START_ASSIGNED_STAGE,
                Capability.HANDOFF_ASSIGNED_STAGE,
            ),
        )
        parsed = parse_permission_export(document)
        self.assertEqual(parsed["source_role"], "Source Role")
        self.assertTrue(parsed["capabilities"][Capability.START_ASSIGNED_STAGE])
        self.assertFalse(parsed["capabilities"][Capability.DISPATCH_ORDER])

    def test_matrix_bundle_round_trip_and_preview(self) -> None:
        original = {
            "Entry Role": state(
                Capability.VIEW_ORDERS,
                Capability.CREATE_ORDER,
                Capability.SUBMIT_ORDER,
                Capability.VIEW_CUSTOMERS,
                Capability.VIEW_EDGE_BANDING_TYPES,
            ),
            "Operator Role": state(
                Capability.VIEW_ORDERS,
                Capability.START_ASSIGNED_STAGE,
                Capability.HANDOFF_ASSIGNED_STAGE,
            ),
        }
        bundle = build_permission_bundle(
            original,
            exported_by="admin@example.com",
            exported_at="2026-08-01 22:00:00",
            app_version="1.0.0-dev",
        )
        self.assertEqual(bundle["kind"], "role_matrix")
        self.assertEqual(len(bundle["roles"]), 2)
        self.assertNotIn("users", bundle)
        self.assertNotIn("passwords", bundle)
        self.assertNotIn("audit", bundle)
        parsed = parse_permission_bundle(bundle)
        self.assertEqual(parsed, original)

        current = {
            "Entry Role": state(Capability.VIEW_ORDERS),
            "Operator Role": original["Operator Role"],
        }
        preview = preview_permission_bundle(current, parsed)
        self.assertEqual(preview["summary"]["role_count"], 2)
        self.assertEqual(preview["summary"]["changed_role_count"], 1)
        self.assertGreater(preview["summary"]["change_count"], 0)

    def test_import_rejects_valid_checksum_with_missing_prerequisites(self) -> None:
        incomplete = build_permission_export(
            role="Broken Role",
            state={Capability.UPLOAD_DXF: True},
        )
        with self.assertRaisesRegex(ValueError, "Missing required permissions"):
            parse_permission_export(incomplete)

    def test_bundle_rejects_tampering_duplicates_and_excess_roles(self) -> None:
        bundle = build_permission_bundle(
            {"Source Role": state(Capability.VIEW_ORDERS)},
            exported_by="Administrator",
            exported_at="2026-08-01 22:00:00",
            app_version="1.0.0-dev",
        )
        tampered = dict(bundle)
        tampered["roles"] = [dict(bundle["roles"][0])]
        tampered["roles"][0]["capabilities"] = list(tampered["roles"][0]["capabilities"]) + [Capability.APPROVE_ORDER]
        with self.assertRaisesRegex(ValueError, "checksum"):
            parse_permission_bundle(tampered)

        duplicate = dict(bundle)
        duplicate["roles"] = [bundle["roles"][0], bundle["roles"][0]]
        with self.assertRaisesRegex(ValueError, "duplicate role"):
            parse_permission_bundle(duplicate)

        excessive = {f"Role {index}": {} for index in range(MAX_TRANSFER_ROLES + 1)}
        with self.assertRaisesRegex(ValueError, "more than"):
            build_permission_bundle(
                excessive,
                exported_by="Administrator",
                exported_at="2026-08-01 22:00:00",
                app_version="1.0.0-dev",
            )

    def test_tampering_future_versions_and_unknown_capabilities_fail_closed(self) -> None:
        document = build_permission_export(role="Source Role", state=state(Capability.VIEW_ORDERS))
        tampered = dict(document)
        tampered["capabilities"] = list(document["capabilities"]) + [Capability.APPROVE_ORDER]
        with self.assertRaisesRegex(ValueError, "checksum"):
            parse_permission_export(tampered)

        future = dict(document)
        future["version"] = PERMISSION_TRANSFER_VERSION + 1
        with self.assertRaisesRegex(ValueError, "version"):
            parse_permission_export(future)

        unknown = dict(document)
        unknown["capabilities"] = ["unknown_capability"]
        with self.assertRaises(ValueError):
            parse_permission_export(unknown)


if __name__ == "__main__":
    unittest.main()
