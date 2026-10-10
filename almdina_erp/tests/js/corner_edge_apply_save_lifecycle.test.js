"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const CORNER_UX = path.resolve(
    __dirname,
    "../../public/js/door_cutting_order/drawing/door_cutting_order_clipped_corner_ux.js"
);

function classList(initial = []) {
    const values = new Set(initial);
    return {
        add(value) { values.add(value); },
        remove(value) { values.delete(value); },
        contains(value) { return values.has(value); },
        toggle(value, enabled) {
            if (enabled === undefined ? !values.has(value) : enabled) values.add(value);
            else values.delete(value);
        },
    };
}

function control(options = {}) {
    return {
        value: String(options.value ?? ""),
        dataset: { ...(options.dataset || {}) },
        disabled: false,
        classList: classList(options.classes || []),
        listeners: {},
        textContent: "",
        innerHTML: "",
        addEventListener(type, handler) { this.listeners[type] = handler; },
        setAttribute() {},
        querySelector(selector) {
            return selector === ".dco-check-mark" ? { textContent: "" } : null;
        },
        select() {},
    };
}

function editorRoot() {
    const position = control({
        dataset: { position: "Top Right" },
        classes: ["dco-corner-position", "is-active"],
    });
    const width = control({ value: 80 });
    const length = control({ value: 160 });
    const preview = control();
    const help = control();
    const equal = control();
    const edgeButtons = [
        "edge_width_top",
        "edge_width_bottom",
        "edge_long_right",
        "edge_long_left",
        "edge_break",
        "edge_break_only",
    ].map((fieldname) => control({ dataset: { cornerEdge: fieldname } }));

    return {
        _cornerEdgeDraft: null,
        edgeButtons,
        querySelector(selector) {
            const values = {
                ".dco-corner-position.is-active": position,
                "[data-corner-remaining='width']": width,
                "[data-corner-remaining='length']": length,
                "[data-corner-preview]": preview,
                "[data-corner-help]": help,
                ".dco-corner-equal": equal,
            };
            return values[selector] || null;
        },
        querySelectorAll(selector) {
            if (selector === ".dco-corner-position") return [position];
            if (selector === "[data-corner-remaining]") return [width, length];
            if (selector === "[data-corner-edge]") return edgeButtons;
            if (selector === "input,button") return [position, width, length, equal, ...edgeButtons];
            return [];
        },
    };
}

function createSandbox() {
    const formHandlers = {};
    const dialogs = [];
    const rowsByName = Object.create(null);
    const setValueGates = [];
    const root = editorRoot();

    class Dialog {
        constructor(options) {
            this.options = options;
            this.hidden = false;
            this.$wrapper = {
                addClass() { return this; },
                on() { return this; },
                find() { return { get() { return root; } }; },
            };
            this.fields_dict = {
                corner_editor: {
                    $wrapper: {
                        html() {},
                        find() { return { get() { return root; } }; },
                    },
                },
            };
            dialogs.push(this);
        }
        show() {}
        hide() { this.hidden = true; }
        disable_primary_action() {}
        enable_primary_action() {}
    }

    const document = {
        documentElement: { lang: "ar" },
        getElementById() { return null; },
        createElement() { return { id: "", textContent: "" }; },
        head: { appendChild() {} },
    };
    const window = { document };
    const frappe = {
        boot: { lang: "ar" },
        model: {
            new_names: {},
            set_value(doctype, name, fieldname, value) {
                const row = rowsByName[name];
                if (row && row.doctype === doctype) row[fieldname] = value;
                return new Promise((resolve) => setValueGates.push(resolve));
            },
        },
        ui: {
            Dialog,
            form: {
                on(doctype, handlers) {
                    formHandlers[doctype] = Object.assign(formHandlers[doctype] || {}, handlers);
                },
            },
        },
        msgprint() {},
        show_alert() {},
    };
    function $(value) { return value; }
    $.isPlainObject = (value) => Boolean(value && value.constructor === Object);

    const sandbox = vm.createContext({
        window,
        document,
        frappe,
        $,
        console,
        Object,
        String,
        Number,
        Boolean,
        Promise,
        Set,
        Map,
        WeakMap,
    });
    window.window = window;
    window.frappe = frappe;

    vm.runInContext(fs.readFileSync(CORNER_UX, "utf8"), sandbox, { filename: CORNER_UX });
    return { window, frappe, formHandlers, dialogs, rowsByName, setValueGates, root };
}

