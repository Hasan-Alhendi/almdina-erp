"use strict";

const assert = require("assert");
const fs = require("fs");
const path = require("path");
const vm = require("vm");

const root = path.resolve(__dirname, "../..");

function load(relative, sandbox) {
    const file = path.join(root, relative);
    vm.runInNewContext(fs.readFileSync(file, "utf8"), sandbox, { filename: file });
}

function element(tag) {
    const node = {
        tag,
        children: [],
        attrs: {},
        hidden: false,
        value: "",
        textContent: "",
        className: "",
        parent: null,
        ownerDocument: null,
        dataset: {},
        listeners: {},
        options: [],
        isConnected: true,
        appendChild(child) {
            child.parent = node;
            child.ownerDocument = node.ownerDocument;
            node.children.push(child);
            if (child.tag === "option") node.options.push(child);
            if (child.tag === "text") node.textContent += child.textContent;
            return child;
        },
        setAttribute(name, value) {
            node.attrs[name] = String(value);
            if (name === "value") node.value = String(value);
            if (name === "class") node.className = String(value);
            if (name === "hidden") node.hidden = true;
            if (name.startsWith("data-") || name === "aria-expanded") {
                const key = name.replace(/^data-/, "").replace(/-([a-z])/g, (_, c) => c.toUpperCase());
                if (name.startsWith("data-")) node.dataset[key] = String(value);
            }
        },
        getAttribute(name) {
            return Object.prototype.hasOwnProperty.call(node.attrs, name) ? node.attrs[name] : null;
        },
        removeAttribute(name) {
            delete node.attrs[name];
            if (name === "hidden") node.hidden = false;
        },
        addEventListener(type, fn) {
            node.listeners[type] = node.listeners[type] || [];
            node.listeners[type].push(fn);
        },
        dispatch(type, event) {
            (node.listeners[type] || []).forEach(fn => fn(event || { target: node, preventDefault() {} }));
        },
        querySelector(selector) {
            return walk(node, selector)[0] || null;
        },
        querySelectorAll(selector) {
            return walk(node, selector);
        },
        contains(other) {
            let current = other;
            while (current) {
                if (current === node) return true;
                current = current.parent;
            }
            return false;
        },
        closest(selector) {
            let current = node;
            while (current) {
                if (matches(current, selector)) return current;
                current = current.parent;
            }
            return null;
        },
    };
    Object.defineProperty(node, "hidden", {
        configurable: true,
        get() { return Boolean(node.__hidden); },
        set(value) {
            node.__hidden = Boolean(value);
            if (value) node.attrs.hidden = "";
            else delete node.attrs.hidden;
        },
    });
    return node;
}

function matches(node, selector) {
    if (!node || node.tag === "fragment") return false;
    if (selector === "input") return node.tag === "input";
    if (selector === "option") return node.tag === "option";
    if (selector.startsWith(".")) {
        return String(node.className || "").split(/\s+/).includes(selector.slice(1));
    }
    if (selector.startsWith("[") && selector.endsWith("]")) {
        const body = selector.slice(1, -1);
        if (body.includes("=")) {
            const [name, raw] = body.split("=");
            return String(node.attrs[name] || "") === raw.replace(/^"|"$/g, "");
        }
        return Object.prototype.hasOwnProperty.call(node.attrs, body)
            || Object.prototype.hasOwnProperty.call(node.dataset || {}, body.replace(/^data-/, "").replace(/-([a-z])/g, (_, c) => c.toUpperCase()));
    }
    return false;
}

function walk(node, selector) {
    const found = [];
    if (matches(node, selector)) found.push(node);
    (node.children || []).forEach(child => {
        if (child.children) walk(child, selector).forEach(item => found.push(item));
    });
    return found;
}

function parseAttrs(source, node) {
    const attrRe = /([^\s=]+)(?:="([^"]*)")?/g;
    let match = attrRe.exec(source || "");
    while (match) {
        if (match[2] == null) {
            node.attrs[match[1]] = "";
            if (match[1] === "hidden") node.hidden = true;
        } else {
            node.setAttribute(match[1], match[2]);
        }
        match = attrRe.exec(source);
    }
}

function parseHTML(html, doc) {
    const root = element("fragment");
    root.ownerDocument = doc;
    const stack = [root];
    const re = /<\/?([a-zA-Z0-9-]+)([^>]*)>|([^<]+)/g;
    const voidTags = new Set(["input", "br", "img"]);
    let match = re.exec(html);
    while (match) {
        if (match[3]) {
            const text = element("text");
            text.textContent = match[3];
            text.ownerDocument = doc;
            stack[stack.length - 1].appendChild(text);
        } else if (match[0].startsWith("</")) {
            stack.pop();
        } else {
            const node = element(match[1].toLowerCase());
            node.ownerDocument = doc;
            parseAttrs(match[2], node);
            stack[stack.length - 1].appendChild(node);
            if (!voidTags.has(node.tag) && !match[0].endsWith("/>")) stack.push(node);
        }
        match = re.exec(html);
    }
    return root;
}

