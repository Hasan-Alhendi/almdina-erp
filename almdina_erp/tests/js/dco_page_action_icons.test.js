"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const root = path.resolve(__dirname, "../..");
const source = fs.readFileSync(
    path.join(root, "public/js/door_cutting_order/core/door_cutting_order_page_action_icons.js"),
    "utf8"
);
const presentationCss = fs.readFileSync(
    path.join(root, "public/css/door_cutting_order_form_presentation.css"),
    "utf8"
);
const tabCss = fs.readFileSync(
    path.join(root, "public/css/door_cutting_order_form_tab_layout.css"),
    "utf8"
);
const assets = fs.readFileSync(path.join(root, "frontend_assets.py"), "utf8");
const catalog = fs.readFileSync(path.join(root, "translations/ar.csv"), "utf8");

assert.match(assets, /door_cutting_order_page_action_icons\.js/);
assert.match(assets, /door_cutting_order_form_presentation\.css\?v=4/);
assert.match(assets, /door_cutting_order_form_tab_layout\.css\?v=9/);
assert.match(presentationCss, /--dco-nav-cluster-gap:\s*6px/);
assert.match(presentationCss, /--dco-nav-end-inset/);
assert.match(presentationCss, /\.page-icon-group/);
assert.match(tabCss, /\.dco-whatsapp-send-measurements/);
assert.match(tabCss, /#e8f6ed/);
assert.match(tabCss, /#167a42/);
assert.match(tabCss, /\.dco-page-action-icon/);
assert.ok(catalog.includes("Share Changes,مشاركة التعديلات"));

class FakeClassList {
    constructor() { this.values = new Set(); }
    add(...values) { values.forEach((value) => this.values.add(value)); }
    contains(value) { return this.values.has(value); }
}

function fakeButton(text) {
    const children = [];
    const node = {
        nodeType: 1,
        isConnected: true,
        classList: new FakeClassList(),
        textContent: text,
        children,
        querySelector(selector) {
            if (selector.includes("data-dco-action-icon")) {
                return children.find((child) => child.getAttribute && child.getAttribute("data-dco-action-icon")) || null;
            }
            if (selector.includes("data-dco-action-label")) {
                return children.find((child) => child.getAttribute && child.getAttribute("data-dco-action-label")) || null;
            }
            return null;
        },
        replaceChildren(...nodes) {
            children.length = 0;
            nodes.forEach((child) => children.push(child));
            this.childElementCount = children.length;
        },
        append(...nodes) {
            nodes.forEach((child) => children.push(child));
            this.childElementCount = children.length;
        },
        get childElementCount() { return children.length; },
        set childElementCount(_value) {},
    };
    return node;
}

function fakeElement(tag) {
    const attributes = {};
    const children = [];
    return {
        tagName: String(tag || "span").toUpperCase(),
        children,
        className: "",
        textContent: "",
        innerHTML: "",
        childElementCount: 0,
        setAttribute(name, value) { attributes[name] = String(value); },
        getAttribute(name) { return Object.prototype.hasOwnProperty.call(attributes, name) ? attributes[name] : null; },
        append(...nodes) {
            nodes.forEach((child) => children.push(child));
            this.childElementCount = children.length;
        },
    };
}

const context = {
    window: {},
    document: {
        createElement(tag) { return fakeElement(tag); },
    },
    String,
    Object,
    Boolean,
};
context.window = context;
vm.createContext(context);
vm.runInContext(source, context);

const api = context.window.AlmdinaDcoPageActionIcons;
assert.ok(api);
const button = fakeButton("Notes");
assert.equal(api.ensure(button, { icon: "message-square", label: "Notes 2" }), true);
assert.equal(button.classList.contains("dco-page-action-with-icon"), true);
assert.equal(button.querySelector("[data-dco-action-label]").textContent, "Notes 2");
assert.equal(button.querySelector("[data-dco-action-icon]").getAttribute("data-dco-action-icon"), "message-square");
assert.equal(api.ensure(button, { icon: "message-square", label: "Notes 3" }), true);
assert.equal(
    button.children.filter((child) => child.getAttribute && child.getAttribute("data-dco-action-icon")).length,
    1
);
assert.equal(button.querySelector("[data-dco-action-label]").textContent, "Notes 3");
assert.match(api.iconMarkup("whatsapp"), /currentColor/);
assert.doesNotMatch(api.iconMarkup("whatsapp"), /emoji/);

console.log("dco page action icons contract passed");
