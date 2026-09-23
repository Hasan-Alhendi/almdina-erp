"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const source = fs.readFileSync(
    path.resolve(__dirname, "../../public/js/door_cutting_order/core/door_cutting_order_form_sidebar_controller.js"),
    "utf8"
);

class ClassList {
    constructor() { this.values = new Set(); }
    add(value) { this.values.add(value); }
    toggle(value, enabled) { enabled ? this.values.add(value) : this.values.delete(value); }
    contains(value) { return this.values.has(value); }
}

class FakeNode {
    constructor() {
        this.nodeType = 1;
        this.classList = new ClassList();
        this.dataset = {};
        this.attributes = {};
        this.listeners = {};
    }
    querySelector(selector) {
        return selector.includes("data-almdina-dco-sidebar-toggle") ? this.toggleButton || null : null;
    }
    addEventListener(type, handler) {
        this.listeners[type] = (this.listeners[type] || 0) + 1;
        this.handler = handler;
    }
    setAttribute(name, value) { this.attributes[name] = String(value); }
    click() { this.handler && this.handler({ preventDefault() {} }); }
}

function runtime() {
    const hooks = [];
    const storage = new Map();
    const window = {
        localStorage: {
            getItem(key) { return storage.has(key) ? storage.get(key) : null; },
            setItem(key, value) { storage.set(key, String(value)); },
        },
    };
    const frappe = {
        session: { user: "operator@example.com" },
        ui: { form: { on(_doctype, handlers) { hooks.push(handlers); } } },
    };
    const context = vm.createContext({ window, frappe, String, Set, Object, encodeURIComponent });
    vm.runInContext(source, context, { filename: "door_cutting_order_form_sidebar_controller.js" });
    return { hooks, storage, controller: window.AlmdinaDcoFormSidebarController };
}

function form(name = "DCO-1") {
    const root = new FakeNode();
    const page = {
        wrapper: root,
        add_action_icon(_icon, _click, className) {
            const button = new FakeNode();
            button.classList.add(className);
            root.toggleButton = button;
            return button;
        },
    };
    return { doctype: "Door Cutting Order", doc: { name }, page, wrapper: root, root };
}

const { hooks, storage, controller } = runtime();
assert.equal(hooks.length, 1, "DCO hooks must register once");
const frm = form();

hooks[0].onload_post_render(frm);
assert.equal(frm.root.classList.contains("almadina-dco-form-sidebar-host"), true);
assert.equal(frm.root.classList.contains("almadina-dco-form-sidebar-collapsed"), true);
assert.equal(frm.root.toggleButton.attributes["aria-expanded"], "false");
assert.equal(frm.root.toggleButton.listeners.click, 1, "mount attaches one toggle listener");

frm.root.toggleButton.click();
assert.equal(frm.root.classList.contains("almadina-dco-form-sidebar-collapsed"), false);
assert.equal(frm.root.toggleButton.attributes["aria-expanded"], "true");
assert.equal([...storage.values()][0], "expanded");

hooks[0].refresh(frm);
hooks[0].refresh(frm);
assert.equal(frm.root.toggleButton.listeners.click, 1, "refresh must not duplicate listeners");
assert.equal(frm.root.classList.contains("almadina-dco-form-sidebar-collapsed"), false);

const secondForm = form("DCO-2");
hooks[0].onload_post_render(secondForm);
assert.equal(secondForm.root.classList.contains("almadina-dco-form-sidebar-collapsed"), false, "preference survives route back");

const other = { doctype: "Customer", page: secondForm.page };
assert.equal(controller.mount(other), null, "other doctypes must not be affected");

console.log("dco form sidebar controller tests passed");
