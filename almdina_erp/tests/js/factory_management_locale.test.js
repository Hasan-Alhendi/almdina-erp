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
    "public/js/factory_production_settings/catalog_labels.js",
    "public/js/factory_production_settings/controller.js",
    "public/js/factory_production_settings/dialogs.js",
    "public/js/factory_production_settings/renderer.js",
    "public/js/factory_production_settings/view_model.js",
    "public/js/factory_production_settings/whatsapp_panel.js",
    "almdina_erp/page/factory_master_data/factory_master_data.js",
    "almdina_erp/page/factory_plan_archive/factory_plan_archive.js",
];

const compatibility = ["غير مسموح", "مسموح"];

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

function parseCsvCatalog(text) {
    const rows = new Map();
    for (const line of text.split(/\r?\n/)) {
        if (!line) continue;
        let source;
        let target;
        if (line.startsWith('"')) {
            const end = line.indexOf('",');
            if (end < 0) continue;
            source = line.slice(1, end).replace(/""/g, '"');
            target = line.slice(end + 2);
            if (target.startsWith('"')) {
                const tend = target.indexOf('"', 1);
                target = tend > 0 ? target.slice(1, tend).replace(/""/g, '"') : target;
            } else {
                target = target.split(",")[0];
            }
        } else {
            const comma = line.indexOf(",");
            if (comma < 0) continue;
            source = line.slice(0, comma);
            target = line.slice(comma + 1).split(",")[0];
        }
        if (source && !rows.has(source)) rows.set(source, target);
    }
    return rows;
}

const csvMap = parseCsvCatalog(fs.readFileSync(path.join(root, "translations/ar.csv"), "utf8"));
const catalogRows = new Set(csvMap.keys());

const messageIds = new Set();
for (const relative of files) {
    const source = fs.readFileSync(path.join(root, relative), "utf8");
    let visible = source;
    for (const phrase of compatibility) {
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
    "View orders",
    "Approve cutting plan",
    "Last {0} backups",
    "Automatic",
    "Enabled",
    "Edit",
]) {
    assert.ok(catalogRows.has(required), required);
}
assert.equal(csvMap.get("Enabled"), "مفعّل");
assert.equal(csvMap.get("Edit"), "تعديل");
assert.equal(csvMap.get("Last {0} backups"), "آخر {0} نسخ احتياطية");
assert.equal(csvMap.get("Other"), "سبب آخر");

assert.match(
    fs.readFileSync(path.join(root, "public/js/factory_permissions/view_model.js"), "utf8"),
    /displayCopy\(/
);
assert.match(
    fs.readFileSync(path.join(root, "almdina_erp/page/factory_production_settings/factory_production_settings.js"), "utf8"),
    /catalog_labels\.js/
);

const matrixSource = fs.readFileSync(
    path.join(root, "almdina_erp/application/security/permission_matrix.py"),
    "utf8"
);
assert.doesNotMatch(matrixSource, /[\u0600-\u06FF]/);
assert.match(matrixSource, /"View orders"/);
assert.match(matrixSource, /"Approve cutting plan"/);

let armed = false;
const french = {
    "Orders": "Commandes",
    "Create, review, approve, and manage the lifecycle of an order.":
        "Creer, revoir, approuver et gerer le cycle de vie d'une commande.",
    "View orders": "Voir les commandes",
    "View the orders you are allowed to see and open their basic details.":
        "Voir les commandes autorisees et ouvrir leurs details.",
    "Cancel order": "Annuler la commande",
    "Cancel the order according to lifecycle rules.": "Annuler selon les regles.",
    "Other permissions": "Autres permissions",
    "Permissions that exist on the server but were not categorized in the management interface. They appear here automatically so that no assignable permission is hidden.":
        "Permissions presentes sur le serveur mais non classees.",
    "System permission registered in the role matrix.": "Permission systeme.",
    "Read + select": "Lecture + selection",
    "Frappe: {0}": "Frappe: {0}",
    "Core Frappe permission": "Permission Frappe de base",
    "Critical": "Critique",
    "Production floor": "Atelier",
    "Source: JSON file from role {0}": "Source: fichier JSON du role {0}",
    "Grant": "Accorder",
    "Cancel": "Annuler",
    "This change removes your last permission to manage permissions. After saving you may not be able to return to the page.":
        "Ce changement retire votre derniere permission.",
    "Does not change the home page": "Ne change pas la page d'accueil",
    "Automatic": "Automatique",
    "Panel Saw": "Scie a panneaux",
    "Last {0} backups": "Dernieres {0} sauvegardes",
    "Enabled": "Active",
    "Disabled": "Desactive",
    "Daily": "Quotidien",
    "Weekly": "Hebdomadaire",
    "Local retention": "Conservation locale",
    "External retention": "Conservation externe",
    "Local backup": "Sauvegarde locale",
    "External backup": "Sauvegarde externe",
    "Local schedule": "Planification locale",
    "External schedule": "Planification externe",
    "SSH server": "Serveur SSH",
    "SSH user": "Utilisateur SSH",
    "Authentication method": "Methode d'authentification",
    "Remote path": "Chemin distant",
    "Credentials": "Identifiants",
    "Not configured": "Non configure",
    "Not set up": "Non defini",
    "Saved securely": "Enregistre en securite",
    "Private Key": "Cle privee",
    "Backup & Restore": "Sauvegarde et restauration",
    "Independent local and external backups built on the official Frappe mechanism, with separate retention and a secure SFTP connection.":
        "Sauvegardes locales et externes.",
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

function identity(message, replacements) {
    let text = String(message == null ? "" : message);
    if (Array.isArray(replacements)) {
        replacements.forEach((value, index) => {
            text = text.split(`{${index}}`).join(String(value));
        });
    }
    return text;
}

function arabicFromCsv(message, replacements) {
    let text = csvMap.has(message) ? csvMap.get(message) : String(message == null ? "" : message);
    if (Array.isArray(replacements)) {
        replacements.forEach((value, index) => {
            text = text.split(`{${index}}`).join(String(value));
        });
    }
    return text;
}

function loadModule(relative, extras = {}) {
    const context = {
        console,
        window: extras.window || {},
        Object,
        Array,
        Set,
        String,
        Boolean,
        Number,
        ...(extras.globals || {}),
    };
    context.window.window = context.window;
    const sandbox = vm.createContext(context);
    armed = false;
    vm.runInContext(
        fs.readFileSync(path.join(root, relative), "utf8"),
        sandbox,
        { filename: path.basename(relative) }
    );
    armed = true;
    return sandbox;
}

const realisticCatalog = [{
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
            standard: false,
            permission_type: "delete",
        },
    ],
}];

