from __future__ import annotations

from typing import Any

import frappe
from frappe import _
from frappe.utils import cint

from almdina_erp.almdina_erp.application.whatsapp.errors import (
    WhatsAppError,
    WhatsAppTransportError,
)
from almdina_erp.almdina_erp.application.whatsapp.send_invoice import (
    send_order_invoice as deliver_order_invoice,
)
from almdina_erp.almdina_erp.application.whatsapp.send_measurements import (
    send_order_measurements as deliver_order_measurements,
)
from almdina_erp.almdina_erp.application.whatsapp.send_stage_completion import (
    send_stage_completion as deliver_stage_completion,
)
from almdina_erp.almdina_erp.application.whatsapp.sessions import (
    create_and_start_factory_session,
    delivery_status,
    get_factory_session,
    get_session_qr,
    reconnect_factory_session,
    session_snapshot,
    stop_factory_session,
)
from almdina_erp.almdina_erp.domain.security.authorization import Capability
from almdina_erp.almdina_erp.infrastructure.frappe.authorization_gateway import (
    require_any_doctype_capability,
    require_doctype_capability,
    require_document_capability,
)
from almdina_erp.almdina_erp.infrastructure.whatsapp.config import load_openwa_config
from almdina_erp.almdina_erp.infrastructure.whatsapp.frappe_adapters import (
    FrappeCustomerPhoneAdapter,
    FrappeInvoicePdfAdapter,
    FrappeMeasurementPdfAdapter,
)
from almdina_erp.almdina_erp.services.cost_document_service import (
    customer_invoice_payload_for_order,
)
from almdina_erp.almdina_erp.services.production_settings_service import (
    whatsapp_message_templates,
    whatsapp_stage_message_template,
)
from almdina_erp.almdina_erp.infrastructure.whatsapp.openwa_client import OpenWAClient


def _require_whatsapp_session() -> None:
    require_doctype_capability(Capability.MANAGE_WHATSAPP_SESSION)


def _authorized_order(order_name: object, capability: str, missing_message: str):
    name = str(order_name or "").strip()
    if not name:
        frappe.throw(_(missing_message), frappe.ValidationError)
    try:
        order = frappe.get_doc("Door Cutting Order", name)
    except frappe.DoesNotExistError:
        frappe.throw(_("الطلب غير موجود."), frappe.DoesNotExistError)
    require_document_capability(order, capability)
    return order


def _client() -> OpenWAClient:
    config = load_openwa_config()
    if not config.configured:
        raise WhatsAppError(
            "not_configured",
            "لم يتم ضبط عنوان خادم WhatsApp أو مفتاح API.",
        )
    return OpenWAClient(config)


def _throw(error: Exception) -> None:
    if isinstance(error, WhatsAppError):
        exception = (
            frappe.PermissionError
            if error.code == "missing_capability"
            else frappe.ValidationError
        )
        frappe.throw(_(str(error)), exception)
    if isinstance(error, WhatsAppTransportError):
        frappe.throw(_(str(error)))
    raise error


@frappe.whitelist()
def get_whatsapp_session() -> dict[str, Any]:
    _require_whatsapp_session()
    config = load_openwa_config()
    if not config.configured:
        return session_snapshot(None, configured=False)
    try:
        return session_snapshot(get_factory_session(OpenWAClient(config)))
    except (WhatsAppError, WhatsAppTransportError) as error:
        _throw(error)
        raise AssertionError("frappe.throw must interrupt execution")


@frappe.whitelist()
def get_whatsapp_delivery_status() -> dict[str, Any]:
    require_any_doctype_capability(
        (Capability.PRINT_MEASUREMENTS, Capability.PRINT_CUSTOMER_INVOICE)
    )
    config = load_openwa_config()
    if not config.configured:
        snapshot = session_snapshot(None, configured=False)
        return {
            "configured": False,
            "working": False,
            "code": snapshot["code"],
            "reason": snapshot["reason"],
        }
    try:
        return dict(delivery_status(OpenWAClient(config)))
    except (WhatsAppError, WhatsAppTransportError) as error:
        _throw(error)
        raise AssertionError("frappe.throw must interrupt execution")


@frappe.whitelist()
def create_whatsapp_session() -> dict[str, Any]:
    _require_whatsapp_session()
    try:
        session = create_and_start_factory_session(_client())
    except (WhatsAppError, WhatsAppTransportError) as error:
        _throw(error)
        raise AssertionError("frappe.throw must interrupt execution")
    return session_snapshot(session)


