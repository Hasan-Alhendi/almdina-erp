from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from almdina_erp.almdina_erp.application.security.permission_matrix import (
    changed_capabilities,
    normalize_capability_state,
    permission_impact,
)
from almdina_erp.almdina_erp.domain.security.authorization import Capability


BUNDLE_SCHEMA = "almdina.permission-matrix"
BUNDLE_VERSION = 1
MAX_BUNDLE_ROLES = 500


@dataclass(frozen=True, slots=True)
class PermissionTemplate:
    key: str
    label: str
    description: str
    capabilities: frozenset[str]


_PERMISSION_TEMPLATES = (
    PermissionTemplate(
        key="order_entry",
        label="إدخال الطلبات",
        description="إنشاء الطلبات وتعديل المسودات وإرسالها للمراجعة وطباعة مستندات الزبون.",
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
        key="drawing_and_planning",
        label="الرسم وخطة القص",
        description="تشغيل مرحلة الرسم وإدارة الخطة وملفات DXF دون صلاحيات تكلفة أو إدارة.",
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
        description="تنفيذ المراحل المسندة وتسجيل الحوادث ومتابعة قطع التعويض التشغيلية فقط.",
        capabilities=frozenset(
            {
                Capability.VIEW_ORDERS,
                Capability.VIEW_CUTTING_PLAN,
                Capability.PRINT_CUTTING_PLAN,
                Capability.START_ASSIGNED_STAGE,
                Capability.HANDOFF_ASSIGNED_STAGE,
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
        description="إرسال الطلبات ومراقبة التنفيذ والرجوع وإعادة الإسناد وإدارة التعويضات.",
        capabilities=frozenset(
            {
                Capability.VIEW_ORDERS,
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
        key="costing_and_documents",
        label="التكلفة والمستندات",
        description="إدارة التكلفة والأسعار والتقارير المالية الداخلية ومستندات الزبون.",
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
                Capability.VIEW_OPERATIONAL_REPORTS,
                Capability.VIEW_FINANCIAL_REPORTS,
            }
        ),
    ),
    PermissionTemplate(
        key="control_center",
        label="مركز التحكم والجودة",
        description="اعتماد الطلبات وأرشفة الخطط وإدارة الحوادث وقطع التعويض دون تعديل التكلفة.",
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
        description="إدارة المستخدمين والإعدادات والبيانات الأساسية ومصفوفة الصلاحيات دون منح تشغيل أو تكلفة تلقائيًا.",
        capabilities=frozenset(
            {
                Capability.MANAGE_USERS,
                Capability.MANAGE_FACTORY_SETTINGS,
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

_TEMPLATE_BY_KEY = {template.key: template for template in _PERMISSION_TEMPLATES}


def template_state(template_key: str) -> dict[str, bool]:
    try:
        template = _TEMPLATE_BY_KEY[str(template_key or "").strip()]
    except KeyError as exc:
        raise ValueError(f"Unknown permission template: {template_key}") from exc
    return normalize_capability_state(
        {capability: True for capability in template.capabilities}
    )


def permission_template_payload() -> list[dict[str, Any]]:
    payload: list[dict[str, Any]] = []
    for template in _PERMISSION_TEMPLATES:
        state = template_state(template.key)
        payload.append(
            {
                "key": template.key,
                "label": template.label,
                "description": template.description,
                "capabilities": state,
                "impact": permission_impact(state),
            }
        )
    return payload


def _canonical_role_rows(
    role_states: Mapping[str, Mapping[str, Any]],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for raw_role, raw_state in sorted(role_states.items()):
        role = str(raw_role or "").strip()
        if not role:
            raise ValueError("Permission bundle roles must have a name.")
        rows.append(
            {
                "role": role,
                "capabilities": normalize_capability_state(raw_state),
            }
        )
    if not rows:
        raise ValueError("Permission bundle must contain at least one role.")
    if len(rows) > MAX_BUNDLE_ROLES:
        raise ValueError(
            f"Permission bundle cannot contain more than {MAX_BUNDLE_ROLES} roles."
        )
    return rows


def _role_checksum(rows: list[dict[str, Any]]) -> str:
    canonical = json.dumps(
        rows,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def build_permission_bundle(
    role_states: Mapping[str, Mapping[str, Any]],
    *,
    exported_by: str,
    exported_at: str,
    app_version: str,
) -> dict[str, Any]:
    rows = _canonical_role_rows(role_states)
    return {
        "schema": BUNDLE_SCHEMA,
        "version": BUNDLE_VERSION,
        "app_version": str(app_version or ""),
        "exported_by": str(exported_by or ""),
        "exported_at": str(exported_at or ""),
        "roles": rows,
        "checksum": _role_checksum(rows),
    }


def parse_permission_bundle(
    bundle: str | Mapping[str, Any],
) -> dict[str, dict[str, bool]]:
    try:
        payload = json.loads(bundle) if isinstance(bundle, str) else dict(bundle)
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        raise ValueError("Permission bundle is not valid JSON.") from exc

    if not isinstance(payload, dict):
        raise ValueError("Permission bundle must be an object.")
    if payload.get("schema") != BUNDLE_SCHEMA:
        raise ValueError("Unsupported permission bundle schema.")
    if payload.get("version") != BUNDLE_VERSION:
        raise ValueError("Unsupported permission bundle version.")

    raw_rows = payload.get("roles")
    if not isinstance(raw_rows, list) or not raw_rows:
        raise ValueError("Permission bundle must contain a non-empty roles list.")
    if len(raw_rows) > MAX_BUNDLE_ROLES:
        raise ValueError(
            f"Permission bundle cannot contain more than {MAX_BUNDLE_ROLES} roles."
        )

    role_states: dict[str, dict[str, bool]] = {}
    for row in raw_rows:
        if not isinstance(row, dict):
            raise ValueError("Every permission bundle role must be an object.")
        role = str(row.get("role") or "").strip()
        if not role:
            raise ValueError("Permission bundle roles must have a name.")
        if role in role_states:
            raise ValueError(f"Permission bundle contains duplicate role: {role}")
        capabilities = row.get("capabilities")
        if not isinstance(capabilities, dict):
            raise ValueError(f"Role {role} must contain a capabilities object.")
        role_states[role] = normalize_capability_state(capabilities)

    canonical_rows = _canonical_role_rows(role_states)
    checksum = str(payload.get("checksum") or "").strip()
    if not checksum or checksum != _role_checksum(canonical_rows):
        raise ValueError("Permission bundle checksum does not match its contents.")
    return role_states


def preview_permission_bundle(
    current_states: Mapping[str, Mapping[str, Any]],
    imported_states: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    role_previews: list[dict[str, Any]] = []
    total_changes = 0
    critical_changes = 0
    for role in sorted(imported_states):
        before = normalize_capability_state(current_states.get(role))
        after = normalize_capability_state(imported_states[role])
        changes = changed_capabilities(before, after)
        total_changes += len(changes)
        critical_changes += sum(
            1 for change in changes if change["risk"] == "critical"
        )
        role_previews.append(
            {
                "role": role,
                "changed": bool(changes),
                "changes": changes,
                "impact": permission_impact(after),
                "capabilities": after,
            }
        )
    return {
        "roles": role_previews,
        "summary": {
            "role_count": len(role_previews),
            "changed_role_count": sum(
                1 for row in role_previews if row["changed"]
            ),
            "change_count": total_changes,
            "critical_change_count": critical_changes,
        },
    }


__all__ = [
    "BUNDLE_SCHEMA",
    "BUNDLE_VERSION",
    "MAX_BUNDLE_ROLES",
    "build_permission_bundle",
    "parse_permission_bundle",
    "permission_template_payload",
    "preview_permission_bundle",
    "template_state",
]