armed = false;
const permissionsSandbox = loadModule("public/js/factory_permissions/view_model.js");
const enModel = permissionsSandbox.window.AlmdinaFactoryPermissionsViewModel.create({ translate: identity });
const enGroups = enModel.permissionGroups(realisticCatalog, { view_orders: true, cancel_order: false });
assert.equal(enGroups[0].label, "Orders");
assert.equal(enGroups[0].capabilities[0].label, "View orders");
assert.equal(enGroups[0].capabilities[0].key, "view_orders");

const arModel = permissionsSandbox.window.AlmdinaFactoryPermissionsViewModel.create({ translate: arabicFromCsv });
const arGroups = arModel.permissionGroups(realisticCatalog, { view_orders: true });
assert.equal(arGroups[0].label, "الطلبات");
assert.equal(arGroups[0].capabilities[0].label, "عرض الطلبات");

const frModel = permissionsSandbox.window.AlmdinaFactoryPermissionsViewModel.create({ translate });
const frGroups = frModel.permissionGroups(realisticCatalog, { view_orders: true });
assert.equal(frGroups[0].label, "Commandes");
assert.equal(frGroups[0].capabilities[0].label, "Voir les commandes");
const frImpact = frModel.impact({
    source: { kind: "import", role: "CNC" },
    changes: [{ key: "view_orders", label: "View orders", after: false }],
    impact: { navigation: { home_page: "shop-floor-inbox", sections: { orders: true } } },
});
assert.equal(frImpact.changes[0].label, "Voir les commandes");
assert.equal(frImpact.home, "Atelier");

armed = false;
const settingsWindow = {};
const settingsCtx = vm.createContext({
    window: settingsWindow,
    Object,
    Array,
    Boolean,
    Number,
    String,
});
settingsWindow.window = settingsWindow;
vm.runInContext(
    fs.readFileSync(path.join(root, "public/js/factory_production_settings/catalog_labels.js"), "utf8"),
    settingsCtx
);
vm.runInContext(
    fs.readFileSync(path.join(root, "public/js/factory_production_settings/view_model.js"), "utf8"),
    settingsCtx
);
armed = true;

const settingsCurrent = {
    optimization_catalog: [
        { id: "auto", label: "تلقائي", available: true },
        { id: "auto_pro", label: "Auto Pro", available: false },
        { id: "ancient_mode", label: "وضع تاريخي", available: true },
    ],
    machine_type_catalog: [
        { id: "Panel Saw", label: "منشار ألواح" },
    ],
    values: {
        default_packing_mode: "auto",
        default_cutting_machine_type: "Panel Saw",
        local_backup_enabled: 1,
        local_backup_frequency: "Daily",
        local_backup_retention: 7,
        external_backup_enabled: 0,
        external_backup_frequency: "Weekly",
        external_backup_retention: 4,
    },
    permissions: {
        can_manage_backups: true,
        sections: {
            cutting: { editable: true },
            costing: { editable: false },
            extra_addons: { editable: false },
            production: { editable: false },
            print_identity: { editable: false },
            whatsapp_messages: { editable: false },
            backup_restore: { editable: true },
        },
    },
};

