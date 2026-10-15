"use strict";

const { test } = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

test("native inputs belong to the current document visit, while B's unsaved edit survives", async () => {
    const handlers = {};
    const elements = {};
    const fields = {};
    for (const name of ["board_description", "board_length_cm", "board_width_cm"]) {
        const element = { value: "", listeners: [] };
        elements[name] = element;
        fields[name] = { df: { fieldname: name }, $input: {
            length: 1, 0: element, get() { return element; },
            val(value) { if (arguments.length) { element.value = value; return this; } return element.value; },
            on(_events, callback) { element.listeners.push(callback); },
        } };
    }
    const frm = {
        doctype: "Door Cutting Order", fields_dict: fields,
        doc: { doctype: "Door Cutting Order", name: "A", board_description: "A White",
            board_length_cm: 244, board_width_cm: 122, pieces: [] },
        is_new() { return false; },
        async set_value(updates) { Object.assign(this.doc, updates); },
    };
    const window = { cur_frm: frm, clearTimeout() {}, setTimeout() { return 1; },
        requestAnimationFrame() {}, dispatchEvent() {}, addEventListener() {} };
    const frappe = { ui: { form: { on(_doctype, hooks) { Object.assign(handlers, hooks); } } },
        model: { new_names: {} }, utils: { escape_html: String } };
    const context = vm.createContext({ window, frappe, console, Set, Map, Object, Number, String,
        Boolean, JSON, Promise, Error, requestAnimationFrame() {},
        CustomEvent: class {}, __: x => x });
    for (const relative of ["core/door_cutting_order_document_context.js",
        "order_entry/door_cutting_order_board_text_ux.js"]) {
        vm.runInContext(fs.readFileSync(path.resolve(__dirname,
            "../../public/js/door_cutting_order", relative), "utf8"), context);
    }
    handlers.before_load(frm);
    handlers.refresh(frm);
    elements.board_description.value = "A White";
    elements.board_description.listeners.forEach(listener => listener());
    const tokenA = window.AlmdinaDocumentContext.capture(frm);
    frm.doc = { doctype: "Door Cutting Order", name: "B", board_description: "B Black",
        board_length_cm: 280, board_width_cm: 130, pieces: [] };
    handlers.before_load(frm);
    assert.equal(elements.board_description.value, "B Black");
    assert.equal(elements.board_length_cm.value, 280);
    assert.equal(window.AlmdinaDocumentContext.isSameDocument(frm, tokenA), false);

    // A stale control read and stale event cannot lend A ownership of B.
    elements.board_description.value = "A White";
    assert.equal((await window.AlmdinaBoardTextUX.syncInputs(frm)).board_description, "B Black");
    assert.equal(frm.doc.board_description, "B Black");

    // An actual B input event carries B's token, so a legitimate unsaved edit
    // is copied into the model before the native Frappe save serializes it.
    elements.board_description.value = "B New Black";
    elements.board_description.listeners.forEach(listener => listener());
    elements.board_length_cm.value = "301";
    elements.board_length_cm.listeners.forEach(listener => listener());
    const saved = await handlers.before_save(frm);
    assert.equal(saved.board_description, "B New Black");
    assert.equal(frm.doc.board_length_cm, 301);
    assert.equal(frm.doc.full_board_length_mm, 3010);
});
