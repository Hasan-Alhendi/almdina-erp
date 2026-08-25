from __future__ import annotations

import ast
import unittest
from pathlib import Path

from almdina_erp.tests.security_endpoint_contracts import (
    EndpointAuthorizationContract,
    WHITELISTED_ENDPOINT_CONTRACTS,
)


ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "almdina_erp"


def _module_name(path: Path) -> str:
    relative = path.relative_to(ROOT).with_suffix("")
    return ".".join((ROOT.name, *relative.parts))


def _is_whitelist(decorator: ast.expr) -> bool:
    target = decorator.func if isinstance(decorator, ast.Call) else decorator
    return (
        isinstance(target, ast.Attribute)
        and isinstance(target.value, ast.Name)
        and target.value.id == "frappe"
        and target.attr == "whitelist"
    )


def _allows_guest(node: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    for decorator in node.decorator_list:
        if not isinstance(decorator, ast.Call) or not _is_whitelist(decorator):
            continue
        for keyword in decorator.keywords:
            if keyword.arg != "allow_guest":
                continue
            if isinstance(keyword.value, ast.Constant) and keyword.value.value is True:
                return True
    return False


def _whitelisted_functions() -> dict[str, tuple[Path, ast.FunctionDef | ast.AsyncFunctionDef]]:
    endpoints: dict[str, tuple[Path, ast.FunctionDef | ast.AsyncFunctionDef]] = {}
    for path in sorted(APP.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        module = _module_name(path)
        for node in tree.body:
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            if any(_is_whitelist(decorator) for decorator in node.decorator_list):
                endpoints[f"{module}.{node.name}"] = (path, node)
    return endpoints


def _call_names(node: ast.AST) -> set[str]:
    names: set[str] = set()
    for child in ast.walk(node):
        if not isinstance(child, ast.Call):
            continue
        target = child.func
        if isinstance(target, ast.Name):
            names.add(target.id)
        elif isinstance(target, ast.Attribute):
            names.add(target.attr)
    return names


class TestWhitelistedEndpointAuthorization(unittest.TestCase):
    def test_every_whitelisted_endpoint_has_one_explicit_contract(self) -> None:
        actual = set(_whitelisted_functions())
        declared = set(WHITELISTED_ENDPOINT_CONTRACTS)
        self.assertEqual(
            actual,
            declared,
            "Every @frappe.whitelist() endpoint must be explicitly classified. "
            "Unclassified or stale contracts:\n"
            + "\n".join(sorted(actual.symmetric_difference(declared))),
        )

    def test_factory_endpoints_are_never_guest_exposed(self) -> None:
        guest_endpoints = sorted(
            endpoint
            for endpoint, (_, node) in _whitelisted_functions().items()
            if _allows_guest(node)
        )
        self.assertEqual(
            guest_endpoints,
            [],
            "Factory business endpoints must never use allow_guest=True: "
            + ", ".join(guest_endpoints),
        )

    def test_contract_kinds_are_closed_and_explicit(self) -> None:
        allowed = {
            EndpointAuthorizationContract.CAPABILITY,
            EndpointAuthorizationContract.DELEGATE,
            EndpointAuthorizationContract.FAIL_CLOSED,
            EndpointAuthorizationContract.SELF_CONTEXT,
        }
        self.assertTrue(WHITELISTED_ENDPOINT_CONTRACTS)
        self.assertFalse(set(WHITELISTED_ENDPOINT_CONTRACTS.values()).difference(allowed))
        self.assertEqual(
            {
                endpoint
                for endpoint, contract in WHITELISTED_ENDPOINT_CONTRACTS.items()
                if contract == EndpointAuthorizationContract.SELF_CONTEXT
            },
            {
                "almdina_erp.almdina_erp.services.master_data_service.can_open_master_data",
                "almdina_erp.almdina_erp.services.permission_context_service.get_permission_context",
            },
        )
        self.assertEqual(
            {
                endpoint
                for endpoint, contract in WHITELISTED_ENDPOINT_CONTRACTS.items()
                if contract == EndpointAuthorizationContract.FAIL_CLOSED
            },
            {
                "almdina_erp.almdina_erp.services.approval_queue_service.approve_order_safely",
                "almdina_erp.almdina_erp.services.approval_queue_service.get_approval_queue_context",
                "almdina_erp.almdina_erp.services.approval_queue_service.get_pending_review_orders",
                "almdina_erp.almdina_erp.services.approval_queue_service.reject_order_safely",
                "almdina_erp.almdina_erp.services.legacy_endpoint_service.retired_product_endpoint",
                "almdina_erp.almdina_erp.services.order_review_service.reject_order",
                "almdina_erp.almdina_erp.services.production_service.pause_stage",
                "almdina_erp.almdina_erp.services.production_service.resume_stage",
            },
        )

    def test_high_risk_endpoints_keep_their_authorization_boundaries(self) -> None:
        endpoints = _whitelisted_functions()
        expected_calls = {
            "almdina_erp.almdina_erp.api.preview_door_cutting_order": {
                "_existing_preview_order",
                "_require_live_preview_access",
                "_use_locked_preview",
            },
            "almdina_erp.almdina_erp.api.get_approved_cutting_plan_snapshot": {
                "check_permission",
                "require_any_document_capability",
            },
            "almdina_erp.almdina_erp.services.order_defaults_service.get_order_defaults": {
                "require_any_doctype_capability",
                "doctype_has_capability",
            },
            "almdina_erp.almdina_erp.services.cost_service.refresh_order_costs": {
                "check_permission",
                "require_document_capability",
            },
        }
        for endpoint, required in expected_calls.items():
            with self.subTest(endpoint=endpoint):
                self.assertIn(endpoint, endpoints)
                calls = _call_names(endpoints[endpoint][1])
                self.assertTrue(
                    required.issubset(calls),
                    f"{endpoint} lost authorization calls: {sorted(required.difference(calls))}",
                )

    def test_preview_uses_persisted_state_not_client_status_for_security(self) -> None:
        source = (APP / "api.py").read_text(encoding="utf-8")
        function_source = source.split("def preview_door_cutting_order", 1)[1].split(
            "\n\n@frappe.whitelist()",
            1,
        )[0]
        self.assertIn("stored = _existing_preview_order(name)", function_source)
        self.assertIn("_use_locked_preview(stored.status)", function_source)
        self.assertNotIn('payload.get("status")', function_source)

        helper_source = source.split("def _require_live_preview_access", 1)[1].split(
            "\n\n@frappe.whitelist()",
            1,
        )[0]
        self.assertIn("Capability.CREATE_ORDER", helper_source)
        self.assertIn("require_doctype_capability", helper_source)
        self.assertIn("Capability.EDIT_ORDER", helper_source)
        self.assertIn("require_document_capability", helper_source)

    def test_order_defaults_never_unconditionally_return_cost_configuration(self) -> None:
        source = (
            APP / "services" / "order_defaults_service.py"
        ).read_text(encoding="utf-8")
        self.assertIn("Capability.VIEW_COSTS", source)
        self.assertIn("doctype_has_capability", source)
        self.assertIn('payload["cutting_cost_per_board_usd"]', source)
        self.assertNotIn(
            '"cutting_cost_per_board_usd": flt(settings.default_cutting_cost_per_board_usd)',
            source,
        )


if __name__ == "__main__":
    unittest.main()
