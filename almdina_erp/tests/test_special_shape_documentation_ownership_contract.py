import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SUBSYSTEM = ROOT / "public" / "js" / "special_shape_documentation"


class TestSpecialShapeDocumentationOwnership(unittest.TestCase):
    def test_documentation_subsystem_has_clean_frontend_layers(self) -> None:
        for layer in ("domain", "application", "infrastructure", "presentation"):
            self.assertTrue((SUBSYSTEM / layer).is_dir(), layer)
        for path in (SUBSYSTEM / "domain").glob("*.js"):
            source = path.read_text(encoding="utf-8")
            self.assertNotIn("frappe.call", source)
            self.assertNotIn("querySelector", source)
        for path in (SUBSYSTEM / "application").glob("*.js"):
            source = path.read_text(encoding="utf-8")
            self.assertNotIn("frappe.call", source)
            self.assertNotIn("querySelector", source)

    def test_one_api_boundary_and_one_mutable_history_owner(self) -> None:
        api = (SUBSYSTEM / "infrastructure" / "workspace_api.js").read_text(encoding="utf-8")
        controller = (SUBSYSTEM / "presentation" / "workspace_controller.js").read_text(encoding="utf-8")
        self.assertIn("frappe.call", api)
        self.assertNotIn("frappe.call", controller)
        self.assertIn("root.History", (SUBSYSTEM / "application" / "history.js").read_text(encoding="utf-8"))

    def test_scanner_adapter_is_loopback_only_and_does_not_own_persistence(self) -> None:
        scanner = (SUBSYSTEM / "infrastructure" / "scanner_bridge.js").read_text(encoding="utf-8")
        self.assertIn('DEFAULT_BASE_URL = "http://127.0.0.1:17831"', scanner)
        self.assertIn("AlmdinaScannerBridgeSetup.exe", scanner)
        self.assertIn('resolved.hostname !== "127.0.0.1"', scanner)
        self.assertIn("window.fetch", scanner)
        self.assertNotIn("frappe.call", scanner)
        self.assertNotIn("special_shape_drawing_json", scanner)
        self.assertNotIn("special_shape_geometry_json", scanner)

    def test_runtime_has_no_legacy_editor_reference(self) -> None:
        roots = [ROOT / "public", ROOT / "almdina_erp" / "page" / "door_drawing"]
        for base in roots:
            for path in base.rglob("*.js"):
                source = path.read_text(encoding="utf-8")
                self.assertNotIn("door_drawing_v3", source, str(path))
                self.assertNotIn("door_drawing_v4", source, str(path))


if __name__ == "__main__":
    unittest.main()
