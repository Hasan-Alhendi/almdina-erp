from __future__ import annotations

import html
from typing import Any

import frappe
from frappe import _
from frappe.utils import cint

from almdina_erp.almdina_erp.application.security.drawing_action_policy import (
    DrawingActionDenied,
    DrawingActionState,
    required_upload_capability,
    validate_assigned_drawing_action,
)
from almdina_erp.almdina_erp.domain.security.authorization import Capability
from almdina_erp.almdina_erp.infrastructure.frappe import shop_floor_gateway
from almdina_erp.almdina_erp.infrastructure.frappe.cutting_plan_authorization import (
    require_cutting_plan_capability,
)
from almdina_erp.almdina_erp.infrastructure.frappe.cutting_plan_runtime_repository import (
    seed_plan_settings,
)
from almdina_erp.almdina_erp.infrastructure.frappe.stage_operational_access import (
    require_stage_operational_access,
)

MAX_DXF_FILE_SIZE = 10 * 1024 * 1024

_POLICY_MESSAGES = {
    "not_at_drawing": "هذا الإجراء متاح فقط عندما يكون الطلب في مرحلة الرسم.",
    "designer_not_assigned": "أسند الطلب إلى مصمم قبل تنفيذ هذا الإجراء.",
    "not_assigned_designer": "فقط المصمم المسند لهذا الطلب يمكنه تنفيذ هذا الإجراء.",
    "plan_already_approved": "الخطة معتمدة ومقفلة ولا يمكن استبدال ملف DXF.",
}


def _drawing_state(order: Any, *, production_dxf: str | None = None) -> DrawingActionState:
    return DrawingActionState(
        status=str(order.status or ""),
        production_path=str(order.production_path or ""),
        current_department=str(order.current_department or ""),
        current_assignee=str(order.current_assignee or ""),
        session_user=str(frappe.session.user or ""),
        approved_plan=str(order.approved_plan or ""),
        production_dxf=(
            str(production_dxf)
            if production_dxf is not None
            else str(order.production_dxf or "")
        ),
    )


def _throw_policy_error(error: DrawingActionDenied) -> None:
    frappe.throw(
        _(_POLICY_MESSAGES.get(error.code, "لا يسمح سير العمل الحالي بتنفيذ إجراء الرسم هذا.")),
        frappe.PermissionError,
    )


def _authorize_order(
    order: Any,
    capability: str,
    *,
    require_unlocked_plan: bool = True,
    require_assigned_designer: bool = True,
    require_stage_role: bool = False,
) -> Any:
    order.check_permission("read")
    require_cutting_plan_capability(order, capability)
    if require_stage_role:
        require_stage_operational_access(order)
    if require_assigned_designer:
        try:
            validate_assigned_drawing_action(
                _drawing_state(order),
                require_unlocked_plan=require_unlocked_plan,
            )
        except DrawingActionDenied as error:
            _throw_policy_error(error)
    elif require_unlocked_plan and order.approved_plan:
        _throw_policy_error(DrawingActionDenied("plan_already_approved"))
    return order


def _get_authorized_order(
    order_name: str,
    capability: str,
    *,
    require_unlocked_plan: bool = True,
    require_assigned_designer: bool = True,
    require_stage_role: bool = False,
) -> Any:
    order = shop_floor_gateway.get_order(order_name)
    return _authorize_order(
        order,
        capability,
        require_unlocked_plan=require_unlocked_plan,
        require_assigned_designer=require_assigned_designer,
        require_stage_role=require_stage_role,
    )


