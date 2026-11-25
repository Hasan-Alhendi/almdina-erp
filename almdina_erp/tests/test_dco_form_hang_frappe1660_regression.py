"""Point to the behavioral JS hang suite; keep a thin Python wiring guard."""

from __future__ import annotations

import subprocess
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BEHAVIORAL = ROOT / "tests" / "js" / "dco_form_hang_behavioral.test.js"
SIDEBAR = (
    ROOT
    / "public"
    / "js"
    / "door_cutting_order"
    / "core"
    / "door_cutting_order_form_sidebar_controller.js"
)


class TestDcoFormHangFrappe1660Regression(unittest.TestCase):
    def test_behavioral_hang_suite_exists(self) -> None:
        self.assertTrue(BEHAVIORAL.exists())
        source = BEHAVIORAL.read_text(encoding="utf-8")
        self.assertIn("preference restore must not use toggle on desktop", source)
        self.assertIn("settle reports ready without another recovery storm", source)

    def test_desktop_preference_uses_show_hide_not_toggle(self) -> None:
        source = SIDEBAR.read_text(encoding="utf-8")
        self.assertIn("wrapper.show", source)
        self.assertIn("wrapper.hide", source)
        self.assertIn("Prefer show/hide over Frappe's toggle helper", source)

    def test_behavioral_hang_suite_passes(self) -> None:
        completed = subprocess.run(
            ["node", str(BEHAVIORAL)],
            capture_output=True,
            text=True,
            check=False,
        )
        if completed.returncode != 0:
            self.fail(
                "behavioral hang suite failed:\n"
                f"stdout:\n{completed.stdout}\n"
                f"stderr:\n{completed.stderr}"
            )


if __name__ == "__main__":
    unittest.main()
