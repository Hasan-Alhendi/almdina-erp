"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

function load(relativePath, sandbox) {
    vm.runInContext(
        fs.readFileSync(path.resolve(__dirname, "../../", relativePath), "utf8"),
        sandbox,
        { filename: relativePath }
    );
}

function element(tag, attrs = {}, children = []) {
    const node = {
        tagName: String(tag).toUpperCase(),
        className: String(attrs.class || ""),
        dataset: {},
        children: [],
        parentElement: null,
        isConnected: true,
        value: attrs.value == null ? "" : String(attrs.value),
        textContent: "",
        prepend(child) { this.children.unshift(child); child.parentElement = this; },
        appendChild(child) { child.parentElement = this; this.children.push(child); return child; },
        setAttribute(name, value) { this.attrs[name] = String(value); },
        getAttribute(name) { return this.attrs[name]; },
        closest(selector) {
            let current = this;
            while (current) {
                if (selector === "tr[data-row-name]" && current.tagName === "TR") return current;
                if (selector === "select.dco-fast-select[data-field='piece_type']"
                    && current.tagName === "SELECT"
                    && current.dataset.field === "piece_type") return current;
                current = current.parentElement;
            }
            return null;
        },
        querySelector(selector) { return this.querySelectorAll(selector)[0] || null; },
        querySelectorAll(selector) {
            const found = [];
            const visit = (item) => {
                const field = item.dataset && item.dataset.field;
                const className = String(item.className || "");
                if (selector === "[data-field]" && field) found.push(item);
                if (selector === ".dco-fast-input[data-field], .dco-fast-select[data-field]" && field && (className.includes("dco-fast-input") || className.includes("dco-fast-select"))) {
                    found.push(item);
                }
                if (selector === ".dco-fast-table" && className.includes("dco-fast-table")) found.push(item);
                if (selector === ":scope > td.dco-select-col" && item.tagName === "TD") found.push(item);
                (item.children || []).forEach(visit);
            };
            visit(this);
            return found;
        },
        addEventListener(type, handler) {
            this.listeners[type] = this.listeners[type] || [];
            this.listeners[type].push(handler);
        },
        dispatch(type) {
            const event = {
                type,
                target: this,
                stopImmediatePropagation() {},
                stopPropagation() {},
            };
            const chain = [];
            let current = this;
            while (current) {
                chain.push(current);
                current = current.parentElement;
            }
            chain.slice().reverse().forEach((node) => {
                (node.listeners && node.listeners[type] || []).forEach((handler) => handler(event));
            });
        },
        focus() {},
        cloneNode() { return element(this.tagName, { class: this.className }); },
        contains(other) {
            let current = other;
            while (current) {
                if (current === this) return true;
                current = current.parentElement;
            }
            return false;
        },
        classList: null,
        listeners: {},
        attrs: { ...attrs },
    };
    Object.entries(attrs).forEach(([name, value]) => {
        if (name.startsWith("data-")) node.dataset[name.slice(5).replace(/-([a-z])/g, (_, letter) => letter.toUpperCase())] = String(value);
    });
    const classes = new Set(String(attrs.class || "").split(/\s+/).filter(Boolean));
    node.classList = {
        contains: (name) => classes.has(name),
        add: (name) => classes.add(name),
        remove: (...names) => names.forEach((name) => classes.delete(name)),
        toggle: (name, enabled) => { if (enabled) classes.add(name); else classes.delete(name); },
    };
    children.forEach((child) => node.appendChild(child));
    return node;
}

const sandbox = vm.createContext({
    console,
    Object,
    Array,
    String,
    Number,
    Boolean,
    Promise,
    Set,
    Map,
    Math,
    JSON,
    Date,
    queueMicrotask,
    setTimeout,
    clearTimeout,
    requestAnimationFrame: (callback) => callback(),
    __: (message) => String(message),
});
sandbox.window = sandbox;
sandbox.document = {
    documentElement: { lang: "ar" },
    createElement: (tag) => element(tag),
    getElementById() { return null; },
    head: { appendChild() {} },
};
sandbox.frappe = {
    ui: { form: { on() {} } },
    utils: { escape_html: (value) => String(value ?? "") },
    model: {
        add_child(doc, _doctype, fieldname) {
            const row = { name: `new-${(doc[fieldname] || []).length + 1}`, qty: 1, doctype: "Door Cutting Order Detail" };
            doc[fieldname] = doc[fieldname] || [];
            doc[fieldname].push(row);
            return row;
        },
    },
    show_alert() {},
};
sandbox.$ = () => ({
    find() { return this; },
    get() { return element("tbody"); },
    each() {},
});