def _validate_dxf_file_metadata(file_url: str) -> tuple[str, Any]:
    """Accept only a private, unattached DXF staging file.

    The browser uploads the file before any plan mutation. Keeping the staged
    File unattached prevents an unauthorized or invalid upload from becoming a
    document attachment before authorization and geometry validation succeed.
    """

    normalized_url = str(file_url or "").strip()
    if not normalized_url:
        frappe.throw(_("اختر ملف DXF ثم أعد المحاولة."), title=_("ملف DXF مطلوب"))
    if not normalized_url.lower().split("?", 1)[0].endswith(".dxf"):
        frappe.throw(
            _("نوع الملف غير صحيح. ارفع ملفًا بامتداد .dxf فقط."),
            title=_("ملف غير مدعوم"),
        )

    file_row = frappe.db.get_value(
        "File",
        {"file_url": normalized_url},
        [
            "name",
            "file_size",
            "is_private",
            "attached_to_doctype",
            "attached_to_name",
            "attached_to_field",
        ],
        as_dict=True,
    )
    if not file_row:
        frappe.throw(
            _("تعذر العثور على الملف المرفوع داخل النظام. أعد اختيار ملف DXF ورفعه مرة أخرى."),
            title=_("الملف غير موجود"),
        )
    if not cint(file_row.is_private):
        frappe.throw(
            _("يجب رفع ملف DXF كملف خاص Private قبل التحقق منه."),
            title=_("ملف DXF غير خاص"),
        )
    if (
        file_row.attached_to_doctype
        or file_row.attached_to_name
        or file_row.attached_to_field
    ):
        frappe.throw(
            _("ملف DXF المرفوع مرتبط مسبقًا بمستند ولا يمكن استخدامه. ارفع ملفًا خاصًا غير مرتبط ثم أعد المحاولة."),
            title=_("الملف مرتبط مسبقًا"),
        )

    file_size = int(file_row.file_size or 0)
    if file_size > MAX_DXF_FILE_SIZE:
        frappe.throw(
            _("حجم ملف DXF هو {0:.1f} MB، والحد الأقصى المسموح هو 10 MB.").format(
                file_size / (1024 * 1024)
            ),
            title=_("ملف DXF كبير جدًا"),
        )
    return normalized_url, file_row


def _attach_validated_dxf_file(plan: Any, file_row: Any) -> None:
    """Attach only a staging file that has passed authorization and validation."""

    frappe.db.set_value(
        "File",
        file_row.name,
        {
            "attached_to_doctype": "Cutting Plan",
            "attached_to_name": plan.name,
            "attached_to_field": "dxf_file",
        },
        update_modified=False,
    )


def _throw_dxf_validation_errors(errors: list[str]) -> None:
    clean_errors = [str(error).strip() for error in errors if str(error).strip()]
    if not clean_errors:
        clean_errors = ["تعذر التحقق من ملف DXF بسبب خطأ غير معروف."]
    visible = clean_errors[:10]
    items = "".join(f"<li>{html.escape(error)}</li>" for error in visible)
    remaining = len(clean_errors) - len(visible)
    extra = f"<p>وهناك {remaining} أخطاء إضافية. صحح الأخطاء الظاهرة أولًا ثم أعد الرفع.</p>" if remaining > 0 else ""
    message = (
        "<p><strong>لم يتم قبول ملف DXF لأن فحص خطة القص وجد الأخطاء التالية:</strong></p>"
        f"<ul>{items}</ul>{extra}"
        "<p>صحح الرسم ثم أعد رفع الملف. لم يتم استبدال خطة DXF الحالية في الطلب.</p>"
    )
    frappe.throw(message, title=_("تعذر قبول ملف DXF"))


@frappe.whitelist()
def mark_dxf_exported(order_name: str) -> dict[str, Any]:
    order = _get_authorized_order(
        order_name,
        Capability.EXPORT_DXF,
        require_assigned_designer=False,
        require_stage_role=True,
        require_unlocked_plan=False,
    )
    current = order.drawing_dxf_status or "None"
    if current in {"None", "Exported"}:
        frappe.db.set_value(
            "Door Cutting Order",
            order.name,
            "drawing_dxf_status",
            "Exported",
            update_modified=True,
        )
    return {
        "name": order.name,
        "drawing_dxf_status": frappe.db.get_value(
            "Door Cutting Order",
            order.name,
            "drawing_dxf_status",
        ),
    }


