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

function createWrapper() {
    let html = "";
    const attrs = {};
    const nodes = [];
    let tabClick = null;

    function refreshNodes() {
        nodes.length = 0;
        const matches = html.matchAll(/<button([^>]*data-plan-tab="[^"]+"[^>]*)>/g);
        for (const match of matches) {
            const tag = match[1];
            const idMatch = tag.match(/data-plan-tab="([^"]+)"/);
            nodes.push({
                disabled: /\sdisabled(?:\s|>|\/|=)/.test(` ${tag}`) || /disabled="/.test(tag),
                attrs: {
                    "data-plan-tab": idMatch ? idMatch[1] : "",
                },
            });
        }
    }

    return {
        attr(name, value) {
            if (value === undefined) return attrs[name];
            attrs[name] = value;
            return this;
        },
        html(value) {
            if (value === undefined) return html;
            html = String(value);
            refreshNodes();
            return this;
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
        get htmlValue() {
            return html;
        },
    };
}

function loadTabs(uploadedRow) {
    const fakeWindow = {
        AlmdinaPermissions: {
            canDocument() {
                return true;
            },
            can() {
                return true;
            },
        },
        AlmdinaPlanWorkspaceState: {
            planForTab(_frm, tab) {
                return tab === "Custom" ? uploadedRow : null;
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
        return {
            attr() {
                return "";
            },
            prop() {
                return this;
            },
            removeAttr() {
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

function renderCustom(tabs, wrapper, needsRecalculation) {
    const frm = {
        doc: {
            name: "DCO-UPLOADED",
            approved_plan: needsRecalculation ? null : "CP-APPROVED",
            approved_plan_source: "Custom",
            custom_plan_json: { sheets: [{ source: "Custom" }] },
            system_plan_json: { sheets: [{ source: "System" }] },
        },
        fields_dict: {
            cutting_plan_html: { $wrapper: wrapper },
        },
        __almdina_active_plan_tab: "Custom",
    };
    assert.equal(tabs.renderDualTabs(frm), true);
    return wrapper.htmlValue;
}

const uploadedGeometry = {
    name: "CP-UP-1",
    source_type: "Uploaded DXF",
    status: "Approved",
    snapshot_json: '{"sheets":[{"source":"Custom"}]}',
    validation: { needs_recalculation: false, status: "Valid" },
};

const freshTabs = loadTabs(uploadedGeometry);
const freshHtml = renderCustom(freshTabs, createWrapper(), false);
assert.match(freshHtml, /dco-plan/);
assert.doesNotMatch(freshHtml, /dco-uploaded-plan-mismatch-banner/);
assert.doesNotMatch(freshHtml, /لا يوجد خطة مرفوعة/);

const staleTabs = loadTabs({
    ...uploadedGeometry,
    status: "Cancelled",
    validation: { needs_recalculation: true, status: "Valid" },
});
const staleHtml = renderCustom(staleTabs, createWrapper(), true);
assert.match(staleHtml, /dco-uploaded-plan-mismatch-banner/);
assert.match(staleHtml, /role="alert"/);
assert.match(staleHtml, /الخطة غير مطابقة للطلب/);
assert.match(staleHtml, /بيانات هذا الطلب تم تعديلها وأصبحت الخطة غير مطابقة/);
assert.match(staleHtml, /dco-uploaded-plan-mismatch-banner[\s\S]*dco-plan/);
assert.match(staleHtml, /dco-plan/);

console.log("Uploaded plan mismatch banner contract passed");
