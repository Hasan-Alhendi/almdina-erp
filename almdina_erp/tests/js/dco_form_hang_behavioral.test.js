"use strict";

/**
 * Behavioral hang regressions for DCO form chrome under Frappe 16.60.
 * Simulates recover/settle remounts; asserts preference apply does not
 * thrash via toggle and that presentation settle stays bounded.
 */

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const ROOT = path.resolve(__dirname, "../..");
const SIDEBAR_SRC = fs.readFileSync(
    path.join(ROOT, "public/js/door_cutting_order/core/door_cutting_order_form_sidebar_controller.js"),
    "utf8"
);
const PRESENTATION_SRC = fs.readFileSync(
    path.join(ROOT, "public/js/door_cutting_order/core/door_cutting_order_form_presentation_owner.js"),
    "utf8"
);
const CONTEXT_SRC = fs.readFileSync(
    path.join(ROOT, "public/js/door_cutting_order/core/door_cutting_order_document_context.js"),
    "utf8"
);

class ClassList {
    constructor() { this.values = new Set(); }
    add(...values) { values.forEach((value) => this.values.add(value)); }
    remove(...values) { values.forEach((value) => this.values.delete(value)); }
    toggle(value, enabled) {
        if (enabled === undefined) {
            this.values.has(value) ? this.values.delete(value) : this.values.add(value);
            return;
        }
        enabled ? this.values.add(value) : this.values.delete(value);
    }
    contains(value) { return this.values.has(value); }
    has(value) { return this.values.has(value); }
}

class FakeNode {
    constructor(tag = "div") {
        this.tagName = String(tag).toUpperCase();
        this.nodeType = 1;
        this.isConnected = true;
        this.classList = new ClassList();
        this.dataset = {};
        this.attributes = {};
        this.children = [];
        this.parentElement = null;
        this.parentNode = null;
        this.events = {};
    }
    querySelector(selector) {
        if (selector.includes("data-almdina-dco-sidebar-toggle")) {
            return (this.toggleButtons || []).find((item) => item.isConnected) || this.toggleButton || null;
        }
        if (selector === ".form-tabs-list") return this.tabsList || null;
        if (selector === ".form-tabs") return this.tabs || null;
        if (selector === ".page-head") return this.head || null;
        if (selector.startsWith(".")) {
            const cls = selector.slice(1);
            return this.children.find((child) => child.classList.contains(cls)) || null;
        }
        return null;
    }
    querySelectorAll(selector) {
        if (selector.includes("data-almdina-dco-sidebar-toggle")) {
            return (this.toggleButtons || []).filter((item) => item.isConnected);
        }
        if (selector.startsWith(".")) {
            const cls = selector.slice(1);
            return this.children.filter((child) => child.classList.contains(cls));
        }
        return [];
    }
    closest(selector) {
        let node = this;
        while (node) {
            if (selector === ".page-container" && node.classList.contains("page-container")) return node;
            if (selector === ".desk-page" && node.classList.contains("desk-page")) return node;
            node = node.parentElement;
        }
        return null;
    }
    insertBefore(node, reference) {
        const index = this.children.indexOf(reference);
        if (index < 0) this.children.push(node);
        else this.children.splice(index, 0, node);
        node.parentNode = this;
        node.parentElement = this;
        return node;
    }
    get previousElementSibling() {
        if (!this.parentNode) return null;
        const index = this.parentNode.children.indexOf(this);
        return index > 0 ? this.parentNode.children[index - 1] : null;
    }
    get nextElementSibling() {
        if (!this.parentNode) return null;
        const index = this.parentNode.children.indexOf(this);
        return index >= 0 && index < this.parentNode.children.length - 1
            ? this.parentNode.children[index + 1]
            : null;
    }
    remove() {
        this.isConnected = false;
        if (this.parentNode) {
            const index = this.parentNode.children.indexOf(this);
            if (index >= 0) this.parentNode.children.splice(index, 1);
            this.parentNode = null;
            this.parentElement = null;
        }
    }
    setAttribute(name, value) { this.attributes[name] = String(value); }
    getAttribute(name) { return this.attributes[name] ?? null; }
    removeAttribute(name) { delete this.attributes[name]; }
}

