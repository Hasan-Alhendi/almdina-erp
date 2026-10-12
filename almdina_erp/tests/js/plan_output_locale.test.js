"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const root = path.resolve(__dirname, "../..");
const planDir = "public/js/door_cutting_order/cutting_plan";
const files = [
    "door_cutting_order_cutting_plan_renderer.js",
    "door_cutting_order_drawing_approval_ux.js",
    "door_cutting_order_drawing_plan_ux.js",
    "door_cutting_order_plan_board_presenter.js",
    "door_cutting_order_plan_content_ux.js",
    "door_cutting_order_plan_context_actions_ux.js",
    "door_cutting_order_plan_source_presentation.js",
    "door_cutting_order_plan_surface_bootstrap.js",
    "door_cutting_order_plan_tabs_ux.js",
    "door_cutting_order_plan_ux.js",
    "door_cutting_order_plan_workspace_presenter_adapter.js",
    "door_cutting_order_text_board_plan_ux.js",
    "secure_dxf_export.js",
    "secure_dxf_upload.js",
];

const compatibility = [
    "رسم",
    "دبل القشاط",
    "دبل كامل",
    "الرسم / DXF",
    "دورة الطلب",
    "تصدير DXF",
    "تصدير DXF للرسم",
    "تصدير DXF للتعديل",
    "تصدير DXF لأوتوكاد",
    "تنزيل DXF المرفوع",
    "تنزيل DXF للإنتاج",
    "رفع ملف DXF",
    "استبدال ملف DXF",
    "اعتماد الرسم",
    "إعادة اعتماد الرسم",
    "طباعة خطة القص",
    "تصدير",
    "تنزيل",
    "الطلب:",
    "الزبون:",
    "اللوح:",
    "الصنف:",
    "مقاس اللوح الكامل",
    "سماكة القص",
    "طريقة الترتيب:",
];

