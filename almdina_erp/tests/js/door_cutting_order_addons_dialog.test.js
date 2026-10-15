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
    __(value) { return Array.isArray(value) ? value[0] : value; },
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
        render(frm) { renders.push(frm.doc.pieces[0].extra_liner); },
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
    const offset = ui.root.querySelector("[data-liner-offset]");
    offset.value = "1.2";
    offset.dispatch("input");
    assert.equal(ui.root.querySelector("[data-liner-offset]"), offset);
    assert.match(ui.root.querySelector("[data-addons-preview]").textContent, /1\.2/);
    ui.root.querySelector("[data-addons-apply]").dispatch("click");
    await tick();
    assert.equal(context.frappe.ui.dialogs.at(-1).hidden, true);
    assert.equal(writes.length, 1);
    assert.equal(writes[0].extra_liner, 1);
    assert.equal(writes[0].liner_offset_cm, 1.2);
    assert.equal(writes[0].liner_reference_side, "edge_width_top");
    assert.equal(row.extra_liner, 1);
    assert.equal(renders.at(-1), 1);

    dialog.open({ doc: { pieces: [row] }, dirty() {} }, row);
    ui = latest();
    ui.root.querySelector('[data-addon-tab="extra_liner"]').dispatch("click");
    assert.equal(ui.root.querySelector("[data-liner-offset]").value, "1.2");
    assert.equal(ui.root.querySelector("[data-addon-enable]").classList.contains("is-on"), true);
    assert.equal(ui.root.querySelector('[data-liner-side="edge_width_top"]').classList.contains("is-active"), true);
    ui.root.querySelector('[data-liner-side="edge_long_left"]').dispatch("click");
    ui.root.querySelector("[data-addons-apply]").dispatch("click");
    await tick();
    assert.equal(writes.at(-1).liner_reference_side, "edge_long_left");
    assert.equal(row.liner_reference_side, "edge_long_left");

    const pair = blankRow({ name: "piece-2" });
    dialog.open({ doc: { pieces: [pair] }, dirty() {} }, pair);
    ui = latest();
    ui.root.querySelector('[data-addon-tab="extra_liner"]').dispatch("click");
    ui.root.querySelector('[data-liner-side="edge_width_bottom"]').dispatch("click");
    ui.root.querySelector("[data-liner-offset]").value = "2.5";
    ui.root.querySelector("[data-liner-offset]").dispatch("input");
    ui.root.querySelector('[data-addon-tab="extra_back_groove"]').dispatch("click");
    ui.root.querySelector('[data-liner-side="edge_width_top"]').dispatch("click");
    ui.root.querySelector("[data-liner-width]").value = "0.8";
    ui.root.querySelector("[data-liner-width]").dispatch("input");
    ui.root.querySelector('[data-addon-tab="extra_recessed_handle_cutout"]').dispatch("click");
    ui.root.querySelector('[data-liner-side="edge_long_right"]').dispatch("click");
    ui.root.querySelector("[data-liner-width]").value = "1";
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

    const invalid = blankRow({ name: "piece-3" });
    dialog.open({ doc: { pieces: [invalid] }, dirty() {} }, invalid);
    ui = latest();
    ui.root.querySelector('[data-addon-tab="extra_liner"]').dispatch("click");
    ui.root.querySelector('[data-liner-side="edge_width_top"]').dispatch("click");
    const length = ui.root.querySelector("[data-liner-length]");
    length.value = "9999";
    length.dispatch("input");
    const apply = ui.root.querySelector("[data-addons-apply]");
    assert.equal(apply.disabled, false);
    const beforeInvalid = writes.length;
    apply.dispatch("click");
    await tick();
    assert.equal(ui.ui.hidden, false);
    assert.equal(writes.length, beforeInvalid);
    assert.equal(ui.root.querySelector("[data-addons-error]").hidden, false);
    assert.equal(ui.root.querySelector("[data-addons-preview] [data-machining-kind]"), null);
    assert.equal(invalid.extra_liner, undefined);

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
    assert.equal(ui.root.querySelector("[data-addons-apply]").disabled, false);
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

    console.log("Unified add-ons dialog interaction passed");
}

interactionChecks().catch((error) => {
    console.error(error);
    process.exit(1);
});
