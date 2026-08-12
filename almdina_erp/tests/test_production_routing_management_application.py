from __future__ import annotations

import unittest
from collections.abc import Mapping
from typing import Any

from almdina_erp.almdina_erp.application.factory.production_routing_management import (
    ProductionRoutingManagementConflict,
    ProductionRoutingManagementError,
    ProductionRoutingManagementPermissionDenied,
    SaveProductionRoutingCommand,
    delete_production_routing,
    routing_command,
    save_production_routing,
    set_production_routing_disabled,
)
from almdina_erp.almdina_erp.domain.security.authorization import Capability


class FakeRoutingRepository:
    def __init__(self) -> None:
        self.saved: SaveProductionRoutingCommand | None = None
        self.toggled: tuple[str, bool, str] | None = None
        self.deleted: tuple[str, str] | None = None

    def save_routing(
        self,
        command: SaveProductionRoutingCommand,
    ) -> Mapping[str, Any]:
        self.saved = command
        return {"name": command.name or command.routing_name, "saved": True}

    def set_routing_disabled(
        self,
        name: str,
        *,
        disabled: bool,
        expected_modified: str,
    ) -> Mapping[str, Any]:
        self.toggled = (name, disabled, expected_modified)
        return {"name": name, "disabled": disabled}

    def delete_routing(self, name: str, *, expected_modified: str) -> None:
        self.deleted = (name, expected_modified)


def route_payload(**overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "routing_name": "مسار جودة",
        "disabled": False,
        "stages": [
            {
                "stage_type": "Drawing",
                "department_label": "رسم",
                "operational_role": "عامل رسم",
                "is_planning_stage": True,
            },
            {
                "stage_type": "Quality Check",
                "department_label": "فحص الجودة",
                "operational_role": "عامل الجودة",
                "is_planning_stage": False,
            },
        ],
    }
    payload.update(overrides)
    return payload


class TestProductionRoutingManagementApplication(unittest.TestCase):
    def test_create_builds_a_valid_atomic_workflow_with_derived_sequences(self) -> None:
        repository = FakeRoutingRepository()
        result = save_production_routing(
            repository,
            {Capability.CREATE_PRODUCTION_ROUTINGS},
            route_payload(),
        )

        self.assertTrue(result["saved"])
        self.assertIsNotNone(repository.saved)
        assert repository.saved is not None
        self.assertEqual([stage.sequence for stage in repository.saved.stages], [10, 20])
        self.assertTrue(repository.saved.stages[0].is_planning_stage)

    def test_create_and_edit_use_distinct_capabilities(self) -> None:
        repository = FakeRoutingRepository()
        with self.assertRaises(ProductionRoutingManagementPermissionDenied):
            save_production_routing(repository, set(), route_payload())

        edit = route_payload(
            name="Existing Route",
            expected_modified="2026-08-09 12:00:00",
        )
        with self.assertRaises(ProductionRoutingManagementPermissionDenied):
            save_production_routing(
                repository,
                {Capability.CREATE_PRODUCTION_ROUTINGS},
                edit,
            )
        save_production_routing(
            repository,
            {Capability.EDIT_PRODUCTION_ROUTINGS},
            edit,
        )
        assert repository.saved is not None
        self.assertEqual(repository.saved.name, "Existing Route")

    def test_stale_edit_without_version_is_rejected_before_repository_access(self) -> None:
        repository = FakeRoutingRepository()
        with self.assertRaises(ProductionRoutingManagementConflict):
            save_production_routing(
                repository,
                {Capability.EDIT_PRODUCTION_ROUTINGS},
                route_payload(name="Existing Route"),
            )
        self.assertIsNone(repository.saved)

    def test_duplicate_codes_and_invalid_planning_order_are_rejected(self) -> None:
        duplicate = route_payload(
            stages=[
                {
                    "stage_type": "CNC",
                    "department_label": "CNC 1",
                    "operational_role": "عامل CNC",
                },
                {
                    "stage_type": "cnc",
                    "department_label": "CNC 2",
                    "operational_role": "عامل CNC",
                },
            ]
        )
        with self.assertRaisesRegex(ProductionRoutingManagementError, "تكرار"):
            routing_command(duplicate)

        invalid_planning = route_payload()
        invalid_planning["stages"][0]["is_planning_stage"] = False
        invalid_planning["stages"][1]["is_planning_stage"] = True
        with self.assertRaisesRegex(ProductionRoutingManagementError, "أول مرحلة"):
            routing_command(invalid_planning)

    def test_toggle_and_delete_are_versioned_and_capability_protected(self) -> None:
        repository = FakeRoutingRepository()
        with self.assertRaises(ProductionRoutingManagementPermissionDenied):
            set_production_routing_disabled(
                repository,
                set(),
                name="Route A",
                disabled=True,
                expected_modified="v1",
            )
        set_production_routing_disabled(
            repository,
            {Capability.EDIT_PRODUCTION_ROUTINGS},
            name="Route A",
            disabled="1",
            expected_modified="v1",
        )
        self.assertEqual(repository.toggled, ("Route A", True, "v1"))

        delete_production_routing(
            repository,
            {Capability.DELETE_PRODUCTION_ROUTINGS},
            name="Route A",
            expected_modified="v2",
        )
        self.assertEqual(repository.deleted, ("Route A", "v2"))


if __name__ == "__main__":
    unittest.main()
