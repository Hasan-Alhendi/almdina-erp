from __future__ import annotations

import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
BRIDGE = ROOT / "tools" / "scanner_bridge" / "windows" / "AlmdinaScannerBridge.ps1"
CONFIG = ROOT / "tools" / "scanner_bridge" / "windows" / "config.example.json"
INSTALLER = ROOT / "tools" / "scanner_bridge" / "windows" / "install.ps1"
UNINSTALLER = ROOT / "tools" / "scanner_bridge" / "windows" / "uninstall.ps1"
REFERENCE_CONTROLLER = ROOT / "almdina_erp" / "public" / "js" / "door_drawing_v4" / "reference" / "reference_controller.js"
SCANNER_CLIENT = ROOT / "almdina_erp" / "public" / "js" / "door_drawing_v4" / "reference" / "scanner_bridge.js"
PAGE = ROOT / "almdina_erp" / "almdina_erp" / "page" / "door_drawing" / "door_drawing.js"


class TestScannerBridgeArchitecture(unittest.TestCase):
    def test_bridge_is_loopback_only_and_origin_guarded(self) -> None:
        source = BRIDGE.read_text(encoding="utf-8")
        self.assertIn('Prefixes.Add("http://127.0.0.1:', source)
        self.assertNotIn("http://0.0.0.0", source)
        self.assertNotIn("http://+:", source)
        self.assertIn("IPAddress]::IsLoopback", source)
        self.assertIn("AllowedOrigins -notcontains", source)
        self.assertIn("Access-Control-Allow-Private-Network", source)
        self.assertIn('Headers["X-Almdina-Scanner-Bridge"]', source)
        self.assertIn("MaxScanBytes", source)
        self.assertIn("$MaxRequestBytes", source)

    def test_config_uses_explicit_origins_without_wildcard(self) -> None:
        payload = json.loads(CONFIG.read_text(encoding="utf-8"))
        self.assertEqual(payload["port"], 17654)
        self.assertEqual(payload["maxScanBytes"], 16 * 1024 * 1024)
        self.assertIn("https://almadina-2.horizontechco.com", payload["allowedOrigins"])
        self.assertNotIn("*", payload["allowedOrigins"])

    def test_browser_provider_uses_only_loopback_and_bounded_payload(self) -> None:
        source = SCANNER_CLIENT.read_text(encoding="utf-8")
        self.assertIn('DEFAULT_BASE_URL = "http://127.0.0.1:17654"', source)
        self.assertIn("MAX_SCAN_BYTES = 16 * 1024 * 1024", source)
        self.assertIn('credentials: "omit"', source)
        self.assertIn('mode: "cors"', source)
        self.assertIn('REQUEST_HEADER = "X-Almdina-Scanner-Bridge"', source)
        self.assertNotIn("0.0.0.0", source)

    def test_scanner_capture_reuses_reference_crop_and_save_pipeline(self) -> None:
        source = REFERENCE_CONTROLLER.read_text(encoding="utf-8")
        self.assertIn("scannerBridge.scan", source)
        self.assertIn("source: domain.SOURCES.SCANNER", source)
        self.assertIn("processFile(context, captured.file", source)
        self.assertIn("cropper.open(file, cropOptions)", source)
        self.assertIn("saveReferenceImage", source)
        self.assertNotIn("special_shape_geometry_json", source)
        self.assertNotIn("special_shape_drawing_json", source)

    def test_page_loads_scanner_before_reference_controller(self) -> None:
        source = PAGE.read_text(encoding="utf-8")
        scanner = source.index("/reference/scanner_bridge.js")
        controller = source.index("/reference/reference_controller.js")
        self.assertLess(scanner, controller)

    def test_install_and_uninstall_manage_only_local_bridge(self) -> None:
        install = INSTALLER.read_text(encoding="utf-8")
        uninstall = UNINSTALLER.read_text(encoding="utf-8")
        self.assertIn('"http://127.0.0.1:$port/"', install)
        self.assertIn("netsh http add urlacl", install)
        self.assertIn("Almdina Scanner Bridge.lnk", install)
        self.assertIn("netsh http delete urlacl", uninstall)
        self.assertIn("Almdina Scanner Bridge.lnk", uninstall)


if __name__ == "__main__":
    unittest.main()
