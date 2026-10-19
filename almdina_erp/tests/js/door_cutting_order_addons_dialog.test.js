"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

function load(relativePath, context) {
    vm.runInContext(fs.readFileSync(path.resolve(__dirname, relativePath), "utf8"), context);
}

const fakeWindow = {};
const context = vm.createContext({
    window: fakeWindow,
    document: { documentElement: { lang: "ar" } },
    frappe: { utils: { escape_html(value) { return String(value ?? ""); } } },
    __(value, values) {
        let text = Array.isArray(value) ? value[0] : String(value ?? "");
        if (Array.isArray(values)) values.forEach((item, index) => { text = text.replaceAll(`{${index}}`, String(item)); });
        return text;
    },
    Object,
    Array,
    Boolean,
    Number,
    String,
    Math,
    Set,
    console,
});
load("../../public/js/door_cutting_order/drawing/door_cutting_order_liner_geometry.js", context);
load("../../public/js/door_cutting_order/drawing/door_cutting_order_machining_overlay.js", context);
load("../../public/js/door_cutting_order/drawing/door_cutting_order_liner_ux.js", context);
load("../../public/js/door_cutting_order/order_entry/extra_addons/door_cutting_order_extra_addons_ux.js", context);
load("../../public/js/door_cutting_order/order_entry/extra_addons/door_cutting_order_addons_dialog.js", context);

const dialog = fakeWindow.AlmdinaDoorAddonsDialog;
const row = {
    piece_type: "Regular",
    width_cm: 40,
    length_cm: 60,
    piece_no: "P-001",
    qty: 2,
    edge_width_top: 1,
    edge_long_right: 1,
    extra_double: 1,
    extra_full_door_double: 0,
    extra_liner: 1,
    liner_reference_side: "edge_width_top",
    liner_offset_cm: 2,
    liner_width_cm: 1.5,
    liner_start_cm: 0,
    liner_length_cm: 40,
    extra_back_groove: 1,
    back_groove_reference_side: "edge_long_right",
    back_groove_offset_cm: 1,
    back_groove_width_cm: 0.8,
    back_groove_start_cm: 5,
    back_groove_length_cm: 20,
    extra_recessed_handle_cutout: 0,
};
const session = dialog.createSession({ doc: {} }, row);
assert.equal(session.activeField, "extra_double");
assert.equal(session.flags.extra_double, 1);
assert.equal(session.drafts.extra_liner.enabled, true);
assert.equal(session.drafts.extra_liner.side, "edge_width_top");
assert.equal(session.drafts.extra_back_groove.side, "edge_long_right");
assert.equal(session.drafts.extra_recessed_handle_cutout.enabled, false);
assert.equal(session.drafts.extra_recessed_handle_cutout.side, "");

assert.equal(dialog.machiningDirty(session, "extra_liner"), false);
dialog.selectTab(session, "extra_back_groove");
assert.equal(dialog.machiningDirty(session, "extra_liner"), false);
assert.equal(session.activeField, "extra_back_groove");
assert.equal(session.flags.extra_double, 1);
assert.equal(row.extra_back_groove, 1);
assert.equal(session.drafts.extra_recessed_handle_cutout.enabled, false);

dialog.setEnabled(session, "extra_full_door_double", true);
assert.equal(session.flags.extra_full_door_double, 1);
assert.equal(session.flags.extra_double, 0);
assert.equal(row.extra_double, 1);
assert.equal(row.extra_full_door_double, 0);

dialog.setEnabled(session, "extra_recessed_handle_cutout", true);
fakeWindow.AlmdinaLinerEditor.selectSide(
    session.drafts.extra_recessed_handle_cutout,
    session.piece,
    "edge_width_bottom"
);
assert.equal(session.drafts.extra_recessed_handle_cutout.enabled, true);
assert.equal(row.extra_recessed_handle_cutout, 0);

const shown = JSON.parse(JSON.stringify(dialog.enabledPreviewDrafts(session).map(item => item.kind)));
assert.deepEqual(shown, ["liner", "back_groove", "recessed_handle_cutout"]);
const preview = dialog.previewMarkup(session);
assert.match(preview, /data-machining-kind="liner"/);
assert.match(preview, /data-machining-kind="back_groove"/);
assert.match(preview, /data-machining-kind="recessed_handle_cutout"/);
assert.match(preview, /data-liner-edge="1"/);

dialog.setEnabled(session, "extra_liner", false);
assert.equal(dialog.machiningDirty(session, "extra_liner"), true);
assert.equal(dialog.machiningDirty(session, "extra_back_groove"), false);
const afterRemove = JSON.parse(JSON.stringify(dialog.enabledPreviewDrafts(session).map(item => item.kind)));
assert.deepEqual(afterRemove, ["back_groove", "recessed_handle_cutout"]);
assert.equal(row.extra_liner, 1);

const clipped = dialog.createSession({ doc: {} }, {
    piece_type: "L-Shaped Corner",
    width_cm: 50,
    length_cm: 70,
    clipped_corner_position: "Top Right",
    clipped_corner_width_cm: 10,
    clipped_corner_length_cm: 12,
    edge_break: 1,
    edge_width_top: 1,
    extra_liner: 1,
    liner_reference_side: "edge_width_top",
    liner_offset_cm: 2,
    liner_width_cm: 1.5,
    liner_start_cm: 0,
    liner_length_cm: 20,
});
dialog.selectTab(clipped, "extra_liner");
const clippedPreview = dialog.previewMarkup(clipped);
assert.match(clippedPreview, /data-machining-kind="liner"/);
assert.match(clippedPreview, /data-liner-edge="1"/);
const polygon = clippedPreview.match(/<polygon points="([^"]+)"/);
assert.ok(polygon && polygon[1].split(" ").length >= 5);

const special = dialog.createSession({ doc: {} }, {
    piece_type: "Special",
    width_cm: 30,
    length_cm: 40,
    extra_double: 1,
});
assert.equal(special.supported, false);
assert.equal(special.flags.extra_double, 1);
assert.equal(Object.keys(special.drafts).length, 0);

