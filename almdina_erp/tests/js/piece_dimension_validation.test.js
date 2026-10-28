"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const root = path.resolve(__dirname, "../../");
const operatorPath = path.join(
    root,
    "public/js/door_cutting_order/order_entry/door_cutting_order_operator_ux.js"
);

const formHandlers = {};
const window = {};
const sandbox = {
    window,
    document: {},
    frappe: {
        ui: { form: { on(doctype, handlers) { formHandlers[doctype] = handlers; } } },
        utils: { escape_html(value) { return String(value); } },
    },
    __: (message, values) => {
        let text = String(message);
        if (Array.isArray(values)) {
            values.forEach((value, index) => {
                text = text.replace(`{${index}}`, String(value));
            });
        }
        return text;
    },
    Object,
    String,
    Number,
    Boolean,
    Promise,
    Set,
    Map,
    console,
};
window.frappe = sandbox.frappe;

vm.runInNewContext(fs.readFileSync(operatorPath, "utf8"), sandbox, { filename: operatorPath });

window.AlmdinaOrderDimensionValidation = {
    boardDimensions() {
        return { length: 280, width: 210, valid: true };
    },
    positiveNumber(value) {
        const number = Number(value);
        return Number.isFinite(number) && number > 0 ? number : null;
    },
};

const issuesFor = (length, width, allow_rotation = 0) => (
    window.AlmdinaDoorCuttingFastEntry.pieceDimensionIssues(
        {},
        { length_cm: length, width_cm: width, allow_rotation }
    )
);
const assertIssues = (actual, expected) => {
    assert.deepEqual(JSON.parse(JSON.stringify(actual)), expected);
};

assertIssues(issuesFor(250, 180), {}); // 1. valid
assertIssues(issuesFor(290, 180), { length_cm: "Exceeds length" }); // 2. length
assertIssues(issuesFor(250, 220), { width_cm: "Exceeds width" }); // 3. width
assertIssues(issuesFor(290, 220), {
    length_cm: "Exceeds length",
    width_cm: "Exceeds width",
}); // 4. both independently
assertIssues(issuesFor(280, 210), {}); // 5. equality
assertIssues(issuesFor(200, 250, 1), { width_cm: "Exceeds width" }); // 6. no rotation swap
assertIssues(issuesFor(280, 220), { width_cm: "Exceeds width" }); // 7. length correction leaves width
assertIssues(issuesFor("", 220), {
    width_cm: "Exceeds width",
    length_cm: "Invalid dimension",
}); // full validity still reports an empty axis; display timing is separate
assertIssues(issuesFor(80, 0), { width_cm: "Invalid dimension" });
assertIssues(issuesFor(-4, 80), { length_cm: "Invalid dimension" });
assertIssues(issuesFor(80, "abc"), { width_cm: "Invalid dimension" });

