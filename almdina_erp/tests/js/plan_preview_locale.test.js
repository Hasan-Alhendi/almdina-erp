"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const root = path.resolve(__dirname, "../..");
const files = [
    "public/js/door_cutting_order/cutting_plan/door_cutting_order_plan_preview_session.js",
    "public/js/door_cutting_order/cutting_plan/door_cutting_order_plan_preview_presenter.js",
    "public/js/door_cutting_order/cutting_plan/door_cutting_order_plan_preview_edit_ux.js",
    "public/js/door_cutting_order/cutting_plan/door_cutting_order_plan_controls_ux.js",
];

for (const relative of files) {
    const source = fs.readFileSync(path.join(root, relative), "utf8");
    assert.doesNotMatch(source, /[\u0600-\u06FF]/, relative);
    assert.doesNotMatch(source, /^(?:const|let|var)\s+\w+\s*=\s*__\(/m, relative);
    assert.doesNotMatch(source, /direction:\s*rtl|labelAr|labelEn|isArabic|language === ["']ar["']/, relative);
    assert.doesNotMatch(source, /\.replace\(\s*["']\{0\}["']/, relative);
}

const catalog = fs.readFileSync(path.join(root, "translations/ar.csv"), "utf8");
for (const row of [
    "Ready to try,جاهز للتجربة",
    "Recalculate with the current settings,إعادة الحساب بالإعدادات الحالية",
    "{0} mm,{0} مم",
    "Width {0} mm / length {1} mm,عرض {0} مم / طول {1} مم",
]) {
    assert.ok(catalog.includes(row), row);
}

let armed = false;
let direction = "rtl";
const calls = [];
const french = {
    "Ready to try": "Prêt à essayer",
    "The previous preview is out of date": "Aperçu périmé",
    "Calculating the preview": "Calcul de l'aperçu",
    "The preview failed": "L'aperçu a échoué",
    "Change the settings as you like, then press “Recalculate with the current settings” to preview the result. Saving stays unavailable until you preview.": "Modifiez puis recalculez.",
    "The settings were changed. Recalculate to preview the new plan before saving.": "Réglages modifiés.",
    "A temporary preview is being calculated. Nothing is saved during the preview.": "Calcul temporaire.",
    "The preview failed. Adjust the settings if needed, then recalculate.": "Échec de l'aperçu.",
    "The current preview is ready to save. Press “Save” to adopt the same plan shown.": "Aperçu prêt à enregistrer.",
    "Saving the same plan that was previewed.": "Enregistrement du plan prévisualisé.",
    "Recalculate with these settings first, then save the plan shown in front of you.": "Recalculez d'abord.",
    "The preview plan was saved and its related cost was updated.": "Plan enregistré et coût mis à jour.",
    "Recalculate with the current settings": "Recalculer avec les réglages actuels",
    "Press “Edit” to try algorithms and settings. Recalculation creates a preview, and the change is not saved until you press “Save”.": "Appuyez sur Modifier.",
    "Auto Pro (recommended)": "Auto Pro recommandé",
    "MaxRects Best Short Side": "MaxRects côté court",
    "Expected plan cost": "Coût prévu du plan",
    "{0} mm": "{0} mm",
    "Width {0} mm / length {1} mm": "Largeur {0} mm / longueur {1} mm",
    "PREVIEW": "APERÇU",
    "Unsaved preview": "Aperçu non enregistré",
    "This plan is only a preview. The new plan becomes official when you press “Save”.": "Plan provisoire.",
    "This plan and its cost are only a preview. They both become official when you press “Save”.": "Plan et coût provisoires.",
};

function translate(message, replacements) {
    if (!armed) throw new Error(`translation during load: ${message}`);
    calls.push(String(message));
    let text = Object.prototype.hasOwnProperty.call(french, message) ? french[message] : `FR:${message}`;
    if (Array.isArray(replacements)) {
        replacements.forEach((value, index) => {
            text = text.split(`{${index}}`).join(String(value));
        });
    }
    return text;
}

function node(className) {
    return { html: "", text: "", attrs: {}, className, children: [] };
}

function jquery(nodes) {
    const api = {
        length: nodes.length,
        nodes,
        find(selector) {
            const found = [];
            const visit = (current) => {
                if (current.className && String(selector).includes(current.className)) found.push(current);
                for (const child of current.children || []) visit(child);
            };
            for (const current of nodes) visit(current);
            return jquery(found);
        },
        first() { return jquery(nodes.slice(0, 1)); },
        children(selector) { return api.find(selector); },
        prepend(html) {
            nodes.forEach((current) => { current.html = String(html) + current.html; });
            return api;
        },
        html(value) {
            if (value === undefined) return nodes[0] ? nodes[0].html : "";
            nodes.forEach((current) => { current.html = String(value); });
            return api;
        },
        text(value) {
            if (value === undefined) return nodes[0] ? nodes[0].text : "";
            nodes.forEach((current) => { current.text = String(value); });
            return api;
        },
        attr(name, value) {
            if (value === undefined) return nodes[0] && nodes[0].attrs[name];
            nodes.forEach((current) => { current.attrs[name] = String(value); });
            return api;
        },
        prop(name, value) {
            if (value === undefined) return false;
            nodes.forEach((current) => { current.attrs[name] = value; });
            return api;
        },
        removeAttr() { return api; },
        off() { return api; },
        on() { return api; },
        remove() { return api; },
        append() { return api; },
        each(callback) {
            nodes.forEach((current, index) => callback(index, current));
            return api;
        },
        get() { return { __almdinaPlanCommandBound: false }; },
    };
    return api;
}

const content = node("dco-plan-tab-content");
const summary = node("plan-summary");
const note = node("dco-plan-note");
const recalc = node("dco-recalculate-plan");
const shell = node("dco-plan-actions-shell");
shell.children.push(note, recalc);
const actionHost = node("plan-actions-host");
actionHost.children.push(shell);
const planHost = node("plan-host");
planHost.children.push(content);

function wrapper(host) {
    return Object.assign(jquery([host]), {
        find(selector) { return jquery([host]).find(selector); },
    });
}

const messages = [];
const alerts = [];
const apiCalls = [];
let editing = false;
let commitError = null;

const context = {
    console,
    document: {
        documentElement: { getAttribute() { return direction === "ltr" ? "ltr" : "rtl"; } },
        head: node("head"),
        getElementById() { return null; },
    },
    window: {},
    frappe: {
        utils: { escape_html: String },
        msgprint(message) { messages.push(String(message)); },
        show_alert(payload) { alerts.push(String(payload && payload.message || "")); },
        confirm() {},
        ui: { form: { on() {} } },
    },
    $: (selector) => selector === "head" ? jquery([context.document.head]) : jquery([]),
    __: translate,
    requestAnimationFrame(callback) { callback(); return 1; },
    MutationObserver: function MutationObserver() { this.observe = function observe() {}; },
    CustomEvent: function CustomEvent(type, init) { this.type = type; this.detail = init && init.detail; },
};
context.window = context;
context.window.AlmdinaLocale = {
    translate,
    direction() { return direction; },
};
context.window.AlmdinaPlanEditSessionUX = {
    isEditing() { return editing; },
    syncPhaseLocks() {},
    draftCanChange() { return true; },
    startEditing() { return true; },
    cancelEditing() { return true; },
    saveEditing() { return true; },
};
context.window.AlmdinaPermissions = {
    canDocument(_frm, capability) { return capability !== "approve_dxf"; },
};
context.window.AlmdinaPlanWorkspaceState = {
    snapshot() {
        return {
            status: "ready",
            editing: true,
            data: { plans: { system_draft: { settings: {} } }, approved_plan: "" },
        };
    },
    activePlan() { return { settings: {} }; },
    async load() { return { status: "ready", data: {} }; },
};
context.window.AlmdinaPlanWorkspaceAPI = {
    async preview(name, settings) {
        apiCalls.push({ method: "preview", name, settings: { ...settings } });
        if (commitError === "preview") throw new Error("server rejected preview");
        return {
            preview_id: "PV-1",
            plan: { sheets: [{ name: "sheet" }] },
            summary: {
                settings: { ...settings },
                validation: { status: "Valid", needs_recalculation: false },
            },
        };
    },
    async commitPreview(name, previewId) {
        apiCalls.push({ method: "commitPreview", name, previewId });
        if (commitError === "commit") throw new Error("server rejected preview");
        return { ok: true };
    },
};
context.window.addEventListener = function addEventListener() {};
context.window.dispatchEvent = function dispatchEvent() {};

const sources = files.map((relative) => fs.readFileSync(path.join(root, relative), "utf8"));
for (const source of sources) vm.runInContext(source, vm.createContext(context));
assert.equal(calls.length, 0);

armed = true;
const session = context.window.AlmdinaPlanPreviewSession;
const presenter = context.window.AlmdinaPlanPreviewPresenter;
const controls = context.window.AlmdinaPlanControlsUX;
const edit = context.window.AlmdinaPlanEditSessionUX;

async function main() {

function frm() {
    return {
        doctype: "Door Cutting Order",
        doc: {
            doctype: "Door Cutting Order",
            name: "DCO-1",
            status: "Draft",
            docstatus: 0,
            revision_state: "Current",
        },
        is_new() { return false; },
        fields_dict: {
            cutting_plan_html: { $wrapper: wrapper(planHost) },
            plan_controls_intro: { $wrapper: wrapper(summary) },
            plan_control_actions: { $wrapper: wrapper(actionHost) },
        },
    };
}

const order = frm();
context.window.cur_frm = order;

const statusText = {
    idle: "Prêt à essayer",
    stale: "Aperçu périmé",
    previewing: "Calcul de l'aperçu",
    error: "L'aperçu a échoué",
};
for (const status of Object.keys(statusText)) {
    content.html = "";
    direction = "rtl";
    presenter.renderPersistedEditingState(order, status);
    assert.match(content.html, /dir="rtl"/, status);
    assert.match(content.html, new RegExp(statusText[status]), status);
    content.html = "";
    direction = "ltr";
    presenter.renderPersistedEditingState(order, status);
    assert.match(content.html, /dir="ltr"/, status);
    assert.equal(status, status);
}

presenter.renderActionMessage(order, true, "idle", false);
assert.equal(note.text, "Modifiez puis recalculez.");
assert.equal(note.attrs.dir, "ltr");
direction = "rtl";
presenter.renderActionMessage(order, true, "stale", false);
assert.equal(note.text, "Réglages modifiés.");
assert.equal(note.attrs.dir, "rtl");
presenter.renderActionMessage(order, true, "previewing", false);
assert.equal(note.text, "Calcul temporaire.");
presenter.renderActionMessage(order, true, "error", false);
assert.equal(note.text, "Échec de l'aperçu.");
presenter.renderActionMessage(order, true, "ready", true);
assert.equal(note.text, "Aperçu prêt à enregistrer.");

const settings = {
    packing_mode: "auto_pro",
    cutting_machine_type: "Panel Saw",
    kerf_mm: 0,
    trim_margin_mm: 0,
    optimization_time_limit_sec: 0,
};
const previewOk = await session.preview(order, settings);
assert.equal(previewOk, true);
const ready = session.snapshot(order);
assert.equal(ready.status, "ready");
assert.equal(ready.previewId, "PV-1");
assert.equal(apiCalls[0].method, "preview");
assert.equal(apiCalls[0].name, "DCO-1");
assert.deepEqual(apiCalls[0].settings, settings);
assert.equal(session.invalidate(order), true);
assert.equal(session.snapshot(order).status, "stale");
assert.equal(session.snapshot(order).previewId, null);

await session.preview(order, settings);
commitError = "commit";
await assert.rejects(session.commit(order), /server rejected preview/);
const rejected = session.snapshot(order);
assert.equal(rejected.status, "stale");
assert.equal(rejected.previewId, null);
assert.equal(rejected.error, "server rejected preview");
assert.equal(calls.includes("server rejected preview"), false);
assert.equal(calls.includes("Could not save the preview."), false);
commitError = null;

const traced = frm();
presenter.renderPreviewPlan(traced, {
    status: "ready",
    payload: {
        summary: { totals: { required_boards: 1, waste_percent: 2 }, quality: { estimated_cut_count: 3 } },
        plan: {
            sheets: [{ name: "sheet" }],
            execution_trace: {
                version: 1,
                requested: {
                    optimization_mode: "auto_pro",
                    machine_type: "بيانات عشوائية",
                    kerf_mm: 0,
                    preferred_trim_mm: 0,
                },
                adaptive_trim: {
                    applied: false,
                    applied_width_trim_mm: 1,
                    applied_length_trim_mm: 2,
                    reason: "سبب غير معروف",
                },
                optimizer: {
                    method_key: "MaxRects Best Short Side",
                    method_label: "Auto اختار: MaxRects - أفضل ضلع قصير",
                    solver_status: "FEASIBLE",
                    attempts: 4,
                    elapsed_sec: 1,
                },
            },
        },
    },
}, true);
assert.match(summary.html, /Auto Pro recommandé/);
assert.match(summary.html, /بيانات عشوائية/);
assert.match(summary.html, /سبب غير معروف/);
assert.match(summary.html, /MaxRects côté court/);
assert.equal(summary.html.includes("Auto اختار: MaxRects - أفضل ضلع قصير"), false);
assert.match(summary.html, /FEASIBLE/);
assert.match(summary.html, /dir="rtl"/);
assert.equal(summary.html.includes("Coût prévu du plan"), false);
assert.equal(calls.includes("بيانات عشوائية"), false);
assert.equal(calls.includes("سبب غير معروف"), false);
assert.equal(calls.includes("MaxRects Best Short Side"), true);
assert.equal(calls.includes("Auto اختار: MaxRects - أفضل ضلع قصير"), false);
assert.equal(calls.includes("FEASIBLE"), false);
assert.match(content.html, /APERÇU/);
assert.equal(content.html.includes("Coût prévu du plan"), false);

const callsBeforeUnknown = calls.length;
presenter.renderPreviewPlan(traced, {
    status: "ready",
    payload: {
        summary: { totals: {}, quality: {} },
        plan: {
            sheets: [{ name: "sheet" }],
            execution_trace: {
                version: 1,
                requested: {},
                adaptive_trim: {},
                optimizer: {
                    method_key: "vendor_custom_strategy",
                    method_label: "Custom vendor strategy",
                },
            },
        },
    },
}, true);
assert.match(summary.html, /Custom vendor strategy/);
assert.equal(calls.slice(callsBeforeUnknown).includes("vendor_custom_strategy"), false);
assert.equal(calls.slice(callsBeforeUnknown).includes("Custom vendor strategy"), false);

presenter.renderPreviewPlan(traced, {
    status: "ready",
    payload: {
        summary: {
            totals: {},
            quality: {},
            cost: { total_cost_usd: 12.5 },
        },
        plan: { sheets: [{ name: "sheet" }] },
    },
}, true);
assert.match(summary.html, /Coût prévu du plan/);
assert.match(summary.html, /\$ 12\.50/);

direction = "ltr";
controls.apply(order);
assert.equal(recalc.text, "Recalculer avec les réglages actuels");
assert.equal(shell.attrs.dir, "ltr");
assert.equal(note.text, "Appuyez sur Modifier.");

session.reset(order);
editing = true;
const blocked = await edit.saveEditing(order);
assert.equal(blocked, false);
assert.equal(messages.at(-1), "Recalculez d'abord.");

await session.preview(order, settings);
const saved = await edit.saveEditing(order);
assert.equal(saved, true);
assert.equal(alerts.at(-1), "Plan enregistré et coût mis à jour.");
assert.equal(session.snapshot(order).status, "idle");
console.log("plan preview locale ok");
}

main().catch((error) => {
    console.error(error);
    process.exitCode = 1;
});
