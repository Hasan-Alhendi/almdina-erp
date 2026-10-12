"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const root = path.resolve(__dirname, "../..");
const files = [
    "almdina_erp/page/factory_permissions/factory_permissions.js",
    "public/js/factory_permissions/controller.js",
    "public/js/factory_permissions/dialogs.js",
    "public/js/factory_permissions/renderer.js",
    "public/js/factory_permissions/view_model.js",
    "almdina_erp/page/factory_workforce/factory_workforce.js",
    "public/js/factory_workforce/controller.js",
    "public/js/factory_workforce/dialogs.js",
    "public/js/factory_workforce/renderer.js",
    "public/js/factory_workforce/toolbar.js",
    "public/js/factory_workforce/view_model.js",
    "almdina_erp/page/factory_production_settings/factory_production_settings.js",
    "public/js/factory_production_settings/backup_panel.js",
    "public/js/factory_production_settings/controller.js",
    "public/js/factory_production_settings/dialogs.js",
    "public/js/factory_production_settings/renderer.js",
    "public/js/factory_production_settings/view_model.js",
    "public/js/factory_production_settings/whatsapp_panel.js",
    "almdina_erp/page/factory_master_data/factory_master_data.js",
    "almdina_erp/page/factory_plan_archive/factory_plan_archive.js",
];

const compatibility = [
    "مسموح",
    "غير مسموح",
];

const DIRECT_PATTERNS = [
    /translate\(\s*"((?:\\.|[^"\\])*)"/g,
    /\bt\(\s*"((?:\\.|[^"\\])*)"/g,
    /__\(\s*"((?:\\.|[^"\\])*)"/g,
];

function collectMessageIds(source) {
    const ids = new Set();
    for (const pattern of DIRECT_PATTERNS) {
        pattern.lastIndex = 0;
        for (const match of source.matchAll(pattern)) {
            const value = match[1];
            if (value && /[A-Za-z]/.test(value) && !/[\u0600-\u06FF]/.test(value)) {
                ids.add(value);
            }
        }
    }
    return ids;
}

const catalog = fs.readFileSync(path.join(root, "translations/ar.csv"), "utf8");
const catalogRows = new Set();
for (const line of catalog.split(/\r?\n/)) {
    if (!line) continue;
    if (line.startsWith('"')) {
        const end = line.indexOf('",');
        if (end > 0) catalogRows.add(line.slice(1, end).replace(/""/g, '"'));
        continue;
    }
    const comma = line.indexOf(",");
    if (comma > 0) catalogRows.add(line.slice(0, comma));
}

