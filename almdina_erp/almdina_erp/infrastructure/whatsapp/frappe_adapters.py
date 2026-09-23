from __future__ import annotations

import frappe

from almdina_erp.almdina_erp.application.whatsapp.errors import WhatsAppError
from almdina_erp.almdina_erp.infrastructure.printing.measurements_print_document import (
    PRINT_IDENTITY_DEFAULTS,
    as_mapping,
    customer_invoice_print_html,
    measurements_print_html,
    order_print_payload,
)
from almdina_erp.almdina_erp.infrastructure.whatsapp.measurement_pdf import (
    PDF_FAILED_MESSAGE,
    html_to_pdf_bytes,
)

INVOICE_PDF_FAILED_MESSAGE = "تعذر إنشاء ملف PDF لفاتورة الزبون."


def _chromium_executable() -> str:
    from frappe.utils.print_utils import find_or_download_chromium_executable

    return str(find_or_download_chromium_executable() or "").strip()


def _print_identity() -> dict[str, str]:
    try:
        settings = frappe.get_single("Almdina ERP Settings")
    except Exception:
        return dict(PRINT_IDENTITY_DEFAULTS)
    values: dict[str, str] = {}
    for fieldname, default in PRINT_IDENTITY_DEFAULTS.items():
        stored = str(settings.get(fieldname) or "").strip()
        values[fieldname] = stored or default
    return values


def _html_to_pdf(html: str) -> bytes:
    def fallback(markup: str) -> bytes:
        from frappe.utils.pdf import get_pdf

        return bytes(get_pdf(markup) or b"")

    try:
        chromium_path = _chromium_executable()
    except Exception:
        chromium_path = ""
    return html_to_pdf_bytes(
        html,
        chromium_path=chromium_path,
        fallback=fallback,
    )


def _customer_phone(order_name: str) -> str:
    customer = frappe.db.get_value("Door Cutting Order", order_name, "customer")
    if not customer:
        return ""
    return str(frappe.db.get_value("Customer", customer, "mobile_no") or "").strip()


class FrappeMeasurementPdfAdapter:
    def render_measurements_pdf(self, order_name: str) -> bytes:
        try:
            order = frappe.get_doc("Door Cutting Order", order_name)
            phone = _customer_phone(order_name)
            html = measurements_print_html(
                order_print_payload(order),
                identity=_print_identity(),
                customer_phone=phone,
                printed_on=str(frappe.utils.now_datetime() or ""),
            )
            if not str(html or "").strip():
                raise WhatsAppError("pdf_failed", PDF_FAILED_MESSAGE)
            return _html_to_pdf(html)
        except WhatsAppError:
            raise
        except Exception as error:
            frappe.log_error(title="WhatsApp measurements PDF failed")
            raise WhatsAppError("pdf_failed", PDF_FAILED_MESSAGE) from error


class FrappeInvoicePdfAdapter:
    def render_invoice_pdf(
        self,
        order_name: str,
        invoice_payload: object = None,
    ) -> bytes:
        try:
            payload = as_mapping(invoice_payload) if invoice_payload is not None else {}
            if str(payload.get("kind") or "") != "customer_invoice":
                raise WhatsAppError("pdf_failed", INVOICE_PDF_FAILED_MESSAGE)
            order = frappe.get_doc("Door Cutting Order", order_name)
            phone = _customer_phone(order_name)
            html = customer_invoice_print_html(
                order_print_payload(order),
                payload,
                identity=_print_identity(),
                customer_phone=phone,
                printed_on=str(frappe.utils.now_datetime() or ""),
            )
            if not str(html or "").strip() or "quote-details" not in html:
                raise WhatsAppError("pdf_failed", INVOICE_PDF_FAILED_MESSAGE)
            return _html_to_pdf(html)
        except WhatsAppError:
            raise
        except frappe.ValidationError:
            raise
        except Exception as error:
            frappe.log_error(title="WhatsApp customer invoice PDF failed")
            raise WhatsAppError("pdf_failed", INVOICE_PDF_FAILED_MESSAGE) from error


class FrappeCustomerPhoneAdapter:
    def get_customer_phone(self, order_name: str) -> str:
        return _customer_phone(order_name)


__all__ = [
    "FrappeCustomerPhoneAdapter",
    "FrappeInvoicePdfAdapter",
    "FrappeMeasurementPdfAdapter",
]
