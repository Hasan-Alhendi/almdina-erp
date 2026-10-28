"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const root = path.resolve(__dirname, "../..");
const source = fs.readFileSync(
    path.join(root, "public/js/door_cutting_order/order_entry/edge_banding/door_cutting_order_edge_profile_controls_ux.js"),
    "utf8"
);
const catalog = fs.readFileSync(path.join(root, "translations/ar.csv"), "utf8");

assert.match(catalog, /^Default edge banding,قشاط افتراضي$/m);
assert.match(catalog, /^Mixed edge banding,قشاطات متعددة$/m);
assert.doesNotMatch(source, /row\.edge_type/);
assert.match(source, /__\("Apply to all four"\)/);
assert.match(source, /__\("Default edge banding"\)/);
assert.match(source, /__\("Mixed edge banding"\)/);
assert.match(source, /text-overflow:ellipsis/);
assert.match(source, /width:122px!important/);

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
        } else if (actual !== attribute[2]) return false;
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
    for (const child of node.children) found.push(child, ...descendants(child));
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
        const parts = raw.replace(/^:scope\s*>\s*/, "").split(/\s+/).filter(Boolean);
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
        textWrites: 0,
        innerHtmlWrites: 0,
        isConnected: true,
        style: {},
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
                if (next) this.add(name);
                else this.remove(name);
            },
        },
        setAttribute(name, value) { attributes[name] = String(value); },
        getAttribute(name) {
            return Object.prototype.hasOwnProperty.call(attributes, name) ? attributes[name] : null;
        },
        appendChild(child) {
            if (child.parentElement) child.remove();
            child.parentElement = node;
            children.push(child);
            return child;
        },
        insertAdjacentElement(position, child) {
            const parent = node.parentElement;
            if (!parent) return null;
            if (child.parentElement) child.remove();
            child.parentElement = parent;
            const index = parent.children.indexOf(node);
            parent.children.splice(position === "afterend" ? index + 1 : index, 0, child);
            return child;
        },
        remove() {
            const parent = node.parentElement;
            if (!parent) return;
            const index = parent.children.indexOf(node);
            if (index >= 0) parent.children.splice(index, 1);
            node.parentElement = null;
        },
        replaceChildren(...nodes) {
            children.splice(0, children.length);
            nodes.forEach(child => {
                child.parentElement = node;
                children.push(child);
            });
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
        contains(child) {
            let current = child;
            while (current) {
                if (current === node) return true;
                current = current.parentElement;
            }
            return false;
        },
        addEventListener(type, fn) {
            node._listeners = node._listeners || {};
            node._listeners[type] = node._listeners[type] || [];
            node._listeners[type].push(fn);
        },
        dispatch(type) {
            const event = {
                target: node,
                preventDefault() {},
                stopPropagation() {},
                stopImmediatePropagation() {},
            };
            let current = node;
            while (current) {
                (current._listeners && current._listeners[type] || []).forEach(fn => fn(event));
                current = current.parentElement;
            }
        },
        getBoundingClientRect() {
            return { top: 20, left: 20, right: 140, bottom: 58, width: 120, height: 38 };
        },
        focus() {},
        dispatchEvent() {},
    };
    Object.defineProperty(node, "textContent", {
        get() {
            if (node._text) return node._text;
            return children.map(child => child.textContent || "").join("");
        },
        set(value) {
            node.textWrites += 1;
            node._text = String(value);
            node._html = "";
            children.splice(0, children.length);
        },
    });
    Object.defineProperty(node, "innerHTML", {
        get() { return node._html || ""; },
        set(value) {
            node.innerHtmlWrites += 1;
            node._html = String(value);
            node._text = "";
            children.splice(0, children.length);
        },
    });
    return node;
}

const head = element("head");
const body = element("body");
const document = {
    head,
    body,
    documentElement: element("html"),
    createElement: element,
    getElementById(id) {
        return descendants(head).find(node => node.id === id || node.getAttribute("id") === id) || null;
    },
    addEventListener() {},
};
Object.defineProperty(element("style"), "id", { set() {}, get() { return ""; } });
const styleProto = element("style");
Object.defineProperty(styleProto, "id", {
    set(value) { styleProto.setAttribute("id", value); },
    get() { return styleProto.getAttribute("id"); },
});

