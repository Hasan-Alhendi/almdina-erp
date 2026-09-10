from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

import frappe
from frappe.utils import cint

from almdina_erp.almdina_erp.application.factory.production_stage_definition_management import (
    ProductionStageDefinitionConflict,
    ProductionStageDefinitionError,
    ProductionStageDefinitionSnapshot,
    SaveProductionStageDefinitionCommand,
)


def _snapshot(row: Any) -> ProductionStageDefinitionSnapshot:
    return ProductionStageDefinitionSnapshot(
        name=str(row.name),
        stage_code=str(row.stage_code or row.name),
        stage_label=str(row.stage_label or row.name),
        description=str(row.description or ""),
        is_planning_default=bool(cint(row.is_planning_default)),
        disabled=bool(cint(row.disabled)),
        modified=str(row.modified or ""),
    )


def _fields() -> list[str]:
    return [
        "name",
        "stage_code",
        "stage_label",
        "description",
        "is_planning_default",
        "disabled",
        "modified",
    ]


def _locked_definition(name: str) -> Mapping[str, Any]:
    rows = frappe.db.sql(
        "select name, modified from `tabProduction Stage Definition` where name = %s for update",
        (name,),
        as_dict=True,
    )
    if not rows:
        raise ProductionStageDefinitionError(
            "المرحلة المطلوبة غير موجودة أو تم حذفها."
        )
    return rows[0]


def _assert_version(snapshot: Mapping[str, Any], expected_modified: str) -> None:
    if str(snapshot.get("modified") or "") != str(expected_modified or ""):
        raise ProductionStageDefinitionConflict(
            "تم تعديل المرحلة بواسطة مستخدم آخر. حدّث الصفحة وراجع التغييرات قبل الحفظ."
        )


class FrappeProductionStageDefinitionRepository:
    def list_definitions(self) -> list[ProductionStageDefinitionSnapshot]:
        rows = frappe.get_all(
            "Production Stage Definition",
            fields=_fields(),
            order_by="disabled asc, stage_label asc, stage_code asc",
        )
        return [_snapshot(row) for row in rows]

    def get_definitions(
        self,
        names: Sequence[str],
    ) -> dict[str, ProductionStageDefinitionSnapshot]:
        resolved = sorted({str(name or "").strip() for name in names if str(name or "").strip()})
        if not resolved:
            return {}
        rows = frappe.get_all(
            "Production Stage Definition",
            filters={"name": ["in", resolved]},
            fields=_fields(),
        )
        return {str(row.name): _snapshot(row) for row in rows}

    def save_definition(
        self,
        command: SaveProductionStageDefinitionCommand,
    ) -> ProductionStageDefinitionSnapshot:
        if command.name:
            locked = _locked_definition(command.name)
            _assert_version(locked, command.expected_modified or "")
            document = frappe.get_doc("Production Stage Definition", command.name)
        else:
            if frappe.db.exists("Production Stage Definition", command.stage_code):
                raise ProductionStageDefinitionError(
                    "يوجد تعريف مرحلة بهذا الرمز. اختر رمزًا مختلفًا."
                )
            document = frappe.new_doc("Production Stage Definition")
            document.stage_code = command.stage_code

        document.stage_label = command.stage_label
        document.description = command.description
        document.is_planning_default = int(command.is_planning_default)
        if command.name:
            document.save(ignore_permissions=True)
        else:
            document.insert(ignore_permissions=True)
        return _snapshot(document)

    def set_disabled(
        self,
        name: str,
        *,
        disabled: bool,
        expected_modified: str,
    ) -> ProductionStageDefinitionSnapshot:
        locked = _locked_definition(name)
        _assert_version(locked, expected_modified)
        document = frappe.get_doc("Production Stage Definition", name)
        document.disabled = int(disabled)
        document.save(ignore_permissions=True)
        return _snapshot(document)

    def is_in_use(self, name: str) -> bool:
        return bool(
            frappe.db.exists(
                "Production Routing Stage",
                {"stage_definition": name},
            )
        )

    def delete_definition(self, name: str, *, expected_modified: str) -> None:
        locked = _locked_definition(name)
        _assert_version(locked, expected_modified)
        frappe.delete_doc(
            "Production Stage Definition",
            name,
            ignore_permissions=True,
        )


__all__ = ["FrappeProductionStageDefinitionRepository"]
