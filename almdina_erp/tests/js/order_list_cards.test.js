"use strict";

const assert = require("assert");
const fs = require("fs");
const vm = require("vm");

const responsiveSource = fs.readFileSync(
    "almdina_erp/public/js/responsive_device.js",
    "utf8"
);
const source = fs.readFileSync(
    "almdina_erp/public/js/door_cutting_order_list.js",
    "utf8"
);

const context = {
    console,
    document: { documentElement: { clientWidth: 390 } },
    frappe: {
        datetime: { str_to_user: value => `date:${value}` },
        listview_settings: {},
        session: { user: "cutting@example.com" },
        utils: {
            escape_html(value) {
                return String(value).replaceAll("<", "&lt;").replaceAll(">", "&gt;");
            },
        },
    },
    window: {
        innerWidth: 390,
        screen: { width: 390, height: 844 },
        AlmdinaShopFloorQuickActions: {
            actionFor(actionContext) {
                return actionContext.canStart
                    ? { kind: "start", label: "بدء العمل", indicator: "primary" }
                    : null;
            },
        },
    },
    __(value) { return value; },
};
context.window.window = context.window;
vm.createContext(context);
vm.runInContext(responsiveSource, context);
vm.runInContext(source, context);

const api = context.window.AlmdinaDoorCuttingOrderListUX;
const doc = {
    name: "DCO-2026-00010",
    customer: "عميل الاختبار",
    order_date: "2026-08-02",
    status: "At Sharyoun",
    board_description: "MDF أبيض 18 مم",
    edge_color: "أسود",
    production_path: "Sharyoun",
    current_department: "شريون",
    current_assignee: "cutting@example.com",
    current_production_stage: "PST-10",
    department_status: "بحاجة للعمل",
};

const html = api.buildCard(doc, true);
assert(html.includes('class="dco-mobile-order-card"'), "the mobile row must be a real card");
assert(html.includes('class="dco-card-workflow"'), "production state must have a dedicated visual group");
assert(html.includes("أسود"), "the card must show edge color");
assert(html.includes("MDF أبيض 18 مم"), "the card must show the board description");
assert(html.includes("بدء العمل"), "the assigned worker must get the valid quick action");
assert(html.includes("فتح الطلب"), "the card must retain a clear detail action");
assert(!html.includes("<select"), "the card must not expose an arbitrary status selector");

const narrowRoot = { getBoundingClientRect: () => ({ width: 340 }) };
assert.strictEqual(api.isPhoneLayout(narrowRoot), true, "a real phone must use order cards");
context.document.documentElement.clientWidth = 700;
context.window.innerWidth = 700;
context.window.screen.width = 1366;
context.window.screen.height = 768;
assert.strictEqual(api.isPhoneLayout(narrowRoot), false, "a laptop must retain the original list table");

const otherWorker = { ...doc, current_assignee: "other@example.com" };
assert.strictEqual(api.quickActionContext(otherWorker).canStart, false);
assert(!api.buildCard(otherWorker, false).includes("dco-card-production-action"));

console.log("Door Cutting Order list-card simulation passed");