class FakeJQuery {
    constructor(target) {
        this.target = target;
        this.length = target ? 1 : 0;
        if (target) this[0] = target;
    }
    parent() { return this.target && this.target.parent ? this.target.parent : new FakeJQuery(null); }
    find(selector) {
        if (selector === ".overlay-sidebar") return new FakeJQuery(this.target && this.target.overlay);
        return new FakeJQuery(null);
    }
    is(selector) { return selector === ":visible" && Boolean(this.target && this.target.visible); }
    show() { if (this.target) this.target.visible = true; return this; }
    hide() { if (this.target) this.target.visible = false; return this; }
    toggle() { if (this.target) this.target.visible = !this.target.visible; return this; }
    on(event, handler) {
        if (!this.target) return this;
        this.target.events ||= {};
        this.target.events[event] ||= new Set();
        this.target.events[event].add(handler);
        return this;
    }
    off(event, handler) {
        if (!this.target || !this.target.events) return this;
        if (!handler) {
            Object.keys(this.target.events)
                .filter((name) => name === event || name.endsWith(event) || name.startsWith(event))
                .forEach((name) => delete this.target.events[name]);
        } else if (this.target.events[event]) {
            this.target.events[event].delete(handler);
        }
        return this;
    }
    trigger(event) {
        for (const [name, handlers] of Object.entries((this.target && this.target.events) || {})) {
            if (name === event || name.split(".")[0] === event) {
                for (const handler of handlers) handler();
            }
        }
        return this;
    }
    tooltip() { return this; }
}

function createHarness() {
    const body = new FakeNode("body");
    const document = {
        body,
        createElement(tag) { return new FakeNode(tag); },
    };
    const hooks = [];
    let toggleCalls = 0;
    let showCalls = 0;
    let hideCalls = 0;
    const timers = [];
    const storage = new Map();
    const windowObj = {
        localStorage: {
            getItem(key) { return storage.has(key) ? storage.get(key) : null; },
            setItem(key, value) { storage.set(key, String(value)); },
        },
        jQuery(target) {
            if (target === document.body || target === body) return new FakeJQuery(body);
            return new FakeJQuery(target && target.nodeType ? target : (target && target[0]) || target);
        },
        addEventListener() {},
        setTimeout(fn, delay) {
            const id = timers.length + 1;
            timers.push({ id, fn, delay: Number(delay) || 0 });
            return id;
        },
        clearTimeout(id) {
            const index = timers.findIndex((timer) => timer.id === id);
            if (index >= 0) timers.splice(index, 1);
        },
        requestAnimationFrame(fn) { return windowObj.setTimeout(fn, 0); },
        cancelAnimationFrame(id) { windowObj.clearTimeout(id); },
        CustomEvent: class CustomEvent {
            constructor(type, init) {
                this.type = type;
                this.detail = init && init.detail;
            }
        },
        dispatchEvent() { return true; },
        console,
        AlmdinaDcoHeaderUx: {
            recoverPresentation() {},
            isReady() { return true; },
            suspendPresentation() {},
        },
        AlmdinaDcoToolbarStabilityUx: {
            recoverPresentation() {},
            isReady() { return true; },
            suspendPresentation() {},
        },
    };
    windowObj.jQuery.fn = {};
    const frappe = {
        session: { user: "tester@example.com" },
        boot: { user: { name: "tester@example.com" } },
        utils: { is_xs: () => false, is_sm: () => false },
        ui: { form: { on(_doctype, handlers) { hooks.push(handlers); } } },
    };
    windowObj.frappe = frappe;
    const context = vm.createContext({
        window: windowObj,
        frappe,
        document,
        console,
        String,
        Set,
        Map,
        Object,
        Array,
        Number,
        Boolean,
        Promise,
        encodeURIComponent,
        WeakMap,
        CustomEvent: windowObj.CustomEvent,
    });
    vm.runInContext(CONTEXT_SRC, context, { filename: "document_context.js" });
    vm.runInContext(SIDEBAR_SRC, context, { filename: "form_sidebar_controller.js" });
    vm.runInContext(PRESENTATION_SRC, context, { filename: "form_presentation_owner.js" });

    function makeForm(name = "DCO-NEW", visible = true) {
        const pageContainer = new FakeNode("div");
        pageContainer.classList.add("page-container");
        const head = new FakeNode("div");
        head.classList.add("page-head");
        pageContainer.head = head;
        pageContainer.children.push(head);
        head.parentElement = pageContainer;

        const root = new FakeNode("div");
        root.parentElement = pageContainer;
        pageContainer.children.push(root);
        const tabs = new FakeNode("div");
        tabs.classList.add("form-tabs");
        root.tabs = tabs;
        root.children.push(tabs);
        tabs.parentNode = root;
        tabs.parentElement = root;

        const side = new FakeNode("aside");
        side.visible = visible;
        side.overlay = new FakeNode("div");
        const sideJq = new FakeJQuery(side);
        side.parent = sideJq;
        const originalShow = sideJq.show.bind(sideJq);
        const originalHide = sideJq.hide.bind(sideJq);
        sideJq.show = () => { showCalls += 1; return originalShow(); };
        sideJq.hide = () => { hideCalls += 1; return originalHide(); };

        const frm = {
            doctype: "Door Cutting Order",
            doc: { name, doctype: "Door Cutting Order" },
            page: {
                wrapper: pageContainer,
                add_action_icon(_icon, callback, className) {
                    const button = new FakeNode("button");
                    button.classList.add(className);
                    button.dataset.almdinaDcoSidebarToggle = "1";
                    button.clickHandler = callback;
                    root.toggleButton = button;
                    root.toggleButtons = [button];
                    return new FakeJQuery(button);
                },
            },
            wrapper: root,
            sidebar: { sidebar: sideJq },
            toolbar: {
                setup_sidebar_toggle(wrapper) {
                    toggleCalls += 1;
                    wrapper.toggle();
                    new FakeJQuery(body).trigger("toggleSidebar");
                },
            },
            fields_dict: {},
        };
        windowObj.cur_frm = frm;
        return frm;
    }

    function flushTimers() {
        let guard = 0;
        while (timers.length && guard < 50) {
            guard += 1;
            const next = timers.shift();
            next.fn();
        }
    }

    return {
        window: windowObj,
        hooks,
        makeForm,
        flushTimers,
        counts() { return { toggleCalls, showCalls, hideCalls }; },
        resetCounts() { toggleCalls = 0; showCalls = 0; hideCalls = 0; },
        storage,
    };
}

