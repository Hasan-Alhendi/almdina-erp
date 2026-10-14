"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");

const root = path.resolve(__dirname, "../..");
const scripts = [
    "public/js/door_cutting_order/order_entry/measurements/door_cutting_order_measurement_actions_ux.js",
    "public/js/door_cutting_order/order_entry/measurements/door_cutting_order_measurement_toolbar_ux.js",
    "public/js/door_cutting_order/order_entry/edge_banding/door_cutting_order_cut_dimensions_ux.js",
    "public/js/door_cutting_order/core/door_cutting_order_toolbar_stability_ux.js",
    "public/js/door_cutting_order/order_entry/edge_banding/door_cutting_order_multi_edge_ux.js",
    "public/js/door_cutting_order/order_entry/edge_banding/door_cutting_order_edge_profile_controls_ux.js",
    "public/js/door_cutting_order/order_entry/edge_banding/door_cutting_order_edge_render_owner.js",
].map(relative => path.join(root, relative));

const FRAME_LIMIT = 50;
const frameQueue = [];
const observerQueue = [];
const observations = [];
let structuralMutations = 0;
let observeCalls = 0;
let ownerStructureNotices = 0;
let activeForm = null;

function classSet(node) {
    return new Set(String(node.className || "").split(/\s+/).filter(Boolean));
}

function matches(node, selector) {
    let raw = String(selector || "").trim();
    if (!raw || !node || node.nodeType !== 1) return false;
    if (raw.includes(",")) return raw.split(",").some(part => matches(node, part.trim()));
    const attribute = raw.match(/\[([^\]=]+)(?:=['"]([^'"]*)['"])?\]/);
    if (attribute) {
        const actual = node.getAttribute(attribute[1]);
        if (attribute[2] === undefined) {
            if (actual === null) return false;
        } else if (actual !== attribute[2]) {
            return false;
        }
        raw = raw.replace(attribute[0], "").trim();
        if (!raw) return true;
    }
    const [tag, ...classNames] = raw.split(".");
    if (tag && node.tagName !== tag.toUpperCase()) return false;
    const owned = classSet(node);
    return classNames.every(name => owned.has(name));
}

function descendants(node) {
    const found = [];
    for (const child of node.children) {
        found.push(child, ...descendants(child));
    }
    return found;
}

function queryAll(node, selector) {
    const raw = String(selector || "").trim();
    if (!raw) return [];
    if (raw.includes(",")) {
        const seen = new Set();
        const found = [];
        raw.split(",").forEach(part => {
            queryAll(node, part.trim()).forEach(match => {
                if (seen.has(match)) return;
                seen.add(match);
                found.push(match);
            });
        });
        return found;
    }
    if (raw.startsWith(":scope")) {
        const parts = raw.replace(/^:scope\s*>\s*/, "").split(/\s+/);
        let current = node.children.filter(child => matches(child, parts[0]));
        parts.slice(1).forEach(part => {
            const next = [];
            current.forEach(start => {
                descendants(start).forEach(child => {
                    if (matches(child, part)) next.push(child);
                });
            });
            current = next;
        });
        return current;
    }
    let current = [node];
    raw.split(/\s+/).forEach(part => {
        const next = [];
        current.forEach(start => {
            descendants(start).forEach(child => {
                if (matches(child, part)) next.push(child);
            });
        });
        current = next;
    });
    return current;
}

function isInside(ancestor, node) {
    let current = node;
    while (current) {
        if (current === ancestor) return true;
        current = current.parentElement;
    }
    return false;
}

function parseMarkup(html) {
    const nodes = [];
    const pattern = /<(\w+)([^>]*)>([\s\S]*?)<\/\1>/g;
    let match = pattern.exec(html);
    while (match) {
        const child = element(match[1]);
        const className = match[2].match(/class="([^"]+)"/);
        if (className) child.className = className[1];
        child._text = match[3].replace(/<[^>]+>/g, "");
        nodes.push(child);
        match = pattern.exec(html);
    }
    return nodes;
}

