from __future__ import annotations

import unittest

from almdina_erp.almdina_erp.application.costing.customer_invoice_addon_summary import (
    summarize_extra_addon_lines,
)


class CustomerInvoiceAddonSummaryTest(unittest.TestCase):
    def test_groups_same_addon_across_leaves_and_hides_leaf_details(self) -> None:
        source = [
            {
                "type": "material",
                "description": "ألواح MDF",
                "quantity": 2,
                "unit": "لوح",
                "rate_usd": 10,
                "amount_usd": 20,
                "note": "",
            },
            {
                "type": "extra_addon",
                "description": "إضافة Liner — درفة رقم 28",
                "quantity": 2,
                "unit": "درفة",
                "rate_usd": 3,
                "amount_usd": 6,
                "note": "ملاحظة خاصة بالدرفة 28",
            },
            {
                "type": "extra_addon",
                "description": "إضافة Liner — درفة رقم 29",
                "quantity": 3,
                "unit": "درفة",
                "rate_usd": 3,
                "amount_usd": 9,
                "note": "ملاحظة خاصة بالدرفة 29",
            },
            {
                "type": "extra_addon",
                "description": "إضافة حفر مسكة غطس — درفة رقم 30",
                "quantity": 1,
                "unit": "درفة",
                "rate_usd": 4,
                "amount_usd": 4,
                "note": "تفصيل داخلي",
            },
        ]

        summarized = summarize_extra_addon_lines(source)

        self.assertEqual(len(summarized), 3)
        liner = summarized[1]
        handle = summarized[2]
        self.assertEqual(liner["description"], "لاينر")
        self.assertEqual(liner["quantity"], 5)
        self.assertEqual(liner["rate_usd"], 3)
        self.assertEqual(liner["amount_usd"], 15)
        self.assertEqual(liner["note"], "")
        self.assertEqual(handle["description"], "مسكة غطس")
        self.assertEqual(handle["quantity"], 1)
        self.assertEqual(handle["amount_usd"], 4)
        self.assertNotIn("درفة رقم", " ".join(line["description"] for line in summarized))
        self.assertEqual(
            sum(line["amount_usd"] for line in summarized),
            sum(line["amount_usd"] for line in source),
        )
        self.assertEqual(source[1]["description"], "إضافة Liner — درفة رقم 28")

    def test_mixed_historical_rates_stay_one_line_and_preserve_amount(self) -> None:
        source = [
            {
                "type": "extra_addon",
                "description": "إضافة Liner — درفة رقم 1",
                "quantity": 1,
                "unit": "درفة",
                "rate_usd": 4,
                "amount_usd": 4,
                "note": "",
            },
            {
                "type": "extra_addon",
                "description": "إضافة لاينر — درفة رقم 2",
                "quantity": 1,
                "unit": "درفة",
                "rate_usd": 6,
                "amount_usd": 6,
                "note": "",
            },
        ]

        summarized = summarize_extra_addon_lines(source)

        self.assertEqual(len(summarized), 1)
        self.assertEqual(summarized[0]["description"], "لاينر")
        self.assertEqual(summarized[0]["quantity"], 2)
        self.assertEqual(summarized[0]["amount_usd"], 10)
        self.assertEqual(summarized[0]["rate_usd"], 5)


if __name__ == "__main__":
    unittest.main()
