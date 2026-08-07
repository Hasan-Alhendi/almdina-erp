from __future__ import annotations

import unittest
import uuid
from collections.abc import Mapping
from typing import Any

from almdina_erp.almdina_erp.application.security.role_administration import (
    RoleAdministration,
    RoleAdministrationError,
)
from almdina_erp.almdina_erp.domain.security.role_management import RoleDefinition


class FakeRoleRepository:
    def __init__(self) -> None:
        self.roles: dict[str, dict[str, Any]] = {}
        self.audits: list[dict[str, Any]] = []
        self.locks: list[str] = []

    def role_exists(self, role: str) -> bool:
        return role in self.roles

    def lock_role(self, role: str) -> None:
        self.locks.append(role)

    def list_roles(self, *, search="", enabled=None, limit=100):
        rows = [dict(value) for value in self.roles.values()]
        if search:
            rows = [row for row in rows if search.lower() in row["name"].lower()]
        if enabled is not None:
            rows = [row for row in rows if row["enabled"] is enabled]
        return sorted(rows, key=lambda row: row["name"])[:limit]

    def get_role(self, role: str):
        if role not in self.roles:
            raise ValueError("Role does not exist.")
        return dict(self.roles[role])

    def create_role(self, definition: RoleDefinition):
        if definition.name in self.roles:
            raise ValueError("Role already exists.")
        snapshot = self._snapshot(
            definition.name,
            description=definition.description,
            enabled=definition.enabled,
        )
        self.roles[definition.name] = snapshot
        return dict(snapshot)

    def update_role(self, role: str, *, name: str, description: str):
        current = self.roles.pop(role)
        current["name"] = name
        current["description"] = description
        self.roles[name] = current
        return dict(current)

    def set_role_enabled(self, role: str, enabled: bool):
        self.roles[role]["enabled"] = enabled
        return dict(self.roles[role])

    def delete_role(self, role: str) -> None:
        self.roles.pop(role)

    def record_audit(
        self,
        *,
        role_name: str,
        action: str,
        before: Mapping[str, Any] | None,
        after: Mapping[str, Any] | None,
        summary: str,
        changed_by: str,
    ) -> str:
        name = f"AUDIT-{len(self.audits) + 1}"
        self.audits.append(
            {
                "name": name,
                "role_name": role_name,
                "role_uid": str(
                    (after or {}).get("role_uid")
                    or (before or {}).get("role_uid")
                    or ""
                ),
                "action": action,
                "changed_by": changed_by,
                "summary": summary,
            }
        )
        return name

    def list_audit(self, *, role_name: str, role_uid: str = "", limit: int = 30):
        rows = [
            row
            for row in self.audits
            if (role_uid and row["role_uid"] == role_uid)
            or (not role_uid and row["role_name"] == role_name)
        ]
        return list(reversed(rows[-limit:]))

    @staticmethod
    def _snapshot(
        name: str,
        *,
        description: str = "",
        enabled: bool = True,
        **overrides: Any,
    ) -> dict[str, Any]:
        return {
            "name": name,
            "description": description,
            "role_uid": str(uuid.uuid4()),
            "enabled": enabled,
            "desk_access": True,
            "is_custom": True,
            "is_almdina_role": True,
            "assigned_users": 0,
            "permission_count": 0,
            "production_routing_references": 0,
            "workflow_references": 0,
            "production_stage_references": 0,
            "active_stage_references": 0,
            "reference_total": 0,
            **overrides,
        }


