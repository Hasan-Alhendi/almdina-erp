from __future__ import annotations

from typing import Any, Callable, TypeVar

import frappe
from frappe import _

from almdina_erp.almdina_erp.application.orders.intake_planning import (
    finish_data_entry as finish_data_entry_use_case,
    get_finish_data_entry_options as get_finish_data_entry_options_use_case,
    initialize_data_entry,
)
from almdina_erp.almdina_erp.domain.orders.intake_lifecycle import (
    IntakeLifecycleError,
    IntakePermissionError,
)
from almdina_erp.almdina_erp.infrastructure.frappe.order_intake_repository import (
    FrappeOrderIntakeRepository,
)


_Result = TypeVar("_Result")
_repository = FrappeOrderIntakeRepository()


def _execute(function: Callable[..., _Result], *args: Any) -> _Result:
    try:
        return function(_repository, *args)
    except IntakePermissionError as error:
        frappe.throw(_(str(error)), frappe.PermissionError)
    except (IntakeLifecycleError, ValueError) as error:
        frappe.throw(_(str(error)), frappe.ValidationError)
    raise AssertionError("frappe.throw must interrupt execution")


def ensure_data_entry_after_save(document: Any, method: str | None = None) -> bool:
    """Initialize DATA_ENTRY after the first successful persisted insert only."""

    del method
    return _execute(initialize_data_entry, document)


@frappe.whitelist()
def get_finish_data_entry_options(order_name: str) -> dict[str, Any]:
    """Return server-authorized routes, route preview data and qualified workers."""

    return _execute(get_finish_data_entry_options_use_case, order_name)


@frappe.whitelist()
def finish_data_entry(
    order_name: str,
    route_name: str,
    assignee: str,
) -> dict[str, Any]:
    """Persist a pending dispatch plan without starting production."""

    return _execute(
        finish_data_entry_use_case,
        order_name,
        route_name,
        assignee,
    )


__all__ = [
    "ensure_data_entry_after_save",
    "finish_data_entry",
    "get_finish_data_entry_options",
]
