"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

function readSource(relativePath) {
    return fs.readFileSync(path.resolve(__dirname, "../../", relativePath), "utf8");
}

const source = readSource(
    "public/js/door_cutting_order/costing/door_cutting_order_cost_workspace_presenter_adapter.js"
);

let legacyInvoiceCalls = 0;
const payload = {
    order_name: "DCO-178-PREVIEW",
    order: {
        required_boards: 0,
        board_rate_usd: 40,
        cutting_cost_per_board_usd: 5,
        offcut_price_usd: 75,
        offcut_price_applicable: true,
        offcut_factory_factory: true,
    },
    pieces: [
        {
            name: "ROW-1",
            qty: 5,
            factory_execution_qty: 4,
            factory_execution_ratio: 0.8,
        },
        {
            name: "ROW-2",
            qty: 1,
            factory_execution_qty: 0,
            factory_execution_ratio: 0,
        },
    ],
    invoice_preview_lines: [
        {
            type: "offcut",
            description: "سعر الفضلة",
            quantity: 1,
            unit: "مجموعة",
            rate_usd: 75,
            amount_usd: 75,
            note: "سعر إجمالي للمجموعة",
        },
        {
            type: "extra_addon",
            description: "إضافة Liner — درفة رقم 1",
            quantity: 4,
            unit: "درفة",
            rate_usd: 3,
            amount_usd: 12,
        },
    ],
    invoice_preview_total_usd: 87,
    pending_factory_price_labels: [],
};

const legacy = {
    render() {
        return true;
    },
    refreshInvoiceSection() {
        return true;
    },
    invoiceLines() {
        legacyInvoiceCalls += 1;
        return [{ type: "legacy", amount: 999 }];
    },
    invoiceTotal() {
        return 999;
    },
    quoteTotal() {
        return 999;
    },
};

const fakeWindow = {
    AlmdinaOrderCostUX: legacy,
    AlmdinaCostWorkspaceState: {
        snapshot() {
            return { status: "ready", data: payload };
        },
        canView() {
            return true;
        },
    },
    addEventListener() {},
    cur_frm: null,
};
const fakeFrappe = {
    utils: {
        escape_html(value) {
            return String(value);
        },
    },
};
const context = vm.createContext({
    window: fakeWindow,
    frappe: fakeFrappe,
    console,
    Object,
    Array,
    Map,
    Set,
    Boolean,
    Number,
    String,
    Math,
    Promise,
    __: value => value,
});

vm.runInContext(source, context, {
    filename: "door_cutting_order_cost_workspace_presenter_adapter.js",
});

const api = fakeWindow.AlmdinaOrderCostUX;
assert.ok(api && api.__a52WorkspaceOwned, "Cost presenter must be workspace-owned");

const frm = {
    doctype: "Door Cutting Order",
    doc: {
        name: "DCO-178-PREVIEW",
        pieces: [
            { name: "ROW-1", qty: 5 },
            { name: "ROW-2", qty: 1 },
        ],
    },
    fields_dict: {},
};

const lines = api.invoiceLines(frm);
assert.deepEqual(
    JSON.parse(JSON.stringify(lines)),
    [
        {
            type: "offcut",
            description: "سعر الفضلة",
            quantity: 1,
            unit: "مجموعة",
            rate: 75,
            amount: 75,
            pending: false,
            note: "سعر إجمالي للمجموعة",
        },
        {
            type: "extra_addon",
            description: "إضافة Liner — درفة رقم 1",
            quantity: 4,
            unit: "درفة",
            rate: 3,
            amount: 12,
            pending: false,
            note: "",
        },
    ],
    "Cost UI must consume the canonical server invoice preview"
);
assert.equal(legacyInvoiceCalls, 0, "ready Cost workspace must not rebuild invoice from legacy DCO qty");
assert.equal(api.invoiceTotal(frm), 87);
assert.equal(api.quoteTotal(frm), 87);
assert.equal(frm.doc.pieces[0].qty, 5, "customer requirement qty must remain unchanged");
assert.equal(frm.doc.pieces[0].factory_execution_qty, 4);
assert.equal(frm.doc.pieces[1].factory_execution_qty, 0);
assert.equal(
    source.includes("setTimeout("),
    false,
    "canonical preview adapter must not introduce timer-based reconciliation"
);

