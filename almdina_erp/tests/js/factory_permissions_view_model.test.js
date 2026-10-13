"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const source = fs.readFileSync(
    path.resolve(__dirname, "../../public/js/factory_permissions/view_model.js"),
    "utf8"
);

function loadModel(translate) {
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
    return fakeWindow.AlmdinaFactoryPermissionsViewModel.create({ translate });
}

const identity = (message, replacements) => {
    let value = String(message || "");
    (replacements || []).forEach((replacement, index) => {
        value = value.replace(`{${index}}`, String(replacement));
    });
    return value;
};

// Realistic server catalog: English canonical message IDs (permission_matrix presentation).
const catalog = [{
    key: "order",
    label: "Orders",
    description: "Create, review, approve, and manage the lifecycle of an order.",
    capabilities: [
        {
            key: "view_orders",
            label: "View orders",
            description: "View the orders you are allowed to see and open their basic details.",
            risk: "normal",
            standard: true,
            permission_type: "read",
        },
        {
            key: "cancel_order",
            label: "Cancel order",
            description: "Cancel the order according to lifecycle rules.",
            risk: "critical",
            standard: true,
            permission_type: "delete",
        },
    ],
}];
const working = {
    view_orders: true,
    cancel_order: false,
    server_only_capability: true,
};

const model = loadModel(identity);
const groups = model.permissionGroups(catalog, working);
assert.equal(groups.length, 2, "Unknown server capabilities must remain visible");
assert.equal(groups[0].label, "Orders");
assert.equal(groups[0].description, "Create, review, approve, and manage the lifecycle of an order.");
assert.equal(groups[0].capabilities[0].label, "View orders");
assert.equal(groups[0].capabilities[0].description, "View the orders you are allowed to see and open their basic details.");
assert.equal(groups[0].count, 2);
assert.equal(groups[0].capabilities[0].checked, true);
assert.deepEqual(
    JSON.parse(JSON.stringify(groups[0].capabilities[0].badges)),
    [
        { kind: "permission", label: "Frappe: Read + select" },
        { kind: "standard", label: "Core Frappe permission" },
    ]
);
assert.equal(groups[1].key, "unclassified");
assert.equal(groups[1].capabilities[0].key, "server_only_capability");
assert.equal(groups[1].capabilities[0].label, "server_only_capability");

assert.deepEqual(
    JSON.parse(JSON.stringify(model.capabilityKeys(catalog, working))),
    ["view_orders", "cancel_order", "server_only_capability"]
);
assert.deepEqual(
    JSON.parse(JSON.stringify(model.groupCapabilityKeys(catalog, working, "order"))),
    ["view_orders", "cancel_order"]
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

const stats = model.stats(catalog, working, [{ key: "cancel_order", after: true }]);
assert.deepEqual(
    JSON.parse(JSON.stringify(stats)),
    { total: 3, enabled: 2, critical: 0, changes: 1 }
);

const impact = model.impact({
    requires_self_lockout_confirmation: true,
    source: { kind: "import", role: "CNC" },
    changes: [{ key: "view_orders", label: "View orders", after: false }],
    impact: {
        navigation: {
            home_page: "shop-floor-inbox",
            workspaces: ["Almdina"],
            sections: { orders: true, costing: false },
        },
    },
});
assert.equal(impact.home, "Production floor");
assert.deepEqual(JSON.parse(JSON.stringify(impact.sections)), ["Orders"]);
assert.equal(impact.source, "Source: JSON file from role CNC");
assert.equal(impact.changes[0].label, "View orders");
assert.equal(impact.changes[0].action, "Cancel");
assert.ok(impact.warning.includes("last permission"));

const audit = model.audit(Array.from({ length: 12 }, (_, index) => ({
    changed_by: `user-${index}`,
    changed_on: `date-${index}`,
    changed_capabilities: `cap-${index}`,
})));
assert.equal(audit.length, 10);
assert.equal(audit[0].changedBy, "user-0");

const french = {
    "Orders": "Commandes",
    "Create, review, approve, and manage the lifecycle of an order.": "Creer, revoir, approuver et gerer le cycle de vie d'une commande.",
    "View orders": "Voir les commandes",
    "View the orders you are allowed to see and open their basic details.": "Voir les commandes autorisees et ouvrir leurs details.",
    "Cancel order": "Annuler la commande",
    "Cancel the order according to lifecycle rules.": "Annuler la commande selon les regles du cycle de vie.",
    "Other permissions": "Autres permissions",
    "Permissions that exist on the server but were not categorized in the management interface. They appear here automatically so that no assignable permission is hidden.":
        "Permissions presentes sur le serveur mais non classees.",
    "System permission registered in the role matrix.": "Permission systeme enregistree.",
    "Read + select": "Lecture + selection",
    "Create": "Creer",
    "Edit": "Modifier",
    "Delete": "Supprimer",
    "Frappe: {0}": "Frappe: {0}",
    "Core Frappe permission": "Permission Frappe de base",
    "Critical": "Critique",
    "Sensitive": "Sensible",
    "Production floor": "Atelier",
    "Orders": "Commandes",
    "Source: JSON file from role {0}": "Source: fichier JSON du role {0}",
    "Grant": "Accorder",
    "Cancel": "Annuler",
    "This change removes your last permission to manage permissions. After saving you may not be able to return to the page.":
        "Ce changement retire votre derniere permission.",
};
const frTranslate = (message, replacements) => {
    let value = Object.prototype.hasOwnProperty.call(french, message) ? french[message] : `FR:${message}`;
    (replacements || []).forEach((replacement, index) => {
        value = value.replace(`{${index}}`, String(replacement));
    });
    return value;
};
const frModel = loadModel(frTranslate);
const frGroups = frModel.permissionGroups(catalog, working);
assert.equal(frGroups[0].label, "Commandes");
assert.equal(frGroups[0].capabilities[0].label, "Voir les commandes");
assert.match(frGroups[0].capabilities[0].description, /autoris/);
const frImpact = frModel.impact({
    requires_self_lockout_confirmation: false,
    source: { kind: "import", role: "CNC" },
    changes: [{ key: "view_orders", label: "View orders", after: true }],
    impact: { navigation: { home_page: "shop-floor-inbox", sections: { orders: true } } },
});
assert.equal(frImpact.changes[0].label, "Voir les commandes");
assert.equal(frImpact.home, "Atelier");

console.log("Factory permissions view-model simulation passed");
