(() => {
    "use strict";

    if (window.AlmdinaDcoWorkspaceAssetRegistry) return;

    const ASSET_ROOT = "/assets/almdina_erp/js/door_cutting_order";
    const pending = new Map();

    const FEATURES = Object.freeze({
        plan: Object.freeze({
            activationField: "results_tab",
            assets: Object.freeze([
                `${ASSET_ROOT}/cutting_plan/door_cutting_order_plan_preview_session.js`,
                `${ASSET_ROOT}/cutting_plan/door_cutting_order_piece_geometry.js`,
                `${ASSET_ROOT}/cutting_plan/door_cutting_order_cutting_plan_renderer.js`,
                `${ASSET_ROOT}/cutting_plan/secure_dxf_upload.js`,
                `${ASSET_ROOT}/cutting_plan/door_cutting_order_plan_ux.js`,
                `${ASSET_ROOT}/cutting_plan/door_cutting_order_text_board_plan_ux.js`,
                `${ASSET_ROOT}/cutting_plan/door_cutting_order_plan_controls_ux.js`,
                `${ASSET_ROOT}/cutting_plan/door_cutting_order_plan_content_styles.js`,
                `${ASSET_ROOT}/cutting_plan/door_cutting_order_plan_board_presenter.js`,
                `${ASSET_ROOT}/cutting_plan/door_cutting_order_plan_content_ux.js`,
                `${ASSET_ROOT}/cutting_plan/door_cutting_order_plan_context_actions_ux.js`,
                `${ASSET_ROOT}/cutting_plan/door_cutting_order_plan_tabs_ux.js`,
                `${ASSET_ROOT}/cutting_plan/door_cutting_order_plan_workspace_presenter_adapter.js`,
                `${ASSET_ROOT}/cutting_plan/door_cutting_order_plan_surface_bootstrap.js`,
                `${ASSET_ROOT}/cutting_plan/door_cutting_order_drawing_plan_ux.js`,
                `${ASSET_ROOT}/cutting_plan/door_cutting_order_drawing_approval_ux.js`,
                `${ASSET_ROOT}/cutting_plan/secure_dxf_export.js`,
                `${ASSET_ROOT}/cutting_plan/door_cutting_order_plan_edit_session_ux.js`,
                `${ASSET_ROOT}/cutting_plan/door_cutting_order_plan_preview_presenter.js`,
                `${ASSET_ROOT}/cutting_plan/door_cutting_order_plan_preview_edit_ux.js`,
                `${ASSET_ROOT}/cutting_plan/door_cutting_order_plan_settings_summary_ux.js`,
                `${ASSET_ROOT}/cutting_plan/door_cutting_order_plan_field_access_adapter.js`,
            ]),
            readyGlobals: Object.freeze([
                "AlmdinaCuttingPlanPieceGeometry",
                "AlmdinaPlanWorkspacePresenterAdapter",
                "AlmdinaCuttingPlanSurfaceBootstrap",
                "AlmdinaPlanEditSessionUX",
                "AlmdinaPlanFieldAccessAdapter",
            ]),
        }),
        cost: Object.freeze({
            activationField: "cost_tab",
            assets: Object.freeze([
                `${ASSET_ROOT}/costing/door_cutting_order_multi_edge_documents_ux.js`,
                `${ASSET_ROOT}/costing/door_cutting_order_cost_presenter.js`,
                `${ASSET_ROOT}/costing/door_cutting_order_cost_workspace_presenter_adapter.js`,
                `${ASSET_ROOT}/costing/door_cutting_order_cost_permissions_ux.js`,
                `${ASSET_ROOT}/costing/door_cutting_order_financial_documents_ux.js`,
                `${ASSET_ROOT}/costing/door_cutting_order_customer_invoice_toolbar_ux.js`,
                `${ASSET_ROOT}/costing/door_cutting_order_cost_edit_session_ux.js`,
            ]),
            readyGlobals: Object.freeze([
                "AlmdinaOrderCostUX",
                "AlmdinaCostWorkspacePresenterAdapter",
                "AlmdinaCostPermissionsUX",
                "AlmdinaCostEditSessionUX",
            ]),
        }),
    });

    function descriptor(featureName) {
        return FEATURES[String(featureName || "").trim()] || null;
    }

    function featureForTab(fieldname) {
        const target = String(fieldname || "").trim();
        return Object.keys(FEATURES).find(
            name => FEATURES[name].activationField === target
        ) || "";
    }

    function activationFields() {
        return Object.values(FEATURES).map(feature => feature.activationField);
    }

    function globalsReady(feature) {
        return Boolean(
            feature
            && feature.readyGlobals.every(name => Boolean(window[name]))
        );
    }

    function isLoaded(featureName) {
        return globalsReady(descriptor(featureName));
    }

    function emit(featureName, phase, error = null) {
        const feature = descriptor(featureName);
        if (!feature || typeof window.dispatchEvent !== "function") return;
        window.dispatchEvent(new CustomEvent("almdina:workspace-assets-status", {
            detail: {
                feature: featureName,
                fieldname: feature.activationField,
                phase,
                error: error ? String(error.message || error) : "",
            },
        }));
    }

    function loader() {
        const frontend = window.AlmdinaFrontend;
        if (frontend && typeof frontend.requireAssets === "function") {
            return assets => frontend.requireAssets(assets);
        }
        if (window.frappe && typeof window.frappe.require === "function") {
            return assets => Promise.resolve(window.frappe.require(assets));
        }
        return null;
    }

    function ensure(featureName, options = {}) {
        const name = String(featureName || "").trim();
        const feature = descriptor(name);
        if (!feature) return Promise.resolve(false);
        if (!options.force && globalsReady(feature)) return Promise.resolve(true);
        if (pending.has(name)) return pending.get(name);

        const requireAssets = loader();
        if (!requireAssets) {
            return Promise.reject(new Error("DCO workspace asset loader is unavailable"));
        }

        emit(name, "loading");
        const operation = Promise.resolve(requireAssets(feature.assets))
            .then(() => {
                if (!globalsReady(feature)) {
                    throw new Error(`DCO ${name} workspace assets did not initialize completely`);
                }
                emit(name, "loaded");
                return true;
            })
            .catch(error => {
                emit(name, "failed", error);
                throw error;
            })
            .finally(() => {
                if (pending.get(name) === operation) pending.delete(name);
            });

        pending.set(name, operation);
        return operation;
    }

    function ensureForTab(fieldname, options = {}) {
        const name = featureForTab(fieldname);
        return name ? ensure(name, options) : Promise.resolve(false);
    }

    function assetsFor(featureName) {
        const feature = descriptor(featureName);
        return feature ? feature.assets.slice() : [];
    }

    window.AlmdinaDcoWorkspaceAssetRegistry = Object.freeze({
        activationFields,
        assetsFor,
        ensure,
        ensureForTab,
        featureForTab,
        isLoaded,
    });
})();