const editor = fakeWindow.AlmdinaLinerEditor;
function machiningRow(kind, widthCm) {
    const piece = {
        piece_type: "Regular",
        width_cm: 80,
        length_cm: 210,
        edge_width_top: 1,
    };
    if (kind === "liner") {
        piece.extra_liner = 1;
        piece.liner_reference_side = "edge_width_top";
        piece.liner_offset_cm = 2;
        piece.liner_width_cm = widthCm;
        piece.liner_start_cm = 4;
        piece.liner_length_cm = 30;
    } else if (kind === "back_groove") {
        piece.extra_back_groove = 1;
        piece.back_groove_reference_side = "edge_width_top";
        piece.back_groove_offset_cm = 1.5;
        piece.back_groove_width_cm = widthCm;
        piece.back_groove_start_cm = 3;
        piece.back_groove_length_cm = 20;
    } else {
        piece.extra_recessed_handle_cutout = 1;
        piece.recessed_handle_reference_side = "edge_width_top";
        piece.recessed_handle_offset_cm = 0.5;
        piece.recessed_handle_width_cm = widthCm;
        piece.recessed_handle_start_cm = 1;
        piece.recessed_handle_length_cm = 12;
    }
    return piece;
}
const linerControls = editor.controlsHtml(editor.draftFromRow(machiningRow("liner", 1.8), "liner"));
assert.match(linerControls, /data-liner-width value="18"/);
assert.match(linerControls, /data-liner-offset value="2"/);
assert.match(linerControls, /data-liner-start value="4"/);
assert.match(linerControls, /data-liner-length value="30"/);
assert.match(linerControls, />mm</);
assert.match(editor.previewSvg(editor.draftFromRow(machiningRow("liner", 1.8), "liner")), /18 mm/);
const grooveControls = editor.controlsHtml(editor.draftFromRow(machiningRow("back_groove", 0.5), "back_groove"));
assert.match(grooveControls, /data-liner-width value="5"/);
assert.match(grooveControls, /data-liner-offset value="1.5"/);
assert.match(grooveControls, /data-liner-start value="3"/);
assert.match(grooveControls, /data-liner-length value="20"/);
const handleControls = editor.controlsHtml(editor.draftFromRow(machiningRow("recessed_handle", 1.5), "recessed_handle_cutout"));
assert.match(handleControls, /data-liner-width value="15"/);
assert.match(handleControls, /data-liner-offset value="0.5"/);
assert.match(handleControls, /data-liner-length value="12"/);
for (const controls of [linerControls, grooveControls, handleControls]) {
    for (const field of ["offset", "width", "start", "length"]) {
        const input = controls.match(new RegExp(`<input[^>]*data-liner-${field}[^>]*>`))?.[0];
        assert.ok(input, `${field} input should exist`);
        assert.match(input, /step="1"/, `${field} spinner should move one displayed unit`);
    }
}

for (const [kind, width] of [
    ["liner", 1.8],
    ["back_groove", 0.8],
    ["recessed_handle_cutout", 1],
]) {
    const valid = editor.draftFromRow(machiningRow(kind, width), kind);
    assert.equal(editor.validationMessage(valid), "", `${kind} valid dimensions`);
    assert.match(editor.validationMessage({ ...valid, lengthCm: 999 }), /exceeds|maximum/i, `${kind} excessive length`);
    assert.equal(
        editor.validationMessage({ ...valid, lengthCm: valid.edgeCm - valid.startCm + 0.024 }),
        "",
        `${kind} must retain the existing 0.25 mm span tolerance`,
    );
    assert.ok(
        editor.validationMessage({ ...valid, lengthCm: valid.edgeCm - valid.startCm + 0.026 }),
        `${kind} span beyond the existing tolerance must be rejected`,
    );
    assert.ok(editor.validationMessage({ ...valid, offsetCm: -0.1 }), `${kind} negative offset`);
    assert.ok(editor.validationMessage({ ...valid, widthCm: 0 }), `${kind} invalid width`);
    assert.ok(editor.validationMessage({ ...valid, side: "edge_break_only" }), `${kind} invalid side`);
    assert.ok(editor.validationMessage({ ...valid, startCm: -0.01 }), `${kind} negative start`);
    assert.ok(editor.validationMessage({ ...valid, startCm: NaN }), `${kind} non-finite start`);
    assert.ok(editor.validationMessage({ ...valid, lengthCm: NaN }), `${kind} non-finite length`);
    const addon = kind === "liner" ? "extra_liner"
        : kind === "back_groove" ? "extra_back_groove"
            : "extra_recessed_handle_cutout";
    const lengthField = kind === "liner" ? "liner_length_cm"
        : kind === "back_groove" ? "back_groove_length_cm"
            : "recessed_handle_length_cm";
    const saveIssue = dialog.validateOrder({ doc: { pieces: [{
        ...machiningRow(kind, width),
        [addon]: 1,
        [lengthField]: 999,
        piece_no: 17,
    }] } });
    assert.equal(saveIssue.code, "liner_span_exceeds_edge", `${kind} invalid saved value must block normal save`);
    assert.match(saveIssue.message, /17/);
    assert.match(saveIssue.message, /maximum allowed length is/);
    assert.ok(saveIssue.message.includes(String(valid.edgeCm)));
    assert.ok(saveIssue.message.includes(String(valid.startCm)));
    assert.ok(saveIssue.message.includes("999"));
    assert.ok(saveIssue.message.includes(String(valid.edgeCm - valid.startCm)));
}

for (const [kind, enabled, side, offset, width, start, length] of [
    ["liner", "extra_liner", "liner_reference_side", "liner_offset_cm", "liner_width_cm", "liner_start_cm", "liner_length_cm"],
    ["back_groove", "extra_back_groove", "back_groove_reference_side", "back_groove_offset_cm", "back_groove_width_cm", "back_groove_start_cm", "back_groove_length_cm"],
    ["recessed_handle_cutout", "extra_recessed_handle_cutout", "recessed_handle_reference_side", "recessed_handle_offset_cm", "recessed_handle_width_cm", "recessed_handle_start_cm", "recessed_handle_length_cm"],
]) {
    const lRow = {
        name: `l-${kind}`,
        piece_no: 1,
        qty: 1,
        piece_type: "L-Shaped Corner",
        width_cm: 60,
        length_cm: 60,
        clipped_corner_position: "Top Right",
        clipped_corner_width_cm: 30,
        clipped_corner_length_cm: 30,
        edge_break: 1,
        [enabled]: 1,
        [side]: "edge_break",
        [offset]: 1,
        [width]: 1,
        [start]: 0,
        [length]: 60,
    };
    assert.equal(dialog.createSession({ doc: {} }, lRow).drafts[enabled].edgeCm, 60);
    assert.equal(dialog.validateOrder({ doc: { pieces: [lRow] } }), null, `${kind} accepts the 60 cm nominal L span`);
    lRow[length] = 60.2;
    assert.equal(dialog.validateOrder({ doc: { pieces: [lRow] } }).code, "liner_span_exceeds_edge", `${kind} rejects 60.2 cm`);
}

