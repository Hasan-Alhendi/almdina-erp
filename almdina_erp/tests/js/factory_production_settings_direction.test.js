"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const documentElement = {
    dir: "rtl",
    getAttribute(name) {
        return name === "dir" ? documentElement.dir : null;
    },
};

const sandbox = {
    document: { documentElement },
    AlmdinaUi: {
        button(options) {
            return `<button class="${options.className || ""}">${options.label || ""}</button>`;
        },
        badge(options) {
            return `<span class="alm-badge">${options.label || ""}</span>`;
        },
    },
};
sandbox.window = sandbox;
sandbox.AlmdinaLocale = {
    direction() {
        return "ltr";
    },
};
vm.createContext(sandbox);
vm.runInContext(
    fs.readFileSync(
        path.resolve(__dirname, "../../public/js/factory_production_settings/renderer.js"),
        "utf8"
    ),
    sandbox,
    { filename: "renderer.js" }
);

let pageHtml = "";
let backupHtml = "";
let whatsappHtml = "";
const $body = {
    html(value) {
        pageHtml = String(value);
        return this;
    },
    find(selector) {
        const key = String(selector);
        if (key.includes("backup")) {
            return { length: 1, html(value) { backupHtml = String(value); } };
        }
        if (key.includes("whatsapp")) {
            return { length: 1, html(value) { whatsappHtml = String(value); } };
        }
        return { length: 0, html() {} };
    },
};

const renderer = sandbox.AlmdinaFactoryProductionSettingsRenderer.create({
    $body,
    escapeHtml: (value) => String(value ?? ""),
    translate: (message) => message,
});

const model = {
    sections: [{
        key: "cutting",
        title: "Cutting",
        description: "Kerf and board defaults",
        editable: true,
        rows: [
            { label: "Kerf", value: "3.5 mm", multiline: false },
            { label: "Note", value: "ملاحظة تشغيل", multiline: true },
        ],
    }],
    hasLegacy: true,
    legacy: [{ label: "Old width", value: "120", multiline: false }],
    canManageWhatsAppSession: true,
    showBackupPanel: true,
};

function render(direction, documentDir) {
    sandbox.AlmdinaLocale = {
        direction() {
            return direction;
        },
    };
    documentElement.dir = documentDir;
    renderer.render(model);
}

function article() {
    const start = pageHtml.indexOf("<article");
    return pageHtml.slice(start, pageHtml.indexOf("</article>", start));
}

function valueRow(label) {
    const start = pageHtml.indexOf(`>${label}<`);
    const rowStart = pageHtml.lastIndexOf("<div", start);
    return pageHtml.slice(rowStart, pageHtml.indexOf("</div>", start));
}

render("ltr", "rtl");
assert.match(pageHtml, /class="almdina-ui aps-shell alm-page alm-page--admin" dir="ltr"/);
const card = article();
assert.ok(card.indexOf("aps-section-accent") < card.indexOf("aps-section-titles"));
assert.ok(card.indexOf("aps-section-titles") < card.indexOf("aps-section-tools"));
const kerf = valueRow("Kerf");
assert.ok(kerf.indexOf("aps-value-label") < kerf.indexOf("aps-value-data"));
assert.match(kerf, /aps-ltr-value/);
assert.match(kerf, /dir="ltr"/);
const note = valueRow("Note");
assert.equal(note.includes("aps-ltr-value"), false);
assert.equal(note.includes('dir="ltr"'), false);
for (const marker of ["data-whatsapp-root", "data-backup-root", "aps-legacy", "aps-note"]) {
    assert.ok(pageHtml.includes(marker), marker);
}

render("rtl", "ltr");
assert.match(pageHtml, /aps-shell alm-page alm-page--admin" dir="rtl"/);
assert.ok(article().indexOf("aps-section-accent") < article().indexOf("aps-section-tools"));
assert.ok(valueRow("Kerf").indexOf("aps-value-label") < valueRow("Kerf").indexOf("aps-value-data"));

sandbox.AlmdinaLocale = {};
documentElement.dir = "ltr";
renderer.render(model);
assert.match(pageHtml, /aps-shell alm-page alm-page--admin" dir="ltr"/);
documentElement.dir = "rtl";
renderer.render(model);
assert.match(pageHtml, /aps-shell alm-page alm-page--admin" dir="rtl"/);

renderer.renderBackup({
    history: [{
        operation_id: "OP-1",
        backup_identifier: "BACKUP-14",
        operation_type: "Backup",
        target: "site",
        status: "Completed",
        requested_on: "2026-10-13",
        total_size: 2048,
    }],
    permissions: {},
    restorable: [],
});
assert.ok(backupHtml.indexOf("aps-section-accent") < backupHtml.indexOf("aps-section-titles"));
assert.ok(backupHtml.indexOf("aps-section-titles") < backupHtml.indexOf("aps-section-tools"));
assert.match(backupHtml, /aps-ltr-value" dir="ltr">BACKUP-14/);
assert.match(backupHtml, /aps-ltr-value" dir="ltr">2.0 KB/);

renderer.renderWhatsApp({
    session: { status: "ready", name: "Desk", phone: "+963900", push_name: "Factory" },
    working: true,
});
assert.ok(whatsappHtml.indexOf("aps-section-accent") < whatsappHtml.indexOf("aps-section-tools"));
assert.match(whatsappHtml, /aps-value-label">Session number[\s\S]*aps-ltr-value" dir="ltr">\+963900/);

const audit = renderer.auditHtml([{
    action: "Update",
    changed_on: "2026-10-13 16:00",
    changed_by: "operator",
    source: "desk",
    changed_fields: "kerf",
}]);
assert.match(audit, /<div class="aps-audit" dir="rtl">/);
assert.ok(audit.indexOf("aps-audit-dot") < audit.indexOf("aps-audit-content"));
assert.match(audit, /aps-ltr-value" dir="ltr">2026-10-13 16:00/);

console.log("factory production settings direction ok");
