from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MEASUREMENTS = (
    ROOT
    / "public"
    / "js"
    / "door_cutting_order"
    / "order_entry"
    / "measurements"
)
ASSETS = ROOT / "frontend_assets.py"
LIFECYCLE = MEASUREMENTS / "door_cutting_order_measurement_lifecycle.js"
OPERATOR = (
    ROOT
    / "public"
    / "js"
    / "door_cutting_order"
    / "order_entry"
    / "door_cutting_order_operator_ux.js"
)
EDGE_BANDING = (
    ROOT
    / "public"
    / "js"
    / "door_cutting_order"
    / "order_entry"
    / "edge_banding"
)

LIFECYCLE_OWNED_REFRESH_MODULES = {
    "door_cutting_order_bulk_rows_ux.js": "bulk-rows",
    "door_cutting_order_compact_measurements_ux.js": "compact-measurements",
    "door_cutting_order_keyboard_columns_ux.js": "keyboard-columns",
    "door_cutting_order_measurement_actions_ux.js": "measurement-actions",
    "door_cutting_order_measurement_resilience_ux.js": "measurement-resilience",
    "door_cutting_order_measurement_toolbar_ux.js": "measurement-toolbar",
    "door_cutting_order_table_performance_ux.js": "table-performance",
}

FINAL_RECONCILIATION_OWNERS = {
    MEASUREMENTS / "door_cutting_order_bulk_rows_ux.js": "bulk-rows",
    MEASUREMENTS / "door_cutting_order_keyboard_columns_ux.js": "keyboard-columns",
    MEASUREMENTS / "door_cutting_order_compact_measurements_ux.js": "compact-measurements",
    MEASUREMENTS / "door_cutting_order_measurement_actions_ux.js": "measurement-actions",
    MEASUREMENTS / "door_cutting_order_measurement_toolbar_ux.js": "measurement-toolbar",
    MEASUREMENTS / "door_cutting_order_measurement_resilience_ux.js": "measurement-resilience",
    MEASUREMENTS / "door_cutting_order_table_performance_ux.js": "table-performance",
    EDGE_BANDING / "door_cutting_order_edge_render_owner.js": "edge-render-owner",
    EDGE_BANDING / "door_cutting_order_cut_dimensions_ux.js": "cut-dimensions",
}


def test_measurement_lifecycle_loads_before_measurement_features_without_reordering_them():
    source = ASSETS.read_text(encoding="utf-8")
    lifecycle = (
        '"public/js/door_cutting_order/order_entry/measurements/'
        'door_cutting_order_measurement_lifecycle.js"'
    )
    bulk = (
        '"public/js/door_cutting_order/order_entry/measurements/'
        'door_cutting_order_bulk_rows_ux.js"'
    )
    keyboard = (
        '"public/js/door_cutting_order/order_entry/measurements/'
        'door_cutting_order_keyboard_columns_ux.js"'
    )
    compact = (
        '"public/js/door_cutting_order/order_entry/measurements/'
        'door_cutting_order_compact_measurements_ux.js"'
    )
    actions = (
        '"public/js/door_cutting_order/order_entry/measurements/'
        'door_cutting_order_measurement_actions_ux.js"'
    )
    toolbar = (
        '"public/js/door_cutting_order/order_entry/measurements/'
        'door_cutting_order_measurement_toolbar_ux.js"'
    )

    for asset in (lifecycle, bulk, keyboard, compact, actions, toolbar):
        assert asset in source
    assert source.index(lifecycle) < source.index(bulk)
    assert source.index(bulk) < source.index(keyboard) < source.index(compact)
    assert source.index(compact) < source.index(actions) < source.index(toolbar)


def test_lifecycle_owner_uses_shared_foundation_and_document_identity_guard():
    source = LIFECYCLE.read_text(encoding="utf-8")
    assert "AlmdinaFrontend" in source
    assert "createLifecycleScope" in source
    assert "AlmdinaDocumentContext" in source
    assert "const scopesByForm = new WeakMap()" in source
    assert "scope.dispose()" in source
    assert "requestAnimationFrame" in source
    assert "cancelAnimationFrame" in source
    assert "documentContext.capture(frm)" in source
    assert "documentContext.isCurrent(frm, documentToken)" in source
    assert "window.AlmdinaMeasurementLifecycle = Object.freeze" in source


def test_measurement_surface_has_real_readiness_recovery_and_final_reconciliation():
    lifecycle = LIFECYCLE.read_text(encoding="utf-8")
    operator = OPERATOR.read_text(encoding="utf-8")
    resilience = (
        MEASUREMENTS / "door_cutting_order_measurement_resilience_ux.js"
    ).read_text(encoding="utf-8")

    assert 'documentContext.registerSurface("measurement-table"' in lifecycle
    assert "function isReady(frm)" in lifecycle
    assert "function recover(frm)" in lifecycle
    assert "function reconcile(frm)" in lifecycle
    assert "featureOwners.forEach" in lifecycle
    assert "documentContext.isCurrent(frm, token)" in lifecycle
    assert "renderer.render(frm)" in lifecycle
    assert "frm.refresh()" not in lifecycle
    assert "frm.reload_doc()" not in lifecycle
    assert 'measurementLifecycle.rendered(frm)' in operator
    assert "lifecycle.isReady(frm) === false" in resilience
    assert "lifecycle.recover(frm)" in resilience

    for path, feature_key in FINAL_RECONCILIATION_OWNERS.items():
        source = path.read_text(encoding="utf-8")
        assert f'registerFeature("{feature_key}"' in source, path.name


def test_repeated_measurement_form_refresh_work_uses_the_lifecycle_owner():
    for filename, feature_key in LIFECYCLE_OWNED_REFRESH_MODULES.items():
        source = (MEASUREMENTS / filename).read_text(encoding="utf-8")
        assert "AlmdinaMeasurementLifecycle" in source, filename
        assert feature_key in source, filename


def test_existing_measurement_behavior_contracts_remain_owned_by_feature_modules():
    toolbar = (MEASUREMENTS / "door_cutting_order_measurement_toolbar_ux.js").read_text(
        encoding="utf-8"
    )
    compact = (MEASUREMENTS / "door_cutting_order_compact_measurements_ux.js").read_text(
        encoding="utf-8"
    )
    actions = (MEASUREMENTS / "door_cutting_order_measurement_actions_ux.js").read_text(
        encoding="utf-8"
    )
    performance = (MEASUREMENTS / "door_cutting_order_table_performance_ux.js").read_text(
        encoding="utf-8"
    )

    assert "{ maxAttempts: 11, delay: 60 }" in toolbar
    assert "{ delays: [180] }" in compact
    assert "{ delays: [180, 600] }" in actions
    assert "{ delays: [220] }" in performance
    assert "event.stopImmediatePropagation()" in performance
