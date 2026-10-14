"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("vm");

const root = path.resolve(__dirname, "../..");
const actionsPath = path.join(
    root,
    "public/js/door_cutting_order/order_entry/measurements/door_cutting_order_measurement_actions_ux.js"
);
const stabilityPath = path.join(
    root,
    "public/js/door_cutting_order/core/door_cutting_order_toolbar_stability_ux.js"
);

function matches(node, selector) {
    const classes = new Set(String(node.className || "").split(/\s+/).filter(Boolean));
    if (selector.startsWith(".")) return classes.has(selector.slice(1));
    return node.tagName === String(selector).toUpperCase();
}

function walk(node, selector) {
    const found = [];
    for (const child of node.children) {
        if (matches(child, selector)) found.push(child);
        found.push(...walk(child, selector));
    }
    return found;
}

function loadActions() {
    let structuralMutations = 0;
    const queued = [];
    const constructedObservers = [];

    function element(tag) {
        const children = [];
        const attributes = {};
        const node = {
            tagName: String(tag).toUpperCase(),
            children,
            parentElement: null,
            className: "",
            dataset: {},
            title: "",
            type: "",
            isConnected: true,
            set id(value) { node.setAttribute("id", value); },
            get id() { return node.getAttribute("id"); },
            setAttribute(name, value) { attributes[name] = String(value); },
            getAttribute(name) {
                return Object.prototype.hasOwnProperty.call(attributes, name) ? attributes[name] : null;
            },
            appendChild(child) {
                structuralMutations += 1;
                child.parentElement = node;
                children.push(child);
                return child;
            },
            remove() {
                structuralMutations += 1;
                if (!node.parentElement) return;
                const list = node.parentElement.children;
                const index = list.indexOf(node);
                if (index >= 0) list.splice(index, 1);
                node.parentElement = null;
            },
            querySelector(selector) { return walk(node, selector)[0] || null; },
            querySelectorAll(selector) { return walk(node, selector); },
            closest(selector) {
                let current = node;
                while (current) {
                    if (matches(current, selector)) return current;
                    current = current.parentElement;
                }
                return null;
            },
            contains(child) {
                let current = child;
                while (current) {
                    if (current === node) return true;
                    current = current.parentElement;
                }
                return false;
            },
            addEventListener() {},
        };
        Object.defineProperty(node, "innerHTML", {
            get() { return node._html || ""; },
            set(value) {
                structuralMutations += 1;
                node._html = String(value);
                node._text = "";
                children.splice(0, children.length);
                if (String(value).includes("<svg")) {
                    const svg = element("svg");
                    svg.parentElement = node;
                    children.push(svg);
                }
            },
        });
        Object.defineProperty(node, "textContent", {
            get() { return node._text || ""; },
            set(value) {
                structuralMutations += 1;
                node._text = String(value);
                node._html = "";
                children.splice(0, children.length);
            },
        });
        return node;
    }

    const head = element("head");
    const body = element("body");
    const document = {
        body,
        head,
        documentElement: element("html"),
        createElement: element,
        getElementById(id) {
            return [...walk(head, "style"), ...walk(body, "style")]
                .find(node => node.getAttribute("id") === id) || null;
        },
        addEventListener() {},
    };
    document.documentElement.setAttribute("dir", "ltr");
    const handlers = [];
    const context = vm.createContext({
        window: {},
        document,
        frappe: {
            ui: { form: { on(doctype, events) { handlers.push({ doctype, events }); } } },
            utils: { escape_html(value) { return String(value ?? ""); } },
        },
        __: (message) => String(message),
        Object,
        Boolean,
        String,
        Number,
        Array,
        Map,
        Promise,
        Math,
        console,
    });
    context.window = context;
    context.window.document = document;
    context.window.requestAnimationFrame = (callback) => {
        queued.push(callback);
        return queued.length;
    };
    context.window.setTimeout = (callback) => {
        queued.push(callback);
        return queued.length;
    };
    context.window.clearTimeout = () => {};
    context.window.addEventListener = () => {};
    context.window.MutationObserver = class {
        constructor(callback) { constructedObservers.push(callback); }
        observe() {}
        disconnect() {}
    };
    context.window.AlmdinaLocale = {
        translate(message) { return String(message); },
        direction() { return "ltr"; },
    };
    vm.runInContext(fs.readFileSync(actionsPath, "utf8"), context);
    return {
        element,
        document,
        actions: context.window.AlmdinaMeasurementActions,
        handlers,
        queued,
        constructedObservers,
        mutations: () => structuralMutations,
    };
}