class TestRoleAdministrationApplication(unittest.TestCase):
    def setUp(self) -> None:
        self.repository = FakeRoleRepository()
        self.application = RoleAdministration(self.repository)
        self.actor = "admin@example.com"

    def test_create_starts_empty_and_records_audit(self) -> None:
        result = self.application.create(
            actor=self.actor,
            name="  عامل   ليزر  ",
            description=" تشغيل مرحلة الليزر ",
        )
        role = result["role"]
        self.assertEqual(role["name"], "عامل ليزر")
        self.assertEqual(role["description"], "تشغيل مرحلة الليزر")
        self.assertTrue(role["enabled"])
        self.assertEqual(role["permission_count"], 0)
        self.assertEqual(role["assigned_users"], 0)
        self.assertEqual(self.repository.audits[0]["action"], "Created")
        self.assertIn("no implicit permissions", self.repository.audits[0]["summary"])

    def test_rename_preserves_stable_identity_and_history(self) -> None:
        created = self.application.create(
            actor=self.actor,
            name="عامل أول",
            description="الوصف الأول",
        )["role"]
        updated = self.application.update(
            actor=self.actor,
            role="عامل أول",
            name="عامل ثان",
            description="الوصف الثاني",
        )["role"]
        self.assertEqual(updated["name"], "عامل ثان")
        self.assertEqual(updated["description"], "الوصف الثاني")
        self.assertEqual(updated["role_uid"], created["role_uid"])
        audit = self.application.audit(
            actor=self.actor,
            role="عامل ثان",
        )
        self.assertEqual(len(audit["events"]), 2)
        self.assertEqual(audit["events"][0]["action"], "Updated")

    def test_duplicate_and_protected_names_are_rejected(self) -> None:
        self.application.create(actor=self.actor, name="دور موجود")
        with self.assertRaisesRegex(RoleAdministrationError, "already exists"):
            self.application.create(actor=self.actor, name="دور موجود")
        with self.assertRaisesRegex(RoleAdministrationError, "protected"):
            self.application.create(actor=self.actor, name="System Manager")
        with self.assertRaisesRegex(RoleAdministrationError, "protected"):
            self.application.update(
                actor=self.actor,
                role="دور موجود",
                name="Desk User",
            )

    def test_disabling_role_in_active_use_is_blocked(self) -> None:
        self.repository.roles["عامل CNC"] = self.repository._snapshot(
            "عامل CNC",
            assigned_users=1,
        )
        with self.assertRaisesRegex(RoleAdministrationError, "assigned users"):
            self.application.set_enabled(
                actor=self.actor,
                role="عامل CNC",
                enabled=False,
            )

        self.repository.roles["عامل CNC"]["assigned_users"] = 0
        self.repository.roles["عامل CNC"]["active_stage_references"] = 1
        with self.assertRaisesRegex(RoleAdministrationError, "active production"):
            self.application.set_enabled(
                actor=self.actor,
                role="عامل CNC",
                enabled=False,
            )

    def test_delete_requires_a_completely_unused_role(self) -> None:
        self.repository.roles["دور مستخدم"] = self.repository._snapshot(
            "دور مستخدم",
            permission_count=2,
        )
        with self.assertRaisesRegex(RoleAdministrationError, "Remove role"):
            self.application.delete(actor=self.actor, role="دور مستخدم")
        self.assertIn("دور مستخدم", self.repository.roles)

        self.repository.roles["دور فارغ"] = self.repository._snapshot("دور فارغ")
        deleted = self.application.delete(actor=self.actor, role="دور فارغ")
        self.assertTrue(deleted["deleted"])
        self.assertNotIn("دور فارغ", self.repository.roles)
        self.assertEqual(self.repository.audits[-1]["action"], "Deleted")

    def test_console_returns_usage_summary_and_action_context(self) -> None:
        self.repository.roles["A"] = self.repository._snapshot(
            "A",
            assigned_users=2,
            permission_count=3,
            production_routing_references=1,
        )
        self.repository.roles["B"] = self.repository._snapshot(
            "B",
            enabled=False,
        )
        console = self.application.console(actor=self.actor)
        self.assertEqual(console["summary"]["total"], 2)
        self.assertEqual(console["summary"]["enabled"], 1)
        self.assertEqual(console["summary"]["disabled"], 1)
        self.assertEqual(console["summary"]["assigned_users"], 2)
        self.assertEqual(console["summary"]["permission_rows"], 3)
        self.assertIn("delete", console["roles"][0]["actions"])
        self.assertFalse(console["roles"][0]["actions"]["delete"]["allowed"])


if __name__ == "__main__":
    unittest.main()
