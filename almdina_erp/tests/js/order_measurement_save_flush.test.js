"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

function load(relativePath, sandbox) {
    const filename = path.resolve(__dirname, "../../", relativePath);
    vm.runInContext(
        fs.readFileSync(filename, "utf8"),
        sandbox,
        { filename }
    );
}

function element(tag, attrs = {}, children = []) {
    const node = {
        tagName: String(tag).toUpperCase(),
        attrs: { ...attrs },
        className: String(attrs.class || ""),
        dataset: {},
        children: [],
        parentElement: null,
        isConnected: true,
        disabled: Boolean(attrs.disabled),
        textContent: "",
        value: attrs.value == null ? "" : String(attrs.value),
        listeners: {},
        setAttribute(name, value) { this.attrs[name] = String(value); },
        getAttribute(name) { return this.attrs[name]; },
        removeAttribute(name) { delete this.attrs[name]; },
        appendChild(child) {
            child.parentElement = this;
            this.children.push(child);
            return child;
        },
        closest(selector) {
            let current = this;
            while (current) {
                if (selector === "tr[data-row-name]" && current.tagName === "TR") return current;
                if (selector === ".dco-tab-edit-save" && String(current.className || "").includes("dco-tab-edit-save")) {
                    return current;
                }
                current = current.parentElement;
            }
            return null;
        },
        querySelector(selector) {
            const matches = this.querySelectorAll(selector);
            return matches[0] || null;
        },
        querySelectorAll(selector) {
            const found = [];
            const visit = (item) => {
                if (selector === ".dco-fast-input[data-field], .dco-fast-select[data-field]"
                    && item.dataset && item.dataset.field
                    && String(item.className || "").includes("dco-fast-input")) {
                    found.push(item);
                }
                if (selector === "input[data-field='width_cm']" && item.dataset && item.dataset.field === "width_cm") {
                    found.push(item);
                }
                if (selector === "input[data-field='length_cm']" && item.dataset && item.dataset.field === "length_cm") {
                    found.push(item);
                }
                if (selector === "input[data-field='notes']" && item.dataset && item.dataset.field === "notes") {
                    found.push(item);
                }
                (item.children || []).forEach(visit);
            };
            visit(this);
            return found;
        },
        addEventListener(type, handler) {
            this.listeners[type] = this.listeners[type] || [];
            this.listeners[type].push(handler);
        },
        classList: {
            contains: (name) => false,
        },
    };
    if (attrs["data-row-name"]) node.dataset.rowName = attrs["data-row-name"];
    if (attrs["data-field"]) node.dataset.field = attrs["data-field"];
    children.forEach((child) => node.appendChild(child));
    if (tag === "tr") {
        node.classList = {
            contains(name) { return String(node.className || "").split(/\s+/).includes(name); },
            add(name) { node.className = `${node.className} ${name}`.trim(); },
            remove(name) {
                node.className = String(node.className || "")
                    .split(/\s+/)
                    .filter((item) => item && item !== name)
                    .join(" ");
            },
            toggle() {},
        };
    }
    return node;
}

function createSandbox() {
    const formHandlers = {};
    const window = {
        AlmdinaDcoEditSessionCoordinator: {
            snapshot() { return { phase: "editing", activeKind: "order" }; },
        },
    };
    const document = {
        getElementById() { return null; },
        createElement() { return { id: "", textContent: "" }; },
        head: { appendChild() {} },
        activeElement: null,
        documentElement: { lang: "ar" },
    };
    function $(selector) {
        return {
            append() { return this; },
            addClass() { return this; },
            closest() { return this; },
            find() { return this; },
            get() { return null; },
        };
    }
    const sandbox = {
        window,
        document,
        $,
        frappe: {
            ui: { form: { on(doctype, handlers) { formHandlers[doctype] = handlers; } } },
            utils: { escape_html(value) { return String(value); } },
            model: {
                add_child(doc, _doctype, fieldname) {
                    const row = { name: `new-${(doc[fieldname] || []).length + 1}`, qty: 1 };
                    doc[fieldname] = doc[fieldname] || [];
                    doc[fieldname].push(row);
                    return row;
                },
                clear_doc() {},
            },
        },
        Object,
        String,
        Number,
        Boolean,
        Promise,
        Set,
        Map,
        console,
    };
    sandbox.window = window;
    sandbox.window.document = document;
    sandbox.window.frappe = sandbox.frappe;
    sandbox.global = sandbox;
    return vm.createContext(sandbox);
}