for (const name of files) {
    const source = fs.readFileSync(path.join(root, planDir, name), "utf8");
    let visible = source;
    const phrases = compatibility.slice().sort((left, right) => right.length - left.length);
    for (const phrase of phrases) visible = visible.split(phrase).join("");
    assert.doesNotMatch(visible, /[\u0600-\u06FF]/, name);
    assert.doesNotMatch(source, /^(?:const|let|var)\s+\w+\s*=\s*__\(/m, name);
    assert.doesNotMatch(source, /direction:\s*rtl|labelAr|labelEn|isArabic|lang=["']ar["']/, name);
    assert.doesNotMatch(source, /\.replace\(\s*["']\{0\}["']/, name);
    assert.doesNotMatch(source, /translate\(\s*["'`][^"'`]*[\u0600-\u06FF]/, name);
}

const dxfSource = fs.readFileSync(path.join(root, planDir, "secure_dxf_export.js"), "utf8");
assert.match(dxfSource, /const EXTRA_DOUBLE_DXF_TEXT = "دبل القشاط"/);
assert.match(dxfSource, /const EXTRA_FULL_DOOR_DOUBLE_DXF_TEXT = "دبل كامل"/);
assert.match(dxfSource, /const DXF_VERSION = "AC1009"/);
assert.match(dxfSource, /const DXF_LAYER_COUNT = 8/);
assert.match(dxfSource, /function pair\(code, value\)/);
assert.doesNotMatch(dxfSource, /translate\(\s*EXTRA_DOUBLE_DXF_TEXT/);
assert.doesNotMatch(dxfSource, /translate\(\s*EXTRA_FULL_DOOR_DOUBLE_DXF_TEXT/);

let armed = false;
let direction = "rtl";
const calls = [];
const french = {
    "Cutting plan": "Plan de coupe",
    "System plan": "Plan système",
    "Uploaded plan": "Plan importé",
    "Approved plan": "Plan approuvé",
    "Save or cancel the cutting plan edit before changing the plan source.": "Enregistrez ou annulez avant de changer la source.",
    "There is no system plan to display.": "Aucun plan système.",
    "Approve the system plan": "Approuver le plan système",
    "Print": "Imprimer",
    "Export DXF": "Exporter DXF",
    "Offcut": "Chute",
    "Board {0}": "Panneau {0}",
    "Unassigned": "Non assigné",
    "Door add-on symbols": "Symboles des ajouts",
    "Edge banding double": "Double chant",
    "Save the order before uploading a DXF file.": "Enregistrez la commande avant le DXF.",
    "Approve drawing": "Approuver le dessin",
    "Plan uploaded from DXF": "Plan importé depuis DXF",
    "MaxRects Best Short Side": "MaxRects côté court",
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

function escapeHtml(value) {
    return String(value ?? "")
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;");
}

function jquery(nodes) {
    const api = {
        length: nodes.length,
        nodes,
        find() { return api; },
        first() { return api; },
        html(value) {
            if (value === undefined) return nodes[0] ? nodes[0].html : "";
            nodes.forEach((node) => { node.html = String(value); });
            return api;
        },
        attr(name, value) {
            if (value === undefined) return nodes[0] && nodes[0].attrs[name];
            nodes.forEach((node) => { node.attrs[name] = String(value); });
            return api;
        },
        prop() { return api; },
        off() { return api; },
        on() { return api; },
        empty() { nodes.forEach((node) => { node.html = ""; }); return api; },
        each(callback) {
            nodes.forEach((node, index) => callback(index, node));
            return api;
        },
        removeAttr() { return api; },
    };
    return api;
}

const host = { html: "", attrs: {} };
const fakeWindow = {
    AlmdinaLocale: {
        translate,
        direction() { return direction; },
        currentLanguage() { return direction === "rtl" ? "fr" : "en"; },
    },
    AlmdinaPermissions: {
        can() { return true; },
        canDocument() { return true; },
    },
};
const fakeDocument = {
    documentElement: { getAttribute() { return direction; } },
    getElementById() { return null; },
    createElement() { return { id: "", textContent: "" }; },
};
const messages = [];
const context = vm.createContext({
    window: fakeWindow,
    document: fakeDocument,
    console,
    JSON,
    Number,
    String,
    Math,
    Set,
    Map,
    Object,
    Array,
    __: translate,
    frappe: {
        provide() {},
        msgprint(message) { messages.push(String(message)); },
        utils: { escape_html: escapeHtml },
        ui: { form: { on() {} } },
        almdina: {},
    },
    $: () => jquery([host]),
});

const geometryFiles = [
    "public/js/door_cutting_order/drawing/door_cutting_order_special_shape_geometry.js",
    "public/js/door_cutting_order/drawing/door_cutting_order_shape_output_contract.js",
    "public/js/door_cutting_order/cutting_plan/door_cutting_order_piece_geometry.js",
];
for (const relative of geometryFiles) {
    vm.runInContext(fs.readFileSync(path.join(root, relative), "utf8"), context, { filename: relative });
}
for (const name of [
    "door_cutting_order_cutting_plan_renderer.js",
    "door_cutting_order_plan_tabs_ux.js",
    "door_cutting_order_plan_source_presentation.js",
    "door_cutting_order_drawing_approval_ux.js",
    "secure_dxf_upload.js",
]) {
    vm.runInContext(
        fs.readFileSync(path.join(root, planDir, name), "utf8"),
        context,
        { filename: name }
    );
}
assert.equal(calls.length, 0, "translation must not run while the modules load");
armed = true;

const frm = {
    doc: {
        name: "DCO-LOCALE",
        customer: "زبون خام",
        board_description: "لوح خاص",
        edge_color: "لون خاص",
        status: "Draft",
        pieces: [],
        system_plan_json: JSON.stringify({ sheets: [{ sheet_no: 1, pieces: [{ w: 1, h: 1 }] }] }),
        custom_plan_json: JSON.stringify({ sheets: [{ sheet_no: 1, pieces: [{ w: 1, h: 1 }] }] }),
        production_dxf: "plan.dxf",
    },
    fields_dict: { cutting_plan_html: { $wrapper: jquery([host]) } },
    __almdina_plan_editing: false,
};
const plan = {
    method_key: "MaxRects Best Short Side",
    method_label: "Auto اختار: MaxRects - أفضل ضلع قصير",
    usable_board_width_cm: 122,
    usable_board_length_cm: 244,
    full_board_width_cm: 122,
    full_board_length_cm: 244,
    used_area_m2: 1,
    total_board_area_m2: 2,
    waste_area_m2: 1,
    sheets: [{
        sheet_no: 1,
        resource_kind: "FULL_BOARD",
        pieces: [{
            x: 10, y: 20, w: 30, h: 40,
            original_w: 30, original_h: 40,
            area_m2: 0.12, label: "1", piece_type: "Regular", rotated: false,
        }],
    }, {
        sheet_no: 2,
        resource_kind: "OFFCUT",
        pieces: [],
    }],
};

const renderer = fakeWindow.AlmdinaCuttingPlanRender;
direction = "rtl";
const rtlHtml = renderer.build(frm, plan);
direction = "ltr";
const ltrHtml = renderer.build(frm, plan);
assert.match(rtlHtml, /dir="rtl"/);
assert.match(ltrHtml, /dir="ltr"/);
assert.match(rtlHtml, /Plan de coupe/);
assert.match(rtlHtml, /Panneau 1/);
assert.match(rtlHtml, /Chute/);
assert.match(rtlHtml, /MaxRects côté court/);
assert.match(rtlHtml, /زبون خام/);
assert.match(rtlHtml, /لوح خاص/);
assert.match(rtlHtml, /لون خاص/);
assert.doesNotMatch(rtlHtml, /أفضل ضلع قصير/);
assert.equal(calls.some((message) => /[\u0600-\u06FF]/.test(message)), false);
const rtlPiece = rtlHtml.match(/left:([\d.]+)%;top:([\d.]+)%/);
const ltrPiece = ltrHtml.match(/left:([\d.]+)%;top:([\d.]+)%/);
assert.deepEqual(rtlPiece.slice(1), ltrPiece.slice(1));

assert.equal(fakeWindow.AlmdinaPlanTabsUX.renderDualTabs(frm), true);
assert.match(host.html, /Plan système/);
assert.match(host.html, /Plan importé/);
assert.match(host.html, /Plan approuvé/);
assert.match(host.html, /dir="ltr"/);
direction = "rtl";
fakeWindow.AlmdinaPlanEditSessionUX = { isEditing: () => true };
fakeWindow.AlmdinaPlanTabsUX.renderDualTabs(frm);
assert.match(host.html, /dir="rtl"/);
assert.match(host.html, /Enregistrez ou annulez avant de changer la source/);
assert.match(host.html, /data-plan-tab="System"/);
assert.match(host.html, /data-plan-tab="Custom"/);
assert.match(host.html, /data-plan-tab="Approved"/);

const presentation = fakeWindow.AlmdinaPlanSourcePresentation;
const projected = presentation.project({
    sheets: [{
        resource_kind: "OFFCUT",
        pieces: [{ piece_instance_id: "A" }],
    }],
    __offcut_assignments: [{
        piece_instance_id: "A",
        business_state: "CUSTOMER_FACTORY",
        business_state_label: "فضلة الزبون الخام",
    }],
})[0];
assert.equal(projected.primary_label, "Chute");
assert.equal(Array.from(projected.business_context_labels).join("|"), "فضلة الزبون الخام");
assert.equal(projected.resource_kind, "OFFCUT");

const sources = fakeWindow.AlmdinaDrawingApprovalUX.approvalSources(frm);
assert.equal(sources.map((item) => String(item.value)).join(","), "System,Custom");
assert.equal(sources[1].label, "Plan importé depuis DXF");

messages.length = 0;
fakeWindow.frappe = context.frappe;
context.frappe.almdina.upload_production_dxf({ is_new: () => true });
assert.deepEqual(messages, ["Enregistrez la commande avant le DXF."]);
