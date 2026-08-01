from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any

from almdina_erp.almdina_erp.application.security.permission_matrix import (
    normalize_capability_state,
    permission_impact,
)
from almdina_erp.almdina_erp.domain.security.authorization import Capability


PERMISSION_TRANSFER_SCHEMA = "almdina.permission-matrix"
PERMISSION_TRANSFER_VERSION = 1


@dataclass(frozen=True, slots=True)
class PermissionTemplate:
    key: str
    label: str
    description: str
    risk: str
    capabilities: frozenset[str]


_TEMPLATE_DEFINITIONS = (
    PermissionTemplate(
        key="order_entry",
        label="إدخال الطلبات",
        description="إنشاء الطلب وتعديله وإرساله للمراجعة مع طباعة القياسات وفاتورة الزبون.",
        risk="normal",
        capabilities=frozenset(
            {
                Capability.VIEW_ORDERS,
                Capability.CREATE_ORDER,
                Capability.EDIT_ORDER,
                Capability.SUBMIT_ORDER,
                Capability.PRINT_MEASUREMENTS,
                Capability.PRINT_CUSTOMER_INVOICE,
            }
        ),
    ),
    PermissionTemplate(
        key="planner_designer",
        label="التخطيط والرسم",
        description="حساب خطة القص وتعديل الرسم ورفع DXF واعتماده وتنفيذ المرحلة المسندة.",
        risk="sensitive",
        capabilities=frozenset(
            {
                Capability.VIEW_ORDERS,
                Capability.VIEW_CUTTING_PLAN,
                Capability.RECALCULATE_PLAN,
                Capability.EDIT_OPTIMIZER_SETTINGS,
                Capability.PRINT_CUTTING_PLAN,
                Capability.VIEW_DRAWING_WORKSPACE,
                Capability.EDIT_SPECIAL_DRAWING,
                Capability.EXPORT_DXF,
                Capability.UPLOAD_DXF,
                Capability.REPLACE_DXF,
                Capability.APPROVE_DXF,
                Capability.START_ASSIGNED_STAGE,
                Capability.HANDOFF_ASSIGNED_STAGE,
            }
        ),
    ),
    PermissionTemplate(
        key="production_operator",
        label="عامل إنتاج",
        description="بدء وتسليم المرحلة المسندة وعرض خطة القص وتسجيل الحوادث وتنفيذ التعويضات.",
        risk="normal",
        capabilities=frozenset(
            {
                Capability.VIEW_ORDERS,
                Capability.START_ASSIGNED_STAGE,
                Capability.HANDOFF_ASSIGNED_STAGE,
                Capability.VIEW_CUTTING_PLAN,
                Capability.PRINT_CUTTING_PLAN,
                Capability.RECORD_INCIDENT,
                Capability.VIEW_REPLACEMENTS,
                Capability.START_REPLACEMENT,
                Capability.COMPLETE_REPLACEMENT,
            }
        ),
    ),
    PermissionTemplate(
        key="production_supervisor",
        label="مشرف إنتاج",
        description="إرسال الطلبات للإنتاج وإعادة الإسناد والرجوع والتسليم وإدارة التعويضات التشغيلية.",
        risk="critical",
        capabilities=frozenset(
            {
                Capability.VIEW_ORDERS,
                Capability.VIEW_CUTTING_PLAN,
                Capability.DISPATCH_ORDER,
                Capability.REVERT_DEPARTMENT,
                Capability.RETURN_ORDER_TO_DRAFT,
                Capability.MARK_DELIVERED,
                Capability.REASSIGN_WORKER,
                Capability.CREATE_REPLACEMENT,
                Capability.VIEW_REPLACEMENTS,
                Capability.APPROVE_REPLACEMENT,
                Capability.CANCEL_REPLACEMENT,
                Capability.VIEW_OPERATIONAL_REPORTS,
            }
        ),
    ),
    PermissionTemplate(
        key="pricing_and_documents",
        label="التسعير والمستندات",
        description="عرض التكلفة وتعديلها واعتماد الأسعار وطباعة المستندات والتقارير المالية الداخلية.",
        risk="critical",
        capabilities=frozenset(
            {
                Capability.VIEW_ORDERS,
                Capability.VIEW_COSTS,
                Capability.EDIT_COST_SETTINGS,
                Capability.EDIT_SPECIAL_PRICE,
                Capability.APPROVE_SPECIAL_PRICE,
                Capability.EDIT_REPLACEMENT_COST,
                Capability.PRINT_MEASUREMENTS,
                Capability.PRINT_CUSTOMER_INVOICE,
                Capability.PRINT_INTERNAL_COST_REPORT,
                Capability.VIEW_FINANCIAL_REPORTS,
            }
        ),
    ),
    PermissionTemplate(
        key="factory_administration",
        label="إدارة المعمل",
        description="إدارة المستخدمين والإعدادات والبيانات الأساسية والصلاحيات دون منح اعتماد الطلبات تلقائيًا.",
        risk="critical",
        capabilities=frozenset(
            {
                Capability.VIEW_USERS,
                Capability.CREATE_USERS,
                Capability.EDIT_USERS,
                Capability.ASSIGN_WORKFORCE_PROFILE,
                Capability.ENABLE_USERS,
                Capability.DISABLE_USERS,
                Capability.RESET_USER_PASSWORD,
                Capability.VIEW_FACTORY_SETTINGS,
                Capability.EDIT_FACTORY_CUTTING_DEFAULTS,
                Capability.EDIT_FACTORY_COST_DEFAULTS,
                Capability.EDIT_FACTORY_PRODUCTION_CONTROLS,
                Capability.VIEW_PRODUCTION_ROUTINGS,
                Capability.CREATE_PRODUCTION_ROUTINGS,
                Capability.EDIT_PRODUCTION_ROUTINGS,
                Capability.DELETE_PRODUCTION_ROUTINGS,
                Capability.VIEW_EDGE_BANDING_TYPES,
                Capability.CREATE_EDGE_BANDING_TYPES,
                Capability.EDIT_EDGE_BANDING_TYPES,
                Capability.DELETE_EDGE_BANDING_TYPES,
                Capability.VIEW_OPERATIONAL_REPORTS,
                Capability.MANAGE_PERMISSIONS,
            }
        ),
    ),
)