function hostFor(doc) {
    const host = element("div");
    host.ownerDocument = doc;
    host.isConnected = true;
    Object.defineProperty(host, "innerHTML", {
        configurable: true,
        set(html) {
            host.children = [];
            const parsed = parseHTML(html, doc);
            parsed.children.forEach(child => host.appendChild(child));
        },
        get() { return ""; },
    });
    return host;
}

function clickToggle(host) {
    const toggle = host.querySelector("[data-tool-picker-toggle]");
    assert.ok(toggle);
    host.dispatch("click", {
        target: toggle,
        preventDefault() {},
    });
}

const doc = element("document");
doc.ownerDocument = doc;
doc.createElement = tag => {
    const node = element(tag);
    node.ownerDocument = doc;
    return node;
};
doc.body = element("body");
doc.body.ownerDocument = doc;
doc.body.contains = other => {
    let current = other;
    while (current) {
        if (current === doc.body || current === doc) return true;
        current = current.parent;
    }
    // Hosts attached only to our test tree still count as connected via isConnected.
    return Boolean(other && other.isConnected);
};
doc.addEventListener = element("document").addEventListener;

const sandbox = {
    window: {},
    document: doc,
    console,
};
sandbox.window = sandbox;
load("public/js/cnc/cnc_tool_picker.js", sandbox);
const api = sandbox.AlmdinaCncToolPicker;

const spec = {
    label: "Tool",
    emptyLabel: "Choose a tool",
    selected: "",
    tools: [
        { value: "tool_a", label: "Ball Nose A" },
        { value: "tool_b", label: "Ball Nose B" },
    ],
    fields: [],
    onToolChange() {},
    onFieldInput() {},
};

const host = hostFor(doc);
doc.body.appendChild(host);

let controller = api.mount(host, spec);
assert.strictEqual(controller.isOpen(), false);
assert.strictEqual(host.dataset.toolPickerBound, "1");
assert.strictEqual((host.listeners.click || []).length, 1);

clickToggle(host);
assert.strictEqual(controller.isOpen(), true, "first click opens");
clickToggle(host);
assert.strictEqual(controller.isOpen(), false, "second click closes");

for (let round = 2; round <= 5; round += 1) {
    controller = api.mount(host, Object.assign({}, spec, {
        selected: round % 2 === 0 ? "tool_a" : "",
        selectedLabel: "Ball Nose A",
        fields: round % 2 === 0
            ? [{ name: "stepdown_mm", label: "Stepdown", value: "1.5" }]
            : [],
    }));
    assert.strictEqual(
        (host.listeners.click || []).length,
        1,
        `mount #${round} must keep a single click listener`
    );
    assert.strictEqual(
        (host.listeners.keydown || []).length,
        1,
        `mount #${round} must keep a single keydown listener`
    );
    assert.strictEqual(controller.isOpen(), false, `remount #${round} starts closed`);
    clickToggle(host);
    assert.strictEqual(controller.isOpen(), true, `remount #${round}: first click opens`);
    clickToggle(host);
    assert.strictEqual(controller.isOpen(), false, `remount #${round}: second click closes`);
}

// setTools without selected keeps the current choice for other consumers.
controller = api.mount(host, Object.assign({}, spec, {
    selected: "tool_a",
    selectedLabel: "Ball Nose A",
    fields: [{ name: "stepdown_mm", label: "Stepdown", value: "1.5" }],
}));
assert.strictEqual(host.querySelector("[data-tool-picker-select]").value, "tool_a");
controller.setTools([
    { value: "tool_a", label: "Ball Nose A" },
    { value: "tool_b", label: "Ball Nose B" },
    { value: "tool_c", label: "Ball Nose C" },
]);
assert.strictEqual(host.querySelector("[data-tool-picker-select]").value, "tool_a");
assert.strictEqual(host.querySelector(".dco-tool-picker__value").textContent, "Ball Nose A");

// Explicit empty selection still clears for profile document switches.
controller.setTools([
    { value: "tool_a", label: "Ball Nose A" },
], "");
assert.strictEqual(host.querySelector("[data-tool-picker-select]").value, "");
assert.strictEqual(host.querySelector(".dco-tool-picker__value").textContent, "Choose a tool");

// Detached modal hosts are pruned from pickerRoots.
const modalHost = hostFor(doc);
modalHost.isConnected = true;
api.mount(modalHost, spec);
assert.ok(api._pickerRoots.has(modalHost));
modalHost.isConnected = false;
api._prunePickerRoots();
assert.equal(api._pickerRoots.has(modalHost), false);

// Vertical profile field order contract (no column breaks).
const profileJson = JSON.parse(fs.readFileSync(
    path.join(root, "almdina_erp/doctype/cnc_machining_profile/cnc_machining_profile.json"),
    "utf8"
));
assert.deepStrictEqual(profileJson.field_order, [
    "profile_id",
    "profile_name",
    "tool_preset",
    "tool_values_json",
    "final_depth_mm",
    "safe_z_mm",
    "home_x_mm",
    "home_y_mm",
    "home_z_mm",
    "enabled",
]);
assert.equal(profileJson.fields.some(field => field.fieldtype === "Column Break"), false);
assert.strictEqual(profileJson.quick_entry, 1);

console.log("cnc_tool_picker_remount.test.js passed");
