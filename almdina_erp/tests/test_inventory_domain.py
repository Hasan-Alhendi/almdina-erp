from __future__ import annotations

import unittest

from almdina_erp.almdina_erp.domain.inventory import (
    MaterialRequirement,
    PieceMaterialInput,
    StockPosition,
    build_material_demand,
    evaluate_stock_availability,
)


class TestInventoryDomain(unittest.TestCase):
    def test_material_demand_aggregates_effective_edge_types(self) -> None:
        demand = build_material_demand(
            board_item="MDF-18-WHITE",
            full_board_count=3,
            default_edge_type="2cm White",
            pieces=(
                PieceMaterialInput(edge_type="", edge_meters=2.5),
                PieceMaterialInput(edge_type="2cm White", edge_meters=1.5),
                PieceMaterialInput(edge_type="4cm Gold", edge_meters=3),
                PieceMaterialInput(edge_type="ignored", edge_meters=0),
            ),
        )

        self.assertEqual(demand.board_item, "MDF-18-WHITE")
        self.assertEqual(demand.full_board_count, 3)
        self.assertEqual(
            [(row.edge_type, row.meters) for row in demand.edge_demands],
            [("2cm White", 4.0), ("4cm Gold", 3.0)],
        )

    def test_availability_subtracts_other_reservations(self) -> None:
        requirement = MaterialRequirement(
            item_code="EDGE-WHITE",
            required_qty=8,
            kind="Edge Banding",
            edge_type="2cm White",
            planned_unit="Meter",
            planned_qty=8,
            stock_uom="Meter",
        )
        report = evaluate_stock_availability(
            requirements=(requirement,),
            positions={
                "EDGE-WHITE": StockPosition(
                    item_code="EDGE-WHITE",
                    actual_qty=10,
                    reserved_qty=4,
                )
            },
            warehouse="Main - AC",
            excluded_reservation="RES-1",
        )

        self.assertFalse(report.is_available)
        line = report.lines[0]
        self.assertEqual(line.available_qty, 6)
        self.assertEqual(line.shortage_qty, 2)
        self.assertEqual(report.excluded_reservation, "RES-1")
        payload = report.as_dict()
        self.assertEqual(payload["materials"][0]["qty"], 8)
        self.assertEqual(payload["shortages"][0]["edge_type"], "2cm White")

    def test_negative_available_stock_is_clamped_to_zero(self) -> None:
        requirement = MaterialRequirement(
            item_code="BOARD",
            required_qty=1,
            kind="Board",
            planned_unit="Board",
            planned_qty=1,
        )
        report = evaluate_stock_availability(
            requirements=(requirement,),
            positions={
                "BOARD": StockPosition(
                    item_code="BOARD",
                    actual_qty=1,
                    reserved_qty=3,
                )
            },
            warehouse="Main - AC",
        )
        self.assertEqual(report.lines[0].available_qty, 0)
        self.assertEqual(report.lines[0].shortage_qty, 1)


if __name__ == "__main__":
    unittest.main()
