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
const cssSource = fs.readFileSync(
    "almdina_erp/public/css/door_cutting_order_mobile_list.css",
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
                if (actionContext.canDeliver) {
                    return { kind: "deliver", label: "تم التسليم", indicator: "success" };
                }
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
    modified: "2026-08-20 09:00:00",
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
        canDeliver: false,
        assignmentState: "assigned",
        queueState: "ready",
    },
};

const model = api.cardViewModel(doc);
assert.strictEqual(model.state.key, "ready");
assert.strictEqual(model.state.label, "جاهز للبدء");
assert.strictEqual(model.state.icon, "play");
assert.strictEqual(model.boardColor, "أبيض لولو");
assert.strictEqual(model.edgeColor, "أسود");
assert.strictEqual(model.edgeType, "PVC 2 مم");

const html = api.buildCard(doc, true);
assert(html.includes("dco-mobile-order-card is-ready"), "the ready order must render with the blue ready theme");
assert(html.includes('class="dco-card-customer-block"'), "customer identity must be the primary header block");
assert(html.includes('class="dco-card-state-pill"'), "the card must expose a visual workflow-state pill");
assert(html.includes('class="dco-card-state-icon"'), "each workflow state must expose a semantic icon in addition to color");
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
assert(html.includes("is-start"));
assert(!html.includes("dco-card-open"), "the redundant open-order footer button must stay removed");
assert(!html.includes("<select"), "the card must not expose an arbitrary status selector");

const inProgress = {
    ...doc,
    department_status: "قيد العمل",
    __almdinaProductionActionContext: {
        stage: "PST-10",
        canStart: false,
        canHandoff: true,
        canDeliver: false,
        assignmentState: "assigned",
        queueState: "in_progress",
    },
};
const inProgressModel = api.cardViewModel(inProgress);
const inProgressHtml = api.buildCard(inProgress, false);
assert.strictEqual(inProgressModel.state.key, "in_progress");
assert.strictEqual(inProgressModel.state.icon, "activity");
assert(inProgressHtml.includes("dco-mobile-order-card is-in-progress"));
assert(inProgressHtml.includes("قيد التنفيذ"));
assert(inProgressHtml.includes("إنهاء العمل"), "an active mobile assignment must expose a clear finish action");
assert(inProgressHtml.includes('data-action-kind="handoff"'));
assert(inProgressHtml.includes("is-finish"));
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
        canDeliver: false,
        assignmentState: "assigned",
        queueState: "ready",
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

const readyForDelivery = {
    ...doc,
    status: "Ready for Delivery",
    department_status: "مكتمل",
    __almdinaProductionActionContext: {
        stage: "PST-10",
        canStart: false,
        canHandoff: false,
        canDeliver: false,
        assignmentState: "completed",
        queueState: "ready_for_delivery",
    },
};
const readyForDeliveryModel = api.cardViewModel(readyForDelivery);
const readyForDeliveryHtml = api.buildCard(readyForDelivery, false);
assert.strictEqual(readyForDeliveryModel.state.key, "ready_for_delivery");
assert.strictEqual(readyForDeliveryModel.state.label, "جاهز للتسليم");
assert.strictEqual(readyForDeliveryModel.state.icon, "package");
assert.strictEqual(readyForDeliveryModel.history, false);
assert(readyForDeliveryHtml.includes("dco-mobile-order-card is-ready-for-delivery"));
assert(readyForDeliveryHtml.includes("جاهز للتسليم"), "production-complete orders must have an explicit waiting-for-delivery state");
assert(!readyForDeliveryHtml.includes("dco-card-complete-state"), "ready for delivery is still actionable work, not history");
assert(!readyForDeliveryHtml.includes("dco-card-production-action"), "delivery capability must still come only from the server");
assert(!readyForDeliveryHtml.includes("dco-list-row-completed"), "ready for delivery must not inherit completed green styling");

const deliveryAuthorized = {
    ...readyForDelivery,
    __almdinaProductionActionContext: {
        stage: "PST-10",
        canStart: false,
        canHandoff: false,
        canDeliver: true,
        assignmentState: "completed",
        queueState: "ready_for_delivery",
    },
};
const deliveryAuthorizedModel = api.cardViewModel(deliveryAuthorized);
const deliveryAuthorizedHtml = api.buildCard(deliveryAuthorized, false);
assert.strictEqual(deliveryAuthorizedModel.state.key, "ready_for_delivery");
assert.strictEqual(deliveryAuthorizedModel.action.kind, "deliver");
assert.strictEqual(deliveryAuthorizedModel.action.label, "تم التسليم");
assert(deliveryAuthorizedHtml.includes("جاهز للتسليم"), "delivery authorization must not replace the actual card state");
assert(deliveryAuthorizedHtml.includes('data-action-kind="deliver"'), "server-authorized delivery must render as the mobile quick action");
assert(deliveryAuthorizedHtml.includes("is-deliver"), "delivery must have its own purple action identity");
assert(deliveryAuthorizedHtml.includes("تم التسليم"), "the delivery action must use the agreed Arabic label");

const completed = {
    ...doc,
    status: "Completed",
    department_status: "مكتمل",
    __almdinaProductionActionContext: {
        stage: "PST-10",
        canStart: false,
        canHandoff: false,
        canDeliver: false,
        assignmentState: "completed",
        queueState: "completed",
    },
};
const completedModel = api.cardViewModel(completed);
const completedHtml = api.buildCard(completed, false);
assert.strictEqual(completedModel.state.key, "completed");
assert.strictEqual(completedModel.state.label, "تم الإنجاز");
assert.strictEqual(completedModel.state.icon, "circle-check");
assert.strictEqual(completedModel.history, true);
assert(completedHtml.includes("dco-mobile-order-card is-completed"));
assert(completedHtml.includes("تم الإنجاز"), "completed mobile work must show a non-interactive completion state");
assert(completedHtml.includes("dco-card-complete-state"));
assert(!completedHtml.includes("dco-card-production-action"), "completed history must not expose a workflow button");

