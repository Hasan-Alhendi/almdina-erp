from __future__ import annotations

from typing import Any

import frappe
from frappe.utils import cint, flt

from almdina_erp.almdina_erp.application.inventory.check_order_stock import (
    OrderStockContext,
)
from almdina_erp.almdina_erp.domain.inventory import (
    MaterialDemand,
    MaterialRequirement,
    PieceMaterialInput,
    StockPosition,
)


METER_UOMS = frozenset({"meter", "metre", "meters", "metres", "m"})


class StockAvailabilityRepositoryError(RuntimeError):
    def __init__(self, code: str, **details: Any) -> None:
        super().__init__(code)
        self.code = code
        self.details = details


class FrappeStockAvailabilityRepository:
    """Read stock-check inputs and balances from Frappe without owning policy."""

    @staticmethod
    def _settings() -> Any:
        return frappe.get_single("Almdina ERP Settings")

    @staticmethod
    def _approved_plan(order_name: str) -> Any:
        plan_name = frappe.db.get_value(
            "Door Cutting Order",
            order_name,
            "approved_plan",
        ) or frappe.db.get_value(
            "Cutting Plan",
            {
                "door_cutting_order": order_name,
                "status": "Approved",
                "plan_kind": "Order",
            },
            "name",
            order_by="revision desc",
        )
        if not plan_name:
            raise StockAvailabilityRepositoryError(
                "approved_plan_required",
                order_name=order_name,
            )
        return frappe.get_doc("Cutting Plan", plan_name)

    def load_context(self, order_name: str) -> OrderStockContext:
        settings = self._settings()
        stock_enabled = bool(cint(settings.enforce_stock_control))
        warehouse = str(settings.default_warehouse or "") or None
        if not stock_enabled:
            return OrderStockContext(
                order_name=order_name,
                plan_name="",
                stock_control_enabled=False,
                warehouse=warehouse,
                board_item="",
                full_board_count=0,
                default_edge_type="",
                pieces=(),
            )

        order = frappe.get_doc("Door Cutting Order", order_name)
        plan = self._approved_plan(order_name)
        full_board_count = sum(
            1
            for source in (plan.sources or [])
            if source.source_type == "Full Board"
        )
        return OrderStockContext(
            order_name=str(order.name),
            plan_name=str(plan.name),
            stock_control_enabled=True,
            warehouse=warehouse,
            board_item=str(getattr(order, "board_item", "") or "").strip(),
            full_board_count=full_board_count,
            default_edge_type=str(order.default_edge_type or ""),
            pieces=tuple(
                PieceMaterialInput(
                    edge_type=str(row.edge_type or ""),
                    edge_meters=flt(row.edge_meters),
                )
                for row in (order.pieces or [])
            ),
        )

    @staticmethod
    def _validate_board_stock_uom(item_code: str) -> None:
        stock_uom = frappe.db.get_value("Item", item_code, "stock_uom")
        if not stock_uom:
            raise StockAvailabilityRepositoryError(
                "board_stock_uom_required",
                item_code=item_code,
            )
        whole = frappe.db.get_value("UOM", stock_uom, "must_be_whole_number")
        if not cint(whole):
            raise StockAvailabilityRepositoryError(
                "board_stock_uom_must_be_whole",
                item_code=item_code,
                stock_uom=stock_uom,
            )

    @staticmethod
    def _meter_to_stock_qty(item_code: str, meters: float) -> tuple[float, str]:
        item = frappe.db.get_value(
            "Item",
            item_code,
            ["stock_uom"],
            as_dict=True,
        )
        if not item:
            raise StockAvailabilityRepositoryError(
                "stock_item_missing",
                item_code=item_code,
            )

        stock_uom = str(item.stock_uom or "")
        if stock_uom.strip().lower() in METER_UOMS:
            return flt(meters), stock_uom

        rows = frappe.get_all(
            "UOM Conversion Detail",
            filters={"parent": item_code, "parenttype": "Item"},
            fields=["uom", "conversion_factor"],
        )
        meter_row = next(
            (
                row
                for row in rows
                if str(row.uom or "").strip().lower() in METER_UOMS
            ),
            None,
        )
        if not meter_row or flt(meter_row.conversion_factor) <= 0:
            raise StockAvailabilityRepositoryError(
                "meter_conversion_required",
                item_code=item_code,
                stock_uom=stock_uom,
            )
        return flt(meters) * flt(meter_row.conversion_factor), stock_uom

    def resolve_requirements(
        self,
        demand: MaterialDemand,
    ) -> tuple[MaterialRequirement, ...]:
        requirements: list[MaterialRequirement] = []
        if demand.full_board_count and demand.board_item:
            self._validate_board_stock_uom(demand.board_item)
            requirements.append(
                MaterialRequirement(
                    item_code=demand.board_item,
                    required_qty=flt(demand.full_board_count),
                    kind="Board",
                    planned_unit="Board",
                    planned_qty=flt(demand.full_board_count),
                )
            )

        for edge_demand in demand.edge_demands:
            edge_master = frappe.db.get_value(
                "Edge Banding Type",
                edge_demand.edge_type,
                ["item_code", "stock_uom", "disabled"],
                as_dict=True,
            )
            if not edge_master or cint(edge_master.disabled):
                raise StockAvailabilityRepositoryError(
                    "edge_type_disabled_or_missing",
                    edge_type=edge_demand.edge_type,
                )
            if not edge_master.item_code:
                raise StockAvailabilityRepositoryError(
                    "edge_type_item_mapping_required",
                    edge_type=edge_demand.edge_type,
                )

            stock_qty, stock_uom = self._meter_to_stock_qty(
                edge_master.item_code,
                edge_demand.meters,
            )
            requirements.append(
                MaterialRequirement(
                    item_code=str(edge_master.item_code),
                    required_qty=stock_qty,
                    kind="Edge Banding",
                    edge_type=edge_demand.edge_type,
                    planned_unit="Meter",
                    planned_qty=flt(edge_demand.meters),
                    stock_uom=stock_uom,
                )
            )

        return tuple(requirements)

    @staticmethod
    def find_active_order_reservation(
        order_name: str,
        plan_name: str,
    ) -> str | None:
        rows = frappe.db.sql(
            """
            select name
            from `tabMaterial Reservation`
            where door_cutting_order = %s
              and cutting_plan = %s
              and status = 'Active'
              and coalesce(replacement_piece, '') = ''
            order by creation desc
            limit 1
            """,
            (order_name, plan_name),
        )
        return str(rows[0][0]) if rows else None

    @staticmethod
    def get_stock_position(
        item_code: str,
        warehouse: str,
        *,
        exclude_reservation: str | None,
    ) -> StockPosition:
        actual_qty = flt(
            frappe.db.get_value(
                "Bin",
                {"item_code": item_code, "warehouse": warehouse},
                "actual_qty",
            )
        )
        conditions = [
            "parent.status = 'Active'",
            "child.item_code = %s",
            "child.warehouse = %s",
        ]
        values: list[Any] = [item_code, warehouse]
        if exclude_reservation:
            conditions.append("parent.name != %s")
            values.append(exclude_reservation)
        result = frappe.db.sql(
            f"""
            select coalesce(sum(child.qty), 0)
            from `tabMaterial Reservation Item` child
            inner join `tabMaterial Reservation` parent
                on parent.name = child.parent
            where {' and '.join(conditions)}
            """,
            tuple(values),
        )
        reserved_qty = flt((result or [[0]])[0][0])
        return StockPosition(
            item_code=item_code,
            actual_qty=actual_qty,
            reserved_qty=reserved_qty,
        )


__all__ = [
    "FrappeStockAvailabilityRepository",
    "StockAvailabilityRepositoryError",
]