function isOwnerStructural(added, removed) {
    return [...added, ...removed].some(node => {
        if (!node || node.nodeType !== 1 || typeof node.matches !== "function") return false;
        if (node.matches(".dco-fast-entry-shell,tbody,tr[data-row-name]")) return true;
        if (node.matches("td") && node.querySelector("input[data-field],select[data-field]")) return true;
        return Boolean(node.querySelector && node.querySelector(
            ".dco-fast-entry-shell,tr[data-row-name],input[data-field='width'],select[data-field='piece_type']"
        ));
    });
}

function notifyChildList(target, added = [], removed = []) {
    for (const observer of observations) {
        if (observer.disconnected) continue;
        const hit = (observer.registrations || []).some(registration => {
            if (!registration.options.childList || !registration.target) return false;
            if (registration.target === target) return true;
            return Boolean(registration.options.subtree)
                && registration.target !== target
                && isInside(registration.target, target);
        });
        if (!hit) continue;
        if (
            activeForm
            && observer === activeForm.__dcoEdgeRenderObserver
            && isOwnerStructural(added, removed)
        ) ownerStructureNotices += 1;
        observerQueue.push(() => observer.callback([{
            type: "childList",
            target,
            addedNodes: added,
            removedNodes: removed,
        }]));
    }
}

function element(tag) {
    const children = [];
    const attributes = {};
    const node = {
        tagName: String(tag).toUpperCase(),
        nodeType: 1,
        children,
        parentElement: null,
        className: "",
        dataset: {},
        title: "",
        type: "",
        disabled: false,
        isConnected: true,
        style: { setProperty() {}, removeProperty() {} },
        classList: {
            contains(name) { return classSet(node).has(name); },
            add(...names) {
                const owned = classSet(node);
                names.forEach(name => owned.add(name));
                node.className = [...owned].join(" ");
            },
            remove(...names) {
                const owned = classSet(node);
                names.forEach(name => owned.delete(name));
                node.className = [...owned].join(" ");
            },
            toggle(name, force) {
                const has = classSet(node).has(name);
                const next = force === undefined ? !has : Boolean(force);
                if (next === has) return next;
                if (next) this.add(name);
                else this.remove(name);
                return next;
            },
        },
        set id(value) { node.setAttribute("id", value); },
        get id() { return node.getAttribute("id"); },
        setAttribute(name, value) { attributes[name] = String(value); },
        getAttribute(name) {
            return Object.prototype.hasOwnProperty.call(attributes, name) ? attributes[name] : null;
        },
        appendChild(child) {
            structuralMutations += 1;
            if (child.parentElement) {
                const previous = child.parentElement.children;
                const index = previous.indexOf(child);
                if (index >= 0) previous.splice(index, 1);
            }
            child.parentElement = node;
            children.push(child);
            notifyChildList(node, [child], []);
            return child;
        },
        insertAdjacentElement(position, child) {
            const parent = node.parentElement;
            if (!parent) return null;
            structuralMutations += 1;
            if (child.parentElement) {
                const previous = child.parentElement.children;
                const previousIndex = previous.indexOf(child);
                if (previousIndex >= 0) previous.splice(previousIndex, 1);
            }
            child.parentElement = parent;
            const index = parent.children.indexOf(node);
            parent.children.splice(position === "afterend" ? index + 1 : index, 0, child);
            notifyChildList(parent, [child], []);
            return child;
        },
        remove() {
            structuralMutations += 1;
            const parent = node.parentElement;
            if (!parent) return;
            const index = parent.children.indexOf(node);
            if (index >= 0) parent.children.splice(index, 1);
            node.parentElement = null;
            notifyChildList(parent, [], [node]);
        },
        replaceChildren(...nodes) {
            if (!nodes.length && !children.length) return;
            structuralMutations += 1;
            const removed = children.splice(0, children.length);
            nodes.forEach(child => {
                child.parentElement = node;
                children.push(child);
            });
            notifyChildList(node, nodes, removed);
        },
        querySelector(selector) { return queryAll(node, selector)[0] || null; },
        querySelectorAll(selector) { return queryAll(node, selector); },
        matches(selector) { return matches(node, selector); },
        closest(selector) {
            let current = node;
            while (current) {
                if (matches(current, selector)) return current;
                current = current.parentElement;
            }
            return null;
        },
        contains(child) { return isInside(node, child); },
        addEventListener() {},
        focus() {},
    };
    Object.defineProperty(node, "innerHTML", {
        get() { return node._html || ""; },
        set(value) {
            structuralMutations += 1;
            node._html = String(value);
            node._text = "";
            const removed = children.splice(0, children.length);
            const created = String(value).includes("<svg") ? [element("svg")] : parseMarkup(String(value));
            created.forEach(child => {
                child.parentElement = node;
                children.push(child);
            });
            notifyChildList(node, created, removed);
        },
    });
    Object.defineProperty(node, "textContent", {
        get() {
            if (node._text) return node._text;
            return children.map(child => child.textContent || "").join("");
        },
        set(value) {
            structuralMutations += 1;
            node._text = String(value);
            node._html = "";
            const removed = children.splice(0, children.length);
            notifyChildList(node, [], removed);
        },
    });
    return node;
}

