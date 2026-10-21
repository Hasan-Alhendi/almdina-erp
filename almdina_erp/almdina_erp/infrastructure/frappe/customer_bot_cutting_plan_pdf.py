"""Render the existing official approved-plan print HTML with site Chromium.

The print format and its ``@page`` rule stay the source of page size and
margins. This adapter does not select Frappe's Chrome PDF generator, which
replaces those rules, and it does not archive a File.
"""

from __future__ import annotations

import re
import subprocess
import tempfile
from pathlib import Path

import frappe

from almdina_erp.almdina_erp.infrastructure.frappe.cutting_plan_runtime_repository import (
    approved_plan_for_order,
)


PRINT_FORMAT = "Door Cutting Plan Production A4"
PDF_TIMEOUT_SEC = 45


class FrappeCustomerBotCuttingPlanPdfAdapter:
    """Use the archive's print source, but never save a File or add comments."""

    def render(self, order_name: str, plan_name: str) -> bytes:
        order = frappe.get_doc("Door Cutting Order", order_name)
        approved = approved_plan_for_order(order)
        if approved is None or str(approved.name) != str(plan_name):
            raise ValueError("approved_plan_changed")

        html = frappe.get_print(
            "Door Cutting Order",
            order.name,
            print_format=PRINT_FORMAT,
            as_pdf=False,
        )
        pdf = _print_html_with_site_chromium(_inline_local_print_styles(str(html or "")))
        if not pdf.startswith(b"%PDF"):
            raise ValueError("cutting_plan_pdf_failed")
        return pdf


def _inline_local_print_styles(html: str) -> str:
    """Embed the print view's local stylesheets so file printing keeps them.

    The print format HTML, including its ``@page`` rule, is left unchanged.
    Remote addresses are not fetched.
    """

    def replace(match: re.Match[str]) -> str:
        css_path = _local_asset_path(match.group(1))
        if css_path is None or not css_path.is_file():
            return match.group(0)
        return "<style>" + css_path.read_text(encoding="utf-8") + "</style>"

    return re.sub(
        r"<link\b[^>]*\bhref=[\"']([^\"']+)[\"'][^>]*>",
        replace,
        html,
    )


def _local_asset_path(href: str) -> Path | None:
    path = href.split("?", 1)[0]
    marker = "/assets/"
    index = path.find(marker)
    if index < 0:
        return None
    relative = path[index + 1 :]
    return Path(frappe.utils.get_bench_path()) / "sites" / relative


def _print_html_with_site_chromium(html: str) -> bytes:
    markup = str(html or "").strip()
    if not markup:
        raise ValueError("cutting_plan_pdf_failed")
    from frappe.utils.print_utils import find_or_download_chromium_executable

    executable = str(find_or_download_chromium_executable() or "").strip()
    if not executable:
        raise ValueError("cutting_plan_pdf_failed")
    try:
        with tempfile.TemporaryDirectory(prefix="almdina-bot-plan-pdf-") as folder:
            root = Path(folder)
            html_path = root / "plan.html"
            pdf_path = root / "plan.pdf"
            profile = root / "profile"
            profile.mkdir()
            html_path.write_text(markup, encoding="utf-8")
            result = subprocess.run(
                [
                    executable,
                    "--headless",
                    "--disable-gpu",
                    "--no-sandbox",
                    "--disable-dev-shm-usage",
                    "--no-first-run",
                    "--disable-extensions",
                    "--disable-background-networking",
                    "--no-pdf-header-footer",
                    "--host-resolver-rules=MAP * ~NOTFOUND",
                    f"--user-data-dir={profile}",
                    f"--print-to-pdf={pdf_path}",
                    html_path.resolve().as_uri(),
                ],
                capture_output=True,
                timeout=PDF_TIMEOUT_SEC,
                check=False,
            )
            if result.returncode != 0 or not pdf_path.is_file():
                raise ValueError("cutting_plan_pdf_failed")
            return pdf_path.read_bytes()
    except ValueError:
        raise
    except Exception as error:
        raise ValueError("cutting_plan_pdf_failed") from error


__all__ = ["FrappeCustomerBotCuttingPlanPdfAdapter", "PRINT_FORMAT"]