load("public/js/door_cutting_order/drawing/door_cutting_order_glass_shape_ux.js", sandbox);
load("public/js/door_cutting_order/drawing/door_cutting_order_liner_geometry.js", sandbox);
load("public/js/door_cutting_order/drawing/door_cutting_order_liner_ux.js", sandbox);
load("public/js/door_cutting_order/order_entry/extra_addons/door_cutting_order_extra_addons_ux.js", sandbox);
load("public/js/door_cutting_order/order_entry/measurements/door_cutting_order_table_performance_ux.js", sandbox);
load("public/js/door_cutting_order/order_entry/door_cutting_order_operator_ux.js", sandbox);

const width = element("input", { class: "dco-fast-input", "data-field": "width_cm", value: "100" });
const length = element("input", { class: "dco-fast-input", "data-field": "length_cm", value: "100" });
const pieceType = element("select", { class: "dco-fast-select dco-piece-type-select", "data-field": "piece_type", value: "Glass" });
const selectCell = element("td", { class: "dco-select-col" });
selectCell.replaceChildren = () => {};
const virtual = element("tr", { class: "dco-virtual-row", "data-row-name": "__virtual__glass" }, [
    selectCell, width, length, pieceType,
]);
const table = element("table", { class: "dco-fast-table" }, [virtual]);
const root = element("div", {}, [table]);
const frm = {
    doc: { docstatus: 0, status: "Draft", pieces: [], name: "DCO-GLASS" },
    fields_dict: { pieces_fast_entry: { $wrapper: { get: () => root, find() { return { get: () => element("tbody"), each() {} }; } } } },
    script_manager: { trigger() { return Promise.resolve(); } },
    dirty() {},
};

sandbox.window.AlmdinaTablePerformanceUX.refreshAll(frm);
pieceType.dispatch("change");
const created = frm.doc.pieces[0];
assert.equal(created.piece_type, "Glass");
assert.equal(created.glass_margin_mode, "All Directions");
assert.equal(created.glass_margin_mm, 60);
assert.equal(created.width_cm, 100);
assert.equal(created.length_cm, 100);
const freshPiece = sandbox.window.AlmdinaLinerGeometry.pieceFromRow(created);
assert.equal(
    sandbox.window.AlmdinaLinerGeometry.validationCode(freshPiece, "edge_long_left", 1, 2),
    ""
);

const saved = {
    name: "saved-glass",
    piece_type: "Glass",
    width_cm: 100,
    length_cm: 100,
    qty: 1,
    glass_margin_mode: "All Directions",
    glass_margin_mm: 80,
};
const savedSelect = element("select", { class: "dco-fast-select", "data-field": "piece_type", value: "Glass" });
const savedWidth = element("input", { class: "dco-fast-input", "data-field": "width_cm", value: "100" });
const savedLength = element("input", { class: "dco-fast-input", "data-field": "length_cm", value: "100" });
const savedRowElement = element("tr", { "data-row-name": "saved-glass" }, [savedSelect, savedWidth, savedLength]);
const savedRoot = element("div", {}, [savedRowElement]);
const savedFrm = {
    doc: { docstatus: 0, status: "Draft", pieces: [saved], name: "DCO-SAVED" },
    fields_dict: { pieces_fast_entry: { $wrapper: { get: () => savedRoot } } },
    dirty() {},
};
sandbox.window.AlmdinaDoorCuttingFastEntry.flush(savedFrm);
assert.equal(saved.glass_margin_mm, 80);
assert.equal(saved.glass_margin_mode, "All Directions");

saved.glass_margin_mode = "Individual Sides";
saved.glass_margin_mm = 0;
saved.glass_margin_top_mm = 50;
saved.glass_margin_bottom_mm = 80;
saved.glass_margin_right_mm = 40;
saved.glass_margin_left_mm = 60;
sandbox.window.AlmdinaDoorCuttingFastEntry.flush(savedFrm);
assert.equal(saved.glass_margin_top_mm, 50);
assert.equal(saved.glass_margin_bottom_mm, 80);
assert.equal(saved.glass_margin_right_mm, 40);
assert.equal(saved.glass_margin_left_mm, 60);