const messageIds = new Set();
for (const relative of files) {
    const source = fs.readFileSync(path.join(root, relative), "utf8");
    let visible = source;
    for (const phrase of compatibility.slice().sort((a, b) => b.length - a.length)) {
        visible = visible.split(phrase).join("");
    }
    assert.doesNotMatch(visible, /[\u0600-\u06FF]/, relative);
    assert.doesNotMatch(source, /^(?:const|let|var)\s+\w+\s*=\s*(?:translate|__|t)\(/m, relative);
    assert.doesNotMatch(source, /(?:translate|t|__)\(\s*["'`][^"'`]*[\u0600-\u06FF]/, relative);
    assert.doesNotMatch(source, /\bdir\s*=\s*["']rtl["']/);
    assert.doesNotMatch(source, /direction:\s*rtl/);
    for (const id of collectMessageIds(source)) messageIds.add(id);
}

for (const messageId of messageIds) {
    assert.ok(catalogRows.has(messageId), `missing ar.csv key: ${messageId}`);
}

for (const required of [
    "Permission management",
    "Workforce management",
    "Factory settings",
    "Production route management",
    "Allowed",
    "Denied",
    "Enabled",
    "Disabled",
    "All",
    "Save",
    "Cancel",
    "Refresh",
]) {
    assert.ok(catalogRows.has(required), required);
    assert.ok(messageIds.has(required), `runtime missing ${required}`);
}

const permissionsRenderer = fs.readFileSync(
    path.join(root, "public/js/factory_permissions/renderer.js"),
    "utf8"
);
assert.match(permissionsRenderer, /dir="\$\{uiDirection\(\)\}"/);
assert.match(permissionsRenderer, /dir="ltr"/);
assert.doesNotMatch(permissionsRenderer, /\bdir\s*=\s*["']rtl["']/);

const workforceRenderer = fs.readFileSync(
    path.join(root, "public/js/factory_workforce/renderer.js"),
    "utf8"
);
assert.match(workforceRenderer, /dir="\$\{uiDirection\(\)\}"/);
assert.match(workforceRenderer, /class="aw-email" dir="ltr"/);

const settingsRenderer = fs.readFileSync(
    path.join(root, "public/js/factory_production_settings/renderer.js"),
    "utf8"
);
assert.match(settingsRenderer, /dir="\$\{uiDirection\(\)\}"/);
assert.match(settingsRenderer, /normalized === t\("Allowed"\) \|\| normalized === "مسموح"/);
assert.match(settingsRenderer, /normalized === t\("Denied"\) \|\| normalized === "غير مسموح"/);

const masterData = fs.readFileSync(
    path.join(root, "almdina_erp/page/factory_master_data/factory_master_data.js"),
    "utf8"
);
assert.match(masterData, /dir="\$\{uiDirection\(\)\}"/);
assert.doesNotMatch(masterData, /\bdir\s*=\s*["']rtl["']/);

const viewModelSource = fs.readFileSync(
    path.join(root, "public/js/factory_permissions/view_model.js"),
    "utf8"
);
assert.match(viewModelSource, /orders:\s*t\("Orders"\)/);
assert.match(viewModelSource, /t\("Production floor"\)/);

let direction = "rtl";
let armed = false;
const french = {
    "Permission management": "Gestion des permissions",
    "Workforce management": "Gestion de la main-d'oeuvre",
    "Factory settings": "Parametres de l'usine",
    "Allowed": "Autorise",
    "Denied": "Refuse",
    "Enabled": "Active",
    "Disabled": "Desactive",
    "All": "Tous",
    "Orders": "Commandes",
    "Production floor": "Atelier",
    "Other permissions": "Autres permissions",
    "System permission registered in the role matrix.": "Permission systeme enregistree dans la matrice du role.",
    "Core Frappe permission": "Permission Frappe de base",
    "Read + select": "Lecture + selection",
    "Create": "Creer",
    "Edit": "Modifier",
    "Delete": "Supprimer",
    "Frappe: {0}": "Frappe: {0}",
    "Critical": "Critique",
    "Sensitive": "Sensible",
    "Grant": "Accorder",
    "Cancel": "Annuler",
    "Source: JSON file from role {0}": "Source: fichier JSON du role {0}",
    "External preview source": "Source de previsualisation externe",
    "This change removes your last permission to manage permissions. After saving you may not be able to return to the page.":
        "Ce changement retire votre derniere permission de gestion. Apres enregistrement vous pourriez ne plus revenir a la page.",
    "Does not change the home page": "Ne change pas la page d'accueil",
    "Almdina main interface": "Interface principale Almdina",
    "Cost": "Cout",
    "Cutting plan": "Plan de coupe",
    "Drawing": "Dessin",
    "Production": "Production",
    "Quality": "Qualite",
    "Users": "Utilisateurs",
    "Settings": "Parametres",
    "Basic data": "Donnees de base",
    "Administration": "Administration",
    "Reports": "Rapports",
    "Permissions that exist on the server but were not categorized in the management interface. They appear here automatically so no assignable permission is hidden.":
        "Permissions presentes sur le serveur mais non classees. Elles apparaissent ici automatiquement.",
};

function translate(message, replacements) {
    if (!armed) throw new Error(`translation during load: ${message}`);
    let text = Object.prototype.hasOwnProperty.call(french, message) ? french[message] : `FR:${message}`;
    if (Array.isArray(replacements)) {
        replacements.forEach((value, index) => {
            text = text.split(`{${index}}`).join(String(value));
        });
    }
    return text;
}

function loadPermissionsViewModel() {
    const context = {
        console,
        window: {
            AlmdinaLocale: {
                translate,
                direction: () => direction,
            },
        },
        Object,
        Array,
        Set,
        String,
        Boolean,
        __(value) { return value; },
    };
    context.window.window = context.window;
    const sandbox = vm.createContext(context);
    armed = false;
    vm.runInContext(viewModelSource, sandbox, { filename: "view_model.js" });
    armed = true;
    return sandbox.window.AlmdinaFactoryPermissionsViewModel.create({ translate });
}

const model = loadPermissionsViewModel();
direction = "rtl";
const groupsFr = model.permissionGroups(
    [{
        key: "orders",
        label: "Orders Fixture",
        description: "fixture",
        capabilities: [{
            key: "view_orders",
            label: "View orders fixture",
            description: "fixture",
            risk: "normal",
            standard: true,
            permission_type: "read",
        }],
    }],
    { view_orders: true }
);
assert.equal(groupsFr[0].capabilities[0].badges[0].label, "Frappe: Lecture + selection");
assert.equal(groupsFr[0].capabilities[0].label, "View orders fixture");

const impactFr = model.impact({
    requires_self_lockout_confirmation: true,
    source: { kind: "import", role: "CNC" },
    changes: [{ key: "view_orders", label: "View orders fixture", after: false }],
    impact: {
        navigation: {
            home_page: "shop-floor-inbox",
            workspaces: ["Almdina"],
            sections: { orders: true },
        },
    },
});
assert.equal(impactFr.home, "Atelier");
assert.deepEqual(JSON.parse(JSON.stringify(impactFr.sections)), ["Commandes"]);
assert.equal(impactFr.source, "Source: fichier JSON du role CNC");
assert.equal(impactFr.changes[0].action, "Annuler");
assert.match(impactFr.warning, /derniere permission/);

direction = "ltr";
const impactEnCatalog = model.impact({
    requires_self_lockout_confirmation: false,
    source: { kind: "manual" },
    changes: [],
    impact: { navigation: { home_page: "", workspaces: [], sections: {} } },
});
assert.equal(impactEnCatalog.home, "Ne change pas la page d'accueil");

const workforceToolbarSource = fs.readFileSync(
    path.join(root, "public/js/factory_workforce/toolbar.js"),
    "utf8"
);
assert.match(workforceToolbarSource, /t\("All"\)/);
assert.match(workforceToolbarSource, /t\("Enabled"\)/);
assert.match(workforceToolbarSource, /t\("Disabled"\)/);
assert.match(workforceToolbarSource, /\["all", t\("All"\)\]/);

const permissionsController = fs.readFileSync(
    path.join(root, "public/js/factory_permissions/controller.js"),
    "utf8"
);
assert.match(permissionsController, /permission_management_service|AlmdinaFactoryPermissionsApi/);
assert.doesNotMatch(permissionsController, /System Manager/);

console.log("factory management locale passed");