function cornerRow(name, overrides = {}) {
    return {
        doctype: "Door Cutting Order Detail",
        name,
        idx: 1,
        piece_no: 1,
        piece_type: "Clipped Corner",
        width_cm: 100,
        length_cm: 200,
        clipped_corner_position: "Top Right",
        clipped_corner_width_cm: 20,
        clipped_corner_length_cm: 40,
        edge_width_top: 0,
        edge_width_bottom: 0,
        edge_long_right: 0,
        edge_long_left: 0,
        edge_break: 0,
        edge_break_only: 1,
        ...overrides,
    };
}

async function waitForGate(gates, index) {
    for (let attempts = 0; attempts < 20 && gates.length <= index; attempts += 1) {
        await Promise.resolve();
    }
    assert.ok(gates.length > index, `set_value gate ${index} should have started`);
}

async function drainSetValues(gates, expected) {
    for (let index = 0; index < expected; index += 1) {
        await waitForGate(gates, index);
        gates[index]();
        await Promise.resolve();
    }
}

async function run() {
    const env = createSandbox();
    const beforeSave = env.formHandlers["Door Cutting Order"]?.before_save;
    assert.equal(
        typeof beforeSave,
        "function",
        "corner Apply must register a before_save barrier for an immediate Save"
    );

    const provisional = cornerRow("new-door-cutting-order-detail-1");
    const persisted = cornerRow("saved-piece-1", {
        piece_instance_id: "piece:stable-1",
    });
    const frm = {
        doctype: "Door Cutting Order",
        doc: { doctype: "Door Cutting Order", name: "DCO-1", pieces: [provisional] },
        dirtyCalls: 0,
        dirty() { this.dirtyCalls += 1; },
    };
    env.rowsByName[provisional.name] = provisional;

    env.window.AlmdinaClippedCornerEditor.open(frm, provisional);
    assert.equal(env.dialogs.length, 1);

    // Frappe's first Save promotes the local child name. The dialog remains open,
    // so Apply must resolve the current child instead of writing its closed-over row.
    env.frappe.model.new_names[provisional.name] = persisted.name;
    delete env.rowsByName[provisional.name];
    env.rowsByName[persisted.name] = persisted;
    frm.doc.pieces = [persisted];

    env.root._cornerEdgeDraft = {
        edge_width_top: 0,
        edge_width_bottom: 1,
        edge_long_right: 0,
        edge_long_left: 1,
        edge_break: 1,
        edge_break_only: 0,
        clipped_corner_position: "Top Right",
        piece_type: "Clipped Corner",
    };

    const applyResult = env.dialogs[0].options.primary_action();
    assert.ok(applyResult && typeof applyResult.then === "function", "Apply must expose its completion");

    let saveBarrierSettled = false;
    const saveBarrier = beforeSave(frm).then(() => { saveBarrierSettled = true; });
    await Promise.resolve();
    assert.equal(saveBarrierSettled, false, "Save must wait while corner fields are still being applied");

    await drainSetValues(env.setValueGates, 9);
    await applyResult;
    await saveBarrier;

    assert.equal(persisted.edge_break, 1);
    assert.equal(persisted.edge_break_only, 0);
    assert.equal(persisted.edge_width_bottom, 1);
    assert.equal(persisted.edge_long_left, 1);
    assert.equal(provisional.edge_break, 0, "the detached provisional row must not be mutated");
    assert.equal(frm.dirtyCalls, 1, "Apply must mark the current form modified exactly once");

    // The persisted model is the source for a direct reopen; no page refresh is needed.
    env.window.AlmdinaClippedCornerEditor.open(frm, persisted);
    assert.equal(env.dialogs.length, 2);
    assert.equal(env.root._cornerEdgeDraft.edge_break, 1);
    assert.equal(env.root._cornerEdgeDraft.edge_break_only, 0);
}

run().then(
    () => console.log("corner edge apply/save lifecycle tests passed"),
    (error) => {
        console.error(error);
        process.exitCode = 1;
    }
);
