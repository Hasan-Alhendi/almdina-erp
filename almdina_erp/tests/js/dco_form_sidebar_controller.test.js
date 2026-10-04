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
    has(value) { return this.values.has(value); }
}

class FakeNode {
    constructor() {
        this.nodeType = 1;
        this.isConnected = true;
        this.classList = new ClassList();
        this.dataset = {};
        this.attributes = {};
    }
    querySelector(selector) {
        return selector.includes("data-almdina-dco-sidebar-toggle") ? this.toggleButtons?.find(item => item.isConnected) || this.toggleButton || null : null;
    }
    querySelectorAll(selector) {
        return selector.includes("data-almdina-dco-sidebar-toggle") ? (this.toggleButtons || []).filter(item => item.isConnected) : [];
    }
    remove() { this.isConnected = false; }
    setAttribute(name, value) { this.attributes[name] = String(value); }
    getAttribute(name) { return this.attributes[name] ?? null; }
    click() { this.clickHandler && this.clickHandler(); }
}

class FakeJQuery {
    constructor(target) {
        this.target = target;
        this.length = target ? 1 : 0;
        if (target) this[0] = target;
    }
    parent() { return this.target.parent; }
    find(selector) {
        if (selector === ".overlay-sidebar") return new FakeJQuery(this.target.overlay);
        return new FakeJQuery(null);
    }
    is(selector) { return selector === ":visible" && this.target.visible; }
    hasClass(value) { return this.target.classList.has(value); }
    toggle() { this.target.visible = !this.target.visible; return this; }
    on(event, handler) {
        this.target.events ||= {};
        this.target.events[event] ||= new Set();
        this.target.events[event].add(handler);
        return this;
    }
    off(event, handler) {
        if (!this.target.events) return this;
        if (!handler) {
            Object.keys(this.target.events)
                .filter(name => name === event || name.endsWith(event))
                .forEach(name => delete this.target.events[name]);
        } else if (this.target.events[event]) this.target.events[event].delete(handler);
        return this;
    }
    trigger(event) {
        for (const [name, handlers] of Object.entries(this.target.events || {})) {
            if (name === event || name.split(".")[0] === event) {
                for (const handler of handlers) handler();
            }
        }
        return this;
    }
    tooltip() { return this; }
}

function createRuntime() {
    const hooks = [];
    const storage = new Map();
    const body = new FakeNode();
    body.__body = true;
    const document = { body };
    let width = 1200;
    const window = {
        localStorage: {
            getItem(key) { return storage.has(key) ? storage.get(key) : null; },
            setItem(key, value) { storage.set(key, String(value)); },
        },
        jQuery(value) {
            if (value && value.__body) return new FakeJQuery(body);
            return new FakeJQuery(value);
        },
    };
    const frappe = {
        session: { user: "operator@example.com" },
        utils: { is_xs: () => width < 768, is_sm: () => width >= 768 && width < 991 },
        ui: { form: { on(_doctype, handlers) { hooks.push(handlers); } } },
    };
    window.frappe = frappe;
    const context = vm.createContext({ window, frappe, document, String, Set, Object, encodeURIComponent });
    vm.runInContext(source, context, { filename: "door_cutting_order_form_sidebar_controller.js" });
    return { hooks, storage, controller: window.AlmdinaDcoFormSidebarController, body, window, setWidth(value) { width = value; } };
}

