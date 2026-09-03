"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const source = fs.readFileSync(
    path.resolve(
        __dirname,
        "../../public/js/door_cutting_order/core/door_cutting_order_workspace_asset_registry.js"
    ),
    "utf8"
);

function deferred() {
    let resolve;
    let reject;
    const promise = new Promise((resolvePromise, rejectPromise) => {
        resolve = resolvePromise;
        reject = rejectPromise;
    });
    return { promise, resolve, reject };
}

class CustomEvent {
    constructor(type, options = {}) {
        this.type = type;
        this.detail = options.detail;
    }
}

(async () => {
    const calls = [];
    const events = [];
    const flights = [];
    const fakeWindow = {
        dispatchEvent(event) {
            events.push(event);
            return true;
        },
        AlmdinaFrontend: {
            requireAssets(assets) {
                const flight = deferred();
                calls.push(Array.from(assets));
                flights.push(flight);
                return flight.promise;
            },
        },
    };

    const context = vm.createContext({
        window: fakeWindow,
        console,
        Promise,
        Object,
        Array,
        Map,
        Set,
        String,
        CustomEvent,
    });

    vm.runInContext(source, context, {
        filename: "door_cutting_order_workspace_asset_registry.js",
    });

    const registry = fakeWindow.AlmdinaDcoWorkspaceAssetRegistry;
    assert.ok(registry);
    assert.deepEqual(Array.from(registry.activationFields()), ["results_tab", "cost_tab"]);
    assert.equal(registry.featureForTab("order_tab"), "");
    assert.equal(await registry.ensureForTab("order_tab"), false);
    assert.equal(calls.length, 0, "Order workspace must not request a derived asset bundle");

    const planOne = registry.ensureForTab("results_tab");
    const planTwo = registry.ensure("plan");
    assert.strictEqual(planOne, planTwo, "concurrent Plan activation must share one asset flight");
    assert.equal(calls.length, 1);
    assert.ok(calls[0].length > 10, "Plan bundle should batch its presentation modules");
    assert.ok(calls[0].every(asset => asset.includes("/cutting_plan/")));
    assert.ok(calls[0].some(asset => asset.endsWith("door_cutting_order_plan_surface_bootstrap.js")));
    assert.ok(calls[0].some(asset => asset.endsWith("door_cutting_order_piece_geometry.js")));
    assert.ok(calls[0].some(asset => asset.endsWith("door_cutting_order_plan_edit_session_ux.js")));
    assert.ok(calls[0].some(asset => asset.endsWith("secure_dxf_export.js")));

    fakeWindow.AlmdinaCuttingPlanPieceGeometry = {};
    fakeWindow.AlmdinaPlanWorkspacePresenterAdapter = {};
    fakeWindow.AlmdinaCuttingPlanSurfaceBootstrap = {};
    fakeWindow.AlmdinaPlanFieldAccessAdapter = {};
    assert.equal(
        registry.isLoaded("plan"),
        false,
        "Plan readiness must not settle before the lazy edit-session API exists"
    );

    // The edit-session module is part of the same cold Plan bundle. A Plan feature
    // becomes ready only after that module has evaluated as well.
    fakeWindow.AlmdinaPlanEditSessionUX = {};
    flights[0].resolve(calls[0]);
    assert.equal(await planOne, true);
    assert.equal(await registry.ensure("plan"), true);
    assert.equal(calls.length, 1, "loaded Plan assets must remain cached by ready globals");

    const costOne = registry.ensureForTab("cost_tab");
    const costTwo = registry.ensure("cost");
    assert.strictEqual(costOne, costTwo, "concurrent Cost activation must share one asset flight");
    assert.equal(calls.length, 2);
    assert.ok(calls[1].length >= 7);
    assert.ok(calls[1].every(asset => asset.includes("/costing/")));
    assert.ok(calls[1].some(asset => asset.endsWith("door_cutting_order_cost_presenter.js")));

    flights[1].reject(new Error("offline"));
    await assert.rejects(costOne, /offline/);
    assert.equal(registry.isLoaded("cost"), false);

    const costRetry = registry.ensure("cost");
    assert.equal(calls.length, 3, "failed bundle must be retryable");
    fakeWindow.AlmdinaOrderCostUX = {};
    fakeWindow.AlmdinaCostWorkspacePresenterAdapter = {};
    fakeWindow.AlmdinaCostPermissionsUX = {};
    fakeWindow.AlmdinaCostEditSessionUX = {};
    flights[2].resolve(calls[2]);
    assert.equal(await costRetry, true);
    assert.equal(registry.isLoaded("cost"), true);

    const phases = events
        .filter(event => event.type === "almdina:workspace-assets-status")
        .map(event => `${event.detail.feature}:${event.detail.phase}`);
    assert.deepEqual(phases, [
        "plan:loading",
        "plan:loaded",
        "cost:loading",
        "cost:failed",
        "cost:loading",
        "cost:loaded",
    ]);

    console.log("DCO workspace asset registry simulation passed");
})().catch(error => {
    console.error(error);
    process.exitCode = 1;
});
