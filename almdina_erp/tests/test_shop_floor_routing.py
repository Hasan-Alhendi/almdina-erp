from __future__ import annotations

import unittest

from almdina_erp.almdina_erp.services import shop_floor_service as sfs


class TestShopFloorRouting(unittest.TestCase):
    def test_compatibility_facade_owns_no_fixed_route_sequence(self) -> None:
        for symbol in (
            "PATH_SEQUENCE",
            "_next_stage_type",
            "_sequence_for_stage",
        ):
            with self.subTest(symbol=symbol):
                self.assertFalse(hasattr(sfs, symbol), symbol)

    def test_compatibility_facade_owns_no_fixed_role_or_department_maps(self) -> None:
        for symbol in (
            "STAGE_ROLE",
            "STAGE_DEPARTMENT",
            "STAGE_ORDER_STATUS",
            "DEPARTMENT_STATUS_MAP",
        ):
            with self.subTest(symbol=symbol):
                self.assertFalse(hasattr(sfs, symbol), symbol)

    def test_historical_api_paths_delegate_to_configurable_services(self) -> None:
        self.assertEqual(
            sfs._COMMANDS,
            "almdina_erp.almdina_erp.services.shop_floor_commands",
        )
        self.assertEqual(
            sfs._QUERIES,
            "almdina_erp.almdina_erp.services.shop_floor_query_service",
        )
        self.assertEqual(
            sfs._DISPATCH,
            "almdina_erp.almdina_erp.services.order_dispatch_service",
        )
        for endpoint in (
            "get_shop_floor_context",
            "get_dispatch_options",
            "start_my_stage",
            "handoff_to_next",
            "dispatch_order",
        ):
            self.assertTrue(callable(getattr(sfs, endpoint)))


if __name__ == "__main__":
    unittest.main()
