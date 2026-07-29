from __future__ import annotations

from typing import Any, NoReturn

import frappe
from frappe import _

from almdina_erp.almdina_erp.application.inventory import (
    CheckOrderStockCommand,
    InsufficientStockError,
    MissingWarehouseError,
    check_order_stock as check_order_stock_use_case,
)
from almdina_erp.almdina_erp.infrastructure.frappe.inventory import (
    FrappeStockAvailabilityRepository,
    StockAvailabilityRepositoryError,
)
from almdina_erp.almdina_erp.services.cutting_plan_service import require_any_role


_repository = FrappeStockAvailabilityRepository()


def _throw_repository_error(error: StockAvailabilityRepositoryError) -> NoReturn:
    details = error.details
    messages = {
        "approved_plan_required": _(
            "Order {0} has no approved Cutting Plan."
        ).format(details.get("order_name")),
        "board_stock_uom_required": _(
            "Board Item {0} has no Stock UOM."
        ).format(details.get("item_code")),
        "board_stock_uom_must_be_whole": _(
            "Board Item {0} must use a whole-number Stock UOM because planned consumption is counted in physical boards."
        ).format(details.get("item_code")),
        "stock_item_missing": _(
            "Stock Item {0} does not exist."
        ).format(details.get("item_code")),
        "meter_conversion_required": _(
            "Edge stock Item {0} uses Stock UOM {1}. Add a Meter UOM conversion before consumption."
        ).format(details.get("item_code"), details.get("stock_uom")),
        "edge_type_disabled_or_missing": _(
            "Edge Banding Type {0} is disabled or missing."
        ).format(details.get("edge_type")),
        "edge_type_item_mapping_required": _(
            "Map Edge Banding Type {0} to a stock Item before approving/consuming this order."
        ).format(details.get("edge_type")),
    }
    frappe.throw(messages.get(error.code, _(error.code)))
    raise AssertionError("frappe.throw must interrupt execution")


def validate_stock_for_order(
    order_name: str,
    *,
    throw_on_shortage: bool = True,
    exclude_own_reservation: bool = True,
) -> dict[str, Any]:
    try:
        report = check_order_stock_use_case(
            CheckOrderStockCommand(
                order_name=order_name,
                throw_on_shortage=throw_on_shortage,
                exclude_own_reservation=exclude_own_reservation,
            ),
            _repository,
        )
    except MissingWarehouseError:
        frappe.throw(
            _(
                "Set Default Warehouse in Almdina ERP Settings before approving/starting production."
            )
        )
    except InsufficientStockError as error:
        lines = [
            _(
                "{0}: required {1}, available after reservations {2}, physical stock {3} in {4}"
            ).format(
                line.requirement.item_code,
                line.requirement.required_qty,
                line.available_qty,
                line.actual_qty,
                line.warehouse,
            )
            for line in error.report.shortages
        ]
        frappe.throw(_("Insufficient stock:\n{0}").format("\n".join(lines)))
    except StockAvailabilityRepositoryError as error:
        _throw_repository_error(error)
    else:
        return report.as_dict()
    raise AssertionError("frappe.throw must interrupt execution")


@frappe.whitelist()
def check_order_stock(order_name: str) -> dict[str, Any]:
    require_any_role(
        "Order Entry",
        "Cutting Operator",
        "Production Manager",
        "Stock Manager",
    )
    return validate_stock_for_order(order_name, throw_on_shortage=False)


__all__ = ["check_order_stock", "validate_stock_for_order"]
