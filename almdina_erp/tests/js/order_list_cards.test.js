"use strict";

const assert = require("assert");
const fs = require("fs");
const vm = require("vm");

const responsiveSource = fs.readFileSync(
    "almdina_erp/public/js/responsive_device.js",
    "utf8"
);
const source = fs.readFileSync(
    "almdina_erp/public/js/door_cutting_order/list_view/door_cutting_order_list.js",
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
                if (actionContext.canStart) {
                    return { kind: "start", label: "بدء العمل", indicator: "primary" };
                }
                if (actionContext.canHandoff) {
                    return { kind: "handoff", label: "إنهاء وإرسال", indicator: "success" };
                }
                return null;
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
    board_description: "أبيض لولو",
    edge_color: "أسود",
    default_edge_type: "PVC 2 مم",
    production_path: "Sharyoun",
    current_department: "شريون",
    current_assignee: "cutting@example.com",
    current_production_stage: "PST-10",
    department_status: "بحاجة للعمل",
    __almdinaProductionActionContext: {
        stage: "PST-10",
        canStart: true,
        canHandoff: false,
        assignmentState: "assigned",
    },
};

const model = api.cardViewModel(doc);
assert.strictEqual(model.state.key, "ready");
assert.strictEqual(model.state.label, "جاهز للبدء");
assert.strictEqual(model.boardColor, "أبيض لولو");
assert.strictEqual(model.edgeColor, "أسود");
assert.strictEqual(model.edgeType, "PVC 2 مم");

const html = api.buildCard(doc, true);
assert(html.includes("dco-mobile-order-card is-ready"), "the ready order must render with the blue ready theme");
assert(html.includes('class="dco-card-customer-block"'), "customer identity must be the primary header block");
assert(html.includes('class="dco-card-state-pill"'), "the card must expose a visual workflow-state pill");
assert(html.includes("جاهز للبدء"), "the initial production state must be clear");
assert(html.includes('class="dco-card-order-link"'), "the order ID must be the detail-navigation affordance");
assert(html.includes("DCO-2026-00010"));
assert(html.includes("عميل الاختبار"));
assert(html.includes("لون اللوح"));
assert(html.includes("أبيض لولو"));
assert(html.includes("لون القشاط"));
assert(html.includes("أسود"));
assert(html.includes("نوع القشاط"));
assert(html.includes("PVC 2 مم"));
assert(html.includes("date:2026-08-02"));
assert.strictEqual((html.match(/dco-card-info-tile/g) || []).length, 3, "the approved card has exactly three information tiles");
assert(!html.includes("dco-card-workflow"), "stage/assignee internals must not compete with the approved card hierarchy");
assert(html.includes("بدء العمل"), "the authorized assigned worker must get the start action");
assert(html.includes('data-action-kind="start"'));
assert(!html.includes("dco-card-open"), "the redundant open-order footer button must stay removed");
assert(!html.includes("<select"), "the card must not expose an arbitrary status selector");

const inProgress = {
    ...doc,
    department_status: "قيد العمل",
    __almdinaProductionActionContext: {
        stage: "PST-10",
        canStart: false,
        canHandoff: true,
        assignmentState: "assigned",
    },
};
const inProgressHtml = api.buildCard(inProgress, false);
assert(inProgressHtml.includes("dco-mobile-order-card is-progress"));
assert(inProgressHtml.includes("قيد التنفيذ"));
assert(inProgressHtml.includes("إنهاء العمل"), "an active mobile assignment must expose a clear finish action");
assert(inProgressHtml.includes('data-action-kind="handoff"'));
assert(!inProgressHtml.includes("إنهاء وإرسال"), "the compact mobile label should describe the worker action, not routing internals");

// Capability denial is represented only by the server-authorized action flags.
// The card may still describe the stage state, but it must render no action.
const permissionDenied = {
    ...doc,
    department_status: "بحاجة للعمل",
    __almdinaProductionActionContext: {
        stage: "PST-10",
        canStart: false,
        canHandoff: false,
        assignmentState: "assigned",
    },
};
const permissionDeniedHtml = api.buildCard(permissionDenied, false);
assert(permissionDeniedHtml.includes("جاهز للبدء"));
assert(
    !permissionDeniedHtml.includes("dco-card-production-action"),
    "an assigned worker without the server-granted production capability must not see a workflow button"
);
assert(!permissionDeniedHtml.includes("بدء العمل"));
assert(!permissionDeniedHtml.includes("إنهاء العمل"));

const completed = {
    ...doc,
    status: "Ready for Delivery",
    department_status: "مكتمل",
    __almdinaProductionActionContext: {
        stage: "PST-10",
        canStart: false,
        canHandoff: false,
        assignmentState: "completed",
    },
};
const completedHtml = api.buildCard(completed, false);
assert(completedHtml.includes("dco-mobile-order-card is-completed"));
assert(completedHtml.includes("تم الإنجاز"), "completed mobile work must show a non-interactive completion state");
assert(completedHtml.includes("dco-list-row-completed"), "completed cards must retain their green completion presentation");
assert(completedHtml.includes("dco-card-complete-state"));
assert(!completedHtml.includes("dco-card-production-action"), "the workflow button must disappear after completion");

const phoneRoot = { getBoundingClientRect: () => ({ width: 340 }) };
assert.strictEqual(api.isPhoneLayout(phoneRoot), true, "a real phone must use order cards");
assert.strictEqual(responsive.usesCardLayout(phoneRoot), true);

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

context.document.documentElement.clientWidth = 820;
context.window.innerWidth = 820;
context.window.screen.width = 820;
context.window.screen.height = 1180;
coarsePointer = true;
noHover = true;
const tabletRoot = { getBoundingClientRect: () => ({ width: 820 }) };
assert.strictEqual(responsive.isTabletDevice(tabletRoot), true, "a portrait touch tablet must be detected as a tablet");
assert.strictEqual(api.isPhoneLayout(tabletRoot), true, "a tablet must use order cards");

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

console.log("Door Cutting Order approved mobile-card simulation passed");