const harness = createHarness();
assert.ok(harness.window.AlmdinaDocumentContext, "document context must boot");
assert.ok(harness.window.AlmdinaDcoFormSidebarController, "sidebar controller must boot");
assert.ok(harness.window.AlmdinaDcoFormPresentationOwner, "presentation owner must boot");

// New-order lifecycle: many recover passes must not thrash via toggle.
const newFrm = harness.makeForm("__new__", true);
harness.storage.clear();
harness.resetCounts();
for (let i = 0; i < 12; i += 1) {
    assert.equal(harness.window.AlmdinaDcoFormPresentationOwner.recover(newFrm), true);
}
const newCounts = harness.counts();
assert.equal(newCounts.toggleCalls, 0, "preference restore must not use toggle on desktop");
assert.ok(newCounts.hideCalls >= 1, "collapsed preference uses hide()");
assert.ok(newCounts.hideCalls <= 2, "hide must not fire every recover pass");
assert.equal(
    harness.window.AlmdinaDcoFormSidebarController.isPreferenceApplied(newFrm),
    true
);

// Saved-order edit: expanded preference restored once, then stable.
const editFrm = harness.makeForm("DCO-100", false);
harness.storage.set(
    `almdina:dco-form-sidebar:v1:${encodeURIComponent("tester@example.com")}:${encodeURIComponent("Door Cutting Order")}`,
    "expanded"
);
harness.resetCounts();
for (let i = 0; i < 12; i += 1) {
    assert.equal(harness.window.AlmdinaDcoFormPresentationOwner.recover(editFrm), true);
}
const editCounts = harness.counts();
assert.equal(editCounts.toggleCalls, 0, "edit recover must not toggle");
assert.ok(editCounts.showCalls >= 1, "expanded preference uses show()");
assert.ok(editCounts.showCalls <= 2, "show must not fire every recover pass");
assert.equal(editFrm.sidebar.sidebar.target.visible, true);
assert.equal(
    harness.window.AlmdinaDcoFormSidebarController.isPreferenceApplied(editFrm),
    true
);

// Settle loop stays bounded: pending surface recovers then completes.
harness.window.AlmdinaDocumentContext.registerSurface("hang-probe", {
    isReady(frm) { return Boolean(frm.__hangProbeReady); },
    recover(frm) {
        frm.__hangProbeReady = true;
        return true;
    },
});
async function assertSettleBounded() {
    const settleFrm = harness.makeForm("DCO-SETTLE", true);
    assert.equal(harness.window.AlmdinaDcoFormPresentationOwner.recover(settleFrm), true);
    settleFrm.__hangProbeReady = false;
    harness.resetCounts();
    assert.equal(harness.window.AlmdinaDocumentContext.settleSurfaces(settleFrm, 0), false);
    assert.ok(settleFrm.__almdinaSurfaceSettleRun, "settle run is tracked while in flight");
    for (let i = 0; i < 20; i += 1) {
        await Promise.resolve();
        if (settleFrm.__hangProbeReady && !settleFrm.__almdinaSurfaceSettleRun) break;
    }
    harness.flushTimers();
    for (let i = 0; i < 10; i += 1) {
        await Promise.resolve();
        if (!settleFrm.__almdinaSurfaceSettleRun) break;
    }
    assert.equal(settleFrm.__hangProbeReady, true);
    assert.equal(settleFrm.__almdinaSurfaceSettleRun, null, "settle run clears after pass");
    assert.equal(
        harness.window.AlmdinaDocumentContext.settleSurfaces(settleFrm, 0),
        true,
        "second settle reports ready without another recovery storm"
    );
}

assertSettleBounded()
    .then(() => {
        console.log("dco form hang behavioral tests passed");
    })
    .catch((error) => {
        console.error(error);
        process.exitCode = 1;
    });
