"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const root = path.resolve(__dirname, "../..");
const costDir = "public/js/door_cutting_order/costing";
const files = [
    "door_cutting_order_compact_pricing_ux.js",
    "door_cutting_order_cost_edit_session_ux.js",
    "door_cutting_order_cost_offcut_assignment_ux.js",
    "door_cutting_order_cost_page_layout_ux.js",
    "door_cutting_order_cost_permissions_ux.js",
    "door_cutting_order_cost_presenter.js",
    "door_cutting_order_cost_workspace_api.js",
    "door_cutting_order_cost_workspace_presenter_adapter.js",
    "door_cutting_order_cost_workspace_state.js",
    "door_cutting_order_customer_invoice_addon_summary.js",
    "door_cutting_order_customer_invoice_toolbar_ux.js",
    "door_cutting_order_financial_documents_ux.js",
    "door_cutting_order_multi_edge_documents_ux.js",
];
const compatibility = [
    "تفريغ مسكة مخفية",
    "حفر مسكة غطس",
    "مسكة غطس",
    "لاينر",
    "إضافة",
    "درفة",
    "رقم",
];

for (const name of files) {
    const source = fs.readFileSync(path.join(root, costDir, name), "utf8");
    let visible = source;
    const phrases = compatibility.slice().sort((left, right) => right.length - left.length);
    for (const phrase of phrases) visible = visible.split(phrase).join("");
    assert.doesNotMatch(visible, /[\u0600-\u06FF]/, name);
    assert.doesNotMatch(source, /^(?:const|let|var)\s+\w+\s*=\s*__\(/m, name);
    assert.doesNotMatch(source, /direction:\s*rtl|lang=["']ar["']/, name);
    assert.doesNotMatch(source, /\.replace\(\s*["']\{0\}["']/, name);
    assert.doesNotMatch(source, /translate\(\s*["'`][^"'`]*[\u0600-\u06FF]/, name);
}

for (const name of [
    "door_cutting_order_multi_edge_documents_ux.js",
    "door_cutting_order_cost_page_layout_ux.js",
]) {
    const source = fs.readFileSync(path.join(root, costDir, name), "utf8");
    assert.doesNotMatch(source, /text-align:\s*(?:right|left)\b/, name);
}
const edgeStyles = fs.readFileSync(
    path.join(root, costDir, "door_cutting_order_multi_edge_documents_ux.js"),
    "utf8"
);
assert.match(edgeStyles, /\.dco-cost-table--invoice td:nth-last-child\(-n\+2\)\{direction:ltr/);

const addonSource = fs.readFileSync(
    path.join(root, costDir, "door_cutting_order_customer_invoice_addon_summary.js"),
    "utf8"
);
assert.match(addonSource, /LEGACY_ADDON_PREFIX/);
assert.doesNotMatch(addonSource, /translate\(\s*LEGACY_ADDON_PREFIX/);

const stateSource = fs.readFileSync(
    path.join(root, costDir, "door_cutting_order_cost_workspace_state.js"),
    "utf8"
);
assert.match(stateSource, /new Error\("Could not load the cost data\."\)/);

let armed = true;
let direction = "rtl";
const french = {
    "Order measurement table": "Tableau des mesures",
    "Quotation details": "Details du devis",
    "Final invoice total": "Total final",
    "Offcut price": "Prix des chutes",
    "Offcut price ($)": "Prix des chutes ($)",
    "MDF boards — {0}": "Panneaux MDF — {0}",
    "Board cutting and preparation": "Decoupe des panneaux",
    "Edge banding — {0}": "Chant — {0}",
    "Special": "Speciale",
    "Regular": "Standard",
    "Operating cost breakdown": "Ventilation du cout",
    "Cost item": "Poste",
    "Saving the cost settings...": "Enregistrement des couts...",
    "Liner": "Doublure",
    "Add-on": "Supplement",
    "Door": "Vantail",
    "Board": "Panneau",
    "Meter": "Metre",
    "Unpriced": "Non tarifé",
};

function translate(message, replacements) {
    if (armed) throw new Error(`translate during load: ${message}`);
    let text = Object.prototype.hasOwnProperty.call(french, message) ? french[message] : String(message);
    if (Array.isArray(replacements)) {
        replacements.forEach((value, index) => {
            text = text.split(`{${index}}`).join(String(value));
        });
    }
    return text;
}

function element() {
    return {
        id: "",
        style: {},
        textContent: "",
        setAttribute() {},
        appendChild() {},
        remove() {},
    };
}

const htmlStore = { value: "" };
const rpcCalls = [];
const view = { costs: true };
const context = vm.createContext({
    window: {
        addEventListener() {},
    },
    document: {
        documentElement: { getAttribute: () => direction },
        getElementById: () => null,
        createElement: () => element(),
        head: { appendChild() {} },
    },
    console,
    Object,
    Array,
    Boolean,
    String,
    Number,
    Math,
    JSON,
    Map,
    Set,
    Promise,
    Error,
    frappe: {
        utils: {
            escape_html(value) {
                return String(value ?? "")
                    .replace(/&/g, "&amp;")
                    .replace(/</g, "&lt;")
                    .replace(/>/g, "&gt;")
                    .replace(/"/g, "&quot;");
            },
        },
        ui: { form: { on() {} } },
        xcall(method, args) {
            rpcCalls.push({ method, args });
            return Promise.resolve({ message: { ok: true } });
        },
        call(request) {
            rpcCalls.push(request);
            if (typeof request.callback === "function") request.callback({ message: { ok: true } });
        },
    },
});
context.window.frappe = context.frappe;
context.window.AlmdinaLocale = {
    translate,
    direction: () => direction,
    currentLanguage: () => "fr",
};
context.window.AlmdinaPermissions = {
    canDocument(_frm, capability) {
        if (capability === "view_costs") return view.costs;
        if (capability === "print_customer_invoice") return true;
        return false;
    },
};
context.window.AlmdinaOrderDocumentPrintTheme = {
    headerHtml(_identity, options) {
        return `<header>${options && options.badge || ""}</header>`;
    },
    headerCss: () => "",
};
context.window.AlmdinaFactoryPrintIdentity = { fallback: () => ({}) };

for (const name of [
    "door_cutting_order_cost_presenter.js",
    "door_cutting_order_customer_invoice_addon_summary.js",
    "door_cutting_order_financial_documents_ux.js",
    "door_cutting_order_cost_workspace_api.js",
    "door_cutting_order_cost_workspace_state.js",
    "door_cutting_order_cost_edit_session_ux.js",
]) {
    vm.runInContext(
        fs.readFileSync(path.join(root, costDir, name), "utf8"),
        context,
        { filename: name }
    );
}
armed = false;

const presenter = context.window.AlmdinaOrderCostUX;
const summary = context.window.AlmdinaCustomerInvoiceAddonSummary;
const financial = context.window.AlmdinaFinancialDocuments;
const api = context.window.AlmdinaCostWorkspaceAPI;
const session = context.window.AlmdinaCostEditSessionUX;
assert.equal(typeof presenter.invoiceLines, "function");
assert.equal(typeof session.saveEditing, "function");
assert.equal(typeof session.cancelEditing, "function");
assert.equal(
    api.READ_METHOD,
    "almdina_erp.almdina_erp.services.cost_permission_service.get_order_cost_snapshot"
);
assert.equal(
    api.SAVE_SETTINGS_METHOD,
    "almdina_erp.almdina_erp.services.cost_permission_service.update_order_cost_settings"
);

function form() {
    return {
        doctype: "Door Cutting Order",
        doc: {
            name: "DCO-COST-1",
            customer_name: "زبون خام",
            board_description: "لوح الزبون الخام",
            default_edge_type: "لون القشاط الخام",
            required_boards: 1,
            board_rate_usd: 0,
            cutting_cost_per_board_usd: 5,
            total_cost_usd: 9999,
            mdf_cost_usd: 8888,
            offcut_price_applicable: 1,
            offcut_price_usd: 0,
            pieces: [{
                name: "PIECE-1",
                piece_type: "شكل خام",
                width_cm: 40,
                length_cm: 80,
                qty: 2,
                edge_type: "لون القشاط الخام",
                edge_meters: 3,
                edge_rate_usd: 2,
                edge_cost_usd: 6,
                notes: "ملاحظة الزبون",
            }],
        },
        fields_dict: {
            order_cost_invoice_html: {
                $wrapper: {
                    html(value) {
                        htmlStore.value = value;
                        return this;
                    },
                    empty() {
                        htmlStore.value = "";
                    },
                    find() {
                        return { on() {} };
                    },
                },
            },
        },
    };
}

const frm = form();
direction = "rtl";
assert.equal(presenter.render(frm), true);
assert.match(htmlStore.value, /dir="rtl"/);
assert.match(htmlStore.value, /Tableau des mesures/);
assert.match(htmlStore.value, /Details du devis/);
assert.match(htmlStore.value, /Total final/);
assert.match(htmlStore.value, /Prix des chutes/);
assert.match(htmlStore.value, /لوح الزبون الخام/);
assert.match(htmlStore.value, /لون القشاط الخام/);
assert.match(htmlStore.value, /شكل خام/);
assert.match(htmlStore.value, /ملاحظة الزبون/);
assert.match(htmlStore.value, /0\.00/);
assert.match(htmlStore.value, /value="0"/);
assert.doesNotMatch(htmlStore.value, /9999/);
assert.doesNotMatch(htmlStore.value, /8888/);

direction = "ltr";
presenter.render(frm);
assert.match(htmlStore.value, /dir="ltr"/);
assert.doesNotMatch(htmlStore.value, /dir="rtl"/);

view.costs = false;
presenter.render(frm);
assert.doesNotMatch(htmlStore.value, /Tableau des mesures|Details du devis|Panneaux MDF|0\.00|9999|view_costs/);
view.costs = true;

const lines = presenter.invoiceLines(frm);
const board = lines.find(line => line.type === "material");
const cutting = lines.find(line => line.type === "cutting");
assert.equal(board.amount, 0);
assert.equal(board.rate, 0);
assert.equal(cutting.amount, 5);
assert.equal(cutting.rate, 5);
assert.equal(board.description.includes("لوح الزبون الخام"), true);
assert.equal(lines.some(line => Object.prototype.hasOwnProperty.call(line, "internal_cost_usd")), false);
assert.equal(JSON.stringify(lines).includes("9999"), false);

const summarized = summary.summarizeLines([
    { type: "material", description: "لوح الزبون الخام", quantity: 1, unit: "لوح", rate: 0, amount: 0 },
    {
        type: "extra_addon",
        description: "إضافة لاينر — درفة رقم 2",
        quantity: 1,
        unit: "درفة",
        rate: 4,
        amount: 4,
        note: "ملاحظة الزبون",
        internal_cost_usd: 9999,
    },
]);
assert.equal(summarized[0].description, "لوح الزبون الخام");
assert.equal(summarized[0].amount, 0);
assert.equal(summarized[1].description, "Doublure");
assert.equal(summarized[1].amount, 4);
assert.equal(JSON.stringify(summarized[0]).includes("9999"), false);

const report = financial.documentHtml({
    kind: "internal_cost_report",
    title: "تقرير خام",
    order_name: "DCO-COST-1",
    classification: "داخلي — لا يسلّم للزبون",
    notes: "ملاحظة الزبون",
    generated_by: "محاسب خام",
    cost_breakdown: [{ label: "لوح الزبون الخام", amount_usd: 0 }],
});
assert.match(report, /dir="ltr"/);
assert.match(report, /Ventilation du cout/);
assert.match(report, /Poste/);
assert.match(report, /تقرير خام/);
assert.match(report, /داخلي — لا يسلّم للزبون/);
assert.match(report, /ملاحظة الزبون/);
assert.match(report, /محاسب خام/);
assert.match(report, /لوح الزبون الخام/);
assert.match(report, /0\.00/);

async function verifyLifecycle() {
    const sessionForm = form();
    context.window.cur_frm = sessionForm;
    assert.equal(await session.cancelEditing(sessionForm), false);
    assert.equal(await session.saveEditing(sessionForm), false);
    assert.equal(sessionForm.doc.board_rate_usd, 0);
    assert.equal(sessionForm.doc.total_cost_usd, 9999);
    assert.equal(rpcCalls.length, 0);

    await api.load("DCO-COST-1");
    await api.saveSettings("DCO-COST-1", {
        board_rate_usd: 0,
        cutting_cost_per_board_usd: 5,
        offcut_price_usd: 0,
    });
    assert.equal(rpcCalls[0].method, api.READ_METHOD);
    assert.equal(JSON.stringify(rpcCalls[0].args), JSON.stringify({ order_name: "DCO-COST-1" }));
    assert.equal(rpcCalls[1].method, api.SAVE_SETTINGS_METHOD);
    assert.equal(rpcCalls[1].freeze_message, "Enregistrement des couts...");
    assert.equal(JSON.stringify(rpcCalls[1].args), JSON.stringify({
        order_name: "DCO-COST-1",
        board_rate_usd: 0,
        cutting_cost_per_board_usd: 5,
        offcut_price_usd: 0,
    }));
}

verifyLifecycle().then(() => {
    console.log("cost workspace locale passed");
}).catch(error => {
    console.error(error);
    process.exit(1);
});
