from __future__ import annotations

from pathlib import Path

from almdina_erp.almdina_erp.application.security.navigation_context import (
    build_navigation_context,
)
from almdina_erp.almdina_erp.domain.security.authorization import Capability


ROOT = Path(__file__).resolve().parents[1]
BOOT = ROOT / "boot.py"
SHARED_SHELL = ROOT / "public" / "js" / "shared_shell.js"


def test_order_entry_navigation_does_not_replace_frappe_home_route() -> None:
    navigation = build_navigation_context(
        {
            Capability.VIEW_ORDERS,
            Capability.CREATE_ORDER,
            Capability.EDIT_ORDER,
            Capability.SUBMIT_ORDER,
            Capability.PRINT_MEASUREMENTS,
            Capability.PRINT_CUSTOMER_INVOICE,
        }
    )

    assert navigation["profile"] == "order_entry"
    assert navigation["shared_shell"] is True
    assert navigation["app_only"] is True
    assert "home_page" not in navigation
    assert "default_route" not in navigation


def test_boot_never_overwrites_native_frappe_landing_fields() -> None:
    source = BOOT.read_text(encoding="utf-8")

    assert 'bootinfo["home_page"] =' not in source
    assert 'bootinfo["default_route"] =' not in source
    assert 'apps_data["default_path"] =' not in source


def test_shared_shell_does_not_invent_a_root_redirect_without_explicit_home() -> None:
    source = SHARED_SHELL.read_text(encoding="utf-8")

    assert (
        "if (!nav || !nav.shared_shell || !nav.home_page || !routeIsRoot()) return true;"
        in source
    )
