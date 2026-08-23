from __future__ import annotations

from typing import Any

import frappe
from frappe import _
from frappe.utils import cint, flt

from almdina_erp.almdina_erp.domain.orders.numeric_input import (
    default_if_missing,
)
from almdina_erp.almdina_erp.domain.replacements.planning import (
    ReplacementPlanError,
    build_replacement_snapshot as build_domain_snapshot,
)
from almdina_erp.almdina_erp.infrastructure.frappe.cutting_plan_runtime_repository import (
    approved_plan_for_order,
    plan_settings,
)


def _board_dimension_cm(
    order: Any,
    fieldname: str,
    legacy_fieldname: str,
) -> float:
    legacy_value = flt(getattr(order, legacy_fieldname, None)) / 10
    value = default_if_missing(
        getattr(order, fieldname, None),
        legacy_value,
    )
    return flt(value)


def build_replacement_snapshot(
    order: Any,
    replacement: Any,
) -> dict[str, Any]:
    """Map replacement input using the exact approved Cutting Plan settings."""

    approved_plan = approved_plan_for_order(order)
    if not approved_plan:
        frappe.throw(_("يجب وجود خطة قص معتمدة وصالحة قبل إنشاء خطة قطعة التعويض."))
    settings = plan_settings(approved_plan)

    try:
        return build_domain_snapshot(
            board_description=str(
                replacement.board_description
                or order.board_description
                or ""
            ).strip(),
            board_width_cm=_board_dimension_cm(
                order,
                "board_width_cm",
                "full_board_width_mm",
            ),
            board_length_cm=_board_dimension_cm(
                order,
                "board_length_cm",
                "full_board_length_mm",
            ),
            trim_margin_mm=flt(settings.trim_margin_mm),
            kerf_mm=flt(settings.kerf_mm),
            original_piece_label=replacement.original_piece_label,
            piece_width_cm=flt(replacement.width_cm),
            piece_length_cm=flt(replacement.length_cm),
            allow_rotation=bool(cint(replacement.allow_rotation)),
            edge_long_right=bool(cint(replacement.edge_long_right)),
            edge_long_left=bool(cint(replacement.edge_long_left)),
            edge_width_top=bool(cint(replacement.edge_width_top)),
            edge_width_bottom=bool(cint(replacement.edge_width_bottom)),
            edge_type=replacement.edge_type or "",
            notes=replacement.notes or "",
        )
    except ReplacementPlanError as exc:
        frappe.throw(_(str(exc)))
