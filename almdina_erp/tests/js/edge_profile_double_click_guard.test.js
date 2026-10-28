"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const root = path.resolve(__dirname, "../..");
const source = fs.readFileSync(
    path.join(
        root,
        "public/js/door_cutting_order/order_entry/edge_banding/door_cutting_order_edge_profile_double_click_guard.js"
    ),
    "utf8"
);

assert.match(source, /flushPendingClick/);
assert.match(source, /pendingClick\.key === (?:target|identity)\.key|pendingClick\.key === target\.key/);
assert.match(source, /orderKey/);
assert.doesNotMatch(source, /CLICK_DELAY_MS\s*=\s*[3-9]\d{2,}/);

const listeners = { click: [], dblclick: [], keydown: [] };
const timers = new Map();
let nextTimerId = 1;
let now = 0;

function clearAllTimers() {
    timers.clear();
}

function runDueTimers() {
    const due = [...timers.entries()]
        .filter(([, entry]) => entry.fireAt <= now)
        .sort((left, right) => left[1].fireAt - right[1].fireAt);
    due.forEach(([id, entry]) => {
        timers.delete(id);
        entry.fn();
    });
}

function advance(ms) {
    now += ms;
    runDueTimers();
}

function element(tag, attrs = {}) {
    const children = [];
    const attributes = { ...attrs };
    const classes = new Set(String(attrs.class || "").split(/\s+/).filter(Boolean));
    const dataset = {};
    Object.keys(attrs).forEach(key => {
        if (key.startsWith("data-")) {
            const raw = key.slice(5);
            const camel = raw.replace(/-([a-z])/g, (_, ch) => ch.toUpperCase());
            dataset[camel] = String(attrs[key]);
        }
    });
    const node = {
        tagName: String(tag || "div").toUpperCase(),
        nodeType: 1,
        children,
        parentElement: null,
        dataset,
        className: String(attrs.class || ""),
        disabled: Boolean(attrs.disabled),
        isConnected: true,
        clickCount: 0,
        classList: {
            add(...names) { names.filter(Boolean).forEach(name => classes.add(name)); },
            remove(...names) { names.forEach(name => classes.delete(name)); },
            contains(name) { return classes.has(name); },
            toggle(name, force) {
                const next = force === undefined ? !classes.has(name) : Boolean(force);
                if (next) classes.add(name);
                else classes.delete(name);
                node.className = [...classes].join(" ");
            },
        },
        appendChild(child) {
            child.parentElement = node;
            children.push(child);
            return child;
        },
        closest(selector) {
            let current = node;
            while (current) {
                if (matches(current, selector)) return current;
                current = current.parentElement;
            }
            return null;
        },
        querySelector(selector) {
            const all = [node, ...descendants(node)];
            return all.find(item => matches(item, selector)) || null;
        },
        querySelectorAll(selector) {
            return [node, ...descendants(node)].filter(item => matches(item, selector));
        },
        contains(other) {
            if (other === node) return true;
            return descendants(node).includes(other);
        },
        click() {
            node.clickCount += 1;
            dispatch("click", {
                target: node,
                detail: 1,
                fromReplay: true,
            });
        },
        getAttribute(name) {
            if (name === "class") return [...classes].join(" ");
            return Object.prototype.hasOwnProperty.call(attributes, name) ? attributes[name] : null;
        },
        setAttribute(name, value) {
            attributes[name] = String(value);
            if (name.startsWith("data-")) {
                const raw = name.slice(5);
                const camel = raw.replace(/-([a-z])/g, (_, ch) => ch.toUpperCase());
                dataset[camel] = String(value);
            }
            if (name === "class") {
                classes.clear();
                String(value).split(/\s+/).filter(Boolean).forEach(item => classes.add(item));
                node.className = [...classes].join(" ");
            }
        },
    };
    Object.defineProperty(node, "className", {
        get() { return [...classes].join(" "); },
        set(value) {
            classes.clear();
            String(value || "").split(/\s+/).filter(Boolean).forEach(item => classes.add(item));
        },
        configurable: true,
    });
    return node;
}

function descendants(node) {
    const found = [];
    node.children.forEach(child => {
        found.push(child, ...descendants(child));
    });
    return found;
}

