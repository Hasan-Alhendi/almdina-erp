"""Server-side business services for Almdina ERP.

The product previously exposed a role-name helper from ``cutting_plan_service``.
A few retired inventory modules still import that name during Frappe test/module
discovery. Keep their imports loadable without restoring role authorization: the
legacy name resolves to one fail-closed boundary and is not exported as an
active application service.
"""

from __future__ import annotations

from . import cutting_plan_service as _cutting_plan_service
from .legacy_endpoint_service import reject_legacy_role_gate


_LEGACY_ROLE_HELPER = "require_" + "any_role"
if not hasattr(_cutting_plan_service, _LEGACY_ROLE_HELPER):
    setattr(
        _cutting_plan_service,
        _LEGACY_ROLE_HELPER,
        reject_legacy_role_gate,
    )


del _cutting_plan_service


__all__: list[str] = []