function measurementForm(element, document) {
    const toolbar = element("div");
    toolbar.className = "dco-fast-entry-toolbar";
    const help = element("div");
    help.className = "dco-fast-help";
    const title = element("b");
    title.className = "dco-measurement-title";
    title.textContent = "Door Measurements Table";
    help.appendChild(title);
    toolbar.appendChild(help);
    const entry = element("div");
    entry.appendChild(toolbar);
    document.body.appendChild(entry);
    return {
        frm: {
            doctype: "Door Cutting Order",
            doc: { name: "DCO-1", pieces: [] },
            fields_dict: { pieces_fast_entry: { $wrapper: { get() { return entry; } } } },
            is_dirty() { return false; },
        },
        toolbar,
    };
}

function drain(queued) {
    let steps = 0;
    while (queued.length && steps < 12) {
        steps += 1;
        const callback = queued.shift();
        callback();
    }
    return steps;
}

const loaded = loadActions();
const { frm, toolbar } = measurementForm(loaded.element, loaded.document);
loaded.actions.ensureActions(frm);
const afterCreate = loaded.mutations();
loaded.actions.ensureActions(frm);
loaded.actions.ensureActions(frm);
assert.equal(
    loaded.mutations(),
    afterCreate,
    "A correct measurement toolbar must not gain child nodes on a repeated ensureActions"
);
assert.equal(loaded.constructedObservers.length, 0, "ensureActions must not install a MutationObserver");

const printButton = toolbar.querySelector(".dco-print-measurements");
assert.ok(printButton.querySelector("svg"), "Print stays an icon");
printButton.textContent = "Print measurements";
assert.equal(printButton.querySelector("svg"), null);
loaded.actions.ensureActions(frm);
assert.ok(printButton.querySelector("svg"), "SVG is restored once after a text overwrite");
assert.equal(printButton.getAttribute("aria-label"), "Print measurements");
assert.equal(printButton.textContent.includes("Print measurements"), false);
const afterRestore = loaded.mutations();
loaded.actions.ensureActions(frm);
assert.equal(loaded.mutations(), afterRestore, "Restoring the icon must not schedule another structural write");

assert.equal(toolbar.querySelectorAll(".dco-measurement-table-actions").length, 1);
assert.equal(toolbar.querySelectorAll(".dco-input-help").length, 1);
assert.equal(toolbar.querySelectorAll(".dco-measurement-instructions").length, 0);
assert.equal(toolbar.querySelectorAll(".dco-measurement-title").length, 1);
assert.equal(toolbar.querySelectorAll(".dco-open-measurements-window").length, 1);

loaded.handlers[0].events.refresh(frm);
const steps = drain(loaded.queued);
assert.ok(steps > 0 && steps < 12, "Refresh follow-up frames stay bounded");
assert.equal(loaded.queued.length, 0, "No frame remains queued after the bounded drain");
assert.equal(loaded.constructedObservers.length, 0, "Refresh must not arm an observer loop");
const afterRefresh = loaded.mutations();
drain(loaded.queued);
assert.equal(loaded.queued.length, 0);
assert.equal(loaded.mutations(), afterRefresh, "An idle follow-up must not mutate the toolbar");

const stability = fs.readFileSync(stabilityPath, "utf8");
const reconcileStart = stability.indexOf("function reconcileMeasurementToolbar");
const reconcileEnd = stability.indexOf("function observeMeasurementToolbar");
const reconcile = stability.slice(reconcileStart, reconcileEnd);
for (const forbidden of ["getBoundingClientRect", "offsetWidth", "clientWidth", "getComputedStyle"]) {
    assert.equal(reconcile.includes(forbidden), false, forbidden);
}
assert.equal(reconcile.includes("--dco-measurement-actions-inline-size"), false);

console.log("measurement toolbar idempotence checks passed");
