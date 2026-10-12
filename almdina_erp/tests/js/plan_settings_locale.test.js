"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const root = path.resolve(__dirname, "../..");
const files = [
    "public/js/door_cutting_order/cutting_plan/door_cutting_order_plan_edit_session_ux.js",
    "public/js/door_cutting_order/cutting_plan/door_cutting_order_plan_settings_summary_ux.js",
    "public/js/door_cutting_order/cutting_plan/door_cutting_order_fast_save_ux.js",
    "public/js/door_cutting_order/cutting_plan/door_cutting_order_plan_workspace_api.js",
];

for (const relative of files) {
    const source = fs.readFileSync(path.join(root, relative), "utf8");
    assert.doesNotMatch(source, /^(?:const|let|var)\s+\w+\s*=\s*__\(/m, relative);
    assert.doesNotMatch(source, /direction:\s*rtl|labelAr|labelEn|isArabic|language === ["']ar["']/, relative);
    assert.doesNotMatch(source, /\.replace\(\s*["']\{0\}["']/, relative);
}

const catalog = fs.readFileSync(path.join(root, "translations/ar.csv"), "utf8");
for (const row of [
    "Auto Pro (recommended),تلقائي متقدم (موصى به)",
    "Panel Saw,منشار ألواح",
    "Cutting plan settings,إعدادات خطة القص",
    "{0} — currently unavailable,{0} — غير متاح حاليًا",
]) {
    assert.ok(catalog.includes(row), row);
}

let armed = false;
let direction = "ltr";
const calls = [];
const french = {
    "Saw blade thickness (mm)": "Épaisseur de lame (mm)",
    "Blade": "Lame",
    "Auto Pro (recommended)": "Auto Pro recommandé",
    "Panel Saw": "Scie à panneaux",
    "Genetic algorithm": "Algorithme génétique",
    "Plan settings": "Réglages du plan",
    "A valid value is required for {0}.": "Valeur requise pour {0}.",
    "{0} — {1}": "{0} — {1}",
    "Recalculating the cutting plan and cost in the background": "Recalcul en arrière-plan",
    "You can keep working on the order. The cutting plan and cost will update automatically when the calculation finishes.": "Vous pouvez continuer.",
    "The cutting plan needs recalculation — press “Recalculate with the current settings” when you finish.": "Le plan doit être recalculé.",
    "Saving cutting plan settings...": "Enregistrement des réglages...",
    "mm": "mm",
    "seconds": "s",
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

function element(tag) {
    const children = [];
    const attributes = {};
    const node = {
        nodeType: 1,
        tagName: String(tag || "div").toUpperCase(),
        children,
        parentElement: null,
        className: "",
        innerHTML: "",
        setAttribute(name, value) { attributes[name] = String(value); },
        getAttribute(name) { return Object.prototype.hasOwnProperty.call(attributes, name) ? attributes[name] : null; },
        appendChild(child) {
            child.parentElement = node;
            child.parentNode = node;
            children.push(child);
            return child;
        },
        insertBefore(child) { return node.appendChild(child); },
        querySelector(selector) {
            const match = String(selector).match(/\[([\w-]+)="([^"]+)"\]/);
            const visit = (current) => {
                if (
                    match
                    && current.getAttribute
                    && current.getAttribute(match[1]) === match[2]
                ) return current;
                for (const child of current.children || []) {
                    const found = visit(child);
                    if (found) return found;
                }
                return null;
            };
            return visit(node);
        },
    };
    node.parentNode = null;
    return node;
}

const catalogs = {
    optimization_catalog: [
        { id: "auto_pro", label: "تلقائي متقدم (موصى به)", available: true },
        { id: "genetic", label: "الخوارزمية الجينية", available: false },
        { id: "legacy-custom", label: "بيانات عشوائية", available: true },
    ],
    machine_type_catalog: [
        { id: "Panel Saw", label: "منشار ألواح", available: true },
        { id: "CNC Router", label: "CNC Router", available: true },
    ],
};

function load() {
    const document = {
        documentElement: element("html"),
        head: element("head"),
        body: element("body"),
        getElementById() { return null; },
        createElement: element,
    };
    document.documentElement.setAttribute("dir", "rtl");
    const window = {
        document,
        addEventListener() {},
        requestAnimationFrame(callback) { callback(); return 0; },
        AlmdinaLocale: {
            translate,
            direction() { return direction; },
            isRTL() { return direction === "rtl"; },
        },
    };
    const frappe = {
        ui: { form: { on() {} } },
        utils: { escape_html(value) { return String(value ?? ""); } },
        call(options) {
            window.calls.push(options);
            return Promise.resolve({ message: { ok: true, message: "رسالة الخادم الجاهزة" } });
        },
    };
    window.calls = [];
    const context = vm.createContext({
        window,
        document,
        frappe,
        __: translate,
        $: () => ({ append() {} }),
        Object, Boolean, String, Number, Array, Map, Promise, Math, Date, Set, console,
    });
    for (const relative of files) {
        vm.runInContext(fs.readFileSync(path.join(root, relative), "utf8"), context);
    }
    return { window, document };
}

armed = false;
const loaded = load();
armed = true;
assert.equal(calls.length, 0);

const workspace = {
    snapshot() {
        return { status: "ready", editing: false, data: catalogs };
    },
    storeFor() {
        return { snapshot: workspace.snapshot };
    },
};
loaded.window.AlmdinaPlanWorkspaceState = workspace;

const editor = loaded.window.AlmdinaPlanEditSessionUX;
const specs = editor.planSettingSpecs({}, { packing_mode: "auto_pro", cutting_machine_type: "Panel Saw" });
const packing = specs.find((spec) => spec.fieldname === "packing_mode");
const machine = specs.find((spec) => spec.fieldname === "cutting_machine_type");
const autoPro = packing.options.find((option) => option.value === "auto_pro");
const genetic = packing.options.find((option) => option.value === "genetic");
const unknown = packing.options.find((option) => option.value === "legacy-custom");
const panelSaw = machine.options.find((option) => option.value === "Panel Saw");
assert.equal(autoPro.label, "Auto Pro (recommended)");
assert.equal(autoPro.canonical, true);
assert.equal(autoPro.value, "auto_pro");
assert.equal(genetic.available, false);
assert.equal(genetic.label, "Genetic algorithm");
assert.equal(unknown.canonical, false);
assert.equal(unknown.label, "بيانات عشوائية");
assert.equal(panelSaw.value, "Panel Saw");
assert.equal(panelSaw.label, "Panel Saw");
assert.equal(calls.includes("بيانات عشوائية"), false);
assert.equal(calls.includes("تلقائي متقدم (موصى به)"), false);
assert.equal(calls.includes("منشار ألواح"), false);

assert.equal(editor.validateDraft({
    kerf_mm: 0,
    trim_margin_mm: 0,
    packing_mode: "auto_pro",
    cutting_machine_type: "Panel Saw",
    optimization_time_limit_sec: 0,
}, {}), "");
assert.equal(
    editor.validateDraft({
        kerf_mm: 0,
        trim_margin_mm: 0,
        packing_mode: "genetic",
        cutting_machine_type: "Panel Saw",
        optimization_time_limit_sec: 0,
    }, {}),
    "Valeur requise pour FR:Piece packing algorithm."
);

const anchor = element("div");
const form = element("div");
form.appendChild(anchor);
loaded.window.AlmdinaPlanWorkspacePresenterAdapter = {
    activeSettings() {
        return {
            kerf_mm: 0,
            trim_margin_mm: 4,
            packing_mode: "legacy-custom",
            cutting_machine_type: "Panel Saw",
            optimization_time_limit_sec: 12,
        };
    },
};
const summaryForm = {
    doctype: "Door Cutting Order",
    doc: { name: "26-00089" },
    wrapper: form,
    fields_dict: { plan_actions_section: { wrapper: anchor } },
};
direction = "rtl";
assert.equal(loaded.window.AlmdinaPlanSettingsSummaryUX.render(summaryForm), true);
const summary = form.querySelector('[data-almdina-plan-settings-summary-owner="stable"]');
assert.equal(summary.getAttribute("dir"), "rtl");
assert.match(summary.innerHTML, /value="0"/);
assert.match(summary.innerHTML, /بيانات عشوائية/);
assert.match(summary.innerHTML, /Scie à panneaux/);
assert.match(summary.innerHTML, /Réglages du plan/);
assert.equal(calls.includes("بيانات عشوائية"), false);
direction = "ltr";
loaded.window.AlmdinaPlanSettingsSummaryUX.render(summaryForm);
assert.equal(summary.getAttribute("dir"), "ltr");

const banners = [];
const fastForm = {
    doctype: "Door Cutting Order",
    doc: { plan_needs_recalculation: 1, cutting_plan_json: "{}" },
    fields_dict: {
        plan_control_actions: {
            $wrapper: {
                find() {
                    const chain = {
                        length: 0,
                        remove() { return chain; },
                        each() { return chain; },
                        text() { return chain; },
                        attr() { return chain; },
                        removeAttr() { return chain; },
                        addClass() { return chain; },
                        removeClass() { return chain; },
                        first() { return chain; },
                    };
                    return chain;
                },
                prepend(html) { banners.push(html); },
            },
        },
    },
};
loaded.window.AlmdinaFastSaveUX.renderStaleState(fastForm);
assert.match(banners.at(-1), /Le plan doit être recalculé/);

async function exerciseSave() {
    const recorded = [];
    loaded.window.calls = recorded;
    await loaded.window.AlmdinaPlanWorkspaceAPI.saveSettings("26-00089", {
        packing_mode: "auto_pro",
        cutting_machine_type: "Panel Saw",
        kerf_mm: 0,
    });
    assert.equal(recorded[0].freeze_message, "Enregistrement des réglages...");
    assert.equal(recorded[0].args.packing_mode, "auto_pro");
    assert.equal(recorded[0].args.cutting_machine_type, "Panel Saw");
    assert.equal(recorded[0].args.kerf_mm, 0);
    assert.equal(recorded[0].method.includes("save_plan_settings"), true);
    console.log("plan settings locale ok");
}

exerciseSave().catch((error) => {
    console.error(error);
    process.exit(1);
});
