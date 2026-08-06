from __future__ import annotations

import ast
import importlib.util
import json
import sys
import types
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from almdina_erp.almdina_erp.infrastructure.frappe.production_stage_write_guard import (
    INTERNAL_STAGE_WRITE_FLAG,
    authorize_internal_stage_write,
    is_internal_stage_write,
)


ROOT = Path(__file__).resolve().parents[1]
RUNTIME_ROOT = ROOT / "almdina_erp"
CONTROLLER_PATH = (
    RUNTIME_ROOT
    / "doctype"
    / "production_stage"
    / "production_stage.py"
)
SCHEMA_PATH = CONTROLLER_PATH.with_suffix(".json")
REPOSITORY_PATH = (
    RUNTIME_ROOT
    / "infrastructure"
    / "frappe"
    / "production_stage_repository.py"
)


class _FakePermissionError(PermissionError):
    pass


class _FakeDocument:
    def __init__(self) -> None:
        self.flags = SimpleNamespace()


class _ControllerHarness:
    @staticmethod
    def load():
        fake_frappe = types.ModuleType("frappe")
        fake_frappe._ = lambda value: value
        fake_frappe.PermissionError = _FakePermissionError

        def throw(message: str, exc_type: type[BaseException] | None = None) -> None:
            raise (exc_type or ValueError)(message)

        fake_frappe.throw = throw

        fake_document_module = types.ModuleType("frappe.model.document")
        fake_document_module.Document = _FakeDocument
        fake_model_module = types.ModuleType("frappe.model")
        fake_model_module.document = fake_document_module
        fake_utils = types.ModuleType("frappe.utils")
        fake_utils.cint = lambda value: int(value or 0)

        replacements = {
            "frappe": fake_frappe,
            "frappe.model": fake_model_module,
            "frappe.model.document": fake_document_module,
            "frappe.utils": fake_utils,
        }
        module_name = "almdina_test_production_stage_controller"
        spec = importlib.util.spec_from_file_location(module_name, CONTROLLER_PATH)
        module = importlib.util.module_from_spec(spec)
        with patch.dict(sys.modules, replacements):
            assert spec and spec.loader
            spec.loader.exec_module(module)
        return module


def _dotted_name(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        parent = _dotted_name(node.value)
        return f"{parent}.{node.attr}" if parent else node.attr
    return ""


def _constant_string(node: ast.AST | None) -> str | None:
    return node.value if isinstance(node, ast.Constant) and isinstance(node.value, str) else None


class TestProductionStageWriteBoundary(unittest.TestCase):
    def test_write_guard_requires_an_explicit_internal_flag(self) -> None:
        document = SimpleNamespace()
        self.assertFalse(is_internal_stage_write(document))

        returned = authorize_internal_stage_write(document)

        self.assertIs(returned, document)
        self.assertTrue(is_internal_stage_write(document))
        self.assertTrue(getattr(document.flags, INTERNAL_STAGE_WRITE_FLAG))

    def test_controller_rejects_direct_save_and_delete(self) -> None:
        module = _ControllerHarness.load()
        stage = module.ProductionStage()
        stage.sequence = 10
        stage.status = "Pending"
        stage.started_by = None
        stage.start_time = None
        stage.finish_time = None

        with self.assertRaisesRegex(_FakePermissionError, "system-managed"):
            stage.validate()
        with self.assertRaisesRegex(_FakePermissionError, "system-managed"):
            stage.before_trash()

        authorize_internal_stage_write(stage)
        stage.validate()
        stage.before_trash()

    def test_stage_schema_is_read_only_in_desk(self) -> None:
        schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
        fields = {row["fieldname"]: row for row in schema["fields"]}
        for fieldname in (
            "door_cutting_order",
            "sequence",
            "stage_type",
            "department_label",
            "eligible_roles_display",
            "status",
            "piece_label",
            "assigned_to",
            "started_by",
            "start_time",
            "finished_by",
            "finish_time",
            "paused_seconds",
            "actual_working_seconds",
            "completed_qty",
            "pauses",
            "notes",
        ):
            with self.subTest(fieldname=fieldname):
                self.assertEqual(fields[fieldname].get("read_only"), 1)
        self.assertEqual(schema["permissions"], [])

    def test_repository_is_the_only_document_mutation_boundary(self) -> None:
        source = REPOSITORY_PATH.read_text(encoding="utf-8")
        self.assertIn("authorize_internal_stage_write", source)
        self.assertEqual(source.count("stage.save(ignore_permissions=True)"), 1)
        self.assertEqual(source.count("stage.insert(ignore_permissions=True)"), 1)
        self.assertNotIn("frappe.db.set_value(", source)
        self.assertIn("def _lock_stage", source)
        self.assertIn("for update", source)

    def test_runtime_has_no_direct_stage_creation_or_database_mutation(self) -> None:
        violations: list[str] = []
        allowed_new_doc = REPOSITORY_PATH.resolve()
        mutators = {
            "frappe.db.set_value",
            "frappe.db.delete",
            "frappe.delete_doc",
        }
        for path in sorted(RUNTIME_ROOT.rglob("*.py")):
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call):
                    continue
                function_name = _dotted_name(node.func)
                first_argument = _constant_string(node.args[0]) if node.args else None
                if (
                    function_name == "frappe.new_doc"
                    and first_argument == "Production Stage"
                    and path.resolve() != allowed_new_doc
                ):
                    violations.append(
                        f"{path.relative_to(RUNTIME_ROOT)}: direct new_doc"
                    )
                if function_name in mutators and first_argument == "Production Stage":
                    violations.append(
                        f"{path.relative_to(RUNTIME_ROOT)}: {function_name}"
                    )
        self.assertEqual(violations, [])


if __name__ == "__main__":
    unittest.main()