class MutationObserver {
    constructor(callback) {
        this.callback = callback;
        this.registrations = [];
        this.target = null;
        this.options = null;
        this.disconnected = false;
        observations.push(this);
    }

    observe(target, options) {
        observeCalls += 1;
        this.disconnected = false;
        this.target = target;
        this.options = options || {};
        this.registrations.push({ target, options: this.options });
    }

    disconnect() {
        this.disconnected = true;
        this.registrations = [];
        this.target = null;
    }

    takeRecords() { return []; }
}

function drain(limit) {
    let steps = 0;
    while ((frameQueue.length || observerQueue.length) && steps < limit) {
        steps += 1;
        const callbacks = observerQueue.splice(0, observerQueue.length);
        callbacks.forEach(callback => callback([]));
        const frames = frameQueue.splice(0, frameQueue.length);
        frames.forEach(callback => callback());
    }
    return steps;
}

const documentHead = element("head");
const documentBody = element("body");
const documentElement = element("html");
documentElement.setAttribute("dir", "ltr");
const document = {
    body: documentBody,
    head: documentHead,
    documentElement,
    createElement: element,
    getElementById(id) {
        return descendants(documentHead).find(node => node.getAttribute("id") === id) || null;
    },
    addEventListener() {},
};

const features = [];
const handlers = [];
const context = vm.createContext({
    window: {},
    document,
    frappe: {
        ui: { form: { on(doctype, events) { handlers.push({ doctype, events }); } } },
        utils: { escape_html(value) { return String(value ?? ""); } },
        msgprint() {},
        call() { return Promise.resolve({ message: { options: [] } }); },
        almdina: { orderCanEdit() { return true; } },
    },
    __: (message) => String(message),
    Object,
    Boolean,
    String,
    Number,
    Array,
    Map,
    Set,
    Promise,
    Math,
    console,
    MutationObserver,
});
context.window = context;
context.window.document = document;
context.window.MutationObserver = MutationObserver;
context.window.innerWidth = 1280;
context.window.getComputedStyle = () => ({ display: "flex", visibility: "visible", position: "fixed" });
context.window.addEventListener = () => {};
context.window.requestAnimationFrame = (callback) => {
    frameQueue.push(callback);
    return frameQueue.length;
};
context.window.setTimeout = (callback) => {
    frameQueue.push(callback);
    return frameQueue.length;
};
context.window.clearTimeout = () => {};
context.window.AlmdinaLocale = {
    translate(message) { return String(message); },
    direction() { return "ltr"; },
};
context.window.AlmdinaMeasurementLifecycle = {
    registerFeature(name, apply) { features.push({ name, apply }); },
    retry(frm, key, apply, options) {
        const maxAttempts = options && options.maxAttempts ? options.maxAttempts : 1;
        let attempts = 0;
        const run = () => {
            attempts += 1;
            const ready = apply() === true;
            if (!ready && attempts < maxAttempts) frameQueue.push(run);
        };
        run();
    },
    schedule(frm, key, apply, options) {
        if (!options || options.immediate !== false) apply();
        if (!options || options.frame !== false) frameQueue.push(() => apply());
        ((options && options.delays) || []).forEach(() => frameQueue.push(apply));
    },
};

