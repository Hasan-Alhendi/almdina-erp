from __future__ import annotations

from pathlib import Path


APP_ROOT = Path(__file__).resolve().parents[1]
PUBLIC_JS = APP_ROOT / "public" / "js"


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
    # workspace/workforce surfaces and then disconnect.
    assert "TRANSIENT_OBSERVER_MS" in js
    assert "function surfaceMode()" in js
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
