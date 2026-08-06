from __future__ import annotations

import ast
import importlib.util
import json
import re
import sys
import types
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from almdina_erp.almdina_erp.infrastructure.frappe.production_stage_write_guard import (
    INTERNAL_STAGE_WRITE_FLAG,
    authorize_internal_stage_write,
    internal_stage_write,
    is_internal_stage_write,
    revoke_internal_stage_write,
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
WRITE_GUARD_PATH = (
    RUNTIME_ROOT
    / "infrastructure"
    / "frappe"
    / "production_stage_write_guard.py"
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


def _literal_text(node: ast.AST | None) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        left = _literal_text(node.left)
        right = _literal_text(node.right)
        if left is not None and right is not None:
            return left + right
    return None


def _mapping_doctype(node: ast.AST | None) -> str | None:
    if isinstance(node, ast.Dict):
        for key, value in zip(node.keys, node.values, strict=True):
            if _literal_text(key) == "doctype":
                return _literal_text(value)
    if isinstance(node, ast.Call) and _dotted_name(node.func) in {"dict", "builtins.dict"}:
        for keyword in node.keywords:
            if keyword.arg == "doctype":
                return _literal_text(keyword.value)
    return None


def _factory_doctype(node: ast.AST | None) -> str | None:
    if not isinstance(node, ast.Call):
        return None
    function_name = _dotted_name(node.func)
    if function_name not in {"frappe.new_doc", "frappe.get_doc"}:
        return None
    if node.args:
        direct = _literal_text(node.args[0])
        if direct:
            return direct
        mapped = _mapping_doctype(node.args[0])
        if mapped:
            return mapped
    for keyword in node.keywords:
        if keyword.arg == "doctype":
            return _literal_text(keyword.value)
    return None


def _is_stage_document_factory(node: ast.AST | None) -> bool:
    if not isinstance(node, ast.Call):
        return False
    function_name = _dotted_name(node.func)
    return bool(
        _factory_doctype(node) == "Production Stage"
        or function_name == "get_stage"
        or function_name.endswith(".get_stage")
    )


def _assigned_names(target: ast.AST) -> set[str]:
    if isinstance(target, ast.Name):
        return {target.id}
    if isinstance(target, (ast.Tuple, ast.List)):
        names: set[str] = set()
        for element in target.elts:
            names.update(_assigned_names(element))
        return names
    return set()


def _raw_sql_mutates_production_stage(node: ast.Call) -> bool:
    if _dotted_name(node.func) != "frappe.db.sql" or not node.args:
        return False
    sql = _literal_text(node.args[0])
    if sql is None:
        return False
    normalized = " ".join(sql.replace("`", "").lower().split())
    if "tabproduction stage" not in normalized:
        return False
    return bool(
        re.search(
            r"\b(update|insert\s+into|delete\s+from|replace\s+into|truncate|alter\s+table|drop\s+table)\b",
            normalized,
        )
    )


class TestProductionStageWriteBoundary(unittest.TestCase):
    def test_write_guard_is_explicit_and_transient(self) -> None:
        document = SimpleNamespace()
        self.assertFalse(is_internal_stage_write(document))

        returned = authorize_internal_stage_write(document)

        self.assertIs(returned, document)
        self.assertTrue(is_internal_stage_write(document))
        self.assertTrue(getattr(document.flags, INTERNAL_STAGE_WRITE_FLAG))

        self.assertIs(revoke_internal_stage_write(document), document)
        self.assertFalse(is_internal_stage_write(document))

        with internal_stage_write(document) as authorized:
            self.assertIs(authorized, document)
            self.assertTrue(is_internal_stage_write(document))
        self.assertFalse(is_internal_stage_write(document))

    def test_write_context_revokes_authority_after_an_exception(self) -> None:
        document = SimpleNamespace()

        with self.assertRaisesRegex(RuntimeError, "persistence failed"):
            with internal_stage_write(document):
                self.assertTrue(is_internal_stage_write(document))
                raise RuntimeError("persistence failed")

        self.assertFalse(is_internal_stage_write(document))

    def test_nested_write_context_restores_outer_authority(self) -> None:
        document = SimpleNamespace()

        with internal_stage_write(document):
            self.assertTrue(is_internal_stage_write(document))
            with internal_stage_write(document):
                self.assertTrue(is_internal_stage_write(document))
            self.assertTrue(is_internal_stage_write(document))

        self.assertFalse(is_internal_stage_write(document))

    def test_nested_exception_preserves_outer_authority(self) -> None:
        document = SimpleNamespace()

        with internal_stage_write(document):
            with self.assertRaisesRegex(RuntimeError, "inner failed"):
                with internal_stage_write(document):
                    raise RuntimeError("inner failed")
            self.assertTrue(is_internal_stage_write(document))

        self.assertFalse(is_internal_stage_write(document))

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

        with internal_stage_write(stage):
            stage.validate()
            stage.before_trash()

        with self.assertRaisesRegex(_FakePermissionError, "system-managed"):
            stage.validate()

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

    def test_repository_uses_a_transient_document_mutation_boundary(self) -> None:
        source = REPOSITORY_PATH.read_text(encoding="utf-8")
        self.assertIn("internal_stage_write", source)
        self.assertEqual(source.count("with internal_stage_write(stage):"), 2)
        self.assertEqual(source.count("stage.save(ignore_permissions=True)"), 1)
        self.assertEqual(source.count("stage.insert(ignore_permissions=True)"), 1)
        self.assertNotIn("authorize_internal_stage_write", source)
        self.assertNotIn("frappe.db.set_value(", source)
        self.assertIn("def _lock_stage", source)
        self.assertIn("for update", source)

    def test_runtime_has_no_stage_write_bypass(self) -> None:
        violations: list[str] = []
        allowed_repository = REPOSITORY_PATH.resolve()
        allowed_privileged_paths = {
            allowed_repository,
            WRITE_GUARD_PATH.resolve(),
        }
        database_mutators = {
            "frappe.db.set_value",
            "frappe.db.delete",
            "frappe.db.bulk_update",
            "frappe.delete_doc",
            "frappe.rename_doc",
        }
        privileged_calls = {
            "authorize_internal_stage_write",
            "internal_stage_write",
        }
        document_mutators = {
            "cancel",
            "db_set",
            "delete",
            "insert",
            "save",
            "submit",
        }

        for path in sorted(RUNTIME_ROOT.rglob("*.py")):
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            resolved_path = path.resolve()
            stage_variables: set[str] = set()

            for node in ast.walk(tree):
                if isinstance(node, ast.Assign) and _is_stage_document_factory(node.value):
                    for target in node.targets:
                        stage_variables.update(_assigned_names(target))
                elif isinstance(node, ast.AnnAssign) and _is_stage_document_factory(node.value):
                    stage_variables.update(_assigned_names(node.target))

            for node in ast.walk(tree):
                if not isinstance(node, ast.Call):
                    continue
                function_name = _dotted_name(node.func)
                first_argument = _literal_text(node.args[0]) if node.args else None

                if (
                    function_name == "frappe.new_doc"
                    and _factory_doctype(node) == "Production Stage"
                    and resolved_path != allowed_repository
                ):
                    violations.append(
                        f"{path.relative_to(RUNTIME_ROOT)}: direct new_doc"
                    )

                if (
                    function_name == "frappe.get_doc"
                    and node.args
                    and _mapping_doctype(node.args[0]) == "Production Stage"
                    and resolved_path != allowed_repository
                ):
                    violations.append(
                        f"{path.relative_to(RUNTIME_ROOT)}: get_doc mapping factory"
                    )

                if function_name in database_mutators and first_argument == "Production Stage":
                    violations.append(
                        f"{path.relative_to(RUNTIME_ROOT)}: {function_name}"
                    )

                if _raw_sql_mutates_production_stage(node):
                    violations.append(
                        f"{path.relative_to(RUNTIME_ROOT)}: raw SQL mutation"
                    )

                if (
                    function_name.rsplit(".", 1)[-1] in privileged_calls
                    and resolved_path not in allowed_privileged_paths
                ):
                    violations.append(
                        f"{path.relative_to(RUNTIME_ROOT)}: privileged write flag"
                    )

                if (
                    isinstance(node.func, ast.Attribute)
                    and isinstance(node.func.value, ast.Name)
                    and node.func.value.id in stage_variables
                    and node.func.attr in document_mutators
                    and resolved_path != allowed_repository
                ):
                    violations.append(
                        f"{path.relative_to(RUNTIME_ROOT)}: stage.{node.func.attr}"
                    )

        self.assertEqual(violations, [])


if __name__ == "__main__":
    unittest.main()
