from __future__ import annotations

from pathlib import Path


APP_ROOT = Path(__file__).resolve().parents[1]
PUBLIC_JS = APP_ROOT / "public" / "js"
DCO_LIST_JS = (
    PUBLIC_JS
    / "door_cutting_order"
    / "list_view"
    / "door_cutting_order_list.js"
)


def _read_js(name: str) -> str:
    return (PUBLIC_JS / name).read_text(encoding="utf-8")


def test_arabic_runtime_localization_is_batched_without_losing_dynamic_support():
    js = _read_js("arabic_operator_ui.js")

    # Keep the Arabic fallback layer available for dynamic/legacy labels, but do
    # not attach it to documentElement where every Desk mutation wakes it up.
    assert "observer.observe(document.documentElement" not in js
    assert "observer.observe(document.body, { childList: true, subtree: true })" in js
    assert "requestAnimationFrame" in js
    assert "pendingRoots" in js
    assert "mutation.addedNodes.forEach(queueNode)" in js

    # Regression guard: important Arabic operator fallbacks remain present.
    required_labels = [
        "إدارة المعمل",
        "طلبات قص الدرف",
        "التشغيل اليومي للمعمل",
        "ترتيب المستطيلات - أفضل ضلع قصير",
        "راوتر CNC",
        "منشار ألواح",
    ]
    for label in required_labels:
        assert label in js, label


def test_permission_visibility_guard_is_route_scoped_and_transient():
    js = _read_js("permission_action_visibility_guard.js")

    # The UI guard is not authorization. It only needs to settle relevant
    # Almdina workspace/workforce surfaces and then disconnect.
    assert "TRANSIENT_OBSERVER_MS" in js
    assert "function surfaceMode()" in js
    assert 'if (ALMDINA_WORKSPACE_ROUTES.has(state.route)) return "workspace";' in js
    assert 'state.kind === "workspace" ||' not in js
    assert "function startTransientObserver()" in js
    assert "observerStopTimer = window.setTimeout(disconnectObserver, TRANSIENT_OBSERVER_MS)" in js
    assert '[100, 300, 800, 1600].forEach' not in js

    # Preserve the existing capability/surface decisions.
    assert 'surfaceAllowed(surface)' in js
    assert 'can("create_users")' in js
    assert 'window.addEventListener("almdina:permissions-updated", refreshSurface)' in js


def test_permission_visibility_guard_only_runs_full_scan_on_relevant_surface_entry():
    js = _read_js("permission_action_visibility_guard.js")

    assert 'if (mode === "none") return;' in js
    assert "applyRoot(document);" in js
    assert "roots.forEach(applyRoot);" in js
    assert "requestAnimationFrame" in js


def test_shared_shell_scans_are_batched_and_stop_after_navigation_settles():
    js = _read_js("shared_shell.js")

    assert "NAVIGATION_SETTLE_MS" in js
    assert "function startNavigationSettleWindow()" in js
    assert "function stopNavigationSettleWindow()" in js
    assert "navigationObserverStopTimer = window.setTimeout(stopNavigationSettleWindow, NAVIGATION_SETTLE_MS)" in js
    assert "roots.forEach(hideUnauthorizedShortcuts);" in js
    assert "requestAnimationFrame" in js

    # Regression guard against the old permanent/full-document retry loops.
    assert "function observeDeskMutations()" not in js
    assert "function schedulePermissionScan()" not in js
    assert "[100, 300, 800].forEach" not in js
    assert "[100, 300, 900, 1800].forEach" not in js


def test_dco_list_has_one_refresh_owner_and_no_delayed_render_storm():
    js = DCO_LIST_JS.read_text(encoding="utf-8")

    assert "function schedulePresentation(" in js
    assert "_dcoPresentationNeedsRoleRefresh" in js
    assert 'schedulePresentation(listview, { refreshRoleFlags: true });' in js
    assert "requestAnimationFrame" in js

    # The previous implementation rendered immediately, in rAF, after 100 ms
    # and after 350 ms for the same refresh. Keep that retry storm retired.
    assert "setTimeout(() => {\n            renderMobileCards(listview);" not in js
    assert "}, 100);" not in js
    assert "}, 350);" not in js


def test_dco_list_role_flags_are_requested_once_per_refresh_generation():
    js = DCO_LIST_JS.read_text(encoding="utf-8")

    assert "function requestOperationalRoleFlags(" in js
    assert "function applyOperationalRoleRows(listview)" in js
    assert "return requestOperationalRoleFlags(listview);" in js
    assert "_dcoRoleFlagGeneration" in js
    assert "_dcoRoleFlagsPendingKey" in js
    assert "_dcoRoleFlagsPendingPromise" in js
    assert js.count("frappe.call({") == 1

    # DOM row arrival may replay cached presentation, but must never own a new
    # server request. The Frappe refresh hook is the only request lifecycle owner.
    assert "if (frappeRowsAdded) schedulePresentation(listview);" in js


def test_dco_mobile_cards_use_incremental_dom_updates():
    js = DCO_LIST_JS.read_text(encoding="utf-8")

    assert "function cardRenderSignature(" in js
    assert "previous.dataset.dcoRenderSignature === signature" in js
    assert "card.dataset.dcoRenderSignature = signature" in js
    assert "containers.forEach(removeMobileCard);" in js
    assert "if (next === listview._dcoLastCardLayout) return;" in js


def test_dco_personal_queue_ordering_remains_active_ready_completed():
    js = DCO_LIST_JS.read_text(encoding="utf-8")

    assert "function personalQueueState(" in js
    assert "function sortPersonalQueueItems(" in js
    assert 'return [...inProgress, ...ready, ...completed];' in js
    assert 'queueState: personalQueueState(doc, flag)' in js
    assert 'flag.assignment_state === "completed"' in js