let editable = true;
let dirtyCalls = 0;
const arabic = {
    "Apply to all four": "تطبيق على الأربعة",
    "Default edge banding": "قشاط افتراضي",
    "Mixed edge banding": "قشاطات متعددة",
};
let language = arabic;

const profiles = new Map([
    ["pvc-white", { name: "pvc-white", label: "PVC أبيض" }],
    ["pvc-script", { name: "pvc-script", label: 'PVC <b> & "مطبخ"' }],
    ["oak", { name: "oak", label: "Oak veneer banding for very long kitchen runs and exterior facades" }],
]);

function blankPiece(name) {
    return {
        doctype: "Door Cutting Order Detail",
        name,
        piece_type: "Regular",
        edge_width_top: 1,
        edge_width_bottom: 1,
        edge_long_right: 1,
        edge_long_left: 1,
        edge_width_top_type_override: "",
        edge_width_bottom_type_override: "",
        edge_long_right_type_override: "",
        edge_long_left_type_override: "",
        edge_type: "SHOULD-NOT-BE-USED",
    };
}

const pieces = [blankPiece("ROW-1")];
const wrapper = element("div");
const table = element("table");
table.className = "dco-fast-table";
const thead = element("thead");
const headerRow = element("tr");
const edgeTypeHeader = element("th");
edgeTypeHeader.className = "dco-col-edge-type";
headerRow.appendChild(edgeTypeHeader);
thead.appendChild(headerRow);
const tbody = element("tbody");
table.appendChild(thead);
table.appendChild(tbody);
const help = element("div");
help.className = "dco-fast-help";
wrapper.appendChild(help);
wrapper.appendChild(table);

function measurementRow(name) {
    const row = element("tr");
    row.dataset.rowName = name;
    row.setAttribute("data-row-name", name);
    const edges = element("td");
    edges.className = "dco-col-edges";
    const buttons = element("div");
    buttons.className = "dco-edge-buttons";
    edges.appendChild(buttons);
    const edgeType = element("td");
    edgeType.className = "dco-col-edge-type";
    row.appendChild(edges);
    row.appendChild(edgeType);
    return row;
}

tbody.appendChild(measurementRow("ROW-1"));

const form = {
    doc: { docstatus: 0, default_edge_type: "pvc-white", pieces },
    fields_dict: { pieces_fast_entry: { $wrapper: { get() { return wrapper; } } } },
    dirty() { dirtyCalls += 1; },
    script_manager: { trigger() { return Promise.resolve(); } },
};

const context = vm.createContext({
    window: {},
    document,
    frappe: {
        utils: {
            escape_html(value) {
                return String(value ?? "")
                    .replaceAll("&", "&amp;")
                    .replaceAll("<", "&lt;")
                    .replaceAll(">", "&gt;")
                    .replaceAll('"', "&quot;");
            },
        },
        ui: { form: { on() {} } },
        almdina: { orderCanEdit() { return editable; } },
    },
    __: message => (Object.prototype.hasOwnProperty.call(language, message) ? language[message] : message),
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
    MutationObserver: class {
        observe() {}
        disconnect() {}
    },
    requestAnimationFrame() { return 1; },
    setTimeout() { return 1; },
    CustomEvent: class {
        constructor(type, init) { this.type = type; this.detail = init && init.detail; }
    },
});
context.window = context;
context.window.document = document;
context.window.innerWidth = 1200;
context.window.innerHeight = 800;
context.window.addEventListener = () => {};
context.window.AlmdinaLocale = { direction() { return "rtl"; }, isRTL() { return true; } };
context.window.AlmdinaMultiEdgeBanding = { profiles: () => profiles, schedule() {} };
context.window.AlmdinaClippedCornerGeometry = {
    locksAdjacentSidesForBreak(row) { return Boolean(row && row.edge_break); },
    breakAdjacentSides() { return ["edge_width_top", "edge_long_right"]; },
};
vm.runInContext(source, context);
const controls = context.window.AlmdinaEdgeProfileControls;

function buttonFor(name = "ROW-1") {
    return tbody.querySelector(`tr[data-row-name='${name}'] .dco-all-sides-profile-button`);
}
function captionFor(name = "ROW-1") {
    return buttonFor(name).querySelector(":scope > .dco-bulk-label");
}

