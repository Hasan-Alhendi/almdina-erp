"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const source = fs.readFileSync(
    path.resolve(__dirname, "../../public/js/door_cutting_order/core/door_cutting_order_form_presentation_owner.js"),
    "utf8"
);

class ClassList {
    constructor() { this.values = new Set(); }
    add(...values) { values.forEach(value => this.values.add(value)); }
    remove(...values) { values.forEach(value => this.values.delete(value)); }
    contains(value) { return this.values.has(value); }
    toggle(value, force) {
        if (force === undefined) force = !this.contains(value);
        force ? this.add(value) : this.remove(value);
        return force;
    }
}

class FakeNode {
    constructor(classes = []) {
        this.nodeType = 1;
        this.isConnected = true;
        this.classList = new ClassList();
        classes.forEach(value => this.classList.add(value));
        this.children = [];
        this.parentElement = null;
        this.previousElementSibling = null;
        this.nodes = new Map();
        this.insertions = 0;
    }
    set className(value) { this.classList = new ClassList(); String(value).split(/\s+/).filter(Boolean).forEach(item => this.classList.add(item)); }
    querySelector(selector) { return this.nodes.get(selector) || null; }
    querySelectorAll(selector) {
        if (selector === ".dco-tabs-fixed-placeholder") {
            return this.children.filter(child => child.classList.contains("dco-tabs-fixed-placeholder"));
        }
        return this.nodes.has(selector) ? this.nodes.get(selector) : [];
    }
    closest(selector) { return selector === ".page-container" ? this.pageContainer || null : null; }
    insertBefore(node, before) {
        if (node.parentElement) {
            node.parentElement.children = node.parentElement.children.filter(child => child !== node);
        }
        const index = before ? this.children.indexOf(before) : this.children.length;
        this.children.splice(index < 0 ? this.children.length : index, 0, node);
        node.parentElement = this;
        node.parentNode = this;
        node.isConnected = true;
        this.children.forEach((child, childIndex) => {
            child.previousElementSibling = this.children[childIndex - 1] || null;
            child.nextElementSibling = this.children[childIndex + 1] || null;
        });
        this.insertions += 1;
        return node;
    }
    remove() {
        this.isConnected = false;
        if (this.parentElement) {
            const parent = this.parentElement;
            parent.children = parent.children.filter(child => child !== this);
            parent.children.forEach((child, index) => {
                child.previousElementSibling = parent.children[index - 1] || null;
                child.nextElementSibling = parent.children[index + 1] || null;
            });
            this.parentElement = null;
            this.parentNode = null;
        }
    }
}

function surface() {
    const root = new FakeNode();
    const head = new FakeNode(["page-head"]);
    const tabs = new FakeNode(["form-tabs-list"]);
    const pageContainer = new FakeNode();
    pageContainer.nodes.set(".page-head", head);
    root.pageContainer = pageContainer;
    root.nodes.set(".form-tabs-list", tabs);
    root.nodes.set(".form-tabs", null);
    root.nodes.set(".dco-tabs-fixed-placeholder", []);
    root.children.push(tabs);
    tabs.parentNode = root;
    tabs.parentElement = root;
    tabs.previousElementSibling = null;
    return { root, head, tabs, pageContainer };
}

function createRuntime() {
    const hooks = [];
    const registered = new Map();
    const events = new Map();
    const sidebar = {
        mountCount: 0,
        ready: true,
        mount() { this.mountCount += 1; },
        isPreferenceApplied() { return this.ready; },
    };
    const header = {
        calls: [],
        recoverPresentation(frm, nodes) {
            this.calls.push({ frm, nodes });
            frm._dco_fixed_tabs_listener_installed = true;
        },
        isReady(frm, nodes) {
            return frm._dco_fixed_tabs === nodes.tabs
                && frm._dco_tabs_placeholder === nodes.placeholder
                && frm._dco_fixed_tabs_listener_installed;
        },
        suspendPresentation(frm) { frm._dco_fixed_tabs_listener_installed = false; },
    };
    const toolbar = {
        calls: [],
        observers: [],
        recoverPresentation(frm, head) {
            this.calls.push({ frm, head });
            if (frm._dcoToolbarObservedHead !== head || !frm._dcoToolbarObserver) {
                if (frm._dcoToolbarObserver) frm._dcoToolbarObserver.disconnect();
                const observer = { disconnected: false, disconnect() { this.disconnected = true; } };
                this.observers.push(observer);
                frm._dcoToolbarObserver = observer;
                frm._dcoToolbarObservedHead = head;
            }
        },
        isReady(frm, head) {
            return frm._dcoToolbarObservedHead === head && Boolean(frm._dcoToolbarObserver);
        },
        suspendPresentation(frm) {
            if (frm._dcoToolbarObserver) frm._dcoToolbarObserver.disconnect();
            frm._dcoToolbarObserver = null;
            frm._dcoToolbarObservedHead = null;
        },
    };
    const frappe = { ui: { form: { on(_doctype, handler) { hooks.push(handler); } } } };
    const window = {
        cur_frm: null,
        AlmdinaDocumentContext: {
            registerSurface(name, probe) { registered.set(name, probe); },
        },
        AlmdinaDcoFormSidebarController: sidebar,
        AlmdinaDcoHeaderUx: header,
        AlmdinaDcoToolbarStabilityUx: toolbar,
        addEventListener(name, handler) {
            events.set(name, [...(events.get(name) || []), handler]);
        },
        jQuery(target) {
            return {
                on(name, handler) {
                    target.jqueryEvents ||= new Map();
                    if (!target.jqueryEvents.has(name)) target.jqueryEvents.set(name, new Set());
                    target.jqueryEvents.get(name).add(handler);
                    return this;
                },
                off(name, handler) {
                    target.jqueryEvents?.get(name)?.delete(handler);
                    return this;
                },
                trigger(name) {
                    target.jqueryEvents?.get(name)?.forEach(handler => handler());
                    return this;
                },
            };
        },
    };
    const document = {
        documentElement: { lang: "ar" },
        createElement() { return new FakeNode(); },
        addEventListener() {},
        removeEventListener() {},
    };
    const context = vm.createContext({ window, frappe, document, CustomEvent, Set, String, Boolean });
    vm.runInContext(source, context, { filename: "door_cutting_order_form_presentation_owner.js" });
    return { window, hooks, registered, events, sidebar, header, toolbar };
}