const regular = { name: "regular-1", piece_type: "Regular", width_cm: 40, length_cm: 60, qty: 1 };
const regularSelect = element("select", { class: "dco-fast-select", "data-field": "piece_type", value: "Glass" });
const regularRow = element("tr", { "data-row-name": "regular-1" }, [regularSelect]);
const regularRoot = element("div", {}, [regularRow]);
const regularFrm = {
    doc: { docstatus: 0, status: "Draft", pieces: [regular], name: "DCO-REGULAR" },
    fields_dict: { pieces_fast_entry: { $wrapper: { get: () => regularRoot } } },
    dirty() {},
};
sandbox.window.AlmdinaDoorCuttingFastEntry.flush(regularFrm);
assert.equal(regular.piece_type, "Glass");
assert.equal(regular.glass_margin_mode, "All Directions");
assert.equal(regular.glass_margin_mm, 60);

const editor = sandbox.window.AlmdinaLinerEditor;
const uniformPreview = editor.previewSvg(editor.draftFromRow({
    piece_type: "Glass",
    width_cm: 100,
    length_cm: 100,
    glass_margin_mode: "All Directions",
    glass_margin_mm: 60,
    extra_liner: 1,
    liner_reference_side: "edge_long_left",
    liner_offset_cm: 1,
    liner_width_cm: 2,
    liner_start_cm: 0,
    liner_length_cm: 20,
}));
assert.match(uniformPreview, /data-glass-opening="1"/);
assert.match(uniformPreview, /data-liner-strip="1"/);
assert.match(uniformPreview, /data-glass-margin-caption="1"/);
assert.match(uniformPreview, /6 سم|6 cm/);

const uneven = editor.draftFromRow({
    piece_type: "Glass",
    width_cm: 100,
    length_cm: 100,
    glass_margin_mode: "Individual Sides",
    glass_margin_top_mm: 50,
    glass_margin_bottom_mm: 80,
    glass_margin_right_mm: 40,
    glass_margin_left_mm: 60,
    extra_liner: 1,
    liner_reference_side: "edge_long_left",
    liner_offset_cm: 1,
    liner_width_cm: 2,
});
const unevenPreview = editor.previewSvg(uneven);
const opening = unevenPreview.match(/data-glass-opening="1" points="([^"]+)"/);
assert.ok(opening, "individual glass margins must draw an opening");
const points = opening[1].split(" ").map((pair) => pair.split(",").map(Number));
const openingLeft = Math.min(...points.map((point) => point[0]));
const openingRight = Math.max(...points.map((point) => point[0]));
const openingTop = Math.min(...points.map((point) => point[1]));
const openingBottom = Math.max(...points.map((point) => point[1]));
const outline = unevenPreview.match(/<polygon points="([^"]+)"/)[1].split(" ").map((pair) => pair.split(",").map(Number));
const outlineLeft = Math.min(...outline.map((point) => point[0]));
const outlineRight = Math.max(...outline.map((point) => point[0]));
const outlineTop = Math.min(...outline.map((point) => point[1]));
const outlineBottom = Math.max(...outline.map((point) => point[1]));
assert.ok(Math.abs((openingLeft - outlineLeft) - (outlineRight - openingRight)) > 1);
assert.ok(Math.abs((openingTop - outlineTop) - (outlineBottom - openingBottom)) > 1);
assert.match(unevenPreview, /5 · 8 · 4 · 6 cm/);
const banded = editor.draftFromRow({
    piece_type: "Glass",
    width_cm: 52,
    length_cm: 72,
    cut_width_cm: 51.8,
    cut_length_cm: 71.8,
    glass_margin_mode: "All Directions",
    glass_margin_mm: 60,
    edge_long_left: 1,
    edge_long_right: 1,
    edge_width_top: 1,
    edge_width_bottom: 1,
    edge_long_thickness_mm: 1,
    edge_width_thickness_mm: 1,
});
assert.equal(banded.piece.glassFrameMm.left, 59);
const bandedPreview = editor.previewSvg(banded);
const bandedOpening = bandedPreview.match(/data-glass-opening="1" points="([^"]+)"/);
assert.ok(bandedOpening);
const bandedLeft = Math.min(...bandedOpening[1].split(" ").map((pair) => Number(pair.split(",")[0])));
assert.ok(Math.abs(bandedLeft - (30 + (59 / 518) * 300)) < 0.2);
assert.equal(
    sandbox.window.AlmdinaLinerGeometry.validationCode(uneven.piece, "edge_long_left", 5, 2),
    "liner_enters_glass_opening"
);
const regularPreview = editor.previewSvg(editor.draftFromRow({
    piece_type: "Regular",
    width_cm: 40,
    length_cm: 60,
    extra_liner: 1,
    liner_reference_side: "edge_width_top",
    liner_offset_cm: 2,
    liner_width_cm: 1.5,
}));
assert.doesNotMatch(regularPreview, /data-glass-opening|data-glass-margin-caption/);

console.log("door_cutting_order_glass_margin_default.test.js: ok");