controls.apply(form);
const header = table.querySelector("th.dco-col-edge-bulk");
assert.equal(header.textContent, "تطبيق على الأربعة");
assert.equal(captionFor().textContent, "قشاط افتراضي");
assert.equal(buttonFor().querySelector(":scope > .dco-bulk-chevron").textContent, "⌄");
assert.equal(buttonFor().disabled, false);

const headerWrites = header.textWrites;
const captionWrites = captionFor().textWrites;
dirtyCalls = 0;
controls.apply(form);
assert.equal(header.textWrites, headerWrites, "unchanged header text must not be rewritten");
assert.equal(captionFor().textWrites, captionWrites, "unchanged button text must not be rewritten");
assert.equal(dirtyCalls, 0, "drawing the button must not dirty the order");
assert.equal(captionFor().innerHtmlWrites, 0);

const rowNode = tbody.querySelector("tr[data-row-name='ROW-1']");
controls.openBulkPopover(form, rowNode, buttonFor());
assert.equal(dirtyCalls, 0, "opening the list must not dirty the order");
assert.equal(pieces[0].edge_width_top_type_override, "");
controls.closePopover();

controls.applyAllSides(form, rowNode, "pvc-white");
assert.equal(captionFor().textContent, "PVC أبيض");
assert.equal(header.textContent, "تطبيق على الأربعة");
assert.equal(pieces[0].edge_width_top_type_override, "pvc-white");
assert.equal(buttonFor().title, "PVC أبيض");
assert.ok(dirtyCalls >= 1);

controls.applyAllSides(form, rowNode, "__almdina_default__");
assert.equal(captionFor().textContent, "قشاط افتراضي");
assert.equal(pieces[0].edge_width_top_type_override, "");
assert.equal(pieces[0].edge_long_left_type_override, "");

const saved = blankPiece("ROW-1");
["edge_width_top_type_override", "edge_width_bottom_type_override", "edge_long_right_type_override", "edge_long_left_type_override"]
    .forEach(field => { saved[field] = "oak"; });
form.doc.pieces = [saved];
tbody.replaceChildren(measurementRow("ROW-1"));
controls.apply(form);
assert.equal(captionFor().textContent, "Oak veneer banding for very long kitchen runs and exterior facades");
assert.equal(buttonFor().title, captionFor().textContent);
assert.equal(buttonFor().querySelector("b"), null);
assert.equal(header.textContent, "تطبيق على الأربعة");
assert.ok(table.contains(buttonFor()));

pieces[0] = saved;
saved.edge_width_top_type_override = "pvc-white";
saved.edge_width_bottom_type_override = "oak";
saved.edge_long_right_type_override = "";
saved.edge_long_left_type_override = "";
saved.edge_break = 0;
controls.apply(form);
assert.equal(captionFor().textContent, "قشاطات متعددة");

saved.edge_break = 1;
saved.edge_width_top_type_override = "ignored-locked";
saved.edge_long_right_type_override = "ignored-locked-too";
saved.edge_width_bottom_type_override = "oak";
saved.edge_long_left_type_override = "oak";
controls.apply(form);
assert.equal(
    captionFor().textContent,
    "Oak veneer banding for very long kitchen runs and exterior facades"
);

saved.edge_break = 0;
["edge_width_top_type_override", "edge_width_bottom_type_override", "edge_long_right_type_override", "edge_long_left_type_override"]
    .forEach(field => { saved[field] = "pvc-script"; });
controls.apply(form);
assert.equal(captionFor().textContent, 'PVC <b> & "مطبخ"');
assert.equal(buttonFor().title, 'PVC <b> & "مطبخ"');
assert.equal(captionFor().querySelector("b"), null);
assert.equal(captionFor().innerHtmlWrites, 0);

saved.edge_width_top_type_override = "retired-profile";
saved.edge_width_bottom_type_override = "retired-profile";
saved.edge_long_right_type_override = "retired-profile";
saved.edge_long_left_type_override = "retired-profile";
controls.apply(form);
assert.equal(captionFor().textContent, "retired-profile");

language = message => message;
editable = false;
const fresh = blankPiece("ROW-NEW");
form.doc.pieces = [fresh];
tbody.replaceChildren(measurementRow("ROW-NEW"));
controls.apply(form);
assert.equal(captionFor("ROW-NEW").textContent, "Default edge banding");
assert.equal(buttonFor("ROW-NEW").disabled, true);
assert.equal(table.querySelector("th.dco-col-edge-bulk").textContent, "Apply to all four");

console.log("bulk edge button label passed");
