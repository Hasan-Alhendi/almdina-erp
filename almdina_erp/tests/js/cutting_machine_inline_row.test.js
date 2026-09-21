"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const source = fs.readFileSync(
    path.resolve(
        __dirname,
        "../../public/js/door_cutting_order/order_entry/door_cutting_order_cutting_machine_ux.js"
    ),
    "utf8"
);

function createNode(tag, className) {
    const classes = new Set(String(className || "").split(/\s+/).filter(Boolean));
    let classNameValue = [...classes].join(" ");
    const node = {
        nodeType: 1,
        tagName: String(tag).toUpperCase(),
        children: [],
        parentElement: null,
        isConnected: true,
        style: {},
        attributes: {},
        textContent: "",
        type: "",
        name: "",
        value: "",
        checked: false,
        disabled: false,
        classList: {
            add(name) {
                classes.add(name);
                classNameValue = [...classes].join(" ");
            },
            remove(name) {
                classes.delete(name);
                classNameValue = [...classes].join(" ");
            },
            contains(name) {
                return classes.has(name);
            },
            toggle(name, force) {
                if (force === false) this.remove(name);
                else if (force === true || !classes.has(name)) this.add(name);
                else this.remove(name);
                return classes.has(name);
            },
        },
        setAttribute(key, value) {
            this.attributes[key] = String(value);
        },
        getAttribute(key) {
            return this.attributes[key];
        },
        removeAttribute(key) {
            delete this.attributes[key];
        },
        appendChild(child) {
            if (child.parentElement && typeof child.parentElement.removeChild === "function") {
                child.parentElement.removeChild(child);
            }
            child.parentElement = this;
            this.children.push(child);
            return child;
        },
        insertBefore(child, reference) {
            if (child.parentElement && typeof child.parentElement.removeChild === "function") {
                child.parentElement.removeChild(child);
            }
            child.parentElement = this;
            const index = this.children.indexOf(reference);
            this.children.splice(index < 0 ? this.children.length : index, 0, child);
            return child;
        },
        removeChild(child) {
            this.children = this.children.filter((item) => item !== child);
            child.parentElement = null;
            return child;
        },
        querySelector(selector) {
            return queryAll(this, selector)[0] || null;
        },
        querySelectorAll(selector) {
            return queryAll(this, selector);
        },
        closest(selector) {
            let current = this;
            while (current) {
                if (matches(current, selector)) return current;
                current = current.parentElement;
            }
            return null;
        },
        addEventListener() {},
    };
    Object.defineProperty(node, "className", {
        get() {
            return classNameValue;
        },
        set(value) {
            classNameValue = String(value || "");
            classes.clear();
            classNameValue.split(/\s+/).filter(Boolean).forEach((name) => classes.add(name));
        },
        enumerable: true,
        configurable: true,
    });
    Object.defineProperty(node, "firstChild", {
        get() {
            return this.children[0] || null;
        },
    });
    return node;
}

function matches(node, selector) {
    if (selector === "input[type='radio']" || selector === 'input[type="radio"]') {
        return node.tagName === "INPUT" && node.type === "radio";
    }
    if (selector.startsWith(".")) {
        return node.classList.contains(selector.slice(1));
    }
    return false;
}

function walk(node, acc) {
    acc.push(node);
    node.children.forEach((child) => walk(child, acc));
    return acc;
}

function queryAll(root, selector) {
    const found = [];
    root.children.forEach((child) => walk(child, found));
    return found.filter((node) => matches(node, selector));
}

function frappeFieldDom() {
    const wrapper = createNode("div", "frappe-control input-max-width");
    wrapper.setAttribute("data-fieldname", "order_cutting_machine");
    wrapper.setAttribute("data-fieldtype", "Select");
    const formGroup = createNode("div", "form-group horizontal");
    const clearfix = createNode("div", "clearfix");
    const label = createNode("label", "control-label");
    label.textContent = "نوع آلة القص";
    const inputWrapper = createNode("div", "control-input-wrapper");
    const controlInput = createNode("div", "control-input");
    const select = createNode("select", "form-control");
    controlInput.appendChild(select);
    inputWrapper.appendChild(controlInput);
    clearfix.appendChild(label);
    formGroup.appendChild(clearfix);
    formGroup.appendChild(inputWrapper);
    wrapper.appendChild(formGroup);
    return { wrapper, formGroup, clearfix, label };
}

const documentNode = createNode("document");
const fakeWindow = {
    AlmdinaOrderCuttingMachineUX: undefined,
    cur_frm: null,
    requestAnimationFrame(callback) {
        callback();
        return 1;
    },
    addEventListener() {},
};
const fakeDocument = {
    getElementById() {
        return null;
    },
    createElement(tag) {
        return createNode(tag);
    },
};
class FakeMutationObserver {
    observe() {}
}

const context = vm.createContext({
    window: fakeWindow,
    document: fakeDocument,
    MutationObserver: FakeMutationObserver,
    $() {
        return { append() {} };
    },
    frappe: {
        ui: {
            form: {
                on() {},
            },
        },
        throw() {},
        utils: { escape_html(value) { return String(value || ""); } },
    },
    __: (value) => value,
    Object,
    String,
    Boolean,
    Number,
    Array,
});
vm.runInContext(source, context, { filename: "door_cutting_order_cutting_machine_ux.js" });

const api = fakeWindow.AlmdinaOrderCuttingMachineUX;
assert.ok(api, "cutting machine UX should export a public API");

const { wrapper, formGroup, clearfix, label } = frappeFieldDom();
const frm = {
    doctype: "Door Cutting Order",
    is_new() { return true; },
    doc: { order_cutting_machine: "CNC" },
    fields_dict: {
        order_cutting_machine: {
            $wrapper: { 0: wrapper, length: 1 },
            wrapper,
        },
    },
    set_value() {},
};
fakeWindow.cur_frm = frm;
api.apply(frm);

const row = wrapper.querySelector(".dco-cutting-machine-row");
const radios = wrapper.querySelector(".dco-cutting-machine-radios");
assert.ok(row, "label and options must share a dedicated row");
assert.ok(radios, "radio options must render");
assert.equal(row.parentElement, formGroup);
assert.equal(clearfix.parentElement, row);
assert.equal(radios.parentElement, row);
assert.equal(row.children[0], clearfix);
assert.equal(row.children[1], radios);
assert.equal(label.parentElement, clearfix);
assert.equal(wrapper.querySelectorAll("input[type='radio']").length, 2);
assert.ok(wrapper.classList.contains("dco-cutting-machine-host"));

api.apply(frm);
assert.equal(wrapper.querySelectorAll(".dco-cutting-machine-row").length, 1);
assert.equal(wrapper.querySelectorAll(".dco-cutting-machine-radios").length, 1);
assert.equal(clearfix.parentElement, row);
assert.equal(radios.parentElement, row);
