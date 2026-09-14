"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const source = fs.readFileSync(
    path.resolve(
        __dirname,
        "../../public/js/door_cutting_order/cutting_plan/door_cutting_order_plan_tabs_ux.js"
    ),
    "utf8"
);

function buttonTag(html, tabId) {
    const match = html.match(new RegExp(`<button[^>]*data-plan-tab="${tabId}"[^>]*>`));
    assert.ok(match, `missing ${tabId} source tab`);
    return match[0];
}

function isDisabled(html, tabId) {
    const tag = buttonTag(html, tabId);
    return /\sdisabled(?:\s|>|\/)/.test(tag) || /disabled="/.test(tag);
}

function createWrapper() {
    let html = "";
    const attrs = {};
    let tabClick = null;
    const nodes = [];

    function refreshNodes() {
        nodes.length = 0;
        const matches = html.matchAll(/<button([^>]*data-plan-tab="[^"]+"[^>]*)>/g);
        for (const match of matches) {
            const tag = match[1];
            const idMatch = tag.match(/data-plan-tab="([^"]+)"/);
            const node = {
                disabled: /\sdisabled(?:\s|>|\/|=)/.test(` ${tag}`) || /disabled="/.test(tag),
                attrs: {
                    "data-plan-tab": idMatch ? idMatch[1] : "",
                    title: (tag.match(/title="([^"]*)"/) || [])[1],
                    "aria-disabled": (tag.match(/aria-disabled="([^"]*)"/) || [])[1],
                },
            };
            nodes.push(node);
        }
    }

    function wrapNode(node) {
        return {
            attr(name, value) {
                if (value === undefined) return node.attrs[name];
                node.attrs[name] = value;
                return this;
            },
            removeAttr(name) {
                delete node.attrs[name];
                return this;
            },
            prop(name, value) {
                if (value === undefined) return Boolean(node[name]);
                node[name] = value;
                return this;
            },
        };
    }

    const wrapper = {
        attr(name, value) {
            if (value === undefined) return attrs[name];
            attrs[name] = value;
            return wrapper;
        },
        html(value) {
            if (value === undefined) return html;
            html = String(value);
            refreshNodes();
            return wrapper;
        },
        find(selector) {
            if (selector === ".dco-plan-context-actions-host") {
                return { first() { return this; }, length: 0 };
            }
            return {
                length: nodes.length,
                on(_event, handler) {
                    tabClick = handler;
                    return this;
                },
                each(callback) {
                    nodes.forEach((node, index) => callback(index, node));
                    return this;
                },
            };
        },
        click(tabId) {
            const node = nodes.find((entry) => entry.attrs["data-plan-tab"] === tabId);
            assert.ok(node, `cannot click missing ${tabId} tab`);
            const bound = wrapNode(node);
            tabClick.call({
                disabled: node.disabled,
                getAttribute(name) {
                    return node.attrs[name];
                },
                attrs: node.attrs,
            });
            return bound;
        },
        get htmlValue() {
            return html;
        },
        get nodes() {
            return nodes;
        },
    };
    return wrapper;
}

function loadTabs(editing) {
    const fakeWindow = {
        AlmdinaPermissions: {
            canDocument() {
                return true;
            },
            can() {
                return true;
            },
        },
        AlmdinaPlanEditSessionUX: {
            isEditing() {
                return editing.value;
            },
        },
        AlmdinaCuttingPlanRender: {
            build(_frm, plan) {
                return `<div class="dco-plan">${plan.sheets[0].source}</div>`;
            },
        },
        dispatchEvent() {
            return true;
        },
    };
    const fakeFrappe = {
        ui: { form: { on() {} } },
        utils: {
            escape_html(value) {
                return String(value ?? "");
            },
        },
    };
    function $(target) {
        if (target && typeof target.attr === "function") return target;
        const attrs = (target && target.attrs) || {};
        return {
            attr(name) {
                return attrs[name];
            },
            prop(name, value) {
                if (value === undefined) return Boolean(target && target[name]);
                target[name] = value;
                return this;
            },
            removeAttr(name) {
                delete attrs[name];
                return this;
            },
        };
    }
    const context = vm.createContext({
        window: fakeWindow,
        frappe: fakeFrappe,
        console,
        Object,
        Array,
        Boolean,
        String,
        Set,
        $,
        __: value => value,
        CustomEvent: class CustomEvent {
            constructor(name, init) {
                this.type = name;
                this.detail = init && init.detail;
            }
        },
    });
    vm.runInContext(source, context, { filename: "door_cutting_order_plan_tabs_ux.js" });
    return fakeWindow.AlmdinaPlanTabsUX;
}

const editing = { value: false };
const tabs = loadTabs(editing);
const wrapper = createWrapper();
const frm = {
    doc: {
        name: "DCO-LOCK",
        approved_plan: "CP-APPROVED",
        approved_plan_source: "Custom",
        custom_plan_json: { sheets: [{ source: "Custom" }] },
        system_plan_json: { sheets: [{ source: "System" }] },
        cutting_plan_json: { sheets: [{ source: "System" }] },
    },
    fields_dict: {
        cutting_plan_html: { $wrapper: wrapper },
    },
    __almdina_active_plan_tab: "Custom",
    __almdina_approved_plan_order: "DCO-LOCK",
    __almdina_approved_plan_snapshot: { sheets: [{ source: "Approved" }] },
};

editing.value = false;
assert.equal(tabs.defaultTab(frm), "Custom");
assert.equal(tabs.renderDualTabs(frm), true);
assert.equal(isDisabled(wrapper.htmlValue, "System"), false);
assert.equal(isDisabled(wrapper.htmlValue, "Custom"), false);
assert.equal(isDisabled(wrapper.htmlValue, "Approved"), false);

editing.value = true;
frm.__almdina_active_plan_tab = "Custom";
assert.equal(tabs.defaultTab(frm), "System", "edit session must force the System source tab");
assert.equal(tabs.renderDualTabs(frm), true);
assert.equal(frm.__almdina_active_plan_tab, "System");
assert.equal(isDisabled(wrapper.htmlValue, "System"), false);
assert.equal(isDisabled(wrapper.htmlValue, "Custom"), true);
assert.equal(isDisabled(wrapper.htmlValue, "Approved"), true);
assert.match(buttonTag(wrapper.htmlValue, "Custom"), /احفظ أو ألغِ تعديل خطة القص قبل تغيير مصدر الخطة/);

assert.equal(tabs.renderDualTabs(frm), true, "a later workspace rerender must keep the lock");
assert.equal(isDisabled(wrapper.htmlValue, "Custom"), true);
assert.equal(isDisabled(wrapper.htmlValue, "Approved"), true);
assert.equal(frm.__almdina_active_plan_tab, "System");

wrapper.click("Custom");
assert.equal(frm.__almdina_active_plan_tab, "System", "locked source tabs must ignore navigation");
assert.equal(isDisabled(wrapper.htmlValue, "Approved"), true);

editing.value = false;
assert.equal(tabs.renderDualTabs(frm), true);
assert.equal(isDisabled(wrapper.htmlValue, "Custom"), false);
assert.equal(isDisabled(wrapper.htmlValue, "Approved"), false);

console.log("Plan source tab edit-lock contract passed");
