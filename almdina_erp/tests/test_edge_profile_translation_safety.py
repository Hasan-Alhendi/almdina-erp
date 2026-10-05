from __future__ import annotations

import ast
import importlib.util
import sys
import types
import unittest
from pathlib import Path
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[1]
REPOSITORY_PATH = (
    ROOT
    / "almdina_erp"
    / "infrastructure"
    / "frappe"
    / "orders"
    / "edge_profile_repository.py"
)


class FakeValidationError(Exception):
    pass


def load_repository_module():
    frappe_module = types.ModuleType("frappe")
    frappe_utils = types.ModuleType("frappe.utils")

    frappe_module._ = lambda message: message

    def throw(message: str) -> None:
        raise FakeValidationError(message)

    frappe_module.throw = throw
    frappe_utils.cint = lambda value: int(value or 0)
    frappe_utils.flt = lambda value: float(value or 0)

    module_name = "_almdina_edge_profile_repository_test"
    previous_modules = {
        name: sys.modules.get(name)
        for name in ("frappe", "frappe.utils", module_name)
    }
    sys.modules["frappe"] = frappe_module
    sys.modules["frappe.utils"] = frappe_utils

    spec = importlib.util.spec_from_file_location(module_name, REPOSITORY_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("Unable to load edge profile repository")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module

    try:
        spec.loader.exec_module(module)
        return module
    finally:
        for name, previous in previous_modules.items():
            if previous is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = previous


class TestEdgeProfileTranslationSafety(unittest.TestCase):
    def test_translation_helper_is_never_shadowed_by_local_assignments(self) -> None:
        tree = ast.parse(REPOSITORY_PATH.read_text(encoding="utf-8"))
        local_underscore_assignments = [
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.Name)
            and node.id == "_"
            and isinstance(node.ctx, ast.Store)
        ]

        self.assertEqual(local_underscore_assignments, [])

    def test_missing_default_edge_raises_validation_message_not_type_error(self) -> None:
        module = load_repository_module()
        repository = module.FrappeEdgeProfileRepository(
            SimpleNamespace(default_edge_type="")
        )
        row = SimpleNamespace(
            edge_long_right=1,
            edge_long_right_type_override="",
        )

        with self.assertRaisesRegex(
            FakeValidationError,
            r"Row 3: Select a default Edge Type before choosing the Long Right edge\.",
        ):
            repository.effective_type(row, "long_right", 3)

    def test_selected_side_uses_override_without_default(self) -> None:
        module = load_repository_module()
        repository = module.FrappeEdgeProfileRepository(
            SimpleNamespace(default_edge_type="")
        )
        row = SimpleNamespace(
            edge_long_right=1,
            edge_long_right_type_override="قشاط 2 سم لميع",
        )

        self.assertEqual(
            repository.effective_type(row, "long_right", 1),
            "قشاط 2 سم لميع",
        )

    def test_required_names_includes_default_edge_type_even_with_no_sides_selected(
        self,
    ) -> None:
        """A corner piece with only edge_break on (no regular side selected)
        still needs the order's default edge type loaded, because the
        costing adapter falls back to it when pricing the break strap.
        Without this, rate_map() would be missing the default type and the
        break strap would price at a silent $0.
        """

        module = load_repository_module()
        repository = module.FrappeEdgeProfileRepository(
            SimpleNamespace(
                default_edge_type="قشاط 2 سم عادي",
                pieces=[
                    SimpleNamespace(
                        edge_long_right=0,
                        edge_long_left=0,
                        edge_width_top=0,
                        edge_width_bottom=0,
                        edge_long_right_type_override="",
                        edge_long_left_type_override="",
                        edge_width_top_type_override="",
                        edge_width_bottom_type_override="",
                    )
                ],
            )
        )

        self.assertIn("قشاط 2 سم عادي", repository._required_names())

    def test_required_names_omits_empty_default_edge_type(self) -> None:
        module = load_repository_module()
        repository = module.FrappeEdgeProfileRepository(
            SimpleNamespace(default_edge_type="", pieces=[])
        )

        self.assertEqual(repository._required_names(), set())


if __name__ == "__main__":
    unittest.main()