const delivered = {
    ...readyForDelivery,
    status: "Delivered",
    modified: "2026-08-20 16:00:00",
    __almdinaProductionActionContext: {
        stage: "PST-10",
        canStart: false,
        canHandoff: false,
        canDeliver: false,
        assignmentState: "completed",
        queueState: "delivered",
    },
};
const deliveredModel = api.cardViewModel(delivered);
const deliveredHtml = api.buildCard(delivered, false);
assert.strictEqual(deliveredModel.state.key, "delivered");
assert.strictEqual(deliveredModel.state.label, "تم التسليم");
assert.strictEqual(deliveredModel.state.icon, "truck");
assert.strictEqual(deliveredModel.history, true);
assert.strictEqual(deliveredModel.action, null);
assert(deliveredHtml.includes("dco-mobile-order-card is-delivered"));
assert(deliveredHtml.includes("dco-card-complete-state"));
assert(deliveredHtml.includes("تم التسليم"), "a delivered order must retain a non-interactive delivered state");
assert(!deliveredHtml.includes("dco-card-production-action"), "a delivered order must never render another workflow button");

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

const queueItems = [
    {
        name: "READY-OLD",
        doc: { status: "At CNC", department_status: "بحاجة للعمل" },
        flag: { assignment_state: "assigned", assignment_time: "2026-08-17 08:00:00" },
    },
    {
        name: "COMPLETED-OLD",
        doc: { status: "At CNC", department_status: "مكتمل" },
        flag: { assignment_state: "completed", completion_time: "2026-08-17 11:00:00" },
    },
    {
        name: "READY-DELIVERY-NEW",
        doc: { status: "Ready for Delivery", department_status: "مكتمل" },
        flag: { assignment_state: "completed", completion_time: "2026-08-17 14:00:00" },
    },
    {
        name: "DELIVERED-OLD",
        doc: { status: "Delivered", department_status: "مكتمل", modified: "2026-08-17 15:00:00" },
        flag: { assignment_state: "completed", completion_time: "2026-08-17 13:00:00" },
    },
    {
        name: "READY-NEW",
        doc: { status: "At CNC", department_status: "بحاجة للعمل" },
        flag: { assignment_state: "assigned", assignment_time: "2026-08-17 10:00:00" },
    },
    {
        name: "IN-PROGRESS",
        doc: { status: "At CNC", department_status: "قيد العمل" },
        flag: { assignment_state: "assigned", assignment_time: "2026-08-17 09:00:00" },
    },
    {
        name: "COMPLETED-NEW",
        doc: { status: "At CNC", department_status: "مكتمل" },
        flag: { assignment_state: "completed", completion_time: "2026-08-17 12:00:00" },
    },
    {
        name: "READY-DELIVERY-OLD",
        doc: { status: "Ready for Delivery", department_status: "مكتمل" },
        flag: { assignment_state: "completed", completion_time: "2026-08-17 13:00:00" },
    },
    {
        name: "DELIVERED-NEW",
        doc: { status: "Delivered", department_status: "مكتمل", modified: "2026-08-17 16:00:00" },
        flag: { assignment_state: "completed", completion_time: "2026-08-17 14:00:00" },
    },
];
assert.deepStrictEqual(
    Array.from(api.sortPersonalQueueItems(queueItems), item => item.name),
    [
        "IN-PROGRESS",
        "READY-OLD",
        "READY-NEW",
        "READY-DELIVERY-OLD",
        "READY-DELIVERY-NEW",
        "COMPLETED-NEW",
        "COMPLETED-OLD",
        "DELIVERED-NEW",
        "DELIVERED-OLD",
    ],
    "worker queue must render in-progress, ready, ready-for-delivery, completed, then delivered with state-specific chronology"
);
assert.strictEqual(
    api.personalQueueState({ status: "At CNC", department_status: "قيد العمل" }, { assignment_state: "assigned" }),
    "in_progress"
);
assert.strictEqual(
    api.personalQueueState({ status: "At CNC", department_status: "بحاجة للعمل" }, { assignment_state: "assigned" }),
    "ready"
);
assert.strictEqual(
    api.personalQueueState({ status: "Ready for Delivery", department_status: "مكتمل" }, { assignment_state: "completed" }),
    "ready_for_delivery",
    "ready for delivery must be a first-class actionable queue state"
);
assert.strictEqual(
    api.personalQueueState({ status: "At CNC", department_status: "قيد العمل" }, { assignment_state: "completed" }),
    "completed",
    "completion must remain authoritative over stale display status"
);
assert.strictEqual(
    api.personalQueueState({ status: "Delivered", department_status: "مكتمل" }, { assignment_state: "completed" }),
    "delivered"
);

assert(cssSource.includes("#2563eb"), "ready/start must use the agreed blue identity");
assert(cssSource.includes("#f59e0b"), "in-progress/finish must use the agreed orange identity");
assert(cssSource.includes("#7c3aed"), "ready-for-delivery/deliver must use the agreed purple identity");
assert(cssSource.includes("#16a34a"), "completed must use the agreed green identity");
assert(cssSource.includes("#047857"), "delivered must use the agreed dark-green identity");
assert(cssSource.includes(".is-ready-for-delivery"));
assert(cssSource.includes(".is-delivered"));
assert(cssSource.includes(".is-deliver"));
assert(!source.includes("frappe.get_roles"), "mobile list presentation must remain capability-driven, never role-name-driven");

console.log("Door Cutting Order five-state mobile-card simulation passed");