fakeWindow.AlmdinaMultiEdgeBanding = {
    calculate() {
        return { cutWidth: 20, cutLength: 60, sides: {} };
    },
};
const staleDimensionIssue = dialog.validateOrder({ doc: { pieces: [{
    ...machiningRow("liner", 3),
    edge_long_right: 1,
    liner_reference_side: "edge_long_right",
    width_cm: 40,
    cut_width_cm: 39,
    liner_offset_cm: 18,
    liner_width_cm: 3,
    liner_start_cm: 0,
    liner_length_cm: 0,
}] } });
assert.equal(staleDimensionIssue.code, "strip_outside", "save preflight must use current edge deductions");
delete fakeWindow.AlmdinaMultiEdgeBanding;

const legacyFull = editor.draftFromRow({
    ...machiningRow("liner", 1.8),
    liner_start_cm: 4.125,
    liner_length_cm: 0,
}, "liner");
assert.equal(legacyFull.fullLength, true);
assert.equal(legacyFull.lengthCm, legacyFull.edgeCm - legacyFull.startCm);
assert.equal(editor.valuesFor("liner", legacyFull, true).liner_length_cm, 0);
const negativeStoredLength = editor.draftFromRow({
    ...machiningRow("liner", 1.8),
    liner_length_cm: -1,
}, "liner");
assert.equal(negativeStoredLength.fullLength, false);
assert.equal(editor.validationIssue(negativeStoredLength).code, "liner_length_invalid");
const nonFiniteStoredLength = editor.draftFromRow({
    ...machiningRow("liner", 1.8),
    liner_length_cm: NaN,
}, "liner");
assert.equal(nonFiniteStoredLength.fullLength, false);
assert.equal(editor.validationIssue(nonFiniteStoredLength).code, "liner_length_invalid");
const precisePartial = editor.draftFromRow({
    ...machiningRow("back_groove", 0.8),
    back_groove_length_cm: 20.123,
}, "back_groove");
assert.equal(editor.controlsHtml(precisePartial).match(/data-liner-length value="([^"]+)"/)[1], "20.123");
assert.equal(editor.valuesFor("back_groove", precisePartial, true).back_groove_length_cm, 20.123);

const incompleteNewRow = {
    name: "new-incomplete-machining-row",
    __islocal: true,
    ...machiningRow("liner", 0),
    extra_liner: 1,
    liner_reference_side: "",
    liner_offset_cm: 0,
    liner_width_cm: 0,
};
assert.equal(
    editor.validationIssue(editor.draftFromRow(incompleteNewRow, "liner", { blankWhenMissing: true })).code,
    "choose_side",
    "new incomplete machining cannot be treated as a historical checkbox-only row",
);
const historicalCheckboxOnly = {
    name: "historical-checkbox-only",
    extra_liner: 1,
    liner_reference_side: "",
    liner_offset_cm: 0,
    liner_width_cm: 0,
};
assert.equal(editor.validationIssue(editor.draftFromRow(historicalCheckboxOnly, "liner", { blankWhenMissing: true })), null);

const retainedPartial = editor.draftFromRow({
    ...machiningRow("liner", 1.8),
    liner_start_cm: 5,
    liner_length_cm: 100,
}, "liner");
editor.selectSide(retainedPartial, retainedPartial.piece, "edge_width_top");
assert.equal(retainedPartial.lengthCm, 100, "a partial length must not be silently clamped when the side changes");
assert.ok(editor.validationMessage(retainedPartial));