const source = fs.readFileSync(operatorPath, "utf8");
assert.match(source, /data-field-error=\"\$\{fieldname\}\"/); // 8. local error node
assert.match(source, /\.dco-piece-dimension-error \{[^}]*display:block/);
assert.match(source, /max-width:100%/);
assert.match(source, /overflow-wrap:anywhere/);
const liveInputHandler = source
    .split('root.addEventListener("input", event => {', 2)[1]
    .split('root.addEventListener("change"', 1)[0];
assert.match(liveInputHandler, /syncInputToModel\(currentFrm, input, false\)/);
assert.match(liveInputHandler, /\}, true\);/);
assert.doesNotMatch(liveInputHandler, /renderFastMeasurements|\.focus\(|\.select\(/);
assert.match(source, /liveRowDimensionValues\(tr, row\)/);
assert.match(source, /length > board\.length/);
assert.match(source, /width > board\.width/);
assert.match(source, /__\("Please enter board length and width first\."\)/);
assert.match(source, /__\("Exceeds width"\)/);
assert.match(source, /__\("Exceeds length"\)/);
assert.match(source, /__\("Invalid dimension"\)/);
const blurHandler = source
    .split('root.addEventListener("blur"', 2)[1]
    .split('root.addEventListener("keydown"', 1)[0];
assert.doesNotMatch(blurHandler, /revealLeftPieceDimensions|noteDimensionRowFocus/);
const catalog = fs.readFileSync(path.join(root, "translations/ar.csv"), "utf8");
assert.match(catalog, /^Exceeds width,يتجاوز العرض$/m);
assert.match(catalog, /^Exceeds length,يتجاوز الطول$/m);
assert.match(catalog, /^Invalid dimension,قياس غير صالح$/m);
assert.match(catalog, /^Exceeds board length,يتجاوز طول اللوح$/m);
assert.match(catalog, /^Exceeds board width,يتجاوز عرض اللوح$/m);

function classSet(node) {
    return new Set(String(node.className || "").split(/\s+/).filter(Boolean));
}

function splitOutside(selector, separator) {
    const parts = [];
    let current = "";
    let bracket = 0;
    for (const char of String(selector)) {
        if (char === "[") bracket += 1;
        if (char === "]" && bracket) bracket -= 1;
        if (char === separator && bracket === 0) {
            if (current.trim()) parts.push(current.trim());
            current = "";
        } else current += char;
    }
    if (current.trim()) parts.push(current.trim());
    return parts;
}

function matches(node, selector) {
    if (!node || node.nodeType !== 1) return false;
    const groups = splitOutside(selector, ",");
    if (groups.length > 1) return groups.some(group => matches(node, group));
    let body = groups[0] || "";
    const negated = [];
    body = body.replace(/:not\(([^)]+)\)/g, (_match, inner) => {
        negated.push(inner);
        return "";
    });
    const attributes = [];
    body = body.replace(/\[([^\]=\s]+)(?:=(['"])(.*?)\2)?\]/g, (_match, name, _quote, value) => {
        attributes.push({ name, value, present: value === undefined });
        return "";
    });
    body = body.trim();
    let tagName = "";
    const classNames = [];
    if (body) {
        const bits = body.split(".");
        tagName = bits[0].toUpperCase();
        classNames.push(...bits.slice(1).filter(Boolean));
    }
    if (tagName && node.tagName !== tagName) return false;
    const owned = classSet(node);
    if (!classNames.every(name => owned.has(name))) return false;
    for (const attribute of attributes) {
        const actual = node.getAttribute(attribute.name);
        if (attribute.present ? actual === null : actual !== attribute.value) return false;
    }
    return !negated.some(inner => matches(node, inner));
}

function walkElements(node, visit) {
    for (const child of node.children || []) {
        visit(child);
        walkElements(child, visit);
    }
}

function queryAll(node, selector) {
    const groups = splitOutside(selector, ",");
    if (groups.length > 1) {
        const seen = new Set();
        const found = [];
        groups.forEach(group => {
            queryAll(node, group).forEach(match => {
                if (seen.has(match)) return;
                seen.add(match);
                found.push(match);
            });
        });
        return found;
    }
    let current = [node];
    splitOutside(groups[0] || "", " ").forEach(part => {
        const next = [];
        current.forEach(start => {
            walkElements(start, child => {
                if (matches(child, part)) next.push(child);
            });
        });
        current = next;
    });
    return current;
}

function dataKey(name) {
    return name.slice(5).replace(/-([a-z])/g, (_match, char) => char.toUpperCase());
}

function createElement(tag) {
    const node = {
        tagName: String(tag).toUpperCase(),
        nodeType: 1,
        children: [],
        childNodes: [],
        parentElement: null,
        className: "",
        dataset: {},
        attributes: {},
        textWrites: 0,
        htmlWrites: 0,
        isConnected: true,
        value: "",
        disabled: false,
        title: "",
        selectionStart: null,
        selectionEnd: null,
        style: {},
    };
    node.classList = {
        contains: name => classSet(node).has(name),
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
            const on = force === undefined ? !has : Boolean(force);
            if (on) node.classList.add(name);
            else node.classList.remove(name);
            return on;
        },
    };
    node.getAttribute = name => {
        if (name === "class") return node.className || null;
        return Object.prototype.hasOwnProperty.call(node.attributes, name) ? node.attributes[name] : null;
    };
    node.setAttribute = (name, value) => {
        const text = String(value);
        node.attributes[name] = text;
        if (name === "class") node.className = text;
        if (name === "value") node.value = text;
        if (name === "disabled") node.disabled = true;
        if (name.startsWith("data-")) node.dataset[dataKey(name)] = text;
    };
    node.removeAttribute = name => {
        delete node.attributes[name];
        if (name === "class") node.className = "";
        if (name.startsWith("data-")) delete node.dataset[dataKey(name)];
    };
    node.appendChild = child => {
        if (child.parentElement) child.remove();
        child.parentElement = node;
        node.childNodes.push(child);
        if (child.nodeType === 1) node.children.push(child);
        child.isConnected = node.isConnected !== false;
        return child;
    };
    node.remove = () => {
        const parent = node.parentElement;
        if (parent) {
            parent.childNodes = parent.childNodes.filter(child => child !== node);
            parent.children = parent.children.filter(child => child !== node);
        }
        node.parentElement = null;
        node.isConnected = false;
    };
    Object.defineProperty(node, "textContent", {
        get() {
            if (!node.childNodes.length) return "";
            return node.childNodes.map(child => (
                child.nodeType === 3 ? child.nodeValue : child.textContent
            )).join("");
        },
        set(value) {
            node.textWrites += 1;
            node.childNodes = [{ nodeType: 3, nodeValue: String(value), parentElement: node }];
            node.children = [];
        },
    });
    Object.defineProperty(node, "innerHTML", {
        get() { return ""; },
        set(value) {
            node.htmlWrites += 1;
            node.childNodes = [];
            node.children = [];
            parseHTML(node, value);
        },
    });
    Object.defineProperty(node, "nextElementSibling", {
        get() {
            if (!node.parentElement) return null;
            const siblings = node.parentElement.children;
            const index = siblings.indexOf(node);
            return index >= 0 ? siblings[index + 1] || null : null;
        },
    });
    node.querySelectorAll = selector => queryAll(node, selector);
    node.querySelector = selector => queryAll(node, selector)[0] || null;
    node.matches = selector => matches(node, selector);
    node.closest = selector => {
        let current = node;
        while (current) {
            if (matches(current, selector)) return current;
            current = current.parentElement;
        }
        return null;
    };
    node.contains = other => {
        let current = other;
        while (current) {
            if (current === node) return true;
            current = current.parentElement;
        }
        return false;
    };
    node.addEventListener = (type, fn, capture = false) => {
        node._listeners = node._listeners || [];
        node._listeners.push({ type, fn, capture: Boolean(capture) });
    };
    node.dispatchEvent = event => {
        event.target = node;
        event.defaultPrevented = false;
        event._stopped = false;
        event.preventDefault = () => { event.defaultPrevented = true; };
        event.stopPropagation = () => { event._stopped = true; };
        const path = [];
        let current = node;
        while (current) {
            path.unshift(current);
            current = current.parentElement;
        }
        const invoke = (host, capture) => {
            event.currentTarget = host;
            for (const listener of host._listeners || []) {
                if (listener.type === event.type && listener.capture === capture) listener.fn(event);
                if (event._stopped) return;
            }
        };
        for (const host of path) {
            if (host === node) break;
            invoke(host, true);
            if (event._stopped) return true;
        }
        invoke(node, true);
        if (event._stopped) return true;
        invoke(node, false);
        if (event._stopped) return true;
        for (const host of [...path].reverse()) {
            if (host === node) continue;
            invoke(host, false);
            if (event._stopped) return true;
        }
        return true;
    };
    node.focus = () => {
        sandbox.document.activeElement = node;
        node.dispatchEvent({ type: "focusin", bubbles: true });
    };
    node.select = () => {
        node.selectionStart = 0;
        node.selectionEnd = String(node.value ?? "").length;
    };
    node.setSelectionRange = (start, end) => {
        node.selectionStart = start;
        node.selectionEnd = end;
    };
    node.setRangeText = (text, start, end) => {
        const value = String(node.value ?? "");
        node.value = `${value.slice(0, start)}${text}${value.slice(end)}`;
        node.selectionStart = start + String(text).length;
        node.selectionEnd = node.selectionStart;
    };
    node.scrollIntoView = () => {};
    node.insertAdjacentHTML = (position, html) => {
        if (position !== "beforeend") throw new Error(`Unsupported position ${position}`);
        const holder = createElement("div");
        holder.innerHTML = html;
        while (holder.childNodes.length) node.appendChild(holder.childNodes[0]);
    };
    return node;
}

function parseHTML(parent, html) {
    const pattern = /<!--[\s\S]*?-->|<\/([A-Za-z0-9-]+)>|<([A-Za-z0-9-]+)([^>]*?)(\/?)>|([^<]+)/g;
    const stack = [parent];
    let match = pattern.exec(html);
    while (match) {
        if (match[1]) {
            const closing = match[1].toUpperCase();
            for (let index = stack.length - 1; index > 0; index -= 1) {
                if (stack[index].tagName === closing) {
                    stack.length = index;
                    break;
                }
            }
        } else if (match[2]) {
            const element = createElement(match[2]);
            const raw = match[3] || "";
            const attribute = /([:@A-Za-z0-9_-]+)(?:\s*=\s*(?:"([^"]*)"|'([^']*)'|([^\s"'>]+)))?/g;
            let found = attribute.exec(raw);
            while (found) {
                element.setAttribute(found[1], found[2] ?? found[3] ?? found[4] ?? "");
                found = attribute.exec(raw);
            }
            stack[stack.length - 1].appendChild(element);
            const voidTag = match[4] === "/" || ["INPUT", "BR", "HR", "IMG", "META", "LINK"].includes(element.tagName);
            if (!voidTag) stack.push(element);
        } else if (match[5] && match[5].trim()) {
            stack[stack.length - 1].appendChild({
                nodeType: 3,
                nodeValue: match[5],
                parentElement: null,
                remove() {},
            });
        }
        match = pattern.exec(html);
    }
}

function jquery(root) {
    return {
        0: root,
        length: 1,
        get: index => (index === 0 ? root : undefined),
        html(value) {
            root.innerHTML = value;
            return this;
        },
        find(selector) {
            const nodes = root.querySelectorAll(selector);
            return {
                length: nodes.length,
                get: index => nodes[index],
                each(fn) { nodes.forEach((item, index) => fn.call(item, index, item)); },
            };
        },
    };
}

const documentElement = createElement("html");
documentElement.setAttribute("dir", "rtl");
sandbox.document = {
    documentElement,
    activeElement: null,
    scrollingElement: { scrollTop: 0, scrollLeft: 0 },
    getElementById() { return null; },
};
sandbox.Array = Array;
sandbox.Error = Error;
sandbox.Event = function Event(type, init = {}) {
    this.type = type;
    this.bubbles = Boolean(init.bubbles);
};
sandbox.setTimeout = fn => { fn(); return 0; };
sandbox.clearTimeout = () => {};
sandbox.window.setTimeout = sandbox.setTimeout;
sandbox.window.clearTimeout = sandbox.clearTimeout;
let materialized = 0;
const prints = [];
sandbox.frappe.model = {
    new_names: {},
    add_child(doc, doctype, field) {
        materialized += 1;
        const child = {
            doctype,
            name: `piece-new-${materialized}`,
            qty: 1,
            piece_type: "Regular",
            notes: "",
        };
        doc[field] = doc[field] || [];
        doc[field].push(child);
        return child;
    },
    clear_doc() {},
};
sandbox.frappe.msgprint = message => { prints.push(message); };
sandbox.frappe.ui.form.on = (doctype, handlers) => {
    formHandlers[doctype] = Object.assign({}, handlers, formHandlers[doctype] || {});
};
const keyboardPath = path.join(
    root,
    "public/js/door_cutting_order/order_entry/measurements/door_cutting_order_fast_entry_keyboard_ux.js"
);
vm.runInNewContext(fs.readFileSync(keyboardPath, "utf8"), sandbox, { filename: keyboardPath });

const pending = [];
let addonsOpened = 0;
window.AlmdinaExtraDoorAddonsUX = {
    renderAddonSummary() {
        return '<button type="button" class="dco-addons-open" data-open-addons="1">Add-ons</button>';
    },
    bindTable() {},
};
window.AlmdinaDoorAddonsDialog = {
    open() { addonsOpened += 1; },
};

function piece(index, overrides) {
    return Object.assign({
        doctype: "Door Cutting Order Detail",
        name: `piece-${index + 1}`,
        idx: index + 1,
        piece_no: index + 1,
        qty: 1,
        width_cm: 40,
        length_cm: 80,
        piece_type: "Regular",
        notes: "",
        allow_rotation: 0,
        edge_long_right: 0,
        edge_long_left: 0,
        edge_width_top: 0,
        edge_width_bottom: 0,
        edge_break: 0,
        edge_break_only: 0,
        edge_type: "",
    }, overrides);
}

function mount(rows, docName = "DCO-1") {
    const host = createElement("div");
    const frm = {
        doc: {
            name: docName,
            doctype: "Door Cutting Order",
            docstatus: 0,
            status: "Draft",
            default_edge_type: "",
            pieces: rows.map((row, index) => piece(index, row)),
        },
        fields_dict: { pieces_fast_entry: { $wrapper: jquery(host) } },
        dirtyCount: 0,
        dirty() { frm.dirtyCount += 1; },
        script_manager: { trigger() { return Promise.resolve(); } },
        _dco_edge_types_loaded: true,
    };
    const before = host.htmlWrites;
    window.AlmdinaDoorCuttingFastEntry.render(frm);
    window.AlmdinaFastEntryKeyboardUX.install(frm);
    frm._htmlWritesAtRender = host.htmlWrites - before;
    return { frm, host };
}

function realRows(host) {
    return host.querySelectorAll("tr[data-row-name]:not(.dco-virtual-row)");
}
function virtualRows(host) {
    return host.querySelectorAll("tr.dco-virtual-row");
}
function input(tr, fieldname) {
    return tr.querySelector(`input[data-field='${fieldname}']`);
}
function errorText(tr, fieldname) {
    const node = tr.querySelector(`[data-field-error='${fieldname}']`);
    return node ? node.textContent.trim() : "";
}
function typeInto(control, value) {
    const start = control.selectionStart;
    const end = control.selectionEnd;
    control.value = value;
    control.selectionStart = start;
    control.selectionEnd = end;
    control.dispatchEvent({ type: "input", bubbles: true });
}
function key(control, name, extras = {}) {
    const event = Object.assign({ type: "keydown", key: name, bubbles: true, cancelable: true }, extras);
    control.dispatchEvent(event);
    return event;
}

// 1. Typing width while length is empty does not show a length error.
{
    const { host } = mount([{ width_cm: "", length_cm: "" }]);
    const row = realRows(host)[0];
    const lengthError = row.querySelector("[data-field-error='length_cm']");
    lengthError.textWrites = 0;
    input(row, "width_cm").focus();
    typeInto(input(row, "width_cm"), "12");
    assert.equal(errorText(row, "width_cm"), "");
    assert.equal(errorText(row, "length_cm"), "");
    assert.equal(lengthError.textWrites, 0);
    assert.equal(input(row, "length_cm").getAttribute("aria-invalid"), null);
}

// 2. Moving between width and length inside the row does not show an empty-value error.
{
    const { host } = mount([{ width_cm: "", length_cm: "" }]);
    const row = realRows(host)[0];
    const width = input(row, "width_cm");
    const length = input(row, "length_cm");
    width.focus();
    const tab = key(width, "Tab");
    assert.equal(tab.defaultPrevented, false);
    length.focus();
    assert.equal(sandbox.document.activeElement, length);
    assert.equal(errorText(row, "width_cm"), "");
    assert.equal(errorText(row, "length_cm"), "");
    const enter = key(width, "Enter");
    assert.equal(enter.defaultPrevented, true);
    assert.equal(sandbox.document.activeElement, length);
    assert.equal(errorText(row, "width_cm"), "");
    input(row, "qty").focus();
    input(row, "notes").focus();
    assert.equal(errorText(row, "width_cm"), "");
    assert.equal(errorText(row, "length_cm"), "");
}

// 3. Clearing and retyping inside the row stays quiet, including after coming back to correct it.
{
    const { host } = mount([{ width_cm: 30, length_cm: 80 }]);
    const row = realRows(host)[0];
    const width = input(row, "width_cm");
    width.focus();
    typeInto(width, "");
    typeInto(width, "36");
    assert.equal(errorText(row, "width_cm"), "");
    assert.equal(errorText(row, "length_cm"), "");

    typeInto(width, "");
    input(realRows(host)[0] && virtualRows(host)[0], "width_cm").focus();
    assert.equal(errorText(row, "width_cm"), "Invalid dimension");
    width.focus();
    typeInto(width, "");
    assert.equal(errorText(row, "width_cm"), "");
    input(row, "length_cm").focus();
    assert.equal(errorText(row, "width_cm"), "");
    assert.equal(errorText(row, "length_cm"), "");
    typeInto(width, "36");
    assert.equal(errorText(row, "width_cm"), "");
}

// 4. Leaving the row with an empty, zero, negative, or non-numeric length flags length only.
{
    const { host } = mount([
        { width_cm: 40, length_cm: "" },
        { width_cm: 50, length_cm: 90 },
    ]);
    const [first, second] = realRows(host);
    input(first, "length_cm").focus();
    typeInto(input(first, "length_cm"), "");
    input(second, "width_cm").focus();
    assert.equal(sandbox.document.activeElement, input(second, "width_cm"));
    assert.equal(errorText(first, "length_cm"), "Invalid dimension");
    assert.equal(errorText(first, "width_cm"), "");
    assert.equal(input(first, "length_cm").getAttribute("aria-invalid"), "true");
    assert.equal(input(first, "width_cm").getAttribute("aria-invalid"), null);

    typeInto(input(first, "length_cm"), "0");
    input(first, "length_cm").focus();
    input(second, "notes").focus();
    assert.equal(errorText(first, "length_cm"), "Invalid dimension");
    assert.equal(errorText(first, "width_cm"), "");

    input(first, "length_cm").focus();
    typeInto(input(first, "length_cm"), "-5");
    input(second, "width_cm").focus();
    assert.equal(errorText(first, "length_cm"), "Invalid dimension");
    assert.equal(errorText(first, "width_cm"), "");

    input(first, "length_cm").focus();
    typeInto(input(first, "length_cm"), "abc");
    key(input(first, "length_cm"), "Enter");
    assert.equal(sandbox.document.activeElement, input(second, "width_cm"));
    assert.equal(errorText(first, "length_cm"), "Invalid dimension");
    assert.equal(errorText(first, "width_cm"), "");
}

// 5. The same leave timing applies to width only.
{
    const { frm, host } = mount([
        { width_cm: "", length_cm: 80 },
        { width_cm: 50, length_cm: 90 },
    ]);
    const [first, second] = realRows(host);
    input(second, "width_cm").focus();
    const shiftTab = key(input(second, "width_cm"), "Tab", { shiftKey: true });
    assert.equal(shiftTab.defaultPrevented, false);
    input(first, "width_cm").focus();
    typeInto(input(first, "width_cm"), "0");
    input(second, "qty").focus();
    key(input(second, "qty"), "Enter");
    assert.equal(errorText(first, "width_cm"), "Invalid dimension");
    assert.equal(errorText(first, "length_cm"), "");
    assert.equal(frm.doc.pieces.length, 2);
}

// 6–8. Exceeds messages are per field, and a correction clears only that field.
{
    const { host } = mount([{ width_cm: "", length_cm: "" }, { width_cm: 20, length_cm: 30 }]);
    const [first, second] = realRows(host);
    const width = input(first, "width_cm");
    const length = input(first, "length_cm");
    const lengthError = first.querySelector("[data-field-error='length_cm']");
    width.focus();
    lengthError.textWrites = 0;
    typeInto(width, "250");
    assert.equal(errorText(first, "width_cm"), "Exceeds width");
    assert.equal(errorText(first, "length_cm"), "");
    assert.equal(lengthError.textWrites, 0);
    assert.equal(width.classList.contains("is-invalid"), true);

    length.focus();
    const widthError = first.querySelector("[data-field-error='width_cm']");
    widthError.textWrites = 0;
    typeInto(length, "300");
    assert.equal(errorText(first, "length_cm"), "Exceeds length");
    assert.equal(errorText(first, "width_cm"), "Exceeds width");
    assert.equal(widthError.textWrites, 0);

    typeInto(width, "100");
    assert.equal(errorText(first, "width_cm"), "");
    assert.equal(width.getAttribute("aria-invalid"), null);
    assert.equal(errorText(first, "length_cm"), "Exceeds length");
    typeInto(length, "90");
    assert.equal(errorText(first, "length_cm"), "");
    assert.equal(errorText(first, "width_cm"), "");
    input(second, "width_cm").focus();
    assert.equal(errorText(first, "width_cm"), "");
    assert.equal(errorText(first, "length_cm"), "");
}

// 9. Mouse, Tab, and Enter reveal the previous row; add-ons and blur do not.
{
    addonsOpened = 0;
    const { frm, host } = mount([{ width_cm: 40, length_cm: "" }]);
    const row = realRows(host)[0];
    const length = input(row, "length_cm");
    length.focus();
    length.dispatchEvent({ type: "blur", bubbles: true });
    assert.equal(errorText(row, "length_cm"), "");
    assert.equal(frm.doc.pieces.length, 1);

    const pieceType = row.querySelector("select[data-field='piece_type']");
    if (pieceType) pieceType.value = "Regular";
    const addons = row.querySelector("[data-open-addons]");
    addons.focus();
    assert.equal(errorText(row, "length_cm"), "");
    const dirtyBefore = frm.dirtyCount;
    addons.dispatchEvent({ type: "click", bubbles: true, cancelable: true });
    assert.equal(addonsOpened, 1);
    assert.equal(errorText(row, "length_cm"), "");
    assert.equal(frm.dirtyCount, dirtyBefore);

    const outside = createElement("div");
    host.appendChild(outside);
    outside.focus();
    assert.equal(errorText(row, "length_cm"), "");

    input(virtualRows(host)[0], "width_cm").focus();
    assert.equal(errorText(row, "length_cm"), "Invalid dimension");
    assert.equal(sandbox.document.activeElement, input(virtualRows(host)[0], "width_cm"));
    assert.equal(errorText(virtualRows(host)[0], "width_cm"), "");
    assert.equal(errorText(virtualRows(host)[0], "length_cm"), "");
}

// 10. Redraw keeps the same document timing; switching documents drops it. Delete drops the row.
{
    const { frm, host } = mount([{ name: "piece-1", width_cm: 40, length_cm: "" }]);
    const row = realRows(host)[0];
    assert.equal(errorText(row, "length_cm"), "");
    window.AlmdinaDoorCuttingFastEntry.render(frm);
    assert.equal(errorText(realRows(host)[0], "length_cm"), "");

    input(realRows(host)[0], "length_cm").focus();
    input(virtualRows(host)[0], "width_cm").focus();
    assert.equal(errorText(realRows(host)[0], "length_cm"), "Invalid dimension");
    input(realRows(host)[0], "length_cm").focus();
    typeInto(input(realRows(host)[0], "length_cm"), "");
    assert.equal(errorText(realRows(host)[0], "length_cm"), "");
    window.AlmdinaDoorCuttingFastEntry.render(frm);
    assert.equal(errorText(realRows(host)[0], "length_cm"), "");

    frm.doc.name = "DCO-2";
    window.AlmdinaDoorCuttingFastEntry.render(frm);
    assert.equal(errorText(realRows(host)[0], "length_cm"), "");
    assert.equal(frm._dcoDimensionDisplay.docKey, "DCO-2");
    assert.equal(frm._dcoDimensionDisplay.revealed.size, 0);

    frm.doc.name = "DCO-1";
    window.AlmdinaDoorCuttingFastEntry.render(frm);
    input(realRows(host)[0], "width_cm").focus();
    input(virtualRows(host)[0], "notes").focus();
    assert.equal(errorText(realRows(host)[0], "length_cm"), "Invalid dimension");
    realRows(host)[0].querySelector(".dco-delete-row").dispatchEvent({ type: "click", bubbles: true, cancelable: true });
    assert.equal(frm.doc.pieces.length, 0);
    frm.doc.pieces.push(piece(0, { name: "piece-1", width_cm: 40, length_cm: "" }));
    window.AlmdinaDoorCuttingFastEntry.render(frm);
    assert.equal(errorText(realRows(host)[0], "length_cm"), "");
}

// 11. Save still rejects invalid live dimensions without leaving the row.
{
    prints.length = 0;
    const { frm, host } = mount([{ width_cm: 40, length_cm: 80 }]);
    const row = realRows(host)[0];
    const length = input(row, "length_cm");
    length.focus();
    length.selectionStart = 1;
    length.selectionEnd = 1;
    typeInto(length, "");
    assert.equal(length.selectionStart, 1);
    assert.equal(errorText(row, "length_cm"), "");
    assert.equal(frm.doc.length_cm, undefined);
    assert.equal(frm.doc.pieces[0].length_cm, 0);
    const htmlWrites = host.htmlWrites;
    const save = formHandlers["Door Cutting Order"].before_save(frm);
    assert.equal(prints.at(-1).message, "Row 1: Invalid dimension");
    assert.equal(errorText(row, "length_cm"), "Invalid dimension");
    assert.equal(errorText(row, "width_cm"), "");
    assert.equal(frm.doc.pieces.length, 1);
    assert.equal(host.htmlWrites, htmlWrites);
    pending.push(save.then(
        () => { throw new Error("save should reject invalid dimensions"); },
        error => { assert.equal(error && error.message, "Invalid dimension"); }
    ));
}

// 12. An empty spare row is not materialized or validated.
{
    const before = materialized;
    const { frm, host } = mount([{ width_cm: 40, length_cm: 80 }]);
    const spare = virtualRows(host)[0];
    input(spare, "width_cm").focus();
    input(spare, "width_cm").dispatchEvent({ type: "blur", bubbles: true });
    input(realRows(host)[0], "notes").focus();
    assert.equal(frm.doc.pieces.length, 1);
    assert.equal(materialized, before);
    assert.equal(errorText(spare, "width_cm"), "");
    assert.equal(errorText(spare, "length_cm"), "");
    assert.equal(virtualRows(host).length, 1);
    prints.length = 0;
    const save = formHandlers["Door Cutting Order"].before_save(frm);
    assert.equal(frm.doc.pieces.length, 1);
    assert.equal(prints.length, 0);
    pending.push(save);
}

// 13. Field sync still updates the model without redrawing, and navigation reaches the next width.
{
    const { frm, host } = mount([{ width_cm: "", length_cm: "" }, { width_cm: 20, length_cm: 30 }]);
    const [first, second] = realRows(host);
    const writes = host.htmlWrites;
    input(first, "width_cm").focus();
    typeInto(input(first, "width_cm"), "15");
    typeInto(input(first, "length_cm"), "25");
    assert.equal(frm.doc.pieces[0].width_cm, 15);
    assert.equal(frm.doc.pieces[0].length_cm, 25);
    assert.equal(host.htmlWrites, writes);
    assert.equal(errorText(first, "width_cm"), "");
    assert.equal(errorText(first, "length_cm"), "");
    key(input(first, "length_cm"), "Enter");
    assert.equal(sandbox.document.activeElement, input(second, "width_cm"));
    input(second, "qty").focus();
    key(input(second, "qty"), "Enter");
    assert.equal(sandbox.document.activeElement, input(virtualRows(host)[0], "width_cm"));
    assert.equal(frm.doc.pieces.length, 2);
}

// Width and length stay Latin on screen. Chrome's Arabic UI locale redraws
// type=number with Arabic-Indic digits and ignores lang, so these cells are
// text controls. Quantity stays a number input.
{
    const { frm, host } = mount([{ width_cm: 68.4, length_cm: 21, qty: 2 }]);
    const row = realRows(host)[0];
    const width = input(row, "width_cm");
    const length = input(row, "length_cm");
    const qty = input(row, "qty");
    assert.equal(width.getAttribute("type"), "text");
    assert.equal(length.getAttribute("type"), "text");
    assert.equal(width.getAttribute("lang"), "en");
    assert.equal(length.getAttribute("lang"), "en");
    assert.equal(width.getAttribute("dir"), "ltr");
    assert.equal(length.getAttribute("dir"), "ltr");
    assert.equal(width.getAttribute("inputmode"), "decimal");
    assert.equal(width.value, "68.4");
    assert.equal(length.value, "21");
    const step = (field, direction) => field.parentElement.querySelector(
        `.dco-dimension-step[data-dimension-step="${direction}"]`
    );
    const widthUp = step(width, "1");
    const widthDown = step(width, "-1");
    assert.equal(widthUp.getAttribute("tabindex"), "-1");
    assert.equal(widthUp.getAttribute("aria-label"), "Increase the measurement");
    assert.equal(widthDown.getAttribute("aria-label"), "Decrease the measurement");
    widthUp.dispatchEvent({ type: "click", bubbles: true, cancelable: true });
    assert.equal(width.value, "69.4");
    assert.equal(frm.doc.pieces[0].width_cm, 69.4);
    widthDown.dispatchEvent({ type: "click", bubbles: true, cancelable: true });
    assert.equal(width.value, "68.4");
    assert.equal(frm.doc.pieces[0].width_cm, 68.4);
    const lengthUp = step(length, "1");
    lengthUp.dispatchEvent({ type: "click", bubbles: true, cancelable: true });
    assert.equal(length.value, "22");
    assert.equal(frm.doc.pieces[0].length_cm, 22);
    const stepValue = window.AlmdinaDoorCuttingFastEntry.stepDimensionValue;
    assert.equal(stepValue("", 1), "1");
    assert.equal(stepValue("", -1), "0");
    assert.equal(stepValue("0", -1), "0");
    assert.equal(stepValue("0.4", -1), "0");
    assert.equal(stepValue("21", 1), "22");
    const spareWidth = input(virtualRows(host)[0], "width_cm");
    assert.equal(spareWidth.value, "");
    spareWidth.parentElement.querySelector(".dco-dimension-step[data-dimension-step='1']")
        .dispatchEvent({ type: "click", bubbles: true, cancelable: true });
    assert.equal(spareWidth.value, "1");
    assert.equal(qty.getAttribute("type"), "number");
    assert.equal(qty.getAttribute("lang"), null);
    assert.equal(input(virtualRows(host)[0], "width_cm").value, "");
    assert.equal(input(virtualRows(host)[0], "length_cm").value, "");

    const plan = window.AlmdinaDoorCuttingFastEntry.planDimensionInsert;
    const typed = plan("12", "3", 2, 2);
    assert.equal(typed.replace, false);
    assert.equal(typed.next, "123");
    const decimal = plan("68", ".", 2, 2);
    assert.equal(decimal.replace, false);
    assert.equal(decimal.next, "68.");
    assert.equal(plan("68.4", ".", 4, 4), null);
    assert.equal(plan("68.4", "a", 4, 4), null);
    const arabic = plan("", "١٢٣٫٥", 0, 0);
    assert.equal(arabic.replace, true);
    assert.equal(arabic.text, "123.5");
    assert.equal(arabic.next, "123.5");
    const empty = plan("", "", 0, 0);
    assert.equal(empty.replace, false);
    assert.equal(empty.next, "");

    width.value = "21";
    width.selectionStart = 2;
    width.selectionEnd = 2;
    const latin = { type: "beforeinput", inputType: "insertText", data: "3", bubbles: true, cancelable: true };
    width.dispatchEvent(latin);
    assert.equal(latin.defaultPrevented, false);
    assert.equal(width.value, "21");

    width.value = "";
    width.selectionStart = 0;
    width.selectionEnd = 0;
    const pasted = { type: "beforeinput", inputType: "insertFromPaste", data: "٦٨٫٤", bubbles: true, cancelable: true };
    width.dispatchEvent(pasted);
    assert.equal(pasted.defaultPrevented, true);
    assert.equal(width.value, "68.4");
    assert.equal(width.selectionStart, 4);

    width.selectionStart = 4;
    width.selectionEnd = 4;
    const letter = { type: "beforeinput", inputType: "insertText", data: "a", bubbles: true, cancelable: true };
    width.dispatchEvent(letter);
    assert.equal(letter.defaultPrevented, true);
    assert.equal(width.value, "68.4");
    assert.equal(frm.doc.pieces[0].width_cm, 68.4);
}

{
    const host = createElement("div");
    const frm = {
        doc: {
            name: "DCO-READ",
            doctype: "Door Cutting Order",
            docstatus: 1,
            status: "Approved",
            default_edge_type: "",
            pieces: [piece(0, { width_cm: 23, length_cm: 21 })],
        },
        fields_dict: { pieces_fast_entry: { $wrapper: jquery(host) } },
        dirty() {},
        script_manager: { trigger() { return Promise.resolve(); } },
        _dco_edge_types_loaded: true,
    };
    window.AlmdinaDoorCuttingFastEntry.render(frm);
    const width = input(realRows(host)[0], "width_cm");
    assert.equal(width.getAttribute("type"), "text");
    assert.equal(width.getAttribute("lang"), "en");
    assert.equal(width.disabled, true);
    assert.equal(width.value, "23");
    const up = width.parentElement.querySelector(".dco-dimension-step[data-dimension-step='1']");
    assert.equal(up.disabled, true);
    up.dispatchEvent({ type: "click", bubbles: true, cancelable: true });
    assert.equal(width.value, "23");
}

Promise.all(pending).then(() => {
    console.log("piece dimension validation tests passed", Object.keys(formHandlers).length);
}).catch(error => {
    console.error(error);
    process.exitCode = 1;
});
