"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const source = fs.readFileSync(
    path.resolve(__dirname, "../../public/js/permission_context.js"),
    "utf8"
);

function load(rawContext) {
    const fakeWindow = {
        setInterval() {
            return 1;
        },
        clearInterval() {},
        setTimeout(callback) {
            callback();
            return 1;
        },
    };
    const fakeFrappe = {
        boot: rawContext === undefined ? {} : { almdina_permissions: rawContext },
        provide(namespace) {
            assert.equal(namespace, "frappe.almdina");
            this.almdina = this.almdina || {};
        },
    };
    const context = vm.createContext({
        window: fakeWindow,
        frappe: fakeFrappe,
        Object,
        String,
        Number,
        Boolean,
        Array,
    });
    vm.runInContext(source, context, { filename: "permission_context.js" });
    return { permissions: fakeWindow.AlmdinaPermissions, frappe: fakeFrappe };
}

const loaded = load({
    version: 3,
    profile: "shop_floor",
    capabilities: {
        view_orders: true,
        create_order: true,
        edit_order: true,
        view_cutting_plan: true,
        view_costs: true,
        upload_dxf: false,
        print_cutting_plan: 1,
    },
    navigation: {
        shared_shell: true,
        app_only: true,
        profile: "shop_floor",
        home_page: "shop-floor-inbox",
        default_route: "/app/shop-floor-inbox",
        workspaces: ["Shop Floor"],
        sections: {
            production: true,
            costing: false,
        },
    },
});

assert.equal(loaded.permissions.version(), 3);
assert.equal(loaded.permissions.profile(), "shop_floor");
assert.equal(loaded.permissions.can("view_orders"), true);
assert.equal(loaded.permissions.can("create_order"), true);
assert.equal(loaded.permissions.can("edit_order"), true);
assert.equal(loaded.permissions.can("view_cutting_plan"), true);
assert.equal(loaded.permissions.can("view_costs"), true);
assert.equal(loaded.permissions.permissionType("create_order"), "create");
assert.equal(loaded.permissions.permissionType("edit_order"), "write");
assert.equal(loaded.permissions.permissionType("view_costs"), "view_costs");
assert.equal(loaded.permissions.can("upload_dxf"), false);
assert.equal(loaded.permissions.can("print_cutting_plan"), false);
assert.equal(loaded.permissions.can("unknown"), false);
assert.equal(loaded.permissions.any("upload_dxf", "view_cutting_plan"), true);
assert.equal(loaded.permissions.all("view_cutting_plan", "upload_dxf"), false);
assert.equal(loaded.permissions.all([]), false);
assert.equal(loaded.permissions.section("production"), true);
assert.equal(loaded.permissions.section("costing"), false);
assert.equal(loaded.permissions.home(), "shop-floor-inbox");
assert.deepEqual(loaded.permissions.workspaces(), ["Shop Floor"]);
assert.equal(loaded.permissions.navigation().shared_shell, true);
assert.equal(loaded.frappe.almdina.permissions, loaded.permissions);
assert.equal(Object.isFrozen(loaded.permissions), true);
assert.equal(Object.isFrozen(loaded.permissions.snapshot()), true);
assert.equal(Object.isFrozen(loaded.permissions.snapshot().capabilities), true);
assert.equal(Object.isFrozen(loaded.permissions.snapshot().navigation), true);
assert.equal(Object.isFrozen(loaded.permissions.snapshot().navigation.sections), true);

const nativeOrderForm = {
    has_perm(permissionType) {
        return ["read", "create", "write", "view_costs", "view_cutting_plan"].includes(permissionType);
    },
};

assert.equal(loaded.permissions.canDocument(nativeOrderForm, "view_orders"), true);
assert.equal(loaded.permissions.canDocument(nativeOrderForm, "create_order"), true);
assert.equal(loaded.permissions.canDocument(nativeOrderForm, "edit_order"), true);
assert.equal(loaded.permissions.canDocument(nativeOrderForm, "view_costs"), true);
assert.equal(loaded.permissions.canDocument(nativeOrderForm, "view_cutting_plan"), true);

const nativeDeniedForm = { has_perm: () => false };
assert.equal(
    loaded.permissions.canDocument(nativeDeniedForm, "view_orders"),
    false,
    "Native read may narrow a granted standard matrix capability"
);
assert.equal(
    loaded.permissions.canDocument(nativeDeniedForm, "create_order"),
    false,
    "Native create may narrow a granted standard matrix capability"
);
assert.equal(
    loaded.permissions.canDocument(nativeDeniedForm, "edit_order"),
    false,
    "Native write may narrow a granted standard matrix capability"
);
assert.equal(
    loaded.permissions.canDocument(nativeDeniedForm, "view_cutting_plan"),
    true,
    "Custom business capabilities remain matrix-authoritative in the UI"
);
assert.equal(
    loaded.permissions.canDocument(nativeDeniedForm, "view_costs"),
    true,
    "Custom business capabilities remain matrix-authoritative in the UI"
);

const missing = load(undefined).permissions;
assert.equal(missing.version(), 0);
assert.equal(missing.profile(), "shared");
assert.equal(missing.can("view_cutting_plan"), false);
assert.equal(
    missing.canDocument(nativeOrderForm, "create_order"),
    false,
    "Native Frappe create permission must never widen an absent matrix capability"
);
assert.equal(
    missing.canDocument(nativeOrderForm, "edit_order"),
    false,
    "Native Frappe write permission must never widen an absent matrix capability"
);
assert.equal(
    missing.canDocument(nativeOrderForm, "view_costs"),
    false,
    "Native custom permission must never widen an absent matrix capability"
);
assert.equal(
    missing.canDocument(nativeOrderForm, "view_cutting_plan"),
    false,
    "Native custom permission must never widen an absent matrix capability"
);
assert.equal(missing.canDocument(nativeOrderForm, "approve_dxf"), false);
assert.equal(missing.section("production"), false);
assert.equal(missing.home(), "");
assert.equal(missing.navigation().shared_shell, false);
assert.equal(missing.navigation().app_only, false);

console.log("Permission and navigation context simulation passed");
