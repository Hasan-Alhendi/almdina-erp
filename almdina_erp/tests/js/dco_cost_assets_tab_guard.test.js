"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

function source(relativePath) {
    return fs.readFileSync(path.resolve(__dirname, "../../", relativePath), "utf8");
}

function verifyCostAssetContract() {
    const fakeWindow = { dispatchEvent() {} };
    const context = vm.createContext({
        window: fakeWindow,
        console,
        Promise,
        Object,
        Array,
        Map,
        Set,
        String,
        CustomEvent: class CustomEvent {
            constructor(type, options = {}) {
                this.type = type;
                this.detail = options.detail;
            }
        },
    });

    vm.runInContext(
        source("public/js/door_cutting_order/core/door_cutting_order_workspace_asset_registry.js"),
        context,
        { filename: "door_cutting_order_workspace_asset_registry.js" }
    );

    const registry = fakeWindow.AlmdinaDcoWorkspaceAssetRegistry;
    assert.ok(registry, "workspace asset registry should initialize");
    const assets = Array.from(registry.assetsFor("cost"));
    assert.ok(assets.length >= 7, "Cost workspace should expose its lazy asset bundle");
    assert.ok(
        assets.every(asset => asset.endsWith(".js") && !asset.includes("?")),
        "Cost lazy assets must be plain JavaScript paths; Frappe owns cache versioning"
    );
    assert.ok(
        assets.some(asset => asset.endsWith("door_cutting_order_cost_page_layout_ux.js")),
        "Cost page layout must remain in the lazy bundle without a query suffix"
    );
    assert.ok(
        assets.some(asset => asset.endsWith("door_cutting_order_cost_edit_session_ux.js")),
        "Cost edit-session API must be ready in the same lazy bundle"
    );
}

function verifyNavigationOwnershipContract() {
    const pageActions = source(
        "public/js/door_cutting_order/core/door_cutting_order_page_edit_action_ux.js"
    );
    const nativeGuard = source(
        "public/js/door_cutting_order/core/door_cutting_order_tab_edit_lifecycle_guard.js"
    );

    assert.match(
        pageActions,
        /activeEditingKind/,
        "page action owner must remain the canonical edit-session discovery API"
    );
    assert.match(
        pageActions,
        /on_tab_change\(frm\)/,
        "toolbar projection should reconcile from Frappe's host tab lifecycle"
    );
    assert.doesNotMatch(
        pageActions,
        /stopImmediatePropagation|tab-local-edit-navigation|TAB_LISTENER_/,
        "page toolbar owner must not install a second DOM navigation blocker"
    );

    assert.match(nativeGuard, /tab\.set_active = guardedSetActive/);
    assert.match(nativeGuard, /showOpenEditMessage\(\)/);
    assert.match(nativeGuard, /restoreState\(frm, state\)/);
}

verifyCostAssetContract();
verifyNavigationOwnershipContract();
console.log("DCO Cost assets and single native tab-guard ownership contract passed");