scripts.forEach(script => vm.runInContext(fs.readFileSync(script, "utf8"), context));

const EDGE_FIELDS = ["edge_width_top", "edge_width_bottom", "edge_long_right", "edge_long_left"];

function piece(name) {
    return {
        name,
        doctype: "Door Cutting Order Detail",
        piece_type: "Regular",
        width_cm: 40,
        length_cm: 80,
        qty: 1,
        edge_width_top: 1,
        edge_width_bottom: 1,
        edge_long_right: 1,
        edge_long_left: 1,
        edge_width_top_type_override: "",
        edge_width_bottom_type_override: "",
        edge_long_right_type_override: "",
        edge_long_left_type_override: "",
    };
}

function measurementRow(name) {
    const row = element("tr");
    row.dataset.rowName = name;
    row.setAttribute("data-row-name", name);
    const edges = element("td");
    edges.className = "dco-col-edges";
    const buttons = element("div");
    buttons.className = "dco-edge-buttons";
    EDGE_FIELDS.forEach(field => {
        const toggle = element("button");
        toggle.className = "dco-check-toggle is-checked";
        toggle.dataset.checkField = field;
        toggle.setAttribute("data-check-field", field);
        const mark = element("span");
        mark.className = "dco-check-mark";
        mark.textContent = "✓";
        toggle.appendChild(mark);
        buttons.appendChild(toggle);
    });
    edges.appendChild(buttons);
    const edgeType = element("td");
    edgeType.className = "dco-col-edge-type";
    row.appendChild(edges);
    row.appendChild(edgeType);
    return row;
}

const wrapper = element("div");
const shell = element("div");
shell.className = "dco-fast-entry-shell";
const toolbar = element("div");
toolbar.className = "dco-fast-entry-toolbar";
const help = element("div");
help.className = "dco-fast-help";
const title = element("b");
title.className = "dco-measurement-title";
title.textContent = "Door Measurements Table";
help.appendChild(title);
toolbar.appendChild(help);
const scroll = element("div");
scroll.className = "dco-fast-entry-scroll";
const table = element("table");
table.className = "dco-fast-table";
const thead = element("thead");
const headerRow = element("tr");
const edgeTypeHeader = element("th");
edgeTypeHeader.className = "dco-col-edge-type";
edgeTypeHeader.textContent = "Edge type";
headerRow.appendChild(edgeTypeHeader);
thead.appendChild(headerRow);
const tbody = element("tbody");
["ROW-1", "ROW-2", "ROW-3"].forEach(name => tbody.appendChild(measurementRow(name)));
table.appendChild(thead);
table.appendChild(tbody);
scroll.appendChild(table);
shell.appendChild(toolbar);
shell.appendChild(scroll);
wrapper.appendChild(shell);
documentBody.appendChild(wrapper);

const pageHead = element("div");
pageHead.className = "page-head";
documentBody.appendChild(pageHead);

const pieces = [piece("ROW-1"), piece("ROW-2"), piece("ROW-3")];
const frm = {
    doctype: "Door Cutting Order",
    doc: { name: "DCO-LOOP", docstatus: 0, default_edge_type: "PVC", pieces },
    fields_dict: { pieces_fast_entry: { $wrapper: { get() { return wrapper; } } } },
    _dco_presentation_head: pageHead,
    _dco_side_edge_profiles_loaded: true,
    is_new() { return false; },
    is_dirty() { return false; },
    dirty() {},
    remove_custom_button() {},
    script_manager: { trigger() { return Promise.resolve(); } },
};
context.window.cur_frm = frm;
activeForm = frm;

function runFormHook(name) {
    handlers
        .filter(handler => handler.doctype === "Door Cutting Order" && handler.events[name])
        .forEach(handler => handler.events[name](frm));
}

