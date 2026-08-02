from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any

from almdina_erp.almdina_erp.application.security.permission_matrix import (
    changed_capabilities,
    normalize_capability_state,
    permission_impact,
)
from almdina_erp.almdina_erp.domain.security.authorization import Capability


PERMISSION_TRANSFER_SCHEMA = "almdina.permission-matrix"
PERMISSION_TRANSFER_VERSION = 1
MAX_TRANSFER_ROLES = 500


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
        key="control_center",
        label="مركز التحكم والجودة",
        description="اعتماد الطلبات وأرشفة الخطط وإدارة الحوادث وقطع التعويض دون صلاحيات مالية.",
        risk="critical",
        capabilities=frozenset(
            {
                Capability.VIEW_ORDERS,
                Capability.APPROVE_ORDER,
                Capability.REJECT_ORDER,
                Capability.VIEW_CUTTING_PLAN,
                Capability.PRINT_CUTTING_PLAN,
                Capability.ARCHIVE_APPROVED_PLAN,
                Capability.CREATE_REPLACEMENT,
                Capability.VIEW_REPLACEMENTS,
                Capability.APPROVE_REPLACEMENT,
                Capability.CANCEL_REPLACEMENT,
                Capability.VIEW_OPERATIONAL_REPORTS,
            }
        ),
    ),
    PermissionTemplate(
        key="factory_administration",
        label="إدارة المعمل",
        description="إدارة المستخدمين والإعدادات والبيانات الأساسية والصلاحيات دون منح تشغيل أو تكلفة أو اعتماد طلبات تلقائيًا.",
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


def _enabled_capabilities(state: Mapping[str, Any] | None) -> list[str]:
    normalized = normalize_capability_state(state)
    return sorted(
        capability
        for capability, granted in normalized.items()
        if granted is True
    )


def _checksum(payload: Mapping[str, Any]) -> str:
    encoded = json.dumps(
        dict(payload),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


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


def build_permission_export(
    *,
    role: str,
    state: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """Build the stable single-role format used by the existing console UX."""

    canonical = _canonical_transfer_payload(
        role=role,
        capabilities=_enabled_capabilities(state),
    )
    return {**canonical, "checksum": _checksum(canonical)}


def parse_permission_export(payload: Mapping[str, Any] | None) -> dict[str, Any]:
    document = dict(payload or {})
    if document.get("schema") != PERMISSION_TRANSFER_SCHEMA:
        raise ValueError("Unsupported permission export schema.")
    if document.get("version") != PERMISSION_TRANSFER_VERSION:
        raise ValueError("Unsupported permission export version.")

    source_role = str(document.get("role") or "").strip()
    if not source_role:
        raise ValueError("Permission export role is required.")
    capabilities = document.get("capabilities")
    if isinstance(capabilities, (str, bytes)) or not isinstance(
        capabilities, Sequence
    ):
        raise ValueError("Permission export capabilities must be a list.")
    if any(
        not isinstance(value, str) or not value.strip()
        for value in capabilities
    ):
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


def _canonical_bundle_roles(
    role_states: Mapping[str, Mapping[str, Any]],
) -> list[dict[str, Any]]:
    roles: list[dict[str, Any]] = []
    for raw_role, state in sorted(role_states.items()):
        role = str(raw_role or "").strip()
        if not role:
            raise ValueError("Permission bundle roles must have a name.")
        roles.append(
            {
                "role": role,
                "capabilities": _enabled_capabilities(state),
            }
        )
    if not roles:
        raise ValueError("Permission bundle must contain at least one role.")
    if len(roles) > MAX_TRANSFER_ROLES:
        raise ValueError(
            f"Permission bundle cannot contain more than {MAX_TRANSFER_ROLES} roles."
        )
    return roles


def _canonical_bundle_payload(
    role_states: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    return {
        "schema": PERMISSION_TRANSFER_SCHEMA,
        "version": PERMISSION_TRANSFER_VERSION,
        "kind": "role_matrix",
        "roles": _canonical_bundle_roles(role_states),
    }


def build_permission_bundle(
    role_states: Mapping[str, Mapping[str, Any]],
    *,
    exported_by: str,
    exported_at: str,
    app_version: str,
) -> dict[str, Any]:
    """Build a checksummed multi-role bundle without users or audit records."""

    canonical = _canonical_bundle_payload(role_states)
    return {
        **canonical,
        "app_version": str(app_version or ""),
        "exported_by": str(exported_by or ""),
        "exported_at": str(exported_at or ""),
        "checksum": _checksum(canonical),
    }


def parse_permission_bundle(
    payload: Mapping[str, Any] | None,
) -> dict[str, dict[str, bool]]:
    document = dict(payload or {})
    if document.get("schema") != PERMISSION_TRANSFER_SCHEMA:
        raise ValueError("Unsupported permission bundle schema.")
    if document.get("version") != PERMISSION_TRANSFER_VERSION:
        raise ValueError("Unsupported permission bundle version.")
    if document.get("kind") != "role_matrix":
        raise ValueError("Permission bundle kind must be role_matrix.")

    raw_roles = document.get("roles")
    if not isinstance(raw_roles, list) or not raw_roles:
        raise ValueError("Permission bundle must contain a non-empty roles list.")
    if len(raw_roles) > MAX_TRANSFER_ROLES:
        raise ValueError(
            f"Permission bundle cannot contain more than {MAX_TRANSFER_ROLES} roles."
        )

    role_states: dict[str, dict[str, bool]] = {}
    for row in raw_roles:
        if not isinstance(row, dict):
            raise ValueError("Every permission bundle role must be an object.")
        role = str(row.get("role") or "").strip()
        if not role:
            raise ValueError("Permission bundle roles must have a name.")
        if role in role_states:
            raise ValueError(f"Permission bundle contains duplicate role: {role}")
        capabilities = row.get("capabilities")
        if isinstance(capabilities, (str, bytes)) or not isinstance(
            capabilities, Sequence
        ):
            raise ValueError(
                f"Permission bundle role {role} must contain a capabilities list."
            )
        if any(
            not isinstance(value, str) or not value.strip()
            for value in capabilities
        ):
            raise ValueError(
                f"Permission bundle role {role} contains an invalid capability key."
            )
        role_states[role] = normalize_capability_state(
            {capability: True for capability in capabilities}
        )

    canonical = _canonical_bundle_payload(role_states)
    checksum = str(document.get("checksum") or "").strip()
    if not checksum or checksum != _checksum(canonical):
        raise ValueError("Permission bundle checksum is invalid.")
    return role_states


def preview_permission_bundle(
    current_states: Mapping[str, Mapping[str, Any]],
    imported_states: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    role_previews: list[dict[str, Any]] = []
    for role in sorted(imported_states):
        before = normalize_capability_state(current_states.get(role))
        after = normalize_capability_state(imported_states[role])
        changes = changed_capabilities(before, after)
        role_previews.append(
            {
                "role": role,
                "changed": bool(changes),
                "changes": changes,
                "capabilities": after,
                "impact": permission_impact(after),
            }
        )

    all_changes = [
        change
        for row in role_previews
        for change in row["changes"]
    ]
    return {
        "roles": role_previews,
        "summary": {
            "role_count": len(role_previews),
            "changed_role_count": sum(
                1 for row in role_previews if row["changed"]
            ),
            "change_count": len(all_changes),
            "critical_change_count": sum(
                1 for change in all_changes if change["risk"] == "critical"
            ),
        },
    }


__all__ = [
    "MAX_TRANSFER_ROLES",
    "PERMISSION_TEMPLATES",
    "PERMISSION_TRANSFER_SCHEMA",
    "PERMISSION_TRANSFER_VERSION",
    "PermissionTemplate",
    "build_permission_bundle",
    "build_permission_export",
    "parse_permission_bundle",
    "parse_permission_export",
    "permission_template_catalog",
    "preview_permission_bundle",
    "template_state",
]
