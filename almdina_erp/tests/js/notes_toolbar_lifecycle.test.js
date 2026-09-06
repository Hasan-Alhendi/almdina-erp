"use strict";

const assert = require("assert");
const fs = require("fs");
const path = require("path");
const vm = require("vm");

class FakeClassList {
    constructor() {
        this.values = new Set();
    }

    add(value) {
        this.values.add(value);
    }

    toggle(value, enabled) {
        if (enabled) this.values.add(value);
        else this.values.delete(value);
    }
}

function makeButton(label) {
    return {
        nodeType: 1,
        isConnected: true,
        textContent: label,
        title: "",
        dataset: {},
        classList: new FakeClassList(),
        attributes: {},
        setAttribute(name, value) {
            this.attributes[name] = value;
        },
        remove() {
            this.isConnected = false;
        },
    };
}

const formHandlers = {};
const surfaces = new Map();
const documentListeners = {};
const documentContext = {
    registerSurface(name, probe) {
        surfaces.set(name, probe);
        return true;
    },
};

const document = {
    addEventListener(name, handler) {
        documentListeners[name] = handler;
    },
};

const frappe = {
    session: { user: "designer@example.com" },
    ui: {
        form: {
            on(doctype, handlers) {
                formHandlers[doctype] = handlers;
            },
        },
    },
    call() {
        return Promise.resolve({
            message: {
                order: "DCO-TEST",
                counts: { order: 2 },
                important_note_preview: "",
                important_note_comment: "",
            },
        });
    },
    msgprint() {},
};

const window = {
    frappe,
    AlmdinaDocumentContext: documentContext,
    AlmdinaNotesPanel: { openForOrder() {} },
    cur_frm: null,
};

const context = {
    window,
    document,
    frappe,
    console,
    Promise,
    CustomEvent: function CustomEvent(name, init) {
        this.type = name;
        this.detail = init && init.detail;
    },
    __: value => value,
};
context.globalThis = context;
vm.createContext(context);

const uxPath = path.resolve(
    __dirname,
    "../../public/js/door_cutting_order/notes/door_cutting_order_notes_ux.js"
);
vm.runInContext(fs.readFileSync(uxPath, "utf8"), context);

function makeForm(status) {
    const toolbarRoot = {
        button: null,
        querySelector(selector) {
            if (selector !== ".dco-notes-toolbar-button") return null;
            return this.button && this.button.isConnected ? this.button : null;
        },
    };

    return {
        doctype: "Door Cutting Order",
        doc: {
            doctype: "Door Cutting Order",
            name: "DCO-TEST",
            status,
            current_department: status === "At Drawing" ? "رسم" : "",
            current_assignee: status === "At Drawing" ? "designer@example.com" : "",
            important_note_preview: "",
            important_note_comment: "",
        },
        page: { wrapper: toolbarRoot },
        custom_buttons: {},
        is_new() {
            return false;
        },
        add_custom_button(label, handler) {
            const button = makeButton(label);
            button.handler = handler;
            toolbarRoot.button = button;
            this.custom_buttons[label] = [button];
            return [button];
        },
        remove_custom_button(label) {
            const stored = this.custom_buttons[label];
            const node = stored && stored[0];
            if (node) node.isConnected = false;
            delete this.custom_buttons[label];
            if (toolbarRoot.button === node) toolbarRoot.button = null;
        },
    };
}

async function main() {
    const frm = makeForm("Draft");
    window.cur_frm = frm;

    formHandlers["Door Cutting Order"].refresh(frm);
    await Promise.resolve();
    await Promise.resolve();

    const first = frm.page.wrapper.button;
    assert(first && first.isConnected, "Notes action should mount on a saved Draft");
    assert(frm.custom_buttons["الملاحظات"], "Frappe registry key must stay stable");

    // Reproduce the reported lifecycle: Frappe rebuilds the toolbar while the
    // same saved order advances into the Drawing stage for the designer.
    first.isConnected = false;
    frm.page.wrapper.button = null;
    frm.doc.status = "At Drawing";
    frm.doc.current_department = "رسم";
    frm.doc.current_assignee = "designer@example.com";

    const surface = surfaces.get("collaborative-notes-toolbar");
    assert(surface, "Notes toolbar must register with the central DCO surface owner");
    assert.strictEqual(surface.isReady(frm), false, "Detached action must be detected");
    assert.strictEqual(surface.recover(frm), true, "Central lifecycle should recover it");

    const second = frm.page.wrapper.button;
    assert(second && second.isConnected, "Recovered Notes action must be connected");
    assert(second.textContent.startsWith("الملاحظات"), "Presentation label should be restored");
    assert(frm.custom_buttons["الملاحظات"], "Stable registry identity must survive recovery");
    assert.strictEqual(frm.doc.status, "At Drawing");
    assert.strictEqual(frm.doc.current_assignee, "designer@example.com");

    console.log("notes toolbar lifecycle recovery: ok");
}

main().catch(error => {
    console.error(error);
    process.exit(1);
});
