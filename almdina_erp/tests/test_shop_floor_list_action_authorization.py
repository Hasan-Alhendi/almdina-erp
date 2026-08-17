from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REPOSITORY = (
    ROOT
    / "almdina_erp"
    / "infrastructure"
    / "frappe"
    / "shop_floor_query_repository.py"
)
AUTHORIZATION = (
    ROOT
    / "almdina_erp"
    / "infrastructure"
    / "frappe"
    / "authorization_gateway.py"
)
LIST_VIEW = (
    ROOT
    / "public"
    / "js"
    / "door_cutting_order"
    / "list_view"
    / "door_cutting_order_list.js"
)
QUICK_ACTIONS = ROOT / "public" / "js" / "shop_floor_quick_actions.js"


def source(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_shop_floor_summary_rows_resolve_to_real_order_before_capability_checks() -> None:
    repository = source(REPOSITORY)
    authorization = source(AUTHORIZATION)

    # get_all list projections do not carry DocType identity. The repository
    # adapter must therefore restore a genuine Door Cutting Order before entering
    # the document-scoped authorization gateway.
    assert '_ORDER_DOCTYPE = "Door Cutting Order"' in repository
    assert "def _order_document(order: Any) -> Any | None:" in repository
    assert "document = frappe.get_doc(_ORDER_DOCTYPE, name)" in repository
    assert "document = _order_document(order)" in repository
    assert "document_has_capability(document, capability)" in repository
    assert "document_has_capability(order, capability)" not in repository

    # Keep the gateway strict: this regression must never be solved by accepting
    # an untyped projection as if it were a transactional document.
    assert 'getattr(document, "doctype", None) != definition.applies_to' in authorization


def test_order_document_bridge_is_request_local_and_reused_for_native_visibility() -> None:
    repository = source(REPOSITORY)

    assert '_ORDER_DOCUMENT_CACHE_KEY = "almdina_shop_floor_order_documents"' in repository
    assert "getattr(frappe.local, _ORDER_DOCUMENT_CACHE_KEY, None)" in repository
    assert "setattr(frappe.local, _ORDER_DOCUMENT_CACHE_KEY, cache)" in repository
    assert "cache[name] = document" in repository
    assert "name = _order_name(order)" in repository
    assert "permissions.worker_can_view_order(user, name)" in repository
    assert 'frappe.has_permission(document, "read", user=user)' in repository


def test_mobile_actions_still_render_only_from_server_authorized_flags() -> None:
    list_view = source(LIST_VIEW)
    quick_actions = source(QUICK_ACTIONS)

    assert "canStart: authorized.canStart === true" in list_view
    assert "canHandoff: authorized.canHandoff === true" in list_view
    assert "if (context && context.canStart === true)" in quick_actions
    assert "if (context && context.canHandoff === true)" in quick_actions
    assert "if (model.action)" in list_view

    # Do not add a visual fallback that exposes a button merely from card state.
    assert 'state.key === "ready" ?' not in list_view
    assert 'state.key === "progress" ?' not in list_view
