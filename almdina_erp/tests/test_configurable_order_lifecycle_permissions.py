from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
AUTHORIZATION = ROOT / "almdina_erp" / "domain" / "security" / "authorization.py"
POLICY = ROOT / "almdina_erp" / "application" / "orders" / "lifecycle_permissions.py"
CONTEXT_SERVICE = ROOT / "almdina_erp" / "services" / "order_lifecycle_permission_service.py"
APPROVAL_SERVICE = ROOT / "almdina_erp" / "services" / "order_approval_service.py"
CANCEL_SERVICE = ROOT / "almdina_erp" / "services" / "order_lifecycle_service.py"
REVISION_SERVICE = ROOT / "almdina_erp" / "services" / "order_revision_service.py"
LIFECYCLE_UX = ROOT / "public" / "js" / "order_lifecycle.js"
REVISION_UX = ROOT / "public" / "js" / "door_cutting_order_revision_ux.js"
HOOKS = ROOT / "hooks.py"


def source(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_lifecycle_capabilities_are_assignable_permission_types():
    authorization = source(AUTHORIZATION)
    for capability in (
        "create_order_revision",
        "submit_order",
        "approve_order",
        "cancel_order",
        "return_order_to_draft",
    ):
        assert capability in authorization


def test_server_actions_use_one_lifecycle_policy_without_role_names():
    context_service = source(CONTEXT_SERVICE)
    approval_service = source(APPROVAL_SERVICE)
    cancel_service = source(CANCEL_SERVICE)
    revision_service = source(REVISION_SERVICE)

    assert "build_lifecycle_context" in context_service
    assert "require_lifecycle_action" in context_service
    assert "document_has_capability" in context_service
    assert "OrderLifecycleAction.APPROVE" in approval_service
    assert "OrderLifecycleAction.CANCEL" in cancel_service
    assert "OrderLifecycleAction.RETURN_TO_DRAFT" in cancel_service
    assert '"in_place": True' in cancel_service
    assert "Capability.CREATE_ORDER_REVISION" in revision_service
    assert "order_lifecycle_service" in revision_service.split(
        "def return_order_to_draft", 1
    )[1]
    assert "Capability.EDIT_ORDER" not in revision_service.split("def create_order_revision", 1)[1].split(
        "def return_order_to_draft", 1
    )[0]

    combined = "\n".join(
        (context_service, approval_service, cancel_service, revision_service)
    )
    assert "require_any_role" not in combined
    assert "Production Manager" not in combined
    assert "Order Entry" not in combined
    assert "System Manager" not in combined


def test_lifecycle_ui_is_capability_driven_and_fail_closed():
    lifecycle_ux = source(LIFECYCLE_UX)
    revision_ux = source(REVISION_UX)
    lifecycle_policy = source(POLICY)
    context_service = source(CONTEXT_SERVICE)

    assert "get_order_lifecycle_context" in lifecycle_ux
    assert 'can(frm, "create_order")' in lifecycle_ux
    assert 'can(frm, "edit_order")' in lifecycle_ux
    assert "function canReturnToDraft(frm, context)" in lifecycle_ux
    assert 'return actionAllowed(context, "return_to_draft");' in lifecycle_ux
    assert "context.actions[action].allowed === true" in lifecycle_ux
    assert (
        "OrderLifecycleAction.RETURN_TO_DRAFT: Capability.RETURN_ORDER_TO_DRAFT"
        in lifecycle_policy
    )
    assert "document_has_capability(order, capability)" in context_service
    assert "documentContext().capture(frm)" in lifecycle_ux
    assert "documentContext().isCurrent(frm, identity)" in lifecycle_ux
    assert "removeLifecycleButtons(frm)" in lifecycle_ux
    assert "Failed to load order lifecycle permissions" in lifecycle_ux
    assert 'can(frm, "create_order_revision")' in revision_ux
    assert 'can(frm, "edit_order")' in revision_ux
    assert "canOfferEditSession" in revision_ux
    assert "__almdina_edit_session" in revision_ux

    combined = lifecycle_ux + revision_ux
    assert "frappe.user_roles" not in combined
    assert "hasRole(" not in combined
    assert "Production Manager" not in combined
    assert "Order Entry" not in combined
    assert "System Manager" not in combined


def test_return_and_revert_are_capability_only_without_status_gates():
    lifecycle_policy = source(POLICY)
    lifecycle_service = source(CANCEL_SERVICE)
    lifecycle_ux = source(LIFECYCLE_UX)
    context_service = source(CONTEXT_SERVICE)
    shop_floor = (ROOT / "public" / "js" / "shop_floor_order_ux.js").read_text(
        encoding="utf-8"
    )
    production_auth = (
        ROOT / "almdina_erp" / "domain" / "orders" / "production_authorization.py"
    ).read_text(encoding="utf-8")
    domain_lifecycle = (
        ROOT / "almdina_erp" / "domain" / "orders" / "lifecycle.py"
    ).read_text(encoding="utf-8")

    return_reason = lifecycle_policy.split(
        "if action == OrderLifecycleAction.RETURN_TO_DRAFT:", 1
    )[1].split("if action == OrderLifecycleAction.CANCEL:", 1)[0]
    assert "can_return_to_draft" not in return_reason
    assert "Capability alone authorizes return-to-draft" in return_reason

    return_fn = lifecycle_service.split("def return_order_to_draft", 1)[1]
    assert "Cutting is already completed" not in return_fn
    assert '"noop": True' in return_fn

    assert (
        "OrderLifecycleAction.RETURN_TO_DRAFT: Capability.RETURN_ORDER_TO_DRAFT"
        in lifecycle_policy
    )
    assert "document_has_capability(order, capability)" in context_service
    assert "function canReturnToDraft(frm, context)" in lifecycle_ux
    assert 'return actionAllowed(context, "return_to_draft");' in lifecycle_ux
    # Standalone toolbar button — not nested under «دورة الطلب».
    install = lifecycle_ux.split("function installButtons(frm, context)", 1)[1].split(
        "function loadContext", 1
    )[0]
    assert "LABELS.return_to_draft" in install
    assert "ACTION_GROUP" not in install.split("LABELS.return_to_draft", 1)[1].split(
        "if (actionAllowed(context, \"cancel\"))", 1
    )[0]
    assert 'can(frm, "revert_department")' in shop_floor
    revert_btn = shop_floor.split("function addRevertButton", 1)[1].split(
        "function addDeliveryButtons", 1
    )[0]
    assert 'frm.add_custom_button(__("إرجاع لمرحلة سابقة"), () => openRevertDialog(frm));' in revert_btn
    assert "PRODUCTION_ACTION_GROUP" not in revert_btn
    assert 'frm.doc.production_path && status !== "Delivered" && can(frm, "revert_department")' not in shop_floor
    assert "Capability alone authorizes revert" in production_auth
    assert "capability-gated, not status-gated" in domain_lifecycle
    assert "capability-gated; status/path do not authorize" in domain_lifecycle


def test_legacy_return_routes_use_dedicated_capability_endpoint():
    hooks = source(HOOKS)
    expected = (
        '"almdina_erp.almdina_erp.services.order_revision_service.return_order_to_draft"'
    )
    assert hooks.count(expected) == 2
    assert (
        '"almdina_erp.almdina_erp.services.order_revision_service.create_order_revision"'
        not in hooks.split("override_whitelisted_methods", 1)[1]
    )


def test_policy_layer_is_framework_independent():
    policy = source(POLICY)
    assert "import frappe" not in policy
    assert "frappe." not in policy