function connectedWrapperObservers() {
    return observations.filter(observer => (
        !observer.disconnected
        && (observer.registrations || []).some(registration => registration.target === wrapper)
    ));
}

test("edge and measurement observers settle without a frame loop", async () => {
    features.forEach(feature => feature.apply(frm));
    runFormHook("onload_post_render");
    runFormHook("refresh");
    context.window.AlmdinaDcoToolbarStabilityUx.recoverPresentation(frm, pageHead);
    await new Promise(resolve => setImmediate(resolve));

    const steps = drain(FRAME_LIMIT);
    assert.ok(steps < FRAME_LIMIT, "shared measurement observers kept scheduling past " + FRAME_LIMIT + " frames");
    assert.equal(frameQueue.length, 0, "animation frame queue did not empty");
    assert.equal(observerQueue.length, 0, "mutation callback queue did not empty");

    const settledMutations = structuralMutations;
    const idleSteps = drain(FRAME_LIMIT);
    assert.equal(idleSteps, 0, "an idle drain still found scheduled work");
    assert.equal(structuralMutations, settledMutations, "DOM mutations continued after the queue emptied");
    assert.equal(connectedWrapperObservers().length, 1, "more than one structural measurement observer stayed connected");
    assert.equal(connectedWrapperObservers()[0], frm.__dcoEdgeRenderObserver);
    assert.equal(wrapper._dcoSideEdgeObserver, null);
    assert.equal(wrapper._dcoCompactEdgeProfileControlsObserver, null);
    const settledObserveCalls = observeCalls;

    context.window.AlmdinaMultiEdgeBanding.schedule(frm);
    context.window.AlmdinaEdgeProfileControls.schedule(frm);
    await new Promise(resolve => setImmediate(resolve));
    const repeatSteps = drain(FRAME_LIMIT);
    assert.ok(repeatSteps < FRAME_LIMIT, "a second apply kept scheduling");
    assert.equal(frameQueue.length + observerQueue.length, 0, "a second apply left scheduled work");
    assert.equal(structuralMutations, settledMutations, "a second apply created new DOM mutations");
    assert.equal(observeCalls, settledObserveCalls, "a delayed apply recreated a measurement observer");
    assert.equal(wrapper._dcoSideEdgeObserver, null);
    assert.equal(wrapper._dcoCompactEdgeProfileControlsObserver, null);
    assert.equal(connectedWrapperObservers().length, 1);

    ownerStructureNotices = 0;
    const added = piece("ROW-4");
    pieces.push(added);
    tbody.appendChild(measurementRow("ROW-4"));
    await new Promise(resolve => setImmediate(resolve));
    const addSteps = drain(FRAME_LIMIT);
    const addReconciliations = ownerStructureNotices;
    assert.equal(addReconciliations, 1, "adding a row reconciled more than once");
    assert.ok(addSteps < FRAME_LIMIT, "adding a row kept scheduling");
    assert.equal(frameQueue.length + observerQueue.length, 0, "adding a row left scheduled work");
    const afterAdd = structuralMutations;
    assert.equal(drain(FRAME_LIMIT), 0);
    assert.equal(structuralMutations, afterAdd, "adding a row did not settle");
    assert.equal(wrapper._dcoSideEdgeObserver, null);
    assert.equal(wrapper._dcoCompactEdgeProfileControlsObserver, null);

    ownerStructureNotices = 0;
    pieces.pop();
    tbody.querySelector("tr[data-row-name='ROW-4']").remove();
    await new Promise(resolve => setImmediate(resolve));
    const removeSteps = drain(FRAME_LIMIT);
    const removeReconciliations = ownerStructureNotices;
    assert.equal(removeReconciliations, 1, "removing a row reconciled more than once");
    assert.ok(removeSteps < FRAME_LIMIT, "removing a row kept scheduling");
    assert.equal(frameQueue.length + observerQueue.length, 0, "removing a row left scheduled work");
    const afterRemove = structuralMutations;
    assert.equal(drain(FRAME_LIMIT), 0);
    assert.equal(structuralMutations, afterRemove, "removing a row did not settle");

    const beforeEdit = structuralMutations;
    pieces[0].edge_long_right_type_override = "PVC-CUSTOM";
    context.window.AlmdinaMultiEdgeBanding.schedule(frm);
    context.window.AlmdinaEdgeProfileControls.schedule(frm);
    await new Promise(resolve => setImmediate(resolve));
    const editSteps = drain(FRAME_LIMIT);
    assert.ok(editSteps < FRAME_LIMIT, "a row edit kept scheduling");
    assert.equal(frameQueue.length + observerQueue.length, 0, "a row edit left scheduled work");
    const edited = tbody.querySelector(
        "tr[data-row-name='ROW-1'] .dco-check-toggle[data-check-field='edge_long_right'] .dco-side-profile-trigger"
    );
    assert.equal(edited.textContent, "✦");
    const editMutations = structuralMutations - beforeEdit;
    assert.equal(editMutations, 1, "a row edit must change only the affected indicator");
    const afterEdit = structuralMutations;
    assert.equal(drain(FRAME_LIMIT), 0);
    assert.equal(structuralMutations, afterEdit, "the row edit did not settle");

    const stray = element("span");
    stray.className = "dco-cut-rule-hint";
    toolbar.appendChild(stray);
    const repairSteps = drain(FRAME_LIMIT);
    assert.ok(repairSteps > 0 && repairSteps < FRAME_LIMIT, "replacing a toolbar child did not settle");
    assert.equal(frameQueue.length + observerQueue.length, 0);
    assert.equal(toolbar.querySelector(".dco-cut-rule-hint"), null, "toolbar stability left an extra toolbar child");
    const repairedMutations = structuralMutations;
    assert.equal(drain(FRAME_LIMIT), 0);
    assert.equal(structuralMutations, repairedMutations, "the repair pass scheduled another mutation cycle");

    const titles = help.querySelectorAll(".dco-measurement-title");
    assert.equal(titles.length, 1);
    assert.equal(String(titles[0].textContent).trim(), "Door Measurements Table");
    assert.equal(help.children.length, 1);
    assert.equal(wrapper.querySelector(".dco-cut-rule-hint"), null);
    assert.equal(toolbar.querySelectorAll(".dco-measurement-table-actions").length, 1);
    const actions = toolbar.querySelector(".dco-measurement-table-actions");
    assert.equal(actions.children.length, 3);
    assert.ok(actions.querySelector(".dco-print-measurements"));
    assert.ok(actions.querySelector(".dco-open-measurements-window"));
    assert.ok(actions.querySelector(".dco-input-help"));

    const toggles = tbody.querySelectorAll(".dco-check-toggle[data-check-field]");
    assert.equal(toggles.length, 12);
    toggles.forEach(toggle => {
        assert.equal(toggle.querySelectorAll(".dco-side-profile-trigger").length, 1);
    });
    assert.equal(table.querySelectorAll("th.dco-col-edge-bulk").length, 1);
    tbody.querySelectorAll("tr[data-row-name]").forEach(row => {
        assert.equal(row.querySelectorAll("td.dco-col-edge-bulk").length, 1);
        assert.equal(row.querySelectorAll(".dco-all-sides-profile-button").length, 1);
    });

    assert.equal(connectedWrapperObservers().length, 1);
    assert.equal(connectedWrapperObservers()[0].options.subtree, true);
    const toolbarObservers = observations.filter(observer =>
        !observer.disconnected
        && (observer.registrations || []).some(registration => registration.target === toolbar)
    );
    assert.equal(toolbarObservers.length, 1);
    assert.equal(toolbarObservers[0].options.subtree, false);

    console.log(
        "measurement toolbar shared loop settled in "
        + steps
        + " frames with "
        + settledMutations
        + " DOM mutations; row edit mutations="
        + editMutations
        + "; add reconciliations="
        + addReconciliations
        + "; remove reconciliations="
        + removeReconciliations
    );
});
