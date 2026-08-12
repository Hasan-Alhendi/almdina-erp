from __future__ import annotations


ALMDINA_APP = "almdina_erp"
ALMDINA_WORKSPACE = "Almdina ERP"


def is_almdina_user(default_app: str | None) -> bool:
    """Return whether a Frappe system user has been adopted into Almdina scope."""

    return str(default_app or "").strip() == ALMDINA_APP


__all__ = ["ALMDINA_APP", "ALMDINA_WORKSPACE", "is_almdina_user"]
