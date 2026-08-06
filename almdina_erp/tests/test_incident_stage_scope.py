from __future__ import annotations

import importlib.util
import sys
import types
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SERVICE_PATH = (
    ROOT
    / "almdina_erp"
    / "services"
    / "replacement_creation_service.py"
)


class _FakeValidationError(ValueError):
    pass


class _FakeDatabase:
    def __init__(self) -> None:
        self.result = None
        self.calls: list[tuple[tuple[object, ...], dict[str, object]]] = []

    def get_value(self, *args, **kwargs):
        self.calls.append((args, kwargs))
        return self.result


class _ServiceHarness:
    @staticmethod
    def load():
        database = _FakeDatabase()
        fake_frappe = types.ModuleType("frappe")
        fake_frappe._ = lambda value: value
        fake_frappe.db = database
        fake_frappe.session = SimpleNamespace(user="incident@example.com")
        fake_frappe.whitelist = lambda function=None, **_kwargs: (
            function if function is not None else (lambda wrapped: wrapped)
        )

        def throw(message: str, *_args, **_kwargs) -> None:
            raise _FakeValidationError(message)

        fake_frappe.throw = throw

        fake_utils = types.ModuleType("frappe.utils")
        fake_utils.cint = lambda value: int(value or 0)
        fake_utils.flt = lambda value: float(value or 0)

        fake_authorization = types.ModuleType(
            "almdina_erp.almdina_erp.domain.security.authorization"
        )
        fake_authorization.Capability = SimpleNamespace(
            RECORD_INCIDENT="record_incident",
            CREATE_REPLACEMENT="create_replacement",
        )

        fake_gateway = types.ModuleType(
            "almdina_erp.almdina_erp.infrastructure.frappe.authorization_gateway"
        )
        fake_gateway.require_doctype_capability = lambda *_args, **_kwargs: None
        fake_gateway.require_document_capability = lambda *_args, **_kwargs: None

        replacements = {
            "frappe": fake_frappe,
            "frappe.utils": fake_utils,
            "almdina_erp.almdina_erp.domain.security.authorization": fake_authorization,
            "almdina_erp.almdina_erp.infrastructure.frappe.authorization_gateway": fake_gateway,
        }
        module_name = "almdina_test_incident_stage_scope"
        spec = importlib.util.spec_from_file_location(module_name, SERVICE_PATH)
        module = importlib.util.module_from_spec(spec)
        with patch.dict(sys.modules, replacements):
            assert spec and spec.loader
            spec.loader.exec_module(module)
        return module, database


class TestIncidentStageScope(unittest.TestCase):
    def test_blank_stage_is_allowed_without_a_database_lookup(self) -> None:
        module, database = _ServiceHarness.load()

        self.assertIsNone(module._validate_incident_stage("DCO-1", "  "))
        self.assertEqual(database.calls, [])

    def test_missing_stage_is_rejected(self) -> None:
        module, database = _ServiceHarness.load()
        database.result = None

        with self.assertRaisesRegex(_FakeValidationError, "does not exist"):
            module._validate_incident_stage("DCO-1", "STAGE-MISSING")

    def test_stage_from_another_order_is_rejected(self) -> None:
        module, database = _ServiceHarness.load()
        database.result = SimpleNamespace(
            name="STAGE-2",
            door_cutting_order="DCO-2",
        )

        with self.assertRaisesRegex(_FakeValidationError, "does not belong"):
            module._validate_incident_stage("DCO-1", "STAGE-2")

    def test_stage_from_the_same_order_is_normalized_and_accepted(self) -> None:
        module, database = _ServiceHarness.load()
        database.result = SimpleNamespace(
            name="STAGE-1",
            door_cutting_order="DCO-1",
        )

        result = module._validate_incident_stage("DCO-1", "  STAGE-1  ")

        self.assertEqual(result, "STAGE-1")
        self.assertEqual(database.calls[0][0][0:2], ("Production Stage", "STAGE-1"))
        self.assertEqual(database.calls[0][1], {"as_dict": True})

    def test_record_incident_persists_only_the_validated_stage(self) -> None:
        source = SERVICE_PATH.read_text(encoding="utf-8")

        self.assertIn(
            "validated_stage = _validate_incident_stage(order.name, production_stage)",
            source,
        )
        self.assertIn("incident.production_stage = validated_stage", source)
        self.assertNotIn("incident.production_stage = production_stage", source)


if __name__ == "__main__":
    unittest.main()