@frappe.whitelist()
def reconnect_whatsapp_session() -> dict[str, Any]:
    _require_whatsapp_session()
    try:
        session = reconnect_factory_session(_client())
    except (WhatsAppError, WhatsAppTransportError) as error:
        _throw(error)
        raise AssertionError("frappe.throw must interrupt execution")
    return session_snapshot(session)


@frappe.whitelist()
def stop_whatsapp_session() -> dict[str, Any]:
    _require_whatsapp_session()
    try:
        session = stop_factory_session(_client())
    except (WhatsAppError, WhatsAppTransportError) as error:
        _throw(error)
        raise AssertionError("frappe.throw must interrupt execution")
    return session_snapshot(session)


@frappe.whitelist()
def get_whatsapp_qr() -> dict[str, Any]:
    _require_whatsapp_session()
    try:
        return get_session_qr(_client())
    except (WhatsAppError, WhatsAppTransportError) as error:
        _throw(error)
        raise AssertionError("frappe.throw must interrupt execution")


def _send_result(result) -> dict[str, Any]:
    return {
        "ok": result.ok,
        "code": result.code,
        "message": result.message,
        "order_name": result.order_name,
        "chat_id": result.chat_id,
        "text_sent": result.text_sent,
        "document_sent": result.document_sent,
        "text_message_id": result.text_message_id,
        "document_message_id": result.document_message_id,
    }


@frappe.whitelist()
def send_order_measurements(order_name: str, amendment: int | str | bool = 0) -> dict[str, Any]:
    order = _authorized_order(
        order_name,
        Capability.PRINT_MEASUREMENTS,
        "تعذر تحديد الطلب لإرسال القياسات.",
    )
    templates = whatsapp_message_templates()
    template_key = (
        "whatsapp_measurement_amendments_text"
        if cint(amendment)
        else "whatsapp_measurements_text"
    )
    try:
        result = deliver_order_measurements(
            _client(),
            FrappeMeasurementPdfAdapter(),
            FrappeCustomerPhoneAdapter(),
            order.name,
            text_template=templates[template_key],
        )
    except (WhatsAppError, WhatsAppTransportError) as error:
        _throw(error)
        raise AssertionError("frappe.throw must interrupt execution")
    return _send_result(result)


@frappe.whitelist()
def send_order_invoice(order_name: str) -> dict[str, Any]:
    order = _authorized_order(
        order_name,
        Capability.PRINT_CUSTOMER_INVOICE,
        "تعذر تحديد الطلب لإرسال الفاتورة.",
    )
    try:
        payload = customer_invoice_payload_for_order(order)
        result = deliver_order_invoice(
            _client(),
            FrappeInvoicePdfAdapter(),
            FrappeCustomerPhoneAdapter(),
            order.name,
            payload,
            text_template=whatsapp_message_templates()["whatsapp_invoice_text"],
        )
    except (WhatsAppError, WhatsAppTransportError) as error:
        _throw(error)
        raise AssertionError("frappe.throw must interrupt execution")
    return _send_result(result)


def notify_stage_completion(
    order_name: object,
    stage_type: object,
    stage_label: object,
) -> dict[str, Any]:
    """Best-effort customer text after a stage handoff. Never raises."""

    config = load_openwa_config()
    if not config.configured:
        return {
            "ok": False,
            "code": "not_configured",
            "message": "لم يتم ضبط عنوان خادم WhatsApp أو مفتاح API.",
        }
    try:
        result = deliver_stage_completion(
            OpenWAClient(config),
            FrappeCustomerPhoneAdapter(),
            order_name,
            stage_label,
            text_template=whatsapp_stage_message_template(stage_type),
        )
    except (WhatsAppError, WhatsAppTransportError) as error:
        return {
            "ok": False,
            "code": getattr(error, "code", "failed"),
            "message": str(error),
        }
    return {
        "ok": result.ok,
        "code": result.code,
        "message": result.message,
        "order_name": result.order_name,
        "chat_id": result.chat_id,
        "text_message_id": result.text_message_id,
    }


__all__ = [
    "create_whatsapp_session",
    "get_whatsapp_delivery_status",
    "get_whatsapp_qr",
    "get_whatsapp_session",
    "notify_stage_completion",
    "reconnect_whatsapp_session",
    "send_order_invoice",
    "send_order_measurements",
    "stop_whatsapp_session",
]