function makeForm(name, state = surface()) {
    const frm = {
        doctype: "Door Cutting Order",
        doc: { doctype: "Door Cutting Order", name, status: "Draft" },
        wrapper: state.root,
        page: { wrapper: state.root },
    };
    return { frm, state };
}

const runtime = createRuntime();
assert.equal(runtime.hooks.length, 1, "presentation owner registers one Frappe hook bundle");
assert.deepEqual([...runtime.events.keys()].sort(), [
    "almdina:permissions-updated",
    "almdina:stage-context-ready",
    "almdina:surfaces-settled",
].sort(), "one module instance installs one listener per lifecycle event");
assert.equal(runtime.registered.has("dco-form-presentation"), true, "presentation surface is registered");
const { frm, state } = makeForm("DCO-1");
runtime.window.cur_frm = frm;

runtime.hooks[0].before_load(frm);
assert.equal(state.root.classList.contains("dco-operator-form"), true, "shell scope is primed before form render");
assert.equal(state.pageContainer.classList.contains("dco-form-presentation-shell"), true, "header scope is primed before form render");
runtime.hooks[0].onload_post_render(frm);
assert.equal(runtime.window.AlmdinaDcoFormPresentationOwner.isReady(frm), true, "saved Draft starts with the Almdina shell");
assert.equal(state.root.classList.contains("dco-operator-form"), true);
assert.equal(state.head.classList.contains("dco-responsive-head"), true);
assert.equal(state.head.classList.contains("dco-stable-actions-head"), true);
assert.equal(state.tabs.classList.contains("dco-sticky-tabs"), true);
assert.equal(state.root.querySelectorAll(".dco-tabs-fixed-placeholder").length, 1, "one fixed-tabs placeholder is acquired");

// Dispatch/reload replaces the current Frappe page-head and tab DOM. Old refs
// are detached; the same frm must acquire the new live nodes without a reload.
const oldRoot = state.root;
const oldHead = state.head;
const oldTabs = state.tabs;
const oldPlaceholder = frm._dco_tabs_placeholder;
const oldObservedHead = frm._dcoToolbarObservedHead;
const oldToolbarObserver = frm._dcoToolbarObserver;
oldRoot.isConnected = false;
oldHead.isConnected = false;
oldTabs.isConnected = false;
if (oldPlaceholder) oldPlaceholder.isConnected = false;
const replacement = surface();
frm.wrapper = replacement.root;
frm.page.wrapper = replacement.root;
frm.doc.status = "In Production";
runtime.hooks[0].refresh(frm);
assert.equal(runtime.window.AlmdinaDcoFormPresentationOwner.isReady(frm), true, "production reload recovers presentation");
assert.equal(replacement.root.classList.contains("dco-operator-form"), true);
assert.equal(replacement.head.classList.contains("dco-responsive-head"), true);
assert.equal(replacement.head.classList.contains("dco-stable-actions-head"), true);
assert.equal(replacement.tabs.classList.contains("dco-sticky-tabs"), true);
assert.equal(replacement.root.querySelectorAll(".dco-tabs-fixed-placeholder").length, 1, "replacement gets one placeholder");
assert.equal(frm._dco_presentation_root, replacement.root);
assert.equal(frm._dco_presentation_head, replacement.head);
assert.equal(frm._dco_fixed_tabs, replacement.tabs);
assert.equal(frm._dco_tabs_placeholder.isConnected, true);
assert.equal(frm._dco_tabs_placeholder, replacement.tabs.previousElementSibling);
assert.equal(frm._dcoToolbarObservedHead, replacement.head);
assert.equal(oldToolbarObserver.disconnected, true, "observer on the detached page head is disconnected");
assert.equal(oldRoot.isConnected, false);
assert.equal(oldHead.isConnected, false);
assert.equal(oldTabs.isConnected, false);
assert.equal(state.pageContainer.classList.contains("dco-form-presentation-shell"), false);
assert.equal(oldObservedHead, oldHead);
assert.equal(runtime.header.calls.at(-1).nodes.head, replacement.head);
assert.equal(runtime.toolbar.calls.at(-1).head, replacement.head);
assert.equal(runtime.sidebar.mountCount >= 2, true, "native sidebar preference is reconciled on refresh");

