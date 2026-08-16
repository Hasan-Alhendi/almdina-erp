from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SHOP_FLOOR_UX = (
    ROOT
    / "public"
    / "js"
    / "door_cutting_order"
    / "production"
    / "shop_floor_order_ux.js"
)
LIFECYCLE_UX = ROOT / "public" / "js" / "door_cutting_order" / "core" / "order_lifecycle.js"
PLAN_SERVICE = ROOT / "almdina_erp" / "services" / "cutting_plan_snapshot_service.py"
DRAWING_APPROVAL_SERVICE = (
    ROOT / "almdina_erp" / "services" / "drawing_approval_service.py"
)
DRAWING_APPROVAL_POLICY = (
    ROOT / "almdina_erp" / "application" / "security" / "drawing_approval_policy.py"
)
SHOP_FLOOR_COMMANDS = (
    ROOT / "almdina_erp" / "application" / "shop_floor" / "commands.py"
)
PRODUCTION_POLICY = (
    ROOT / "almdina_erp" / "domain" / "orders" / "production_authorization.py"
)
DRAWING_APPROVAL_UX = (
    ROOT
    / "public"
    / "js"
    / "door_cutting_order"
    / "cutting_plan"
    / "door_cutting_order_drawing_approval_ux.js"
)


def _source(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_order_creator_dispatches_directly_without_approval_or_plan_lock():
    shop_floor = _source(SHOP_FLOOR_UX)
    lifecycle = _source(LIFECYCLE_UX)

    assert "function openDispatchDialog(frm)" in shop_floor
    assert 'can(frm, "dispatch_order")' in shop_floor
    assert 'frm.add_custom_button(__("إرسال للإنتاج"), () => openDispatchDialog(frm));' in shop_floor
    assert "get_dispatch_options" in shop_floor
    assert "dispatch_order" in shop_floor
    assert "approve_order" not in shop_floor
    assert "lock_cutting_plan" not in shop_floor

    # Returning to Draft remains a separate lifecycle action and is not coupled
    # to the production dispatch presenter.
    assert "return_to_draft" in lifecycle
    assert "return_order_to_draft" in lifecycle


def test_dispatch_uses_capability_and_calculated_plan_policy():
    shop_floor = _source(SHOP_FLOOR_COMMANDS)
    policy = _source(PRODUCTION_POLICY)
    dispatch = shop_floor.split("def dispatch_order", 1)[1].split(
        "def start_my_stage", 1
    )[0]

    assert "Capability.DISPATCH_ORDER" in dispatch
    assert "_assert_action_allowed" in dispatch
    assert "can_dispatch_from_status(facts.order_status)" in policy
    assert "facts.has_cutting_plan" in policy
    assert "facts.plan_needs_recalculation" in policy
    assert '"already_dispatched"' in policy


def test_review_and_order_approval_are_retired_in_favor_of_direct_dispatch():
    lifecycle_ux = _source(LIFECYCLE_UX)
    shop_floor_ux = _source(SHOP_FLOOR_UX)
    permissions = _source(
        ROOT / "almdina_erp" / "application" / "orders" / "lifecycle_permissions.py"
    )
    domain = _source(ROOT / "almdina_erp" / "domain" / "orders" / "lifecycle.py")

    # Form never installs the retired review/approve buttons.
    install = lifecycle_ux.split("function installButtons(frm, context)", 1)[1].split(
        "function loadContext", 1
    )[0]
    assert "submit_for_review" not in install
    assert 'LABELS.approve' not in install
    assert "return_to_draft" in install

    # Domain + UI both allow draft (and leftover review) to go to production.
    assert '"Pending Review"' in domain.split("DISPATCHABLE_ORDER_STATUSES", 1)[1].split(
        "PRE_PRODUCTION_ORDER_STATUSES", 1
    )[0]
    assert "DISPATCHABLE_STATUSES" in shop_floor_ux
    assert '"Draft"' in shop_floor_ux.split("const DISPATCHABLE_STATUSES", 1)[1].split(
        "function addDispatchButton", 1
    )[0]
    assert 'status !== "Approved"' not in shop_floor_ux
    # Direct toolbar button — never nested under «صالة الإنتاج».
    dispatch_btn = shop_floor_ux.split("function addDispatchButton", 1)[1].split(
        "function revertTargetsKey", 1
    )[0]
    assert 'frm.add_custom_button(__("إرسال للإنتاج"), () => openDispatchDialog(frm));' in dispatch_btn
    assert "PRODUCTION_ACTION_GROUP" not in dispatch_btn

    assert "إرسال الطلب للمراجعة أُلغي" in permissions
    assert "اعتماد الطلب أُلغي" in permissions


def test_role_managed_drawing_approval_preserves_shop_floor_status():
    plan_service = _source(PLAN_SERVICE)
    approval_service = _source(DRAWING_APPROVAL_SERVICE)
    policy = _source(DRAWING_APPROVAL_POLICY)
    lock_impl = plan_service.split("def lock_order_for_production", 1)[1].split(
        "\n\n__all__", 1
    )[0]

    assert "Capability.APPROVE_DXF" in approval_service
    assert "require_document_capability" in approval_service
    assert "require_stage_operational_access" in approval_service
    assert "current_assignee" not in policy
    assert "session_user" not in policy
    assert "approval_warning" in policy
    assert "preserve_status=True" in approval_service
    assert "was_previously_approved" in approval_service
    assert "if preserve_status:" in lock_impl
    assert '"status": "Approved"' in lock_impl
    assert "require_any_role" not in approval_service


def test_drawing_form_exposes_reapproval_with_warning():
    ux = _source(DRAWING_APPROVAL_UX)
    assert 'permissions.canDocument(frm, "approve_dxf")' in ux
    assert 'const APPROVE_LABEL = __("اعتماد الرسم")' in ux
    assert 'const REAPPROVE_LABEL = __("إعادة اعتماد الرسم")' in ux
    assert "approve_production_dxf" in ux
    assert "plan_source: source" in ux
    assert "تم اعتماد خطة لهذا الطلب سابقًا" in ux
    assert "current_assignee" not in ux
    assert "isAssignedToCurrentUser" not in ux
    assert "lock_cutting_plan" not in ux
    assert "frm.add_custom_button" not in ux
