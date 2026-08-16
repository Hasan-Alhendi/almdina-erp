"""Retired historical order-creation module.

Native Door Cutting Order creation is owned by Frappe's DocType flow. The two
historical RPC names that used to live in this module remain intentionally
registered in ``override_whitelisted_methods`` and fail closed through
``legacy_endpoint_service.retired_product_endpoint``.

No runtime code may import this module or place order-creation business logic
here again.
"""

__all__: list[str] = []
