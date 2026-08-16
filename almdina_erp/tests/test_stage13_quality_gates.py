from __future__ import annotations

import ast
import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parent
APP = ROOT / "almdina_erp"
DOMAIN = APP / "domain"
APPLICATION = APP / "application"
WORKFLOW = REPO_ROOT / ".github" / "workflows" / "stage13-quality-gates.yml"

_OUTER_LAYERS = frozenset(
    {
        "application",
        "services",
        "infrastructure",
        "presentation",
        "doctype",
        "page",
        "report",
    }
)
_APPLICATION_FORBIDDEN_LAYERS = frozenset(
    {
        "services",
        "infrastructure",
        "presentation",
        "doctype",
        "page",
        "report",
    }
)
_FIXED_BUSINESS_ROLES = frozenset(
    {
        "Production Manager",
        "Accounts Manager",
        "Accounts Management",
        "Accounts User",
        "Order Entry",
        "Sales Manager",
        "Cutting Operator",
        "Edge Operator",
    }
)
_ROLE_GATE_CALLS = frozenset(
    {
        "require_any_role",
        "require_roles",
        "has_role",
    }
)
_COMPATIBILITY_ROLE_GATE_EXCEPTIONS = frozenset(
    {
        APP / "services" / "legacy_endpoint_service.py",
    }
)


def _python_files(root: Path) -> list[Path]:
    return sorted(path for path in root.rglob("*.py") if "__pycache__" not in path.parts)


def _imports(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    targets: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            targets.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            targets.append(node.module or "")
    return targets


def _imports_framework(target: str) -> bool:
    return target == "frappe" or target.startswith("frappe.")


def _imports_layer(target: str, forbidden: frozenset[str]) -> bool:
    components = tuple(part for part in target.split(".") if part)
    return any(component in forbidden for component in components)


def _call_name(node: ast.Call) -> str:
    if isinstance(node.func, ast.Name):
        return node.func.id
    if isinstance(node.func, ast.Attribute):
        parts = [node.func.attr]
        value = node.func.value
        while isinstance(value, ast.Attribute):
            parts.append(value.attr)
            value = value.value
        if isinstance(value, ast.Name):
            parts.append(value.id)
        return ".".join(reversed(parts))
    return ""


def _string_literals(tree: ast.AST) -> set[str]:
    return {
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    }


class TestStage13QualityGates(unittest.TestCase):
    def test_domain_is_framework_free_and_depends_only_inward(self) -> None:
        offenders: list[str] = []
        for path in _python_files(DOMAIN):
            for target in _imports(path):
                if _imports_framework(target):
                    offenders.append(f"{path.relative_to(ROOT)} imports framework {target}")
                if _imports_layer(target, _OUTER_LAYERS):
                    offenders.append(f"{path.relative_to(ROOT)} imports outer layer {target}")
        self.assertEqual(offenders, [], "\n".join(offenders))

    def test_application_is_framework_free_and_does_not_depend_on_adapters(self) -> None:
        offenders: list[str] = []
        for path in _python_files(APPLICATION):
            for target in _imports(path):
                if _imports_framework(target):
                    offenders.append(f"{path.relative_to(ROOT)} imports framework {target}")
                if _imports_layer(target, _APPLICATION_FORBIDDEN_LAYERS):
                    offenders.append(f"{path.relative_to(ROOT)} imports adapter layer {target}")
        self.assertEqual(offenders, [], "\n".join(offenders))

    def test_active_authorization_does_not_reintroduce_fixed_role_gates(self) -> None:
        offenders: list[str] = []
        for path in _python_files(APP):
            if path in _COMPATIBILITY_ROLE_GATE_EXCEPTIONS:
                continue
            if "patches" in path.parts:
                continue
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            calls = {_call_name(node) for node in ast.walk(tree) if isinstance(node, ast.Call)}
            literals = _string_literals(tree)

            forbidden_calls = sorted(
                call
                for call in calls
                if call.rsplit(".", 1)[-1] in _ROLE_GATE_CALLS
            )
            if forbidden_calls:
                offenders.append(
                    f"{path.relative_to(ROOT)} uses retired role-gate call(s): "
                    + ", ".join(forbidden_calls)
                )

            if any(call.endswith("frappe.get_roles") or call == "frappe.get_roles" for call in calls):
                fixed = sorted(_FIXED_BUSINESS_ROLES & literals)
                if fixed:
                    offenders.append(
                        f"{path.relative_to(ROOT)} combines frappe.get_roles with fixed business role(s): "
                        + ", ".join(fixed)
                    )
        self.assertEqual(offenders, [], "\n".join(offenders))

    def test_architecture_core_never_uses_direct_sql_or_frappe_documents(self) -> None:
        offenders: list[str] = []
        patterns = (
            re.compile(r"\bfrappe\.db\.sql\b"),
            re.compile(r"\bfrappe\.get_doc\b"),
            re.compile(r"\bfrappe\.new_doc\b"),
        )
        for root in (DOMAIN, APPLICATION):
            for path in _python_files(root):
                source = path.read_text(encoding="utf-8")
                for pattern in patterns:
                    if pattern.search(source):
                        offenders.append(
                            f"{path.relative_to(ROOT)} contains {pattern.pattern}"
                        )
        self.assertEqual(offenders, [], "\n".join(offenders))

    def test_stage13_workflow_is_non_bypassable_by_default(self) -> None:
        source = WORKFLOW.read_text(encoding="utf-8")
        for branch in ("main", "Develop", "develop"):
            self.assertIn(branch, source)
        self.assertIn("pull_request:", source)
        self.assertIn("push:", source)
        self.assertIn("contents: read", source)
        self.assertNotIn("continue-on-error: true", source)
        self.assertNotIn("|| true", source)
        for contract in (
            "test_stage13_quality_gates",
            "test_backend_legacy_stage11_closure",
            "test_backend_legacy_audit_contract",
            "test_final_security_architecture",
            "test_stage12_security_gate",
            "test_shop_floor_command_architecture",
            "test_shop_floor_query_architecture",
            "test_cutting_plan_architecture",
            "test_order_costing_architecture",
            "test_unified_order_controller_architecture",
        ):
            self.assertIn(contract, source)


if __name__ == "__main__":
    unittest.main()
