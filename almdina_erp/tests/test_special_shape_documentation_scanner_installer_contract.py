from __future__ import annotations

import unittest
from pathlib import Path


PACKAGE_ROOT = Path(__file__).resolve().parents[1]
REPOSITORY_ROOT = PACKAGE_ROOT.parent
BRIDGE = REPOSITORY_ROOT / "tools" / "almdina_scanner_bridge"
APP_PROJECT = BRIDGE / "src" / "Almdina.ScannerBridge" / "Almdina.ScannerBridge.csproj"
SERVER = BRIDGE / "src" / "Almdina.ScannerBridge" / "Infrastructure" / "LoopbackHttpServer.cs"
WIA = BRIDGE / "src" / "Almdina.ScannerBridge" / "Infrastructure" / "WiaScanner.cs"
CORE = BRIDGE / "src" / "Almdina.ScannerBridge.Core"
INSTALLER = BRIDGE / "installer" / "AlmdinaScannerBridge.iss"
WORKFLOW = REPOSITORY_ROOT / ".github" / "workflows" / "scanner-bridge-windows.yml"


class TestSpecialShapeDocumentationScannerInstallerContract(unittest.TestCase):
    def test_employee_runtime_is_a_background_windows_app_not_powershell(self) -> None:
        project = APP_PROJECT.read_text(encoding="utf-8")
        self.assertIn("<OutputType>WinExe</OutputType>", project)
        self.assertIn("<UseWindowsForms>true</UseWindowsForms>", project)
        self.assertIn("<SelfContained>true</SelfContained>", project)
        self.assertIn("<ApplicationIcon>", project)
        self.assertTrue((BRIDGE / "assets" / "AlmdinaScannerBridge.ico").is_file())
        self.assertFalse(any(BRIDGE.glob("*.ps1")), "employees must not run a PowerShell bridge")

    def test_network_and_scanner_adapters_remain_separate_and_local(self) -> None:
        server = SERVER.read_text(encoding="utf-8")
        scanner = WIA.read_text(encoding="utf-8")
        origin = (CORE / "OriginPolicy.cs").read_text(encoding="utf-8")
        self.assertIn("IPAddress.Loopback", server)
        self.assertNotIn("IPAddress.Any", server)
        self.assertNotIn("HttpListener", server, "HTTP.sys URL ACLs would reintroduce administrator setup")
        self.assertIn('"WIA.CommonDialog"', scanner)
        self.assertIn("StringComparer.OrdinalIgnoreCase", origin)
        self.assertNotIn("frappe", (CORE / "BridgeRequestDispatcher.cs").read_text(encoding="utf-8").lower())

    def test_installer_is_per_user_and_enables_login_startup(self) -> None:
        source = INSTALLER.read_text(encoding="utf-8")
        self.assertIn("PrivilegesRequired=lowest", source)
        self.assertIn("{localappdata}", source)
        self.assertIn("Windows\\CurrentVersion\\Run", source)
        self.assertIn("--background", source)
        self.assertIn("--shutdown", source)
        self.assertNotIn("netsh", source.lower())

    def test_windows_ci_builds_tests_signs_and_packages_the_installer(self) -> None:
        workflow = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("windows-2025", workflow)
        self.assertIn("Almdina.ScannerBridge.Core.Tests", workflow)
        self.assertIn("dotnet publish", workflow)
        self.assertIn("signtool", workflow.lower())
        self.assertIn("AlmdinaScannerBridgeSetup.exe", workflow)
        self.assertIn("Require signed production binaries", workflow)


if __name__ == "__main__":
    unittest.main()