const settingsEn = settingsWindow.AlmdinaFactoryProductionSettingsViewModel.create({ translate: identity });
assert.equal(settingsEn.catalogLabel(settingsCurrent, "optimization_catalog", "auto"), "Automatic");
assert.equal(settingsEn.catalogLabel(settingsCurrent, "optimization_catalog", "ancient_mode"), "وضع تاريخي");
assert.equal(settingsEn.catalogLabel(settingsCurrent, "optimization_catalog", "ghost"), "ghost");
const enBackup = settingsEn.page(settingsCurrent).sections.find((section) => section.key === "backup_restore");
assert.equal(enBackup.rows[2].value, "Last 7 backups");
assert.equal(enBackup.rows[5].value, "Last 4 backups");

const settingsAr = settingsWindow.AlmdinaFactoryProductionSettingsViewModel.create({ translate: arabicFromCsv });
assert.equal(settingsAr.catalogLabel(settingsCurrent, "optimization_catalog", "auto"), "تلقائي");
assert.equal(settingsAr.page(settingsCurrent).sections.find((s) => s.key === "backup_restore").rows[2].value, "آخر 7 نسخ احتياطية");

const settingsFr = settingsWindow.AlmdinaFactoryProductionSettingsViewModel.create({ translate });
assert.equal(settingsFr.catalogLabel(settingsCurrent, "optimization_catalog", "auto"), "Automatique");
assert.equal(settingsFr.catalogLabel(settingsCurrent, "machine_type_catalog", "Panel Saw"), "Scie a panneaux");
assert.equal(
    settingsFr.page(settingsCurrent).sections.find((s) => s.key === "backup_restore").rows[2].value,
    "Dernieres 7 sauvegardes"
);

armed = false;
const dialogWindow = {
    AlmdinaFactoryProductionSettingsCatalogLabels: settingsWindow.AlmdinaFactoryProductionSettingsCatalogLabels,
};
const dialogCtx = vm.createContext({
    window: dialogWindow,
    Object,
    Array,
    Boolean,
    Number,
    String,
    Set,
    frappe: { ui: { Dialog: class { constructor() {} show() {} } }, msgprint() {}, show_alert() {} },
    $() {
        return { length: 0, find() { return this; }, each() { return this; }, prop() { return this; }, text() { return this; } };
    },
});
dialogWindow.window = dialogWindow;
vm.runInContext(
    fs.readFileSync(path.join(root, "public/js/factory_production_settings/dialogs.js"), "utf8"),
    dialogCtx
);
armed = true;
const dialogs = dialogWindow.AlmdinaFactoryProductionSettingsDialogs.create({
    translate: identity,
    escapeHtml: String,
});
const cuttingFields = dialogs.sectionFields("cutting", settingsCurrent);
const packingField = cuttingFields.find((field) => field.fieldname === "default_packing_mode");
assert.ok(packingField.options.includes("Automatic"));
assert.ok(packingField.options.includes("وضع تاريخي"));
assert.equal(packingField.default, "Automatic");
// Frappe Select stores the visible option text; normalize must recover stable IDs.
const normalized = (() => {
    const algorithms = settingsCurrent.optimization_catalog.map((entry) => (
        dialogWindow.AlmdinaFactoryProductionSettingsCatalogLabels.localizeEntry(
            "optimization_catalog",
            entry,
            identity
        )
    ));
    const machines = settingsCurrent.machine_type_catalog.map((entry) => (
        dialogWindow.AlmdinaFactoryProductionSettingsCatalogLabels.localizeEntry(
            "machine_type_catalog",
            entry,
            identity
        )
    ));
    const algorithm = algorithms.find((entry) => entry.label === "Automatic");
    const machine = machines.find((entry) => entry.label === "Panel Saw");
    return {
        default_packing_mode: algorithm ? algorithm.id : "Automatic",
        default_cutting_machine_type: machine ? machine.id : "Panel Saw",
    };
})();
assert.equal(normalized.default_packing_mode, "auto");
assert.equal(normalized.default_cutting_machine_type, "Panel Saw");
assert.equal(
    dialogWindow.AlmdinaFactoryProductionSettingsCatalogLabels.localizeEntry(
        "optimization_catalog",
        { id: "auto_pro", label: "Auto Pro", available: false },
        identity
    ).available,
    false
);

assert.doesNotMatch(
    fs.readFileSync(path.join(root, "public/js/factory_permissions/controller.js"), "utf8"),
    /System Manager/
);

console.log("factory management locale passed");
