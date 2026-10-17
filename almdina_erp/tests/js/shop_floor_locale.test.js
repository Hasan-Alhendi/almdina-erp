"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const root = path.resolve(__dirname, "../..");
const files = [
    "public/js/door_cutting_order/production/shop_floor_order_ux.js",
    "almdina_erp/page/shop_floor_inbox/shop_floor_inbox.js",
    "public/js/shop_floor_inbox/api.js",
    "public/js/shop_floor_inbox/controller.js",
    "public/js/shop_floor_inbox/dialogs.js",
    "public/js/shop_floor_inbox/interactions.js",
    "public/js/shop_floor_inbox/renderer.js",
    "public/js/shop_floor_inbox/state.js",
    "public/js/shop_floor_inbox/view_model.js",
    "public/js/shop_floor_quick_actions.js",
    "public/js/production_routing_ux.js",
];

const compatibility = [
    "إرسال للإنتاج",
    "تم التسليم",
    "إرجاع لمرحلة سابقة",
    "بدء العمل",
    "إرسال للقسم التالي",
    "جاهزة للتسليم",
    "إنهاء وإرسال",
    "تغيير العامل",
    "رجوع لصالة الإنتاج",
    "العودة إلى الطلبات",
    "رسم",
    "شريون",
    "تقشيط",
    "تسليم",
    "صالة الإنتاج",
];

