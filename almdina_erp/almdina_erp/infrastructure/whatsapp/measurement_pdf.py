from __future__ import annotations

from collections.abc import Callable, Sequence
from pathlib import Path
import subprocess
import tempfile

from almdina_erp.almdina_erp.application.whatsapp.errors import WhatsAppError


PDF_FAILED_MESSAGE = "تعذر إنشاء ملف PDF لجدول القياسات. أعد المحاولة أو راجع سجل الخادم."
CHROMIUM_PRINT_TIMEOUT_SEC = 30


def html_to_pdf_via_chromium(
    html: str,
    *,
    chromium_path: str,
    runner: Callable[..., object] | None = None,
    timeout_sec: float = CHROMIUM_PRINT_TIMEOUT_SEC,
) -> bytes:
    executable = str(chromium_path or "").strip()
    markup = str(html or "").strip()
    if not executable or not markup:
        raise WhatsAppError("pdf_failed", PDF_FAILED_MESSAGE)
    run = runner or subprocess.run
    with tempfile.TemporaryDirectory(prefix="almdina-wa-pdf-") as folder:
        root = Path(folder)
        html_path = root / "measurements.html"
        pdf_path = root / "measurements.pdf"
        profile = root / "profile"
        profile.mkdir()
        html_path.write_text(markup, encoding="utf-8")
        command: Sequence[str] = (
            executable,
            "--headless",
            "--disable-gpu",
            "--no-sandbox",
            "--disable-dev-shm-usage",
            "--no-first-run",
            "--no-pdf-header-footer",
            f"--user-data-dir={profile}",
            f"--print-to-pdf={pdf_path}",
            html_path.resolve().as_uri(),
        )
        try:
            result = run(
                list(command),
                capture_output=True,
                timeout=timeout_sec,
                check=False,
            )
        except Exception as error:
            raise WhatsAppError("pdf_failed", PDF_FAILED_MESSAGE) from error
        code = getattr(result, "returncode", 1)
        if code not in (0, None) or not pdf_path.is_file():
            raise WhatsAppError("pdf_failed", PDF_FAILED_MESSAGE)
        data = pdf_path.read_bytes()
        if not data.startswith(b"%PDF"):
            raise WhatsAppError("pdf_failed", PDF_FAILED_MESSAGE)
        return data


def html_to_pdf_bytes(
    html: str,
    *,
    chromium_path: str = "",
    runner: Callable[..., object] | None = None,
    fallback: Callable[[str], bytes] | None = None,
) -> bytes:
    markup = str(html or "").strip()
    if not markup:
        raise WhatsAppError("pdf_failed", PDF_FAILED_MESSAGE)
    last_error: BaseException | None = None
    try:
        return html_to_pdf_via_chromium(
            markup,
            chromium_path=chromium_path,
            runner=runner,
        )
    except Exception as error:
        last_error = error
    if fallback is not None:
        try:
            content = fallback(markup)
            if content:
                return bytes(content)
        except Exception as error:
            last_error = error
    raise WhatsAppError("pdf_failed", PDF_FAILED_MESSAGE) from last_error


__all__ = [
    "CHROMIUM_PRINT_TIMEOUT_SEC",
    "PDF_FAILED_MESSAGE",
    "html_to_pdf_bytes",
    "html_to_pdf_via_chromium",
]
