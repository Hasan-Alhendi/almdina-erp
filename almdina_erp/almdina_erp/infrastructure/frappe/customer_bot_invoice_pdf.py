"""Customer-bot adapter for the existing customer-invoice PDF renderer.

The adapter only renders. It does not create a WhatsApp session, send a file,
write a File record, or return a server path.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from almdina_erp.almdina_erp.infrastructure.whatsapp.frappe_adapters import (
    FrappeInvoicePdfAdapter,
)


class FrappeCustomerBotInvoicePdfAdapter:
    def __init__(self, renderer: FrappeInvoicePdfAdapter | None = None) -> None:
        self._renderer = renderer or FrappeInvoicePdfAdapter()

    def render(self, order_name: str, invoice_payload: Mapping[str, Any]) -> bytes:
        return self._renderer.render_invoice_pdf(order_name, invoice_payload)


__all__ = ["FrappeCustomerBotInvoicePdfAdapter"]
