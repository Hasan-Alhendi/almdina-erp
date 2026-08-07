from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "almdina_erp"
TEMPLATE_MODULE = APP / "application" / "security" / "permission_templates.py"
SERVICE = APP / "services" / "permission_management_service.py"
PAGE = APP / "page" / "factory_permissions" / "factory_permissions.js"


class TestPermissionTemplatesRetired(unittest.TestCase):
    def test_permission_templates_are_not_part_of_runtime(self) -> None:
        self.assertFalse(TEMPLATE_MODULE.exists())
        service = SERVICE.read_text(encoding="utf-8")
        page = PAGE.read_text(encoding="utf-8")
        self.assertNotIn("preview_permission_template", service)
        self.assertNotIn("permission_template_catalog", service)
        self.assertNotIn("template_state", service)
        self.assertNotIn("preview_permission_template", page)
        self.assertNotIn("apc-template", page)
        self.assertIn("preview_permission_import", page)


if __name__ == "__main__":
    unittest.main()