// Repeated refresh, true DOM replacement/recovery, and lifecycle events remain
// idempotent: one current observer, one placeholder, and no stale references.
let currentSurface = replacement;
for (let i = 0; i < 10; i += 1) {
    runtime.hooks[0].refresh(frm);
    runtime.events.get("almdina:permissions-updated").forEach(handler => handler({ detail: { frm } }));
    runtime.events.get("almdina:stage-context-ready").forEach(handler => handler({ detail: { frm } }));
    runtime.events.get("almdina:surfaces-settled").forEach(handler => handler({ detail: { frm } }));
    const previous = currentSurface;
    const previousObserver = frm._dcoToolbarObserver;
    const previousPlaceholder = frm._dco_tabs_placeholder;
    previous.root.isConnected = false;
    previous.head.isConnected = false;
    previous.tabs.isConnected = false;
    previousPlaceholder.isConnected = false;
    currentSurface = surface();
    frm.wrapper = currentSurface.root;
    frm.page.wrapper = currentSurface.root;
    runtime.hooks[0].refresh(frm);
    assert.equal(previousObserver.disconnected, true, `recovery ${i + 1} disconnects the old toolbar observer`);
    assert.equal(frm._dco_presentation_root, currentSurface.root);
    assert.equal(frm._dco_presentation_head, currentSurface.head);
    assert.equal(frm._dco_fixed_tabs, currentSurface.tabs);
    assert.equal(frm._dco_tabs_placeholder, currentSurface.tabs.previousElementSibling);
    assert.equal(currentSurface.root.querySelectorAll(".dco-tabs-fixed-placeholder").length, 1);
}
assert.equal(runtime.toolbar.observers.filter(observer => !observer.disconnected).length, 1);
assert.equal(currentSurface.root.querySelectorAll(".dco-tabs-fixed-placeholder").length, 1);
assert.equal(frm._dcoToolbarObservedHead, currentSurface.head);
for (const handlers of runtime.events.values()) assert.equal(handlers.length, 1, "lifecycle signals have one module listener");

// Same status with another dynamic capability context retains the same shell.
frm.doc.status = "In Production";
frm.__almdina_permissions = { view_plan: false, view_costs: false };
runtime.events.get("almdina:permissions-updated").forEach(handler => handler({ detail: { frm } }));
assert.equal(runtime.window.AlmdinaDcoFormPresentationOwner.isReady(frm), true);
runtime.hooks[0].refresh(frm);
assert.equal(currentSurface.root.querySelectorAll(".dco-tabs-fixed-placeholder").length, 1, "recovery remains idempotent");

// A later Frappe refresh can remove decorator classes and rebuild controls.
currentSurface.head.classList.remove("dco-stable-actions-head");
currentSurface.tabs.classList.remove("dco-sticky-tabs");
assert.equal(runtime.registered.get("dco-form-presentation").isReady(frm), false);
runtime.registered.get("dco-form-presentation").recover(frm);
assert.equal(runtime.registered.get("dco-form-presentation").isReady(frm), true);

const beforeHideRoot = currentSurface.root;
const beforeHideHead = currentSurface.head;
const beforeHidePlaceholder = frm._dco_tabs_placeholder;
runtime.window.jQuery(frm.page.wrapper).trigger("hide.almdinaDcoFormPresentation");
assert.equal(beforeHideRoot.classList.contains("dco-operator-form"), false);
assert.equal(beforeHideHead.classList.contains("dco-responsive-head"), false);
assert.equal(beforeHideHead.classList.contains("dco-stable-actions-head"), false);
assert.equal(beforeHidePlaceholder.isConnected, false);
assert.equal(frm._dco_presentation_head, null);
assert.equal(frm._dcoToolbarObserver, null);
runtime.events.get("almdina:permissions-updated").forEach(handler => handler({ detail: { frm } }));
assert.equal(beforeHideRoot.classList.contains("dco-operator-form"), false, "late events do not revive a hidden form shell");
runtime.hooks[0].before_load(frm);
runtime.hooks[0].refresh(frm);
assert.equal(runtime.registered.get("dco-form-presentation").isReady(frm), true, "returning to DCO binds a fresh presentation lifecycle");

console.log("dco form presentation owner lifecycle tests passed");
