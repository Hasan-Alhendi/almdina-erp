from __future__ import annotations

import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "almdina_erp"
TEMPLATE_MODULE = APP / "application" / "security" / "permission_templates.py"
SERVICE = APP / "services" / "permission_management_service.py"
PAGE = APP / "page" / "factory_permissions" / "factory_permissions.js"
PERMISSION_API = ROOT / "public" / "js" / "factory_permissions" / "api.js"
PERMISSION_CONTROLLER = ROOT / "public" / "js" / "factory_permissions" / "controller.js"
DOCTYPE_ROOT = APP / "doctype"


class TestPermissionTemplatesRetired(unittest.TestCase):
    def test_permission_templates_are_not_part_of_runtime(self) -> None:
        self.assertFalse(TEMPLATE_MODULE.exists())
        service = SERVICE.read_text(encoding="utf-8")
        page = PAGE.read_text(encoding="utf-8")
        api = PERMISSION_API.read_text(encoding="utf-8")
        controller = PERMISSION_CONTROLLER.read_text(encoding="utf-8")
        browser_surface = "\n".join((page, api, controller))

        self.assertNotIn("preview_permission_template", service)
        self.assertNotIn("permission_template_catalog", service)
        self.assertNotIn("template_state", service)
        self.assertNotIn("preview_permission_template", browser_surface)
        self.assertNotIn("apc-template", browser_surface)
        self.assertIn("preview_permission_import", api)
        self.assertIn("previewImport", controller)

    def test_business_doctype_metadata_never_seeds_fixed_role_policy(self) -> None:
        offenders: list[str] = []
        for path in sorted(DOCTYPE_ROOT.glob("*/*.json")):
            payload = json.loads(path.read_text(encoding="utf-8"))
            if payload.get("doctype") != "DocType" or payload.get("istable"):
                continue
            permissions = payload.get("permissions") or []
            if permissions:
                roles = sorted(
                    {
                        str(row.get("role") or "")
                        for row in permissions
                        if isinstance(row, dict) and row.get("role")
                    }
                )
                offenders.append(
                    f"{path.relative_to(ROOT)} seeds fixed roles: {', '.join(roles)}"
                )
        self.assertEqual(
            offenders,
            [],
            "Role grants must be created through the permission matrix, not DocType JSON.\n"
            + "\n".join(offenders),
        )


if __name__ == "__main__":
    unittest.main()
