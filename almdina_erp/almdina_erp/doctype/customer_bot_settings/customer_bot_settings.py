from __future__ import annotations

from frappe.model.document import Document

from almdina_erp.almdina_erp.infrastructure.frappe.customer_bot_settings_records import (
    reject_direct_customer_bot_settings_mutation,
)


class CustomerBotSettings(Document):
    def validate(self) -> None:
        reject_direct_customer_bot_settings_mutation(self)

    def on_trash(self) -> None:
        reject_direct_customer_bot_settings_mutation(self)