const dialogSource = fs.readFileSync(
    path.resolve(__dirname, "../../public/js/door_cutting_order/order_entry/extra_addons/door_cutting_order_addons_dialog.js"),
    "utf8"
);
assert.doesNotMatch(dialogSource, /frm\.save\s*\(/);

console.log("Unified add-ons dialog session passed");

function ClassList(el) {
    this.el = el;
}
ClassList.prototype.contains = function contains(name) {
    return this.el.className.split(/\s+/).filter(Boolean).includes(name);
};
ClassList.prototype.add = function add(name) {
    if (!this.contains(name)) this.el.className = `${this.el.className} ${name}`.trim();
};
ClassList.prototype.remove = function remove(name) {
    this.el.className = this.el.className.split(/\s+/).filter(item => item && item !== name).join(" ");
};
ClassList.prototype.toggle = function toggle(name, force) {
    const next = force === undefined ? !this.contains(name) : Boolean(force);
    if (next) this.add(name);
    else this.remove(name);
    return next;
};

function Element(tag) {
    this.tagName = String(tag || "").toLowerCase();
    this.children = [];
    this.parent = null;
    this.attrs = {};
    this.className = "";
    this.classList = new ClassList(this);
    this.listeners = {};
    this.value = "";
    this.text = "";
    this.disabled = false;
    this.hidden = false;
}
Element.prototype.setAttribute = function setAttribute(name, value) {
    this.attrs[name] = String(value);
    if (name === "class") this.className = String(value);
    if (name === "value") this.value = String(value);
    if (name === "hidden") this.hidden = true;
    if (name === "disabled") this.disabled = true;
};
Element.prototype.getAttribute = function getAttribute(name) {
    if (name === "class") return this.className;
    return Object.prototype.hasOwnProperty.call(this.attrs, name) ? this.attrs[name] : null;
};
Element.prototype.removeAttribute = function removeAttribute(name) {
    delete this.attrs[name];
    if (name === "aria-busy") return;
};
Element.prototype.remove = function remove() {
    if (!this.parent) return;
    this.parent.children = this.parent.children.filter(child => child !== this);
    this.parent = null;
};
Element.prototype.append = function append(node) {
    node.parent = this;
    this.children.push(node);
};
Object.defineProperty(Element.prototype, "textContent", {
    get() {
        return `${this.text}${this.children.map(child => child.textContent).join("")}`;
    },
    set(value) {
        this.text = String(value ?? "");
        this.children = [];
    },
});
Element.prototype.addEventListener = function addEventListener(type, handler) {
    (this.listeners[type] || (this.listeners[type] = [])).push(handler);
};
Element.prototype.dispatch = function dispatch(type) {
    const event = {
        type,
        target: this,
        currentTarget: null,
    };
    let node = this;
    while (node) {
        event.currentTarget = node;
        (node.listeners[type] || []).forEach(handler => handler(event));
        node = node.parent;
    }
};
Element.prototype.matches = function matches(selector) {
    if (selector.startsWith("[") && selector.endsWith("]")) {
        const body = selector.slice(1, -1);
        const eq = body.indexOf("=");
        if (eq < 0) return this.getAttribute(body) !== null;
        const name = body.slice(0, eq);
        const value = body.slice(eq + 1).trim().replace(/^["']|["']$/g, "");
        return this.getAttribute(name) === value;
    }
    const pieces = selector.split(".");
    const tag = pieces[0];
    if (tag && tag !== this.tagName) return false;
    return pieces.slice(1).every(name => this.classList.contains(name));
};
Element.prototype.closest = function closest(selector) {
    let node = this;
    while (node) {
        if (typeof node.matches === "function" && node.matches(selector)) return node;
        node = node.parent;
    }
    return null;
};
Element.prototype.contains = function contains(node) {
    let current = node;
    while (current) {
        if (current === this) return true;
        current = current.parent;
    }
    return false;
};
Element.prototype.querySelectorAll = function querySelectorAll(selector) {
    const parts = selector.trim().split(/\s+/);
    const walk = (nodes, part) => {
        const found = [];
        nodes.forEach((node) => {
            node.children.forEach((child) => {
                if (child.matches(part)) found.push(child);
                found.push(...walk([child], part));
            });
        });
        return found;
    };
    let current = [this];
    parts.forEach((part) => {
        current = walk(current, part);
    });
    return current;
};
Element.prototype.querySelector = function querySelector(selector) {
    return this.querySelectorAll(selector)[0] || null;
};
Element.prototype.insertAdjacentHTML = function insertAdjacentHTML(position, html) {
    if (position !== "beforeend") return;
    parseHTML(html).forEach(node => this.append(node));
};

function parseAttrs(node, raw) {
    const pattern = /([^\s=]+)(?:\s*=\s*("([^"]*)"|'([^']*)'|([^\s"'>]+)))?/g;
    let match = pattern.exec(raw);
    while (match) {
        const name = match[1];
        const value = match[3] ?? match[4] ?? match[5] ?? "";
        node.setAttribute(name, value);
        match = pattern.exec(raw);
    }
}

function parseHTML(html) {
    const root = new Element("fragment");
    const stack = [root];
    const pattern = /<\/([a-zA-Z0-9-]+)>|<([a-zA-Z0-9-]+)([^>]*?)(\/?)>|([^<]+)/g;
    let match = pattern.exec(html);
    while (match) {
        if (match[1]) {
            if (stack.length > 1) stack.pop();
        } else if (match[2]) {
            const node = new Element(match[2]);
            parseAttrs(node, match[3] || "");
            stack[stack.length - 1].append(node);
            const voids = new Set(["input", "img", "br", "hr"]);
            if (!match[4] && !voids.has(node.tagName)) stack.push(node);
        } else if (match[5] && match[5].trim()) {
            stack[stack.length - 1].text += match[5];
        }
        match = pattern.exec(html);
    }
    return root.children;
}

Object.defineProperty(Element.prototype, "innerHTML", {
    set(html) {
        this.children = [];
        parseHTML(html).forEach(node => this.append(node));
    },
});

function tick() {
    return new Promise(resolve => setImmediate(resolve));
}

async function interactionChecks() {
    const messages = [];
    const writes = [];
    const renders = [];
    let failNext = false;
    context.frappe.msgprint = (message) => messages.push(message);
    function Dialog(options) {
        this.options = options;
        this.hidden = false;
        const wrapper = new Element("div");
        this.$wrapper = {
            addClass() {},
            find() {
                return { attr() {}, get() { return null; } };
            },
        };
        this.show = () => {};
        this.hide = () => { this.hidden = true; };
        this.get_field = () => ({
            $wrapper: {
                html(markup) { wrapper.innerHTML = markup; },
                find: (selector) => ({ get: () => wrapper.querySelector(selector) }),
            },
        });
        context.frappe.ui.dialogs.push(this);
    }
    context.frappe.ui = { Dialog, dialogs: [] };
    fakeWindow.AlmdinaDoorCuttingFastEntry = {
        isEditable() { return true; },
        render(frm) {
            const piece = frm.doc.pieces[0];
            renders.push(piece.extra_liner);
            if (frm._addonsTable) {
                fakeWindow.AlmdinaExtraDoorAddonsUX.syncAddonButtons(frm._addonsTable, piece, true);
            }
        },
    };
    fakeWindow.AlmdinaClippedCornerEditor = {
        resolveChildRow(_frm, row) { return row; },
        async commitChildValues(_frm, row, values) {
            if (failNext) {
                failNext = false;
                throw new Error("save failed");
            }
            writes.push(JSON.parse(JSON.stringify(values)));
            Object.assign(row, values);
            return row;
        },
    };

    function blankRow(extra) {
        return Object.assign({
            doctype: "Door Cutting Order Detail",
            name: "piece-1",
            piece_type: "Regular",
            width_cm: 80,
            length_cm: 210,
            piece_no: 1,
            qty: 1,
        }, extra || {});
    }

    function mountTable(order, piece) {
        const table = new Element("tr");
        table.setAttribute("data-row-name", piece.name);
        const cell = new Element("td");
        cell.innerHTML = fakeWindow.AlmdinaExtraDoorAddonsUX.renderAddonSummary(piece, { editable: true });
        table.append(cell);
        order._addonsTable = table;
        return table;
    }

    function addonLabel(table) {
        return table.querySelector(".dco-addons-open-label").textContent;
    }

    function latest() {
        const ui = context.frappe.ui.dialogs.at(-1);
        const shell = ui.get_field().$wrapper.find("[data-addons-dialog]").get(0);
        return { ui, root: shell };
    }

    const row = blankRow();
    assert.equal(dialog.open({ doc: { pieces: [row] }, dirty() {} }, row), true);
    let ui = latest();
    const footer = ui.root.querySelector(".dco-addons-footer");
    assert.equal(footer.children[0].classList.contains("dco-addons-footer-main"), true);
    assert.equal(footer.children[0].querySelector("[data-addons-cancel]") !== null, true);
    assert.equal(footer.children[0].querySelector("[data-addons-apply]") !== null, true);
    assert.equal(footer.children[1].getAttribute("data-addons-remove"), "");
    const css = fs.readFileSync(path.resolve(__dirname, "../../public/css/door_cutting_order_extra_addons.css"), "utf8");
    assert.match(css, /grid-template-areas:\s*"actions \. remove"/);
    assert.match(css, /grid-area:\s*actions/);
    assert.match(css, /grid-area:\s*remove/);
    assert.match(css, /direction:\s*ltr/);

    ui.root.querySelector('[data-addon-tab="extra_liner"]').dispatch("click");
    assert.equal(ui.root.querySelector("[data-liner-sides] .is-active"), null);
    assert.equal(ui.root.querySelector('[data-addons-preview] [data-machining-kind="liner"]'), null);
    assert.match(ui.root.querySelector("[data-addons-hint]").textContent, /reference side/);
    const beforeSide = writes.length;
    ui.root.querySelector('[data-liner-side="edge_width_top"]').dispatch("click");
    assert.equal(writes.length, beforeSide);
    assert.equal(row.extra_liner, undefined);
    assert.equal(ui.root.querySelector("[data-addon-enable]").classList.contains("is-on"), true);
    assert.equal(ui.root.querySelector('[data-liner-side="edge_width_top"]').classList.contains("is-active"), true);
    assert.equal(ui.root.querySelector('[data-addons-preview] [data-machining-kind="liner"]') !== null, true);
    const widthInput = ui.root.querySelector("[data-liner-width]");
    assert.equal(widthInput.value, "15");
    assert.match(widthInput.parent.textContent, /mm/);
    assert.match(ui.root.querySelector("[data-liner-offset]").parent.textContent, /cm/);
    assert.match(ui.root.querySelector("[data-liner-start]").parent.textContent, /cm/);
    assert.match(ui.root.querySelector("[data-liner-length]").parent.textContent, /cm/);
    assert.equal(ui.root.querySelector("[data-liner-length]").value, "80");
    assert.match(ui.root.querySelector("[data-addons-preview]").textContent, /15 mm/);
    const offset = ui.root.querySelector("[data-liner-offset]");
    offset.value = "1.2";
    offset.dispatch("input");
    widthInput.value = "18";
    widthInput.dispatch("input");
    assert.equal(ui.root.querySelector("[data-liner-offset]"), offset);
    assert.equal(widthInput.value, "18");
    assert.match(ui.root.querySelector("[data-addons-preview]").textContent, /1\.2/);
    assert.match(ui.root.querySelector("[data-addons-preview]").textContent, /18 mm/);
    ui.root.querySelector("[data-addons-apply]").dispatch("click");
    await tick();
    assert.equal(context.frappe.ui.dialogs.at(-1).hidden, true);
    assert.equal(writes.length, 1);
    assert.equal(writes[0].extra_liner, 1);
    assert.equal(writes[0].liner_offset_cm, 1.2);
    assert.equal(writes[0].liner_width_cm, 1.8);
    assert.equal(writes[0].liner_reference_side, "edge_width_top");
    assert.equal(row.extra_liner, 1);
    assert.equal(row.liner_width_cm, 1.8);
    assert.equal(renders.at(-1), 1);

    dialog.open({ doc: { pieces: [row] }, dirty() {} }, row);
    ui = latest();
    ui.root.querySelector('[data-addon-tab="extra_liner"]').dispatch("click");
    assert.equal(ui.root.querySelector("[data-liner-offset]").value, "1.2");
    assert.equal(ui.root.querySelector("[data-liner-width]").value, "18");
    assert.equal(ui.root.querySelector("[data-liner-start]").value, "0");
    assert.equal(ui.root.querySelector("[data-liner-length]").value, "80");
    assert.equal(ui.root.querySelector("[data-addon-enable]").classList.contains("is-on"), true);
    assert.equal(ui.root.querySelector('[data-liner-side="edge_width_top"]').classList.contains("is-active"), true);
    ui.root.querySelector('[data-liner-side="edge_long_left"]').dispatch("click");
    ui.root.querySelector("[data-addons-apply]").dispatch("click");
    await tick();
    assert.equal(writes.at(-1).liner_reference_side, "edge_long_left");
    assert.equal(row.liner_reference_side, "edge_long_left");

    const pair = blankRow({ name: "piece-2" });
    const pairOrder = { doc: { pieces: [pair] }, dirty() {} };
    const pairTable = mountTable(pairOrder, pair);
    dialog.open(pairOrder, pair);
    ui = latest();
    ui.root.querySelector('[data-addon-tab="extra_liner"]').dispatch("click");
    ui.root.querySelector('[data-liner-side="edge_width_bottom"]').dispatch("click");
    ui.root.querySelector("[data-liner-offset]").value = "2.5";
    ui.root.querySelector("[data-liner-offset]").dispatch("input");
    assert.equal(ui.root.querySelector("[data-liner-offset]").value, "2.5");
    assert.match(ui.root.querySelector("[data-liner-offset]").parent.textContent, /cm/);
    ui.root.querySelector('[data-addon-tab="extra_back_groove"]').dispatch("click");
    ui.root.querySelector('[data-liner-side="edge_width_top"]').dispatch("click");
    assert.equal(ui.root.querySelector("[data-liner-width]").value, "15");
    assert.match(ui.root.querySelector("[data-liner-width]").parent.textContent, /mm/);
    assert.equal(ui.root.querySelector("[data-liner-start]").value, "0");
    assert.equal(ui.root.querySelector("[data-liner-length]").value, "80");
    ui.root.querySelector("[data-liner-width]").value = "8";
    ui.root.querySelector("[data-liner-width]").dispatch("input");
    ui.root.querySelector('[data-addon-tab="extra_recessed_handle_cutout"]').dispatch("click");
    ui.root.querySelector('[data-liner-side="edge_long_right"]').dispatch("click");
    assert.equal(ui.root.querySelector("[data-liner-width]").value, "15");
    ui.root.querySelector("[data-liner-width]").value = "10";
    ui.root.querySelector("[data-liner-width]").dispatch("input");
    const beforePair = writes.length;
    ui.root.querySelector("[data-addons-apply]").dispatch("click");
    await tick();
    assert.equal(writes.length, beforePair + 1);
    assert.equal(writes.at(-1).extra_liner, 1);
    assert.equal(writes.at(-1).liner_offset_cm, 2.5);
    assert.equal(writes.at(-1).liner_reference_side, "edge_width_bottom");
    assert.equal(writes.at(-1).extra_back_groove, 1);
    assert.equal(writes.at(-1).back_groove_width_cm, 0.8);
    assert.equal(writes.at(-1).extra_recessed_handle_cutout, 1);
    assert.equal(writes.at(-1).recessed_handle_reference_side, "edge_long_right");
    assert.equal(writes.at(-1).recessed_handle_width_cm, 1);
    assert.equal(pair.extra_back_groove, 1);
    assert.equal(pair.extra_recessed_handle_cutout, 1);
    assert.equal(addonLabel(pairTable), "Liner · Back Groove");
    assert.equal(pairTable.querySelector(".dco-addons-more").textContent, "+1");

    const invalid = blankRow({ name: "piece-3" });
    dialog.open({ doc: { pieces: [invalid] }, dirty() {} }, invalid);
    ui = latest();
    ui.root.querySelector('[data-addon-tab="extra_liner"]').dispatch("click");
    ui.root.querySelector('[data-liner-side="edge_width_top"]').dispatch("click");
    const length = ui.root.querySelector("[data-liner-length]");
    length.value = "9999";
    length.dispatch("input");
    const apply = ui.root.querySelector("[data-addons-apply]");
    assert.equal(apply.disabled, true);
    assert.equal(length.getAttribute("aria-invalid"), "true");
    assert.equal(length.closest(".dco-corner-input-wrap").classList.contains("is-error"), true);
    const beforeInvalid = writes.length;
    apply.dispatch("click");
    await tick();
    assert.equal(ui.ui.hidden, false);
    assert.equal(writes.length, beforeInvalid);
    assert.equal(ui.root.querySelector("[data-addons-error]").hidden, false);
    assert.equal(ui.root.querySelector("[data-addons-preview] [data-machining-kind]"), null);
    assert.equal(invalid.extra_liner, undefined);
    length.value = "30.123";
    length.dispatch("input");
    assert.equal(apply.disabled, false, "correcting the field must re-enable Apply immediately");
    assert.equal(length.getAttribute("aria-invalid"), null);
    assert.equal(length.closest(".dco-corner-input-wrap").classList.contains("is-error"), false);
    ui.root.querySelector("[data-addons-cancel]").dispatch("click");
    assert.equal(ui.ui.hidden, true);

    const crossTabInvalid = blankRow({
        name: "piece-cross-tab-invalid",
        extra_liner: 1,
        liner_reference_side: "edge_width_top",
        liner_offset_cm: 2,
        liner_width_cm: 1.5,
        liner_start_cm: 0,
        liner_length_cm: 40,
        extra_back_groove: 1,
        back_groove_reference_side: "edge_width_top",
        back_groove_offset_cm: 1,
        back_groove_width_cm: 0.8,
        back_groove_start_cm: 0,
        back_groove_length_cm: 999,
    });
    dialog.open({ doc: { pieces: [crossTabInvalid] }, dirty() {} }, crossTabInvalid);
    ui = latest();
    assert.equal(ui.root.querySelector("[data-addons-apply]").disabled, true);
    ui.root.querySelector('[data-addon-tab="extra_liner"]').dispatch("click");
    assert.equal(ui.root.querySelector("[data-addons-apply]").disabled, true, "another enabled tab's invalid draft blocks Apply");
    ui.root.querySelector('[data-addon-tab="extra_back_groove"]').dispatch("click");
    assert.equal(ui.root.querySelector("[data-addons-apply]").disabled, true);
    ui.root.querySelector("[data-addons-remove]").dispatch("click");
    assert.equal(ui.root.querySelector("[data-addons-apply]").disabled, false, "the invalid enabled add-on can be removed");
    ui.root.querySelector("[data-addons-apply]").dispatch("click");
    await tick();
    assert.equal(crossTabInvalid.extra_back_groove, 0);

    const precision = blankRow({
        name: "piece-precision",
        extra_liner: 1,
        liner_reference_side: "edge_width_top",
        liner_offset_cm: 2,
        liner_width_cm: 1.5,
        liner_start_cm: 4.125,
        liner_length_cm: 30.123,
    });
    dialog.open({ doc: { pieces: [precision] }, dirty() {} }, precision);
    ui = latest();
    ui.root.querySelector('[data-addon-tab="extra_liner"]').dispatch("click");
    assert.equal(ui.root.querySelector("[data-liner-start]").value, "4.125");
    assert.equal(ui.root.querySelector("[data-liner-length]").value, "30.123");
    ui.root.querySelector("[data-liner-offset]").value = "2.125";
    ui.root.querySelector("[data-liner-offset]").dispatch("input");
    ui.root.querySelector("[data-addons-apply]").dispatch("click");
    await tick();
    assert.equal(writes.at(-1).liner_start_cm, 4.125);
    assert.equal(writes.at(-1).liner_length_cm, 30.123);

    const legacyLength = blankRow({
        name: "piece-legacy-full",
        extra_liner: 1,
        liner_reference_side: "edge_width_top",
        liner_offset_cm: 2,
        liner_width_cm: 1.5,
        liner_start_cm: 4.125,
        liner_length_cm: 0,
    });
    dialog.open({ doc: { pieces: [legacyLength] }, dirty() {} }, legacyLength);
    ui = latest();
    ui.root.querySelector('[data-addon-tab="extra_liner"]').dispatch("click");
    assert.equal(ui.root.querySelector("[data-liner-length]").value, "75.875");
    ui.root.querySelector("[data-liner-offset]").value = "2.125";
    ui.root.querySelector("[data-liner-offset]").dispatch("input");
    ui.root.querySelector("[data-addons-apply]").dispatch("click");
    await tick();
    assert.equal(writes.at(-1).liner_length_cm, 0, "opening and editing another field must retain the legacy full-edge sentinel");

    const retained = blankRow({ name: "piece-4" });
    dialog.open({ doc: { pieces: [retained] }, dirty() {} }, retained);
    ui = latest();
    ui.root.querySelector('[data-addon-tab="extra_liner"]').dispatch("click");
    ui.root.querySelector("[data-addon-enable]").dispatch("click");
    const retainedOffset = ui.root.querySelector("[data-liner-offset]");
    retainedOffset.value = "3.4";
    retainedOffset.dispatch("input");
    ui.root.querySelector('[data-addon-tab="extra_back_groove"]').dispatch("click");
    ui.root.querySelector('[data-addon-tab="extra_liner"]').dispatch("click");
    assert.equal(ui.root.querySelector("[data-liner-offset]").value, "3.4");
    assert.equal(ui.root.querySelector("[data-addon-enable]").classList.contains("is-on"), true);
    const stableOffset = ui.root.querySelector("[data-liner-offset]");
    const side = ui.root.querySelector('[data-liner-side="edge_long_right"]');
    side.dispatch("click");
    assert.equal(ui.root.querySelector("[data-liner-offset]"), stableOffset);
    assert.equal(stableOffset.value, "3.4");

    const cancelled = blankRow({ name: "piece-5" });
    dialog.open({ doc: { pieces: [cancelled] }, dirty() {} }, cancelled);
    ui = latest();
    ui.root.querySelector('[data-addon-tab="extra_liner"]').dispatch("click");
    ui.root.querySelector('[data-liner-side="edge_width_top"]').dispatch("click");
    assert.equal(ui.root.querySelector('[data-addons-preview] [data-machining-kind="liner"]') !== null, true);
    const beforeCancel = writes.length;
    ui.root.querySelector("[data-addons-cancel]").dispatch("click");
    assert.equal(ui.ui.hidden, true);
    assert.equal(writes.length, beforeCancel);
    assert.equal(cancelled.extra_liner, undefined);

    const saved = blankRow({
        name: "piece-6",
        extra_liner: 1,
        liner_reference_side: "edge_width_top",
        liner_offset_cm: 2,
        liner_width_cm: 1.5,
        liner_start_cm: 0,
        liner_length_cm: 80,
    });
    dialog.open({ doc: { pieces: [saved] }, dirty() {} }, saved);
    ui = latest();
    ui.root.querySelector('[data-addon-tab="extra_liner"]').dispatch("click");
    assert.equal(ui.root.querySelector("[data-liner-width]").value, "15");
    assert.equal(ui.root.querySelector("[data-liner-offset]").value, "2");
    assert.equal(ui.root.querySelector("[data-liner-start]").value, "0");
    assert.equal(ui.root.querySelector("[data-liner-length]").value, "80");
    assert.equal(ui.root.querySelector('[data-liner-side="edge_width_top"]').classList.contains("is-active"), true);
    assert.equal(ui.root.querySelector('[data-addons-preview] [data-machining-kind="liner"]') !== null, true);
    ui.root.querySelector("[data-addons-remove]").dispatch("click");
    assert.equal(ui.root.querySelector("[data-addon-enable]").classList.contains("is-on"), false);
    assert.equal(ui.root.querySelector("[data-addons-preview] [data-machining-kind]"), null);
    assert.match(ui.root.querySelector("[data-addons-hint]").textContent, /Apply/);
    assert.equal(saved.extra_liner, 1);
    ui.root.querySelector("[data-addons-apply]").dispatch("click");
    await tick();
    assert.equal(writes.at(-1).extra_liner, 0);
    assert.equal(saved.extra_liner, 0);
    assert.equal(saved.liner_reference_side, "");

    const removable = blankRow({
        name: "piece-remove-cancel",
        extra_liner: 1,
        liner_reference_side: "edge_width_top",
        liner_offset_cm: 2,
        liner_width_cm: 1.5,
        liner_start_cm: 0,
        liner_length_cm: 80,
    });
    dialog.open({ doc: { pieces: [removable] }, dirty() {} }, removable);
    ui = latest();
    ui.root.querySelector('[data-addon-tab="extra_liner"]').dispatch("click");
    ui.root.querySelector("[data-addons-remove]").dispatch("click");
    assert.equal(ui.root.querySelector("[data-addons-preview] [data-machining-kind]"), null);
    ui.root.querySelector("[data-addons-cancel]").dispatch("click");
    assert.equal(removable.extra_liner, 1);
    dialog.open({ doc: { pieces: [removable] }, dirty() {} }, removable);
    ui = latest();
    ui.root.querySelector('[data-addon-tab="extra_liner"]').dispatch("click");
    assert.equal(ui.root.querySelector('[data-addons-preview] [data-machining-kind="liner"]') !== null, true);

    const flaky = blankRow({ name: "piece-7" });
    dialog.open({ doc: { pieces: [flaky] }, dirty() {} }, flaky);
    ui = latest();
    ui.root.querySelector('[data-addon-tab="extra_double"]').dispatch("click");
    ui.root.querySelector("[data-addon-enable]").dispatch("click");
    failNext = true;
    const beforeFail = writes.length;
    ui.root.querySelector("[data-addons-apply]").dispatch("click");
    await tick();
    assert.equal(ui.ui.hidden, false);
    assert.equal(writes.length, beforeFail);
    assert.equal(flaky.extra_double, undefined);
    ui.root.querySelector("[data-addons-apply]").dispatch("click");
    await tick();
    assert.equal(ui.ui.hidden, true);
    assert.equal(writes.at(-1).extra_double, 1);
    assert.equal(writes.at(-1).extra_full_door_double, 0);
    assert.equal(flaky.extra_double, 1);

    const shapes = [
        blankRow({ name: "regular-shape" }),
        blankRow({
            name: "clipped-shape",
            piece_type: "Clipped Corner",
            clipped_corner_position: "Top Right",
            clipped_corner_width_cm: 10,
            clipped_corner_length_cm: 12,
        }),
        blankRow({
            name: "l-shape",
            piece_type: "L-Shaped Corner",
            clipped_corner_position: "Top Right",
            clipped_corner_width_cm: 10,
            clipped_corner_length_cm: 12,
        }),
    ];
    shapes.forEach((shape) => {
        dialog.open({ doc: { pieces: [shape] }, dirty() {} }, shape);
        const view = latest();
        view.root.querySelector('[data-addon-tab="extra_liner"]').dispatch("click");
        view.root.querySelector("[data-addon-enable]").dispatch("click");
        assert.equal(view.root.querySelector("[data-addon-enable]").classList.contains("is-on"), true);
        assert.equal(view.root.querySelector("[data-addons-apply]").disabled, true);
        view.root.querySelector("[data-liner-side]").dispatch("click");
        assert.equal(view.root.querySelector("[data-addons-apply]").disabled, false);
        assert.equal(view.root.querySelector("polygon") !== null, true);
    });

    context.__ = (message, values) => {
        let text = String(message ?? "");
        if (Array.isArray(values)) {
            values.forEach((value, index) => {
                text = text.replaceAll(`{${index}}`, String(value));
            });
        }
        return text;
    };
    const mixed = blankRow({ name: "piece-mixed" });
    dialog.open({ doc: { pieces: [mixed] }, dirty() {} }, mixed);
    ui = latest();
    ui.root.querySelector('[data-addon-tab="extra_liner"]').dispatch("click");
    ui.root.querySelector("[data-addon-enable]").dispatch("click");
    const beforeMissingSide = writes.length;
    ui.root.querySelector("[data-addons-apply]").dispatch("click");
    await tick();
    assert.equal(ui.ui.hidden, false);
    assert.equal(writes.length, beforeMissingSide);
    assert.match(ui.root.querySelector("[data-addons-error]").textContent, /reference side/);
    assert.equal(ui.root.querySelector("[data-addons-apply]").disabled, true);
    ui.root.querySelector('[data-liner-side="edge_width_top"]').dispatch("click");
    ui.root.querySelector("[data-liner-length]").value = "9999";
    ui.root.querySelector("[data-liner-length]").dispatch("input");
    ui.root.querySelector('[data-addon-tab="extra_back_groove"]').dispatch("click");
    ui.root.querySelector('[data-liner-side="edge_long_right"]').dispatch("click");
    const beforeMixed = writes.length;
    ui.root.querySelector("[data-addons-apply]").dispatch("click");
    await tick();
    assert.equal(ui.ui.hidden, false);
    assert.equal(writes.length, beforeMixed);
    assert.equal(ui.root.querySelector('[data-addon-tab="extra_liner"]').classList.contains("is-selected"), true);
    assert.match(messages.at(-1).message, /Liner:/);
    assert.equal(mixed.extra_liner, undefined);

    const repeated = blankRow({ name: "piece-repeat" });
    dialog.open({ doc: { pieces: [repeated] }, dirty() {} }, repeated);
    ui = latest();
    ui.root.querySelector('[data-addon-tab="extra_full_door_double"]').dispatch("click");
    ui.root.querySelector("[data-addon-enable]").dispatch("click");
    let releaseSave;
    const held = new Promise(resolve => { releaseSave = resolve; });
    const commitValues = fakeWindow.AlmdinaClippedCornerEditor.commitChildValues;
    fakeWindow.AlmdinaClippedCornerEditor.commitChildValues = async (frm, current, values) => {
        await held;
        return commitValues(frm, current, values);
    };
    const beforeRepeat = writes.length;
    ui.root.querySelector("[data-addons-apply]").dispatch("click");
    ui.root.querySelector("[data-addons-apply]").dispatch("click");
    assert.equal(ui.root.querySelector("[data-addons-apply]").textContent, "Saving");
    releaseSave();
    await tick();
    await tick();
    assert.equal(writes.length, beforeRepeat + 1);
    assert.equal(writes.at(-1).extra_full_door_double, 1);
    assert.equal(writes.at(-1).extra_double, 0);
    assert.equal(ui.ui.hidden, true);

    const live = blankRow({ name: "piece-live" });
    const order = {
        doc: { pieces: [live] },
        dirtyCount: 0,
        dirty() { this.dirtyCount += 1; },
        save() { throw new Error("order must stay unsaved"); },
    };
    const table = mountTable(order, live);
    assert.equal(addonLabel(table), "Add-ons");
    dialog.open(order, live);
    ui = latest();
    ui.root.querySelector('[data-addon-tab="extra_liner"]').dispatch("click");
    ui.root.querySelector('[data-liner-side="edge_width_top"]').dispatch("click");
    const beforeDismiss = writes.length;
    ui.root.querySelector("[data-addons-cancel]").dispatch("click");
    assert.equal(writes.length, beforeDismiss);
    assert.equal(order.dirtyCount, 0);
    assert.equal(live.extra_liner, undefined);
    assert.equal(addonLabel(table), "Add-ons");

    dialog.open(order, live);
    ui = latest();
    ui.root.querySelector('[data-addon-tab="extra_double"]').dispatch("click");
    assert.equal(ui.root.querySelector("[data-liner-side]"), null);
    ui.root.querySelector("[data-addon-enable]").dispatch("click");
    assert.equal(ui.root.querySelector("[data-addon-enable]").classList.contains("is-on"), true);
    assert.equal(ui.root.querySelector('[data-addon-tab="extra_double"]').classList.contains("is-enabled"), true);
    assert.equal(live.extra_double, undefined);
    assert.equal(addonLabel(table), "Add-ons");
    ui.root.querySelector('[data-addon-tab="extra_full_door_double"]').dispatch("click");
    assert.equal(ui.root.querySelector("[data-liner-side]"), null);
    ui.root.querySelector("[data-addon-enable]").dispatch("click");
    assert.equal(ui.root.querySelector("[data-addon-enable]").classList.contains("is-on"), true);
    assert.equal(ui.root.querySelector('[data-addon-tab="extra_double"]').classList.contains("is-enabled"), false);
    assert.equal(ui.root.querySelector('[data-addon-tab="extra_full_door_double"]').classList.contains("is-enabled"), true);
    ui.root.querySelector("[data-addons-apply]").dispatch("click");
    await tick();
    assert.equal(live.extra_full_door_double, 1);
    assert.equal(live.extra_double, 0);
    assert.equal(order.dirtyCount, 1);
    assert.equal(addonLabel(table), "Full Double");
    live.extra_double = 0;
    live.extra_full_door_double = 0;
    fakeWindow.AlmdinaExtraDoorAddonsUX.syncAddonButtons(table, live, true);
    assert.equal(addonLabel(table), "Add-ons");

    dialog.open(order, live);
    ui = latest();
    ui.root.querySelector('[data-addon-tab="extra_double"]').dispatch("click");
    ui.root.querySelector("[data-addon-enable]").dispatch("click");
    ui.root.querySelector("[data-addons-apply]").dispatch("click");
    await tick();
    assert.equal(live.extra_double, 1);
    assert.equal(live.extra_full_door_double, 0);
    assert.equal(addonLabel(table), "Double Banding");
    assert.equal(order.dirtyCount, 2);
    dialog.open(order, live);
    ui = latest();
    ui.root.querySelector('[data-addon-tab="extra_double"]').dispatch("click");
    assert.equal(ui.root.querySelector("[data-addon-enable]").classList.contains("is-on"), true);
    ui.root.querySelector("[data-addon-enable]").dispatch("click");
    assert.equal(ui.root.querySelector("[data-addon-enable]").classList.contains("is-on"), false);
    ui.root.querySelector("[data-addons-apply]").dispatch("click");
    await tick();
    assert.equal(live.extra_double, 0);
    assert.equal(addonLabel(table), "Add-ons");

    live.extra_double = 1;
    fakeWindow.AlmdinaExtraDoorAddonsUX.syncAddonButtons(table, live, true);
    assert.equal(addonLabel(table), "Double Banding");
    dialog.open(order, live);
    ui = latest();
    ui.root.querySelector('[data-addon-tab="extra_double"]').dispatch("click");
    ui.root.querySelector("[data-addons-remove]").dispatch("click");
    ui.root.querySelector("[data-addons-apply]").dispatch("click");
    await tick();
    assert.equal(live.extra_double, 0);
    assert.equal(addonLabel(table), "Add-ons");
    live.extra_double = 1;
    fakeWindow.AlmdinaExtraDoorAddonsUX.syncAddonButtons(table, live, true);
    assert.equal(addonLabel(table), "Double Banding");

    console.log("Unified add-ons dialog interaction passed");
}

interactionChecks().catch((error) => {
    console.error(error);
    process.exit(1);
});
