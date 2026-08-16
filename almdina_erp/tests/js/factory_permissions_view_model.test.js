"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const source = fs.readFileSync(
    path.resolve(__dirname, "../../public/js/factory_permissions/view_model.js"),
    "utf8"
);
const fakeWindow = {};
const context = vm.createContext({
    window: fakeWindow,
    Object,
    Array,
    Set,
    String,
    Boolean,
});
vm.runInContext(source, context, { filename: "view_model.js" });

const translate = (message, replacements) => {
    let value = String(message || "");
    (replacements || []).forEach((replacement, index) => {
        value = value.replace(`{${index}}`, String(replacement));
    });
    return value;
};
const model = fakeWindow.AlmdinaFactoryPermissionsViewModel.create({ translate });

const catalog = [{
    key: "orders",
    label: "الطلبات",
    description: "صلاحيات الطلبات",
    capabilities: [
        {
            key: "view_orders",
            label: "عرض الطلبات",
            description: "عرض قائمة الطلبات",
            risk: "normal",
            standard: true,
            permission_type: "read",
        },
        {
            key: "delete_order",
            label: "حذف الطلب",
            description: "حذف الطلب",
            risk: "critical",
            standard: true,
            permission_type: "delete",
        },
    ],
}];
const working = {
    view_orders: true,
    delete_order: false,
    server_only_capability: true,
};

const groups = model.permissionGroups(catalog, working);
assert.equal(groups.length, 2, "Unknown server capabilities must remain visible");
assert.equal(groups[0].count, 2);
assert.equal(groups[0].capabilities[0].checked, true);
assert.deepEqual(
    JSON.parse(JSON.stringify(groups[0].capabilities[0].badges)),
    [
        { kind: "permission", label: "Frappe: قراءة + اختيار" },
        { kind: "standard", label: "صلاحية Frappe أساسية" },
    ]
);
assert.equal(groups[1].key, "unclassified");
assert.equal(groups[1].capabilities[0].key, "server_only_capability");

assert.deepEqual(
    JSON.parse(JSON.stringify(model.capabilityKeys(catalog, working))),
    ["view_orders", "delete_order", "server_only_capability"]
);
assert.deepEqual(
    JSON.parse(JSON.stringify(model.groupCapabilityKeys(catalog, working, "orders"))),
    ["view_orders", "delete_order"]
);

const roles = model.roleMenu(
    [
        { name: "CNC", desk_access: 1 },
        { name: "Order Entry", desk_access: 0 },
    ],
    "cn",
    "CNC"
);
assert.equal(roles.length, 1);
assert.equal(roles[0].selected, true);
assert.equal(roles[0].deskAccess, true, "Truthy backend desk_access values must remain supported");

const bulk = model.bulkControls(catalog, working);
assert.equal(bulk.groups[0].allEnabled, false);
assert.equal(bulk.groups[1].allEnabled, true);
assert.equal(bulk.globalAllEnabled, false);

const stats = model.stats(catalog, working, [{ key: "delete_order", after: true }]);
assert.deepEqual(
    JSON.parse(JSON.stringify(stats)),
    { total: 3, enabled: 2, critical: 0, changes: 1 }
);

const impact = model.impact({
    requires_self_lockout_confirmation: true,
    source: { kind: "import", role: "CNC" },
    changes: [{ key: "view_orders", label: "عرض الطلبات", after: false }],
    impact: {
        navigation: {
            home_page: "shop-floor-inbox",
            workspaces: ["Almdina"],
            sections: { orders: true, costing: false },
        },
    },
});
assert.equal(impact.home, "صالة الإنتاج");
assert.deepEqual(JSON.parse(JSON.stringify(impact.sections)), ["الطلبات"]);
assert.equal(impact.source, "المصدر: ملف JSON من الدور CNC");
assert.equal(impact.changes[0].action, "إلغاء");
assert.ok(impact.warning.includes("آخر صلاحية"));

const audit = model.audit(Array.from({ length: 12 }, (_, index) => ({
    changed_by: `user-${index}`,
    changed_on: `date-${index}`,
    changed_capabilities: `cap-${index}`,
})));
assert.equal(audit.length, 10);
assert.equal(audit[0].changedBy, "user-0");

console.log("Factory permissions view-model simulation passed");
