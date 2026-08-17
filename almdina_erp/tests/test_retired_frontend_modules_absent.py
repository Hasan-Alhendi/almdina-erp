from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HOOKS = ROOT / "hooks.py"
PUBLIC_JS = ROOT / "public" / "js"
RETIRED_FRONTEND_MODULES = (
    "door_cutting_order_workflow.js",
    "door_cutting_order_cost_invoice_ux.js",
    "production_stage.js",
)


class TestRetiredFrontendModulesAbsent(unittest.TestCase):
    def test_retired_frontend_modules_are_not_shipped_or_loaded(self) -> None:
        hooks = HOOKS.read_text(encoding="utf-8")

        for filename in RETIRED_FRONTEND_MODULES:
            with self.subTest(filename=filename):
                self.assertFalse(
                    (PUBLIC_JS / filename).exists(),
                    f"Retired frontend module must stay deleted: {filename}",
                )
                self.assertNotIn(f'"public/js/{filename}"', hooks)


if __name__ == "__main__":
    unittest.main()
