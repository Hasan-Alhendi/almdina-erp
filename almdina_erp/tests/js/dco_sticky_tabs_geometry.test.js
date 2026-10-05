"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const source = fs.readFileSync(
    path.resolve(__dirname, "../../public/js/door_cutting_order/responsive/door_cutting_order_header_ux.js"),
    "utf8"
);

const listeners = { scroll: new Set(), resize: new Set() };
const observers = [];
class ResizeObserverMock {
    constructor(callback) { this.callback = callback; this.targets = new Set(); this.disconnected = false; observers.push(this); }
    observe(target) { this.targets.add(target); }
    disconnect() { this.disconnected = true; this.targets.clear(); }
    trigger() { if (!this.disconnected) this.callback(); }
}
const window = {
    cur_frm: null,
    ResizeObserver: ResizeObserverMock,
    AlmdinaDocumentContext: {
        scheduleFrame(_frm, _key, callback) { callback(); },
        registerCleanup() {},
    },
    getComputedStyle() { return { position: "static" }; },
    addEventListener(type, callback) { listeners[type].add(callback); },
    removeEventListener(type, callback) { listeners[type].delete(callback); },
};
const document = {
    documentElement: { lang: "en" },
    addEventListener(type, callback) { listeners[type].add(callback); },
    removeEventListener(type, callback) { listeners[type].delete(callback); },
};
vm.runInNewContext(source, { window, document, frappe: { boot: { lang: "en" } }, requestAnimationFrame() {} });

function makeNodes(left, width) {
    const parent = { isConnected: true };
    const placeholder = {
        isConnected: true,
        parentElement: parent,
        rect: { left, width, top: -1 },
        getBoundingClientRect() { return this.rect; },
        style: {},
    };
    const classes = new Set();
    const tabs = {
        isConnected: true,
        offsetHeight: 44,
        style: { removeProperty(name) { delete this[name]; } },
        classList: {
            add(name) { classes.add(name); },
            remove(name) { classes.delete(name); },
            contains(name) { return classes.has(name); },
        },
        getBoundingClientRect() { return { height: 44 }; },
    };
    return {
        root: { isConnected: true },
        pageWrapper: { isConnected: true },
        pageContainer: { isConnected: true },
        head: { isConnected: true, getBoundingClientRect() { return { top: 0, bottom: 0 }; } },
        tabs,
        placeholder,
    };
}

const frm = {};
window.cur_frm = frm;
const header = window.AlmdinaDcoHeaderUx;
let nodes = makeNodes(34, 720);
frm._dco_presentation_head = nodes.head;
frm._dco_fixed_tabs = nodes.tabs;
frm._dco_tabs_placeholder = nodes.placeholder;
assert.equal(header.recoverPresentation(frm, nodes), true);
assert.equal(nodes.tabs.style.left, "34px");
assert.equal(nodes.tabs.style.width, "720px");
assert.equal(observers.length, 1);
assert.equal(observers[0].targets.has(nodes.head), true);
assert.equal(observers[0].targets.has(nodes.placeholder.parentElement), true);

// Desk sidebar expands without a window resize; the anchor reflows in CSS.
nodes.placeholder.rect = { left: 24, width: 570, top: -1 };
observers[0].trigger();
assert.equal(nodes.tabs.style.left, "24px");
assert.equal(nodes.tabs.style.width, "570px");
for (let index = 0; index < 10; index += 1) header.recoverPresentation(frm, nodes);
assert.equal(observers.length, 1, "refresh keeps one observer");
assert.equal(listeners.scroll.size, 1);
assert.equal(listeners.resize.size, 1);

// Frappe replaces the page-head and tab DOM under the same page wrapper.
const replacement = makeNodes(42, 650);
replacement.pageWrapper = nodes.pageWrapper;
frm._dco_presentation_head = replacement.head;
frm._dco_fixed_tabs = replacement.tabs;
frm._dco_tabs_placeholder = replacement.placeholder;
header.recoverPresentation(frm, replacement);
assert.equal(observers[0].disconnected, true);
assert.equal(observers.length, 2);
assert.equal(replacement.tabs.style.width, "650px");
assert.equal(listeners.scroll.size, 1);
assert.equal(listeners.resize.size, 1);
header.suspendPresentation(frm);
assert.equal(observers[1].disconnected, true);
assert.equal(listeners.scroll.size, 0);
assert.equal(listeners.resize.size, 0);
