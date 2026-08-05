from __future__ import annotations

import unittest
from pathlib import Path

from almdina_erp.almdina_erp.application.security.permission_templates import (
    MAX_TRANSFER_ROLES,
    PERMISSION_TEMPLATES,
    PERMISSION_TRANSFER_SCHEMA,
    PERMISSION_TRANSFER_VERSION,
    build_permission_bundle,
    build_permission_export,
    parse_permission_bundle,
    parse_permission_export,
    permission_template_catalog,
    preview_permission_bundle,
    template_state,
)
from almdina_erp.almdina_erp.domain.security.authorization import (
    ALL_CAPABILITIES,
    Capability,
)


ROOT = Path(__file__).resolve().parents[1]
POLICY = (
    ROOT
    / "almdina_erp"
    / "application"
    / "security"
    / "permission_templates.py"
)


class TestPermissionTemplates(unittest.TestCase):
    def test_policy_is_framework_independent(self) -> None:
        source = POLICY.read_text(encoding="utf-8")
        self.assertNotIn("import frappe", source)
        self.assertNotIn("from frappe", source)
        self.assertNotIn("Custom DocPerm", source)

    def test_catalog_is_complete_unique_and_json_safe(self) -> None:
        rows = permission_template_catalog()
        self.assertEqual(len(rows), len(PERMISSION_TEMPLATES))
        self.assertEqual(len({row["key"] for row in rows}), len(rows))
        for row in rows:
            self.assertIn(row["risk"], {"normal", "sensitive", "critical"})
            self.assertEqual(set(row["capabilities"]), set(ALL_CAPABILITIES))
            self.assertTrue(
                all(
                    isinstance(value, bool)
                    for value in row["capabilities"].values()
                )
            )
            self.assertIn("navigation", row["impact"])

    def test_templates_are_optional_least_privilege_profiles(self) -> None:
        order_entry = template_state("order_entry")
        self.assertTrue(order_entry[Capability.CREATE_ORDER])
        self.assertTrue(order_entry[Capability.SUBMIT_ORDER])
        self.assertFalse(order_entry[Capability.APPROVE_ORDER])
        self.assertFalse(order_entry[Capability.VIEW_COSTS])
        self.assertFalse(order_entry[Capability.MANAGE_PERMISSIONS])

        operator = template_state("production_operator")
        self.assertTrue(operator[Capability.START_ASSIGNED_STAGE])
        self.assertTrue(operator[Capability.HANDOFF_ASSIGNED_STAGE])
        self.assertFalse(operator[Capability.DISPATCH_ORDER])
        self.assertFalse(operator[Capability.REASSIGN_WORKER])
        self.assertFalse(operator[Capability.VIEW_FINANCIAL_REPORTS])

        supervisor = template_state("production_supervisor")
        self.assertTrue(supervisor[Capability.DISPATCH_ORDER])
        self.assertTrue(supervisor[Capability.REASSIGN_WORKER])
        self.assertFalse(supervisor[Capability.APPROVE_ORDER])
        self.assertFalse(supervisor[Capability.VIEW_FINANCIAL_REPORTS])

        control_center = template_state("control_center")
        self.assertTrue(control_center[Capability.APPROVE_ORDER])
        self.assertTrue(control_center[Capability.ARCHIVE_APPROVED_PLAN])
        self.assertFalse(control_center[Capability.VIEW_COSTS])
        self.assertFalse(control_center[Capability.VIEW_FINANCIAL_REPORTS])

        administrator = template_state("factory_administration")
        self.assertTrue(administrator[Capability.MANAGE_PERMISSIONS])
        self.assertTrue(administrator[Capability.CREATE_USERS])
        self.assertTrue(
            administrator[Capability.DELETE_PRODUCTION_ROUTINGS]
        )
        self.assertFalse(administrator[Capability.APPROVE_ORDER])
        self.assertFalse(administrator[Capability.APPROVE_SPECIAL_PRICE])
        self.assertFalse(administrator[Capability.VIEW_OPERATIONAL_REPORTS])
        self.assertFalse(administrator[Capability.VIEW_FINANCIAL_REPORTS])

    def test_template_dependencies_are_normalized(self) -> None:
        pricing = template_state("pricing_and_documents")
        self.assertTrue(pricing[Capability.VIEW_FINANCIAL_REPORTS])
        self.assertTrue(pricing[Capability.VIEW_OPERATIONAL_REPORTS])
        self.assertTrue(pricing[Capability.VIEW_COSTS])
        self.assertTrue(pricing[Capability.VIEW_ORDERS])

    def test_export_round_trip_preserves_capabilities(self) -> None:
        source = template_state("planner_designer")
        document = build_permission_export(role="Designer Test", state=source)
        self.assertEqual(document["schema"], PERMISSION_TRANSFER_SCHEMA)
        self.assertEqual(document["version"], PERMISSION_TRANSFER_VERSION)
        self.assertEqual(document["role"], "Designer Test")
        self.assertTrue(document["checksum"])

        parsed = parse_permission_export(document)
        self.assertEqual(parsed["source_role"], "Designer Test")
        self.assertEqual(parsed["capabilities"], source)

    def test_export_can_be_imported_for_another_target_role(self) -> None:
        document = build_permission_export(
            role="Source Role",
            state=template_state("production_operator"),
        )
        parsed = parse_permission_export(document)
        self.assertEqual(parsed["source_role"], "Source Role")
        self.assertTrue(
            parsed["capabilities"][Capability.START_ASSIGNED_STAGE]
        )

    def test_matrix_bundle_round_trip_and_preview(self) -> None:
        original = {
            "Entry Role": template_state("order_entry"),
            "Operator Role": template_state("production_operator"),
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
            "Entry Role": template_state("production_operator"),
            "Operator Role": template_state("production_operator"),
        }
        preview = preview_permission_bundle(current, parsed)
        self.assertEqual(preview["summary"]["role_count"], 2)
        self.assertEqual(preview["summary"]["changed_role_count"], 1)
        self.assertGreater(preview["summary"]["change_count"], 0)

    def test_bundle_rejects_tampering_duplicates_and_excess_roles(self) -> None:
        bundle = build_permission_bundle(
            {"Source Role": template_state("order_entry")},
            exported_by="Administrator",
            exported_at="2026-08-01 22:00:00",
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
                exported_at="2026-08-01 22:00:00",
                app_version="1.0.0-dev",
            )

    def test_tampering_future_versions_and_unknown_templates_fail_closed(self) -> None:
        document = build_permission_export(
            role="Source Role",
            state=template_state("order_entry"),
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

        with self.assertRaisesRegex(ValueError, "Unknown permission template"):
            template_state("missing-template")


if __name__ == "__main__":
    unittest.main()