@frappe.whitelist()
def upload_production_dxf(order_name: str, file_url: str) -> dict[str, Any]:
    # Security order is intentional and regression-tested:
    # private+unattached staging -> authorization -> geometry validation ->
    # Cutting Plan persistence -> File attachment -> compatibility projection.
    normalized_url, file_row = _validate_dxf_file_metadata(file_url)

    order = shop_floor_gateway.get_order(order_name)
    from almdina_erp.almdina_erp.services.cutting_plan_command_service import (
        current_uploaded_dxf_file,
        mirror_uploaded_dxf_projection,
        save_uploaded_dxf_plan,
    )

    canonical_existing_file = current_uploaded_dxf_file(order.name)
    # One-time migration fallback for a legacy pre-A2 custom DXF that has not yet
    # been represented by a Cutting Plan revision.
    existing_file = canonical_existing_file or str(order.production_dxf or "")
    upload_capability = required_upload_capability(
        _drawing_state(order, production_dxf=existing_file)
    )
    order = _authorize_order(
        order,
        upload_capability,
        require_assigned_designer=False,
        require_stage_role=True,
    )
    replacing_existing_file = bool(existing_file)

    from almdina_erp.almdina_erp.services.dxf_import_service import DxfImportError
    from almdina_erp.almdina_erp.services.strict_dxf_import_service import (
        parse_production_dxf,
    )

    try:
        custom_snapshot = parse_production_dxf(
            normalized_url,
            order,
            settings=seed_plan_settings(order.name),
        )
    except DxfImportError as error:
        _throw_dxf_validation_errors(error.errors)

    validation = custom_snapshot.get("validation") or {}
    if not validation.get("is_valid"):
        _throw_dxf_validation_errors(validation.get("errors") or [])

    plan = save_uploaded_dxf_plan(
        order,
        custom_snapshot,
        normalized_url,
        capability=upload_capability,
    )

    # The file is linked only after all business authorization, geometry checks,
    # and canonical plan persistence have succeeded.
    _attach_validated_dxf_file(plan, file_row)
    mirror_uploaded_dxf_projection(order, plan)

    order.add_comment(
        "Info",
        text=_("DXF file {0} by {1}.").format(
            _("replaced") if replacing_existing_file else _("uploaded"),
            frappe.session.user,
        ),
    )
    return {
        "name": order.name,
        "cutting_plan": plan.name,
        "production_dxf": normalized_url,
        "drawing_dxf_status": "Uploaded",
        "custom_plan_json": str(plan.snapshot_json or ""),
        "required_capability": upload_capability,
    }


@frappe.whitelist()
def recalculate_drawing_plan(
    order_name: str,
    packing_mode: str | None = None,
    cutting_machine_type: str | None = None,
    kerf_mm: float | None = None,
    trim_margin_mm: float | None = None,
    optimization_time_limit_sec: float | None = None,
) -> dict[str, Any]:
    """Compatibility facade for the canonical focused cutting-plan command."""

    from almdina_erp.almdina_erp.services.order_plan_permission_service import (
        recalculate_order,
    )

    return recalculate_order(
        order_name=order_name,
        packing_mode=packing_mode,
        cutting_machine_type=cutting_machine_type,
        kerf_mm=kerf_mm,
        trim_margin_mm=trim_margin_mm,
        optimization_time_limit_sec=optimization_time_limit_sec,
    )


@frappe.whitelist()
def approve_production_dxf(
    order_name: str,
    plan_source: str = "System",
) -> dict[str, Any]:
    """Compatibility facade for the focused role-managed approval service."""

    from almdina_erp.almdina_erp.services.drawing_approval_service import (
        approve_production_dxf as approve_drawing_plan,
    )

    return approve_drawing_plan(order_name=order_name, plan_source=plan_source)


__all__ = [
    "approve_production_dxf",
    "mark_dxf_exported",
    "recalculate_drawing_plan",
    "upload_production_dxf",
]
