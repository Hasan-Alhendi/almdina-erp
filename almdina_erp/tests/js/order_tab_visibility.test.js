"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const source = fs.readFileSync(
    path.resolve(__dirname, "../../public/js/door_cutting_order/core/door_cutting_order_tab_permissions_ux.js"),
    "utf8"
);
const pageEditSource = fs.readFileSync(
    path.resolve(__dirname, "../../public/js/door_cutting_order/core/door_cutting_order_page_edit_action_ux.js"),
    "utf8"
);

function tabNode() {
    const nav = {
        hidden: false,
        style: { display: "" },
        attributes: {},
        setAttribute(name, value) {
            this.attributes[name] = value;
        },
    };
    return {
        nav,
        field: {
            closest() {
                return nav;
            },
        },
    };
}

const results = tabNode();
const costs = tabNode();
const planHtml = { html: "<div class=\"dco-cutting-plan\">PLAN-SENTINEL</div>" };

const root = {
    querySelectorAll(selector) {
        if (selector === '[data-fieldname="results_tab"]') return [results.field];
        if (selector === '[data-fieldname="cost_tab"]') return [costs.field];
        return [];
    },
};

const handlers = {};
const fakeWindow = {
    cur_frm: null,
    requestAnimationFrame(callback) {
        callback();
        return 1;
    },
    setTimeout(callback) {
        callback();
        return 1;
    },
    addEventListener() {},
};
const fakeFrappe = {
    ui: {
        form: {
            on(doctype, mapping) {
                assert.equal(doctype, "Door Cutting Order");
                Object.assign(handlers, mapping);
            },
        },
    },
};

const context = vm.createContext({
    window: fakeWindow,
    frappe: fakeFrappe,
    Object,
    String,
    Boolean,
});
vm.runInContext(source, context, { filename: "door_cutting_order_tab_permissions_ux.js" });

fakeWindow.AlmdinaPermissions = {
    canDocument(_frm, capability) {
        return capability === "view_cutting_plan";
    },
    can(capability) {
        return capability === "view_cutting_plan";
    },
};

let layoutMutationCount = 0;
const frm = {
    doctype: "Door Cutting Order",
    wrapper: [root],
    // Reproduce the production mismatch: Plan is visibly selected through the
    // canonical Frappe API while layout.current_tab still points at hidden Cost.
    get_active_tab() {
        return { df: { fieldname: "results_tab" } };
    },
    layout: { current_tab: { df: { fieldname: "cost_tab" } } },
    fields_dict: {
        cutting_plan_html: {
            $wrapper: {
                html() {
                    return planHtml.html;
                },
            },
        },
    },
    set_df_property() {
        layoutMutationCount += 1;
        throw new Error("Tab visibility must never rebuild the Frappe layout");
    },
    set_active_tab() {
        throw new Error("The visible cutting-plan tab must stay active even when layout.current_tab is stale");
    },
};

fakeWindow.AlmdinaOrderTabPermissionsUX.apply(frm);

assert.equal(layoutMutationCount, 0);
assert.equal(results.nav.hidden, false);
assert.equal(results.nav.style.display, "");
assert.equal(results.nav.attributes["aria-hidden"], "false");
assert.equal(costs.nav.hidden, true);
assert.equal(costs.nav.style.display, "none");
assert.equal(costs.nav.attributes["aria-hidden"], "true");
assert.match(planHtml.html, /PLAN-SENTINEL/);

// Frappe v16 keeps the selected tab on Form.active_tab_map and exposes it
// through get_active_tab(). Layout.current_tab is only the layout-construction
// cursor and may still point at a later/hidden Tab Break such as cost_tab.
const pageEditWindow = {
    addEventListener() {},
    requestAnimationFrame() {},
};
const pageEditFrappe = {
    ui: {
        form: {
            on(doctype) {
                assert.equal(doctype, "Door Cutting Order");
            },
        },
    },
};
const pageEditContext = vm.createContext({
    window: pageEditWindow,
    frappe: pageEditFrappe,
    console,
    Object,
    String,
    Boolean,
    Promise,
});
vm.runInContext(pageEditSource, pageEditContext, {
    filename: "door_cutting_order_page_edit_action_ux.js",
});

const activeTab = { df: { fieldname: "results_tab" } };
const routedPlanForm = {
    doctype: "Door Cutting Order",
    doc: { name: "DCO-2026-00005" },
    get_active_tab() {
        return activeTab;
    },
    // Intentionally contradictory: this is the stale construction cursor that
    // caused the visible Plan tab to be treated as Cost before the regression.
    layout: { current_tab: { df: { fieldname: "cost_tab" } } },
    wrapper: [{ querySelector() { return null; } }],
};
assert.equal(
    pageEditWindow.AlmdinaPageEditActionUX.activeKind(routedPlanForm),
    "plan",
    "visible results_tab must win over the layout construction cursor"
);
activeTab.df.fieldname = "order_tab";
assert.equal(pageEditWindow.AlmdinaPageEditActionUX.activeKind(routedPlanForm), "order");

console.log("order tab visibility simulation passed");