function form(name = "DCO-1", visible = true) {
    const root = new FakeNode();
    const side = new FakeNode();
    side.visible = visible;
    side.overlay = new FakeNode();
    side.overlay.classList = new ClassList();
    const sideJq = new FakeJQuery(side);
    side.parent = sideJq;
    const page = {
        wrapper: root,
        add_action_icon(_icon, callback, className) {
            const button = new FakeNode();
            button.classList.add(className);
            button.clickHandler = callback;
            root.toggleButton = button;
            root.toggleButtons ||= [];
            root.toggleButtons.push(button);
            return new FakeJQuery(button);
        },
    };
    const frm = {
        doctype: "Door Cutting Order",
        doc: { name },
        page,
        wrapper: root,
        root,
        sidebar: { sidebar: sideJq },
        toolbar: {
            setup_sidebar_toggle(wrapper) {
                if (runtimeState.mobile) {
                    const overlay = wrapper.find(".overlay-sidebar").target;
                    overlay.classList.toggle("opened", !overlay.classList.has("opened"));
                } else wrapper.toggle();
                new FakeJQuery(runtimeState.body).trigger("toggleSidebar");
            },
        },
    };
    return frm;
}

let runtimeState;
function makeForm(runtime, name, visible) {
    runtimeState = { body: runtime.body, mobile: false };
    const frm = form(name, visible);
    runtime.window.cur_frm = frm;
    return frm;
}

const runtime = runtimeState = createRuntime();
assert.equal(runtime.hooks.length, 0, "sidebar behavior is driven by the form presentation owner");
const frm = makeForm(runtime, "DCO-1", true);

runtime.controller.mount(frm);
assert.equal(frm.root.classList.contains("almadina-dco-form-sidebar-host"), true);
assert.equal(frm.root.classList.contains("almadina-dco-form-sidebar-native-collapsed"), true);
assert.equal(frm.root.toggleButton.attributes["aria-expanded"], "false");
    assert.equal(typeof frm.root.toggleButton.clickHandler, "function", "native callback must be attached once");
assert.equal([...runtime.storage.values()][0], "collapsed");

frm.root.toggleButton.click();
assert.equal(frm.root.classList.contains("almadina-dco-form-sidebar-native-collapsed"), false);
assert.equal(frm.root.toggleButton.attributes["aria-expanded"], "true");
assert.equal([...runtime.storage.values()][0], "expanded");

// Frappe's native menu uses the same toolbar path and body event.
frm.toolbar.setup_sidebar_toggle(frm.sidebar.sidebar.parent());
assert.equal(frm.root.toggleButton.attributes["aria-expanded"], "false");
assert.equal([...runtime.storage.values()][0], "collapsed");

// Toolbar.clear_icons() removes the custom icon; refresh recreates exactly one.
const oldButton = frm.root.toggleButton;
oldButton.isConnected = false;
frm.root.toggleButton = null;
runtime.controller.mount(frm);
assert.notEqual(frm.root.toggleButton, oldButton);
assert.equal(frm.root.toggleButton.attributes["aria-expanded"], "false");
runtime.controller.mount(frm);
assert.equal(frm.root.toggleButton.attributes["aria-expanded"], "false");
assert.equal(frm.root.querySelectorAll("[data-almdina-dco-sidebar-toggle=\"1\"]").length, 1);
const duplicateToggle = new FakeNode();
duplicateToggle.isConnected = true;
duplicateToggle.dataset.almdinaDcoSidebarToggle = "1";
frm.root.toggleButtons.push(duplicateToggle);
runtime.controller.mount(frm);
assert.equal(duplicateToggle.isConnected, false, "duplicate native sidebar action is removed");
assert.equal(frm.root.querySelectorAll("[data-almdina-dco-sidebar-toggle=\"1\"]").length, 1);
assert.equal([...runtime.body.events["toggleSidebar.almdinaDcoFormSidebar"]].length, 1, "one body listener per mounted controller");

// Route-away cleanup removes the body subscription; returning can bind again.
new FakeJQuery(frm.root).trigger("hide");
runtime.window.cur_frm = { doctype: "Customer" };
new FakeJQuery(runtime.body).trigger("toggleSidebar");
assert.equal(frm.root.toggleButton.attributes["aria-expanded"], "false");

const second = makeForm(runtime, "DCO-2", true);
runtime.controller.mount(second);
assert.equal(second.root.classList.contains("almadina-dco-form-sidebar-native-collapsed"), true, "preference survives route back");
assert.equal(runtime.controller.isPreferenceApplied(second), true);

