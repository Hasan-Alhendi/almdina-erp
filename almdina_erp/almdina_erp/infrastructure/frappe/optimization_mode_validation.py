from __future__ import annotations

import frappe
from frappe import _

from almdina_erp.almdina_erp.domain.cutting.catalog import (
    OptimizationModeUnavailableError,
    UnsupportedOptimizationModeError,
    optimization_mode,
    require_engine_mode,
)


def require_executable_optimization_mode(mode_value: str | None) -> str:
    """Resolve one runnable mode or raise a user-facing Frappe validation error.

    Domain catalog errors remain transport-agnostic. This boundary is only for
    Frappe request/execution surfaces that need a clear message instead of a raw
    domain exception. Historical low-level engine modes remain executable exactly
    as stored because ``require_engine_mode`` preserves that compatibility path.
    """

    try:
        return require_engine_mode(mode_value)
    except OptimizationModeUnavailableError as error:
        mode = optimization_mode(error.mode_id)
        label = mode.label if mode is not None else error.mode_id
        frappe.throw(
            _(
                "خوارزمية {0} غير متاحة للتنفيذ حاليًا. يرجى اختيار خوارزمية متاحة."
            ).format(label),
            frappe.ValidationError,
        )
    except UnsupportedOptimizationModeError:
        frappe.throw(
            _("خوارزمية التحسين المحددة غير معروفة. يرجى اختيار خوارزمية متاحة."),
            frappe.ValidationError,
        )

    raise AssertionError("unreachable")


__all__ = ["require_executable_optimization_mode"]
