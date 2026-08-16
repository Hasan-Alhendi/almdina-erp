from __future__ import annotations

import ast
import unittest
from pathlib import Path


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


def _whitelisted_endpoints() -> set[str]:
    endpoints: set[str] = set()
    for path in sorted(APP.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        module = _module_name(path)
        for node in tree.body:
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            if any(_is_whitelist(decorator) for decorator in node.decorator_list):
                endpoints.add(f"{module}.{node.name}")
    return endpoints


class TestWhitelistedEndpointAuthorization(unittest.TestCase):
    def test_inventory_all_whitelisted_endpoints(self) -> None:
        # Stage 12.2 bootstraps this manifest from the AST-discovered source of
        # truth. Keeping this empty for the first CI pass intentionally makes the
        # failure print every currently exposed endpoint; the final contract test
        # replaces it with an explicit classified manifest and exact-set check.
        declared: set[str] = set()
        actual = _whitelisted_endpoints()
        self.assertEqual(
            actual,
            declared,
            "Whitelisted endpoint inventory:\n" + "\n".join(sorted(actual)),
        )


if __name__ == "__main__":
    unittest.main()