function matches(node, selector) {
    let raw = String(selector || "").trim();
    if (!raw || !node || node.nodeType !== 1) return false;
    if (raw.includes(",")) return raw.split(",").some(part => matches(node, part.trim()));
    while (raw.includes("[")) {
        const attribute = raw.match(/\[([^\]=\]]+)(?:=["']?([^"'\]]+)["']?)?\]/);
        if (!attribute) break;
        const actual = node.getAttribute(attribute[1]) || node.dataset[
            attribute[1].replace(/^data-/, "").replace(/-([a-z])/g, (_, ch) => ch.toUpperCase())
        ];
        if (attribute[2] === undefined) {
            if (actual == null) return false;
        } else if (String(actual) !== attribute[2]) {
            return false;
        }
        raw = raw.replace(attribute[0], "").trim();
    }
    if (!raw) return true;
    const [tag, ...classNames] = raw.split(".");
    if (tag && node.tagName !== tag.toUpperCase()) return false;
    return classNames.every(name => node.classList.contains(name));
}

function makeToggle(side) {
    return element("button", {
        class: "dco-check-toggle dco-edge-profile-target",
        "data-edge-side": side,
        "data-check-field": ({
            long_right: "edge_long_right",
            long_left: "edge_long_left",
            width_top: "edge_width_top",
            width_bottom: "edge_width_bottom",
        })[side],
    });
}

function makeRow(name, sides) {
    const tr = element("tr", { "data-row-name": name });
    sides.forEach(side => tr.appendChild(makeToggle(side)));
    return tr;
}

const wrapperRoot = element("div");
const table = element("table");
const tbody = element("tbody");
table.appendChild(tbody);
wrapperRoot.appendChild(table);

const popoverCalls = [];
const fakeWindow = {
    AlmdinaEdgeProfileControls: {
        openSidePopover(frm, tr, config, toggle) {
            popoverCalls.push({
                order: frm.doc.name,
                row: tr.dataset.rowName,
                side: config.side,
                toggle,
            });
        },
    },
    setTimeout(fn, ms) {
        const id = nextTimerId++;
        timers.set(id, { fn, fireAt: now + Number(ms || 0) });
        return id;
    },
    clearTimeout(id) {
        timers.delete(id);
    },
};

const formHandlers = [];
const fakeFrappe = {
    almdina: { orderCanEdit() { return true; } },
    ui: {
        form: {
            on(_doctype, handlers) { formHandlers.push(handlers); },
        },
    },
};

function dispatch(type, { target, detail = 1, fromReplay = false }) {
    const event = {
        target,
        detail,
        preventDefault() {},
        stopPropagation() {},
        stopImmediatePropagation() {},
        fromReplay,
    };
    listeners[type].forEach(listener => listener(event));
}

const context = vm.createContext({
    window: fakeWindow,
    document: {
        addEventListener(type, listener) {
            if (!listeners[type]) listeners[type] = [];
            listeners[type].push(listener);
        },
    },
    frappe: fakeFrappe,
    console,
    setTimeout: fakeWindow.setTimeout,
    clearTimeout: fakeWindow.clearTimeout,
    Number,
    String,
    Boolean,
    Array,
    Object,
    Map,
    Set,
    Error,
});

vm.runInContext(source, context, { filename: "edge_profile_double_click_guard.js" });
const guard = fakeWindow.AlmdinaEdgeProfileDoubleClickGuard;
assert.equal(typeof guard.flushPendingClick, "function");
assert.equal(typeof guard.cancelPendingClick, "function");
assert.equal(guard.CLICK_DELAY_MS, 260);

const frm = {
    doc: { name: "DCO-EDGE-1", docstatus: 0, doctype: "Door Cutting Order" },
    fields_dict: {
        pieces_fast_entry: {
            $wrapper: { get() { return wrapperRoot; } },
        },
    },
};
formHandlers.forEach(handlers => handlers.refresh(frm));

const sides = ["long_right", "long_left", "width_top", "width_bottom"];
const rowA = makeRow("ROW-A", sides);
const rowB = makeRow("ROW-B", sides);
tbody.appendChild(rowA);
tbody.appendChild(rowB);

function toggleFor(row, side) {
    return row.querySelector(`.dco-check-toggle.dco-edge-profile-target[data-edge-side="${side}"]`);
}

function clickToggle(toggle, detail = 1) {
    dispatch("click", { target: toggle, detail });
}

function dblclickToggle(toggle) {
    dispatch("dblclick", { target: toggle, detail: 2 });
}

function clickCounts(row) {
    return sides.map(side => toggleFor(row, side).clickCount);
}

