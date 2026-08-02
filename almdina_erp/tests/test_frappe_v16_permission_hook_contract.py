from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

from almdina_erp import permissions


def test_broad_scope_document_hooks_return_explicit_true() -> None:
    order = SimpleNamespace(name="DCO-TEST")
    stage = SimpleNamespace(assigned_to="other@example.com")

    with patch.object(permissions, "_requires_assigned_scope", return_value=False):
        assert permissions.door_cutting_order_has_permission(
            order,
            user="order@example.com",
            permission_type="read",
        ) is True
        assert permissions.door_cutting_order_has_permission(
            order,
            user="order@example.com",
            permission_type="write",
        ) is True
        assert permissions.production_stage_has_permission(
            stage,
            user="order@example.com",
            permission_type="read",
        ) is True


def test_assigned_scope_still_denies_unassigned_documents() -> None:
    order = SimpleNamespace(name="DCO-TEST")

    with (
        patch.object(permissions, "_requires_assigned_scope", return_value=True),
        patch.object(permissions, "_assigned_order_exists", return_value=False),
    ):
        assert permissions.door_cutting_order_has_permission(
            order,
            user="worker@example.com",
            permission_type="read",
        ) is False


def test_guest_read_is_denied_explicitly() -> None:
    order = SimpleNamespace(name="DCO-TEST")

    assert permissions.door_cutting_order_has_permission(
        order,
        user="Guest",
        permission_type="read",
    ) is False