function verifyPresenterOwnsOffcutPriceSurface() {
    const presenterSource = readSource(
        "public/js/door_cutting_order/costing/door_cutting_order_cost_presenter.js"
    );
    let rendered = "";
    let canViewCosts = true;
    let canPrintInvoice = true;
    const styles = new Map();
    const emptySelection = {
        length: 0,
        first() { return this; },
        on() { return this; },
    };
    const wrapper = {
        length: 1,
        html(value) {
            if (value === undefined) return rendered;
            rendered = String(value);
            return this;
        },
        empty() {
            rendered = "";
            return this;
        },
        find() {
            return emptySelection;
        },
    };
    const presenterWindow = {
        AlmdinaPermissions: {
            canDocument(_target, capability) {
                if (capability === "view_costs") return canViewCosts;
                if (capability === "print_customer_invoice") return canPrintInvoice;
                return false;
            },
        },
    };
    const presenterFrappe = {
        utils: {
            escape_html(value) {
                return String(value);
            },
        },
    };
    const fakeDocument = {
        head: {
            appendChild(element) {
                if (element && element.id) styles.set(element.id, element);
            },
        },
        getElementById(id) {
            return styles.get(id) || null;
        },
        createElement() {
            return { id: "", textContent: "" };
        },
    };
    const presenterContext = vm.createContext({
        window: presenterWindow,
        frappe: presenterFrappe,
        document: fakeDocument,
        console,
        Object,
        Array,
        Map,
        Set,
        Boolean,
        Number,
        String,
        Math,
        __: value => String(value),
    });
    vm.runInContext(presenterSource, presenterContext, {
        filename: "door_cutting_order_cost_presenter.js",
    });

    const presenterFrm = {
        doctype: "Door Cutting Order",
        doc: {
            name: "DCO-OFFCUT-PRICE",
            pieces: [],
            required_boards: 0,
            mdf_cost_usd: 0,
            cutting_cost_usd: 0,
            edge_cost_usd: 0,
            total_cost_usd: 0,
            offcut_price_usd: 0,
            offcut_price_applicable: false,
        },
        fields_dict: {
            order_cost_invoice_html: { $wrapper: wrapper },
        },
    };

    assert.equal(presenterWindow.AlmdinaOrderCostUX.render(presenterFrm), true);
    assert.equal(
        rendered.includes("data-offcut-price-section"),
        false,
        "OFFCUT price surface must stay absent when server applicability is false"
    );

    presenterFrm.doc.offcut_price_applicable = true;
    presenterFrm.doc.offcut_price_usd = 0;
    presenterWindow.AlmdinaOrderCostUX.render(presenterFrm);
    assert.equal(
        rendered.includes("data-offcut-price-section"),
        true,
        "FACTORY+FACTORY applicability must render a stable presenter-owned OFFCUT price surface"
    );
    assert.equal(rendered.includes("data-offcut-price-input"), true);
    assert.equal(
        rendered.includes('value="0" disabled readonly'),
        true,
        "zero is a valid OFFCUT price and must remain visible in read mode"
    );

    presenterFrm.doc.offcut_price_usd = 8.5;
    presenterWindow.AlmdinaOrderCostUX.render(presenterFrm);
    assert.equal(rendered.includes('value="8.5" disabled readonly'), true);

    canViewCosts = false;
    canPrintInvoice = true;
    presenterWindow.AlmdinaOrderCostUX.render(presenterFrm);
    assert.equal(
        rendered.includes("data-offcut-price-section"),
        false,
        "print-only authority must not expose the internal Cost-tab price editor surface"
    );
}

