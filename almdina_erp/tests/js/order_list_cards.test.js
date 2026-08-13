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

let coarsePointer = false;
let noHover = false;
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
        matchMedia(query) {
            if (query === "(pointer: coarse)") return { matches: coarsePointer };
            if (query === "(hover: none)") return { matches: noHover };
            return { matches: false };
        },
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

const responsive = context.window.AlmdinaResponsiveDevice;
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
    __almdinaProductionActionContext: {
        stage: "PST-10",
        canStart: true,
        canHandoff: false,
    },
};

const html = api.buildCard(doc, true);
assert(html.includes('class="dco-mobile-order-card"'), "the compact row must be a real card");
assert(html.includes('class="dco-card-workflow"'), "production state must have a dedicated visual group");
assert(html.includes("أسود"), "the card must show edge color");
assert(html.includes("MDF أبيض 18 مم"), "the card must show the board description");
assert(html.includes("بدء العمل"), "the assigned worker must get the valid quick action");
assert(html.includes("فتح الطلب"), "the card must retain a clear detail action");
assert(!html.includes("<select"), "the card must not expose an arbitrary status selector");

const phoneRoot = { getBoundingClientRect: () => ({ width: 340 }) };
assert.strictEqual(api.isPhoneLayout(phoneRoot), true, "a real phone must use order cards");
assert.strictEqual(responsive.usesCardLayout(phoneRoot), true);

// Narrow live viewports get cards even when screen.* still reports a desktop monitor.
context.document.documentElement.clientWidth = 390;
context.window.innerWidth = 390;
context.window.screen.width = 1440;
context.window.screen.height = 900;
coarsePointer = false;
noHover = false;
const narrowViewportRoot = { getBoundingClientRect: () => ({ width: 390 }) };
assert.strictEqual(
    api.isPhoneLayout(narrowViewportRoot),
    true,
    "a phone-sized viewport must use order cards without relying on screen.*"
);

// A portrait touch-first tablet uses cards even though its viewport is below 900px.
context.document.documentElement.clientWidth = 820;
context.window.innerWidth = 820;
context.window.screen.width = 820;
context.window.screen.height = 1180;
coarsePointer = true;
noHover = true;
const tabletRoot = { getBoundingClientRect: () => ({ width: 820 }) };
assert.strictEqual(responsive.isTabletDevice(tabletRoot), true, "a portrait touch tablet must be detected as a tablet");
assert.strictEqual(api.isPhoneLayout(tabletRoot), true, "a tablet must use order cards");

// A laptop keeps the original Frappe table even at a similar viewport width.
context.document.documentElement.clientWidth = 1024;
context.window.innerWidth = 1024;
context.window.screen.width = 1366;
context.window.screen.height = 768;
coarsePointer = false;
noHover = false;
const laptopRoot = { getBoundingClientRect: () => ({ width: 1024 }) };
assert.strictEqual(responsive.isTabletDevice(laptopRoot), false, "a laptop must not be treated as a tablet");
assert.strictEqual(api.isPhoneLayout(laptopRoot), false, "a laptop must retain the original list table");

const otherWorker = {
    ...doc,
    current_assignee: "other@example.com",
    __almdinaProductionActionContext: null,
};
assert.strictEqual(api.quickActionContext(otherWorker).canStart, false);
assert(!api.buildCard(otherWorker, false).includes("dco-card-production-action"));

console.log("Door Cutting Order responsive list-card simulation passed");