// 1) Four rapid singles on one door — all applied once.
sides.forEach(side => clickToggle(toggleFor(rowA, side)));
assert.deepEqual(clickCounts(rowA), [1, 1, 1, 0], "first three flush immediately; last still pending");
advance(260);
assert.deepEqual(clickCounts(rowA), [1, 1, 1, 1]);

// Clear by toggling all four off rapidly.
sides.forEach(side => clickToggle(toggleFor(rowA, side)));
advance(260);
assert.deepEqual(clickCounts(rowA), [2, 2, 2, 2]);

// 2) Rapid clicks across two doors — none dropped.
clearAllTimers();
guard.cancelPendingClick();
const aRightBefore = toggleFor(rowA, "long_right").clickCount;
const bTopBefore = toggleFor(rowB, "width_top").clickCount;
clickToggle(toggleFor(rowA, "long_right"));
clickToggle(toggleFor(rowB, "width_top"));
assert.equal(toggleFor(rowA, "long_right").clickCount, aRightBefore + 1, "row A flushes when row B is clicked");
assert.equal(toggleFor(rowB, "width_top").clickCount, bTopBefore, "row B still pending");
advance(260);
assert.equal(toggleFor(rowB, "width_top").clickCount, bTopBefore + 1);

// 3) Double-click same side opens popover without an extra single replay.
clearAllTimers();
popoverCalls.length = 0;
const same = toggleFor(rowA, "long_left");
const before = same.clickCount;
clickToggle(same, 1);
clickToggle(same, 2);
dblclickToggle(same);
assert.equal(same.clickCount, before, "double-click cancels the delayed single on the same side");
assert.equal(popoverCalls.length, 1);
assert.equal(popoverCalls[0].side, "long_left");
assert.equal(popoverCalls[0].row, "ROW-A");

// 4) Pending side A then double-click side B — A applies, B opens popover.
clearAllTimers();
popoverCalls.length = 0;
const first = toggleFor(rowA, "width_bottom");
const second = toggleFor(rowA, "long_right");
const firstBefore = first.clickCount;
const secondBefore = second.clickCount;
clickToggle(first, 1);
clickToggle(second, 1);
clickToggle(second, 2);
dblclickToggle(second);
assert.equal(first.clickCount, firstBefore + 1, "pending different side flushes before double-click");
assert.equal(second.clickCount, secondBefore, "double-clicked side does not get a delayed single");
assert.equal(popoverCalls.length, 1);
assert.equal(popoverCalls[0].side, "long_right");

// 5) Virtual row materializes while a click is pending — resolve via live <tr>.
clearAllTimers();
const virtual = makeRow("__virtual__1", sides);
tbody.appendChild(virtual);
const virtualToggle = toggleFor(virtual, "width_top");
clickToggle(virtualToggle, 1);
virtual.dataset.rowName = "ROW-NEW";
virtual.setAttribute("data-row-name", "ROW-NEW");
// Detach the original button reference path by marking toggle disconnected but
// keeping a replacement on the same row (simulates a partial rebuild).
virtualToggle.isConnected = false;
const replacement = makeToggle("width_top");
virtual.appendChild(replacement);
advance(260);
assert.equal(replacement.clickCount, 1, "pending click retargets the live side button after materialize");

// 6) Save flush applies the pending single immediately.
clearAllTimers();
const saveToggle = toggleFor(rowB, "long_left");
const saveBefore = saveToggle.clickCount;
clickToggle(saveToggle, 1);
assert.equal(saveToggle.clickCount, saveBefore);
assert.equal(guard.flushPendingClick(frm), true);
assert.equal(saveToggle.clickCount, saveBefore + 1);
assert.equal(guard.flushPendingClick(frm), false);

// 7) Switching orders cancels the pending timer — no cross-order mutation.
clearAllTimers();
const cross = toggleFor(rowA, "width_top");
const crossBefore = cross.clickCount;
clickToggle(cross, 1);
const otherFrm = {
    doc: { name: "DCO-EDGE-2", docstatus: 0, doctype: "Door Cutting Order" },
    fields_dict: frm.fields_dict,
};
formHandlers.forEach(handlers => handlers.refresh(otherFrm));
advance(500);
assert.equal(cross.clickCount, crossBefore, "pending click must not fire after order switch");
assert.equal(guard.flushPendingClick(otherFrm), false);

console.log("edge_profile_double_click_guard tests passed");
