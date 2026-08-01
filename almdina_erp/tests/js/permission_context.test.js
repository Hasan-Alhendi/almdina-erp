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
    const fakeWindow = {};
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
    });
    vm.runInContext(source, context, { filename: "permission_context.js" });
    return { permissions: fakeWindow.AlmdinaPermissions, frappe: fakeFrappe };
}

const loaded = load({
    version: 1,
    profile: "shop_floor",
    capabilities: {
        view_cutting_plan: true,
        upload_dxf: false,
        print_cutting_plan: 1,
    },
});

assert.equal(loaded.permissions.version(), 1);
assert.equal(loaded.permissions.profile(), "shop_floor");
assert.equal(loaded.permissions.can("view_cutting_plan"), true);
assert.equal(loaded.permissions.can("upload_dxf"), false);
assert.equal(loaded.permissions.can("print_cutting_plan"), false);
assert.equal(loaded.permissions.can("unknown"), false);
assert.equal(loaded.permissions.any("upload_dxf", "view_cutting_plan"), true);
assert.equal(loaded.permissions.all("view_cutting_plan", "upload_dxf"), false);
assert.equal(loaded.permissions.all([]), false);
assert.equal(loaded.frappe.almdina.permissions, loaded.permissions);
assert.equal(Object.isFrozen(loaded.permissions), true);
assert.equal(Object.isFrozen(loaded.permissions.snapshot()), true);
assert.equal(Object.isFrozen(loaded.permissions.snapshot().capabilities), true);

const missing = load(undefined).permissions;
assert.equal(missing.version(), 0);
assert.equal(missing.profile(), "full");
assert.equal(missing.can("view_cutting_plan"), false);

console.log("Permission context simulation passed");
