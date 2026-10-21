"""Render the customer measurements document with site Chromium.

The WhatsApp measurements adapter mixes this HTML with send errors and a
wkhtmltopdf fallback. This adapter calls the same HTML builder and prints it
with the site Chromium only. It does not send, save a File, or write the order.
"""

from __future__ import annotations

import subprocess
import tempfile
from collections.abc import Callable
from pathlib import Path
from typing import Any

from almdina_erp.almdina_erp.infrastructure.frappe.customer_bot_measurements_reader import (
    load_owned_measurement_source,
)
from almdina_erp.almdina_erp.infrastructure.printing.measurements_print_document import (
    PRINT_IDENTITY_DEFAULTS,
    measurements_print_html,
)


PDF_TIMEOUT_SEC = 45


class FrappeCustomerBotMeasurementsPdfAdapter:
    def render(self, phone: str, order_name: str) -> bytes:
        import frappe

        source = load_owned_measurement_source(phone, order_name)
        if source is None or source.cancelled or not (source.payload.get("pieces") or []):
            raise ValueError("measurements_pdf_failed")
        html = measurements_print_html(
            source.payload,
            identity=_print_identity(),
            customer_phone=source.phone,
            printed_on=str(frappe.utils.now_datetime() or ""),
            language=getattr(frappe.local, "lang", None) or "ar",
            translator=frappe._,
        )
        executable = _chromium_executable()
        pdf = _print_measurements_html(html, executable=executable)
        if not pdf.startswith(b"%PDF"):
            raise ValueError("measurements_pdf_failed")
        return pdf


def _print_identity() -> dict[str, str]:
    import frappe

    try:
        settings = frappe.get_single("Almdina ERP Settings")
    except Exception:
        return dict(PRINT_IDENTITY_DEFAULTS)
    values: dict[str, str] = {}
    for fieldname, default in PRINT_IDENTITY_DEFAULTS.items():
        stored = str(settings.get(fieldname) or "").strip()
        values[fieldname] = stored or default
    return values


def _chromium_executable() -> str:
    from frappe.utils.print_utils import find_or_download_chromium_executable

    return str(find_or_download_chromium_executable() or "").strip()


def _restore_dimension_table_cells(html: str) -> str:
    """Keep width and length inside their table columns.

    The shared measurements stylesheet sets ``.ltr`` to ``inline-block``.
    Those two cells use that class, so Chromium stops treating them as
    table cells and paints the dimensions on top of each other. The same
    HTML is what the current measurements document already builds; this
    adapter only restores ``table-cell`` on its own copy.
    """

    fix = "<style>td.ltr{display:table-cell}</style>"
    if "</head>" in html:
        return html.replace("</head>", fix + "</head>", 1)
    return fix + html


def _print_measurements_html(
    html: str,
    *,
    executable: str,
    runner: Callable[..., Any] | None = None,
    timeout_sec: float = PDF_TIMEOUT_SEC,
) -> bytes:
    markup = _restore_dimension_table_cells(str(html or "").strip())
    binary = str(executable or "").strip()
    if not markup or not binary:
        raise ValueError("measurements_pdf_failed")
    run = runner or subprocess.run
    with tempfile.TemporaryDirectory(prefix="almdina-bot-measurements-pdf-") as folder:
        root = Path(folder)
        html_path = root / "measurements.html"
        pdf_path = root / "measurements.pdf"
        profile = root / "profile"
        profile.mkdir()
        html_path.write_text(markup, encoding="utf-8")
        try:
            result = run(
                [
                    binary,
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
                timeout=timeout_sec,
                check=False,
            )
        except Exception as error:
            raise ValueError("measurements_pdf_failed") from error
        if getattr(result, "returncode", 1) != 0 or not pdf_path.is_file():
            raise ValueError("measurements_pdf_failed")
        data = pdf_path.read_bytes()
        if not data.startswith(b"%PDF"):
            raise ValueError("measurements_pdf_failed")
        return data


__all__ = [
    "FrappeCustomerBotMeasurementsPdfAdapter",
    "PDF_TIMEOUT_SEC",
]