const DIRECT_PATTERNS = [
    /translate\(\s*"((?:\\.|[^"\\])*)"/g,
    /deny\(\s*"((?:\\.|[^"\\])*)"/g,
    /deny\(\s*[\w.]+\s*\|\|\s*"((?:\\.|[^"\\])*)"/g,
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
    for (const block of ["PRODUCTION_ACTION_IDS", "STATUS_LABELS", "SECTION_LABELS"]) {
        const match = source.match(
            new RegExp(`${block}\\s*=\\s*(?:Object\\.freeze\\()?(\\{|\\[)([\\s\\S]*?)(?:\\}|\\])\\)?`)
        );
        if (!match) continue;
        for (const entry of match[2].matchAll(/"((?:\\.|[^"\\])*)"/g)) {
            const value = entry[1];
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
    assert.doesNotMatch(source, /^(?:const|let|var)\s+\w+\s*=\s*(?:translate|__)\(/m, relative);
    assert.doesNotMatch(source, /translate\(\s*["'`][^"'`]*[\u0600-\u06FF]/, relative);
    assert.doesNotMatch(source, /__\(\s*["'`][^"'`]*[\u0600-\u06FF]/, relative);
    assert.doesNotMatch(source, /direction:\s*rtl|text-align:\s*(?:right|left)\b/, relative);
    assert.doesNotMatch(source, /\bdir\s*=\s*["']rtl["']/, relative);
    for (const id of collectMessageIds(source)) messageIds.add(id);
}

for (const messageId of messageIds) {
    assert.ok(catalogRows.has(messageId), `missing ar.csv key: ${messageId}`);
}

for (const required of [
    "Production floor",
    "Start work",
    "Finish and send",
    "Delivered",
    "Needs work",
    "In progress",
    "Paused",
    "Send to production",
    "Return to a previous stage",
    "Change worker",
]) {
    assert.ok(catalogRows.has(required), required);
    assert.ok(messageIds.has(required), `runtime missing ${required}`);
}

const orderSource = fs.readFileSync(
    path.join(root, "public/js/door_cutting_order/production/shop_floor_order_ux.js"),
    "utf8"
);
assert.match(orderSource, /LEGACY_PRODUCTION_ACTION_LABELS/);
assert.match(orderSource, /current_department === "رسم"/);
assert.match(orderSource, /Sharyoun: \["شريون", "تقشيط", "تسليم"\]/);
assert.match(orderSource, /direction:\$\{uiDirection\(\)\}/);
assert.doesNotMatch(orderSource, /direction:\s*rtl/);

const rendererSource = fs.readFileSync(
    path.join(root, "public/js/shop_floor_inbox/renderer.js"),
    "utf8"
);
assert.match(rendererSource, /dir="ltr"/);
assert.match(rendererSource, /\$section\.attr\("dir", pageDir\)/);
assert.match(rendererSource, /Pending: translate\("Needs work"\)/);
assert.doesNotMatch(rendererSource, /translate\(\s*(?:row\.|model\.)(?:customer|assigned_to|fullName|user|door_cutting_order)/);

const quickSource = fs.readFileSync(path.join(root, "public/js/shop_floor_quick_actions.js"), "utf8");
assert.match(quickSource, /\$wrapper\.attr\("dir", uiDirection\(\)\)/);
assert.match(quickSource, /METHODS\.start/);
assert.match(quickSource, /METHODS\.handoff/);
assert.match(quickSource, /METHODS\.deliver/);

let direction = "rtl";
let armed = false;
const french = {
    "Start work": "Demarrer le travail",
    "Finish and send": "Terminer et envoyer",
    "Delivered": "Livre",
    "Needs work": "A traiter",
    "In progress": "En cours",
    "Paused": "En pause",
    "Completed": "Termine",
    "Production floor": "Atelier",
    "Production board": "Tableau de production",
    "Order list": "Liste des commandes",
    "Account": "Compte",
    "Shop floor navigation": "Navigation atelier",
    "Shop floor sections": "Sections atelier",
};

function translate(message) {
    if (!armed) throw new Error(`translation during load: ${message}`);
    return Object.prototype.hasOwnProperty.call(french, message) ? french[message] : `FR:${message}`;
}

function loadQuickActions() {
    const context = {
        console,
        document: {
            head: { appendChild() {} },
            documentElement: { getAttribute: () => direction, clientHeight: 800 },
            getElementById() { return null; },
            createElement() {
                return {
                    setAttribute() {},
                    classList: { toggle() {}, add() {}, remove() {} },
                };
            },
        },
        window: {
            AlmdinaLocale: {
                translate,
                direction: () => direction,
            },
            innerHeight: 800,
        },
        frappe: {
            ui: { Dialog: class { constructor() {} show() {} hide() {} } },
            call() { return Promise.resolve({ message: {} }); },
            confirm(message, yes) { if (typeof yes === "function") yes(); },
            show_alert() {},
            msgprint() {},
            session: { user: "worker@example.com" },
            utils: { escape_html: String },
        },
        __(value) { return value; },
    };
    context.window.window = context.window;
    const sandbox = vm.createContext(context);
    armed = false;
    vm.runInContext(quickSource, sandbox);
    armed = true;
    return sandbox.window.AlmdinaShopFloorQuickActions;
}

const api = loadQuickActions();
direction = "rtl";
assert.equal(api.actionFor({ canStart: true }).label, "Demarrer le travail");
assert.equal(api.actionFor({ canHandoff: true }).label, "Terminer et envoyer");
assert.equal(api.actionFor({ canDeliver: true }).label, "Livre");
direction = "ltr";
assert.equal(api.actionFor({ canStart: true }).label, "Demarrer le travail");
assert.equal(api.actionFor({ canDeliver: true }).kind, "deliver");

assert.match(rendererSource, /dir="\$\{pageDir\}"/);
assert.match(rendererSource, /\$section\.attr\("dir", pageDir\)/);
assert.match(rendererSource, /dir="ltr"/);
assert.doesNotMatch(rendererSource, /\bdir\s*=\s*["']rtl["']/);

const pageSource = fs.readFileSync(
    path.join(root, "almdina_erp/page/shop_floor_inbox/shop_floor_inbox.js"),
    "utf8"
);
assert.match(pageSource, /const pageDir = uiDirection\(\)/);
assert.match(pageSource, /\$main\.attr\("dir", pageDir\)/);

assert.match(orderSource, /services\.shop_floor_service\.start_my_stage/);
assert.match(orderSource, /services\.shop_floor_service\.handoff_to_next|openHandoffDialog/);
assert.match(quickSource, /args\.order_name|order_name:/);

console.log("shop floor locale passed");