// Expanded preference survives native refresh and a lifecycle/status transition.
second.root.toggleButton.click();
assert.equal(second.sidebar.sidebar.target.visible, true);
assert.equal([...runtime.storage.values()][0], "expanded");
second.sidebar.sidebar.target.visible = false; // Frappe's saved-document refresh can change native visibility.
runtime.controller.mount(second);
assert.equal(second.sidebar.sidebar.target.visible, true, "expanded preference is restored after refresh");
second.doc.status = "In Production";
second.sidebar.sidebar.target.visible = false;
runtime.controller.mount(second);
assert.equal(second.sidebar.sidebar.target.visible, true, "production transition preserves expanded preference");

// A collapsed preference is likewise restored if Frappe expands its sidebar on render.
second.root.toggleButton.click();
assert.equal([...runtime.storage.values()][0], "collapsed");
second.sidebar.sidebar.target.visible = true;
runtime.controller.mount(second);
assert.equal(second.sidebar.sidebar.target.visible, false, "collapsed preference is restored after reload");

// The same frm can receive a new page/root instance; the sidebar controller
// must detach its old hide handler and bind exactly once to the live root.
const detachedSidebarRoot = second.root;
detachedSidebarRoot.isConnected = false;
const liveSidebarRoot = new FakeNode();
second.root = liveSidebarRoot;
second.wrapper = liveSidebarRoot;
second.page.wrapper = liveSidebarRoot;
second.page.add_action_icon = (_icon, callback, className) => {
    const button = new FakeNode();
    button.classList.add(className);
    button.dataset.almdinaDcoSidebarToggle = "1";
    button.clickHandler = callback;
    liveSidebarRoot.toggleButton = button;
    liveSidebarRoot.toggleButtons = [button];
    return new FakeJQuery(button);
};
second.sidebar.sidebar.target.visible = true;
runtime.controller.mount(second);
assert.equal(runtime.controller.isPreferenceApplied(second), true);
assert.equal(second.__almdinaDcoFormSidebarController.boundRoot, liveSidebarRoot);
assert.equal(Object.values(detachedSidebarRoot.events || {}).every(handlers => handlers.size === 0), true);
assert.equal([...runtime.body.events["toggleSidebar.almdinaDcoFormSidebar"]].length, 1);

for (let i = 0; i < 10; i += 1) {
    second.doc.status = i % 2 ? "Draft" : "In Production";
    second.doc.current_production_stage = i % 2 ? "Cutting" : "Assembly";
    second.__almdina_permissions = { can_edit_plan: i % 2 === 0 };
    second.__profile = i % 2 ? "designer" : "operator";
    second.sidebar.sidebar.target.visible = true;
    runtime.controller.mount(second);
    assert.equal(second.sidebar.sidebar.target.visible, false);
    assert.equal([...runtime.storage.values()][0], "collapsed", "presentation context never rewrites preference");
}
assert.equal([...runtime.body.events["toggleSidebar.almdinaDcoFormSidebar"]].length, 1, "recovery does not duplicate body listeners");

const other = { doctype: "Customer", page: second.page };
assert.equal(runtime.controller.mount(other), null, "other doctypes must not be affected");

// Mobile delegates to native overlay and does not overwrite desktop preference.
runtime.setWidth(500);
runtimeState.mobile = true;
const mobile = makeForm(runtime, "DCO-MOBILE", true);
runtimeState.mobile = true;
runtime.controller.mount(mobile);
assert.equal(mobile.root.classList.contains("almadina-dco-form-sidebar-native-collapsed"), false);
mobile.root.toggleButton.click();
assert.equal(mobile.root.toggleButton.attributes["aria-expanded"], "true");
assert.equal([...runtime.storage.values()][0], "collapsed");

console.log("dco native form sidebar adapter tests passed");