PERMISSION_TEMPLATES = MappingProxyType(
    {template.key: template for template in _TEMPLATE_DEFINITIONS}
)


def template_state(template_key: str) -> dict[str, bool]:
    try:
        template = PERMISSION_TEMPLATES[str(template_key or "").strip()]
    except KeyError as exc:
        raise ValueError(f"Unknown permission template: {template_key}") from exc
    return normalize_capability_state(
        {capability: True for capability in template.capabilities}
    )


def permission_template_catalog() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for template in _TEMPLATE_DEFINITIONS:
        state = template_state(template.key)
        rows.append(
            {
                "key": template.key,
                "label": template.label,
                "description": template.description,
                "risk": template.risk,
                "capabilities": state,
                "impact": permission_impact(state),
            }
        )
    return rows


def _canonical_transfer_payload(
    *,
    role: str,
    capabilities: Sequence[str],
) -> dict[str, Any]:
    return {
        "schema": PERMISSION_TRANSFER_SCHEMA,
        "version": PERMISSION_TRANSFER_VERSION,
        "role": str(role or "").strip(),
        "capabilities": sorted(str(value) for value in capabilities),
    }


def _checksum(payload: Mapping[str, Any]) -> str:
    encoded = json.dumps(
        dict(payload),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def build_permission_export(
    *,
    role: str,
    state: Mapping[str, Any] | None,
) -> dict[str, Any]:
    normalized = normalize_capability_state(state)
    enabled = [
        capability
        for capability, granted in normalized.items()
        if granted is True
    ]
    canonical = _canonical_transfer_payload(role=role, capabilities=enabled)
    return {**canonical, "checksum": _checksum(canonical)}


def parse_permission_export(payload: Mapping[str, Any] | None) -> dict[str, Any]:
    document = dict(payload or {})
    if document.get("schema") != PERMISSION_TRANSFER_SCHEMA:
        raise ValueError("Unsupported permission export schema.")
    if document.get("version") != PERMISSION_TRANSFER_VERSION:
        raise ValueError("Unsupported permission export version.")

    source_role = str(document.get("role") or "").strip()
    capabilities = document.get("capabilities")
    if isinstance(capabilities, (str, bytes)) or not isinstance(capabilities, Sequence):
        raise ValueError("Permission export capabilities must be a list.")
    if any(not isinstance(value, str) or not value.strip() for value in capabilities):
        raise ValueError("Permission export contains an invalid capability key.")

    canonical = _canonical_transfer_payload(
        role=source_role,
        capabilities=list(capabilities),
    )
    checksum = str(document.get("checksum") or "").strip()
    if not checksum or checksum != _checksum(canonical):
        raise ValueError("Permission export checksum is invalid.")

    state = normalize_capability_state(
        {capability: True for capability in canonical["capabilities"]}
    )
    return {
        "source_role": source_role,
        "schema": PERMISSION_TRANSFER_SCHEMA,
        "version": PERMISSION_TRANSFER_VERSION,
        "capabilities": state,
    }


__all__ = [
    "PERMISSION_TEMPLATES",
    "PERMISSION_TRANSFER_SCHEMA",
    "PERMISSION_TRANSFER_VERSION",
    "PermissionTemplate",
    "build_permission_export",
    "parse_permission_export",
    "permission_template_catalog",
    "template_state",
]