function makeFrm(root, pieces) {
    let dirty = false;
    return {
        doctype: "Door Cutting Order",
        doc: { pieces, name: "DCO-1", doctype: "Door Cutting Order" },
        fields_dict: {
            pieces_fast_entry: {
                $wrapper: {
                    get() { return root; },
                    find() { return { length: 1, each() {} }; },
                    html() {},
                },
            },
        },
        dirty() { dirty = true; },
        is_dirty() { return dirty; },
        script_manager: { trigger() { return Promise.resolve(); } },
    };
}

async function run() {
    const sandbox = createSandbox();
    load("public/js/door_cutting_order/order_entry/door_cutting_order_operator_ux.js", sandbox);
    const api = sandbox.window.AlmdinaDoorCuttingFastEntry;
    assert.ok(api && typeof api.flush === "function", "flush API must be exported");

    const width = element("input", { class: "dco-fast-input", "data-field": "width_cm", value: "91.5" });
    const length = element("input", { class: "dco-fast-input", "data-field": "length_cm", value: "210" });
    const row = { name: "PIECE-1", width_cm: 80, length_cm: 200, qty: 1 };
    const tr = element("tr", { "data-row-name": "PIECE-1" }, [width, length]);
    const root = element("div", {}, [tr]);
    const frm = makeFrm(root, [row]);

    api.flush(frm);

    assert.equal(row.width_cm, 91.5);
    assert.equal(row.length_cm, 210);
    assert.equal(frm.is_dirty(), true);

    const emptyWidth = element("input", { class: "dco-fast-input", "data-field": "width_cm", value: "" });
    const emptyLength = element("input", { class: "dco-fast-input", "data-field": "length_cm", value: "" });
    const virtual = element("tr", { "data-row-name": "__virtual__1", class: "dco-virtual-row" }, [
        emptyWidth,
        emptyLength,
    ]);
    virtual.className = "dco-virtual-row";
    const rootB = element("div", {}, [virtual]);
    const frmB = makeFrm(rootB, []);
    api.flush(frmB);
    assert.equal((frmB.doc.pieces || []).length, 0, "empty virtual rows must not materialize on flush");

    const typedWidth = element("input", { class: "dco-fast-input", "data-field": "width_cm", value: "60" });
    const typedLength = element("input", { class: "dco-fast-input", "data-field": "length_cm", value: "90" });
    const virtualTyped = element("tr", { "data-row-name": "__virtual__2", class: "dco-virtual-row" }, [
        typedWidth,
        typedLength,
    ]);
    virtualTyped.className = "dco-virtual-row";
    const rootC = element("div", {}, [virtualTyped]);
    const frmC = makeFrm(rootC, []);
    sandbox.frappe.model.add_child = (doc, _doctype, fieldname) => {
        const created = { name: "new-piece-1", qty: 1 };
        doc[fieldname] = doc[fieldname] || [];
        doc[fieldname].push(created);
        return created;
    };
    api.flush(frmC);
    assert.equal(frmC.doc.pieces.length, 1);
    assert.equal(frmC.doc.pieces[0].width_cm, 60);
    assert.equal(frmC.doc.pieces[0].length_cm, 90);

    const coordinatorSource = fs.readFileSync(
        path.resolve(__dirname, "../../public/js/door_cutting_order/core/door_cutting_order_edit_session_coordinator.js"),
        "utf8"
    );
    const coordSandbox = vm.createContext({ window: {}, Object, String, Number, Boolean, Promise, Set, WeakMap });
    vm.runInContext(coordinatorSource, coordSandbox);
    const coordinator = coordSandbox.window.AlmdinaDcoEditSessionCoordinator;
    const form = {
        doctype: "Door Cutting Order",
        doc: { doctype: "Door Cutting Order", name: "DCO-SAVE" },
        trigger() {},
    };
    coordSandbox.window.cur_frm = form;
    coordinator.register("order", {
        canStart() { return true; },
        start() { return true; },
        async save() { return true; },
        cancel() { return true; },
    });
    assert.equal(await coordinator.start(form, "order"), true);
    assert.equal(await coordinator.save(form, "order"), true);
    assert.equal(coordinator.snapshot(form).phase, "idle");

    console.log("order measurement save flush tests passed");
}

run().catch((error) => {
    console.error(error);
    process.exit(1);
});
