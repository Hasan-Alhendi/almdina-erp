from __future__ import annotations

import ast
import unittest
from pathlib import Path

from almdina_erp.almdina_erp.domain.orders.production_authorization import (
    ProductionActionFacts,
    decide_production_action,
)
from almdina_erp.almdina_erp.domain.security.authorization import Capability
from almdina_erp.almdina_erp.domain.security.workforce import (
    WorkforceAction,
    WorkforceFacts,
    decide_workforce_action,
)


ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "almdina_erp"
HOOKS = ROOT / "hooks.py"
NATIVE_PERMISSIONS = APP / "infrastructure" / "frappe" / "native_document_permissions.py"
DXF_SERVICE = APP / "services" / "shop_floor_dxf_service.py"
WORKFORCE_SERVICE = APP / "services" / "workforce_service.py"


def _literal_assignment(path: Path, name: str):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == name
            for target in node.targets
        ):
            return ast.literal_eval(node.value)
        if (
            isinstance(node, ast.AnnAssign)
            and isinstance(node.target, ast.Name)
            and node.target.id == name
        ):
            return ast.literal_eval(node.value)
    raise AssertionError(f"Missing assignment {name} in {path}")


class TestStage12SecurityGate(unittest.TestCase):
    def test_native_frappe_surfaces_have_query_and_document_guards(self) -> None:
        query_hooks = _literal_assignment(HOOKS, "permission_query_conditions")
        document_hooks = _literal_assignment(HOOKS, "has_permission")
        hardened_prefix = (
            "almdina_erp.almdina_erp.infrastructure.frappe."
            "native_document_permissions."
        )
        for doctype in (
            "Door Cutting Order",
            "Production Stage",
            "Production Incident",
            "Cutting Plan",
            "Replacement Piece",
        ):
            with self.subTest(doctype=doctype):
                self.assertIn(doctype, query_hooks)
                self.assertIn(doctype, document_hooks)
                self.assertTrue(document_hooks[doctype].startswith(hardened_prefix))

    def test_native_mutations_are_fail_closed_outside_canonical_commands(self) -> None:
        mutating = set(
            _literal_assignment(NATIVE_PERMISSIONS, "_NATIVE_MUTATING_PERMISSION_TYPES")
        )
        command_only = set(
            _literal_assignment(NATIVE_PERMISSIONS, "_NATIVE_COMMAND_ONLY_PERMISSION_TYPES")
        )
        self.assertTrue(
            {"create", "write", "delete", "submit", "cancel", "amend"}.issubset(mutating),
            mutating,
        )
        self.assertTrue({"delete", "submit", "cancel", "amend"}.issubset(command_only))

    def test_native_dco_write_rechecks_assigned_document_scope(self) -> None:
        source = NATIVE_PERMISSIONS.read_text(encoding="utf-8")
        self.assertIn('resolved_type == "write"', source)
        self.assertIn("base_permissions._requires_assigned_scope", source)
        self.assertIn("base_permissions.worker_can_view_order", source)
        self.assertIn('getattr(doc, "name", None)', source)

    def test_dxf_upload_is_private_unattached_then_authorized_and_scoped(self) -> None:
        source = DXF_SERVICE.read_text(encoding="utf-8")
        for marker in (
            "if not cint(file_row.is_private)",
            "file_row.attached_to_doctype",
            "file_row.attached_to_name",
            "file_row.attached_to_field",
            '"attached_to_doctype": "Cutting Plan"',
            '"attached_to_name": plan.name',
            '"attached_to_field": "dxf_file"',
            'require_stage_assignment_access(order)',
            'order.check_permission("read")',
            'require_cutting_plan_capability(order, capability)',
        ):
            self.assertIn(marker, source)
        self.assertNotIn("require_stage_operational_access", source)

        upload_source = source.split("def upload_production_dxf", 1)[1]
        staged = upload_source.index("_validate_dxf_file_metadata(file_url)")
        authorized = upload_source.index("_authorize_order(")
        validated = upload_source.index("parse_production_dxf(")
        persisted = upload_source.index("save_uploaded_dxf_plan(")
        attached = upload_source.index("_attach_validated_dxf_file(")
        self.assertLess(staged, authorized)
        self.assertLess(authorized, validated)
        self.assertLess(validated, persisted)
        self.assertLess(persisted, attached)

    def test_workforce_blocks_self_role_change_and_self_disable(self) -> None:
        role_decision = decide_workforce_action(
            {Capability.ASSIGN_USER_ROLES},
            action=WorkforceAction.ASSIGN_ROLES,
            facts=WorkforceFacts(actor="me@example.com", target_user="me@example.com"),
        )
        disable_decision = decide_workforce_action(
            {Capability.DISABLE_USERS},
            action=WorkforceAction.DISABLE,
            facts=WorkforceFacts(actor="me@example.com", target_user="me@example.com"),
        )
        self.assertFalse(role_decision.allowed)
        self.assertEqual(role_decision.code, "self_role_change")
        self.assertFalse(disable_decision.allowed)
        self.assertEqual(disable_decision.code, "self_disable")

    def test_workforce_blocks_role_change_and_disable_with_active_assignments(self) -> None:
        for action, capability in (
            (WorkforceAction.ASSIGN_ROLES, Capability.ASSIGN_USER_ROLES),
            (WorkforceAction.DISABLE, Capability.DISABLE_USERS),
        ):
            with self.subTest(action=action):
                decision = decide_workforce_action(
                    {capability},
                    action=action,
                    facts=WorkforceFacts(
                        actor="admin@example.com",
                        target_user="worker@example.com",
                        active_assignments=1,
                    ),
                )
                self.assertFalse(decision.allowed)
                self.assertEqual(decision.code, "active_assignments")

    def test_workforce_protects_platform_users_and_privileged_role_grants(self) -> None:
        for target in ("Administrator", "Guest"):
            decision = decide_workforce_action(
                {Capability.EDIT_USERS},
                action=WorkforceAction.EDIT,
                facts=WorkforceFacts(actor="admin@example.com", target_user=target),
            )
            self.assertFalse(decision.allowed)
            self.assertEqual(decision.code, "protected_user")
        source = WORKFORCE_SERVICE.read_text(encoding="utf-8")
        self.assertIn("_guard_privileged_roles(roles)", source)
        self.assertIn("Capability.MANAGE_PERMISSIONS in _granted()", source)

    def test_worker_cannot_start_stage_assigned_to_another_worker(self) -> None:
        decision = decide_production_action(
            Capability.START_ASSIGNED_STAGE,
            capabilities={Capability.START_ASSIGNED_STAGE},
            facts=ProductionActionFacts(
                order_status="At CNC",
                current_stage_name="STAGE-CNC",
                stage_name="STAGE-CNC",
                stage_type="CNC",
                stage_status="Pending",
                assigned_to="other@example.com",
                actor="worker@example.com",
                operational_role="CNC Worker",
                actor_roles=("CNC Worker",),
            ),
        )
        self.assertFalse(decision.allowed)
        self.assertEqual(decision.code, "not_assigned")

    def test_assigned_worker_with_capability_is_not_denied_by_operational_role(self) -> None:
        decision = decide_production_action(
            Capability.START_ASSIGNED_STAGE,
            capabilities={Capability.START_ASSIGNED_STAGE},
            facts=ProductionActionFacts(
                order_status="At Edge Banding",
                current_stage_name="STAGE-EDGE",
                stage_name="STAGE-EDGE",
                stage_type="Edge Banding",
                stage_status="Pending",
                assigned_to="cnc@example.com",
                actor="cnc@example.com",
                operational_role="Edge Worker",
                actor_roles=("CNC Worker",),
            ),
        )
        self.assertTrue(decision.allowed, decision)
        self.assertEqual(decision.code, "allowed")

    def test_supervisor_reassignment_does_not_require_worker_role(self) -> None:
        decision = decide_production_action(
            Capability.REASSIGN_WORKER,
            capabilities={Capability.REASSIGN_WORKER},
            facts=ProductionActionFacts(
                order_status="At CNC",
                current_stage_name="STAGE-CNC",
                stage_name="STAGE-CNC",
                stage_type="CNC",
                stage_status="Pending",
                assigned_to="worker@example.com",
                actor="supervisor@example.com",
                operational_role="CNC Worker",
                actor_roles=("Production Supervisor",),
            ),
        )
        self.assertTrue(decision.allowed, decision)


if __name__ == "__main__":
    unittest.main()