function verifyEditSessionBindsStablePresenterInput() {
    const editSource = readSource(
        "public/js/door_cutting_order/costing/door_cutting_order_cost_edit_session_ux.js"
    );
    assert.equal(
        editSource.includes("dco-offcut-price-editor"),
        false,
        "edit session must not own structural OFFCUT section markup"
    );
    assert.equal(
        editSource.includes('.find(".dco-cost-shell").first().prepend(control)'),
        false,
        "edit session must not inject children into the presenter-owned Cost shell"
    );
    assert.equal(editSource.includes('[data-offcut-price-input]'), true);

    const inputState = {
        value: "0",
        disabled: true,
        readOnly: true,
        handlers: new Map(),
    };
    const input = {
        length: 1,
        first() { return this; },
        off() {
            inputState.handlers.clear();
            return this;
        },
        val(value) {
            if (arguments.length === 0) return inputState.value;
            inputState.value = String(value);
            return this;
        },
        prop(name, value) {
            if (arguments.length === 1) return inputState[name];
            inputState[name] = value;
            return this;
        },
        on(name, handler) {
            inputState.handlers.set(name, handler);
            return this;
        },
    };
    const emptyControl = {
        length: 0,
        first() { return this; },
        attr() { return this; },
    };
    const nativeField = () => ({
        df: {},
        refresh() {},
        $wrapper: {
            length: 1,
            find() { return emptyControl; },
        },
    });
    const costWrapper = {
        length: 1,
        find(selector) {
            return selector === "[data-offcut-price-input]" ? input : emptyControl;
        },
    };
    const draft = {
        board_rate_usd: 22,
        cutting_cost_per_board_usd: 2.5,
        offcut_price_applicable: true,
        offcut_price_usd: 0,
    };
    let editing = true;
    let latestPatch = null;
    const store = {
        snapshot() {
            return {
                status: "ready",
                editing,
                draft: editing ? { ...draft } : null,
                data: { order: { ...draft } },
                dirty: false,
            };
        },
        patchDraft(patch) {
            latestPatch = { ...patch };
            Object.assign(draft, patch);
            return true;
        },
        cancelEdit() {
            editing = false;
            return true;
        },
    };
    const editFrm = {
        doctype: "Door Cutting Order",
        doc: {
            name: "DCO-OFFCUT-EDIT",
            docstatus: 0,
            revision_state: "Current",
            status: "Draft",
            offcut_price_usd: 0,
        },
        fields_dict: {
            board_rate_usd: nativeField(),
            cutting_cost_per_board_usd: nativeField(),
            order_cost_invoice_html: { $wrapper: costWrapper },
        },
        is_new() { return false; },
        is_dirty() { return false; },
        trigger() {},
    };
    const editWindow = {
        cur_frm: editFrm,
        addEventListener() {},
        requestAnimationFrame(callback) { callback(); },
        AlmdinaPermissions: {
            canDocument() { return true; },
        },
        AlmdinaCostWorkspaceState: {
            storeFor() { return store; },
            snapshot() { return store.snapshot(); },
            settings() { return { ...draft }; },
        },
        AlmdinaWorkspaceFieldEditor: {
            mount() {},
            unmount() {},
            focus() {},
        },
        AlmdinaCostWorkspacePresenterAdapter: {
            project() {},
        },
        AlmdinaCostPermissionsUX: {
            pendingPricePieces() { return []; },
            async flushPendingPriceEdits() { return false; },
            async discardPendingPriceEdits() { return false; },
        },
    };
    const editFrappe = {
        ui: { form: { on() {} } },
        msgprint() {},
        show_alert() {},
    };
    const editContext = vm.createContext({
        window: editWindow,
        frappe: editFrappe,
        console,
        Promise,
        Object,
        Array,
        Map,
        Set,
        String,
        Number,
        Boolean,
        JSON,
        Date,
        __: value => String(value),
    });
    vm.runInContext(editSource, editContext, {
        filename: "door_cutting_order_cost_edit_session_ux.js",
    });

    const editApi = editWindow.AlmdinaCostEditSessionUX;
    editApi.sync(editFrm);
    assert.equal(inputState.disabled, false, "edit mode must enable the existing presenter input");
    assert.equal(inputState.readOnly, false);
    assert.equal(inputState.value, "0", "zero-value draft must not disappear when entering edit mode");

    inputState.value = "12.5";
    const inputHandler = inputState.handlers.get("input.almdinaOffcutPrice");
    assert.ok(inputHandler, "edit mode must bind one namespaced input handler");
    inputHandler({ currentTarget: { value: "12.5" } });
    assert.deepEqual(latestPatch, { offcut_price_usd: "12.5" });
    assert.equal(editApi.captureCostSettings(editFrm, draft).offcut_price_usd, "12.5");

    editing = false;
    editApi.sync(editFrm);
    assert.equal(inputState.disabled, true, "read mode must keep the same input and disable editing");
    assert.equal(inputState.readOnly, true);
}

verifyPresenterOwnsOffcutPriceSurface();
verifyEditSessionBindsStablePresenterInput();

console.log("ALMADINA-178 Cost preview + OFFCUT price presenter lifecycle simulation passed");
