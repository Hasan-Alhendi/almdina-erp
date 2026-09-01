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
assert.strictEqual(model.productionStageLabel, "شريون");
assert.strictEqual(model.stageLabel, "شريون");

const html = api.buildCard(doc, true);
assert(html.includes("dco-mobile-order-card is-ready"), "the ready order must render with the blue ready theme");
assert(html.includes('class="dco-card-customer-block"'), "customer identity must be the primary header block");
assert(html.includes('class="dco-card-header-meta"'), "stage and queue state must share a compact header meta column");
assert(html.includes('class="dco-card-stage"'), "the current production stage must be visible on the worker card");
assert(html.includes("شريون"), "the worker card must show the current department name");
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
assert(inProgressHtml.includes("dco-card-stage"));
assert(inProgressHtml.includes("شريون"));
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
assert.strictEqual(readyForDeliveryModel.productionStageLabel, "");
assert(!readyForDeliveryHtml.includes("dco-card-stage"), "delivery cards must not repeat a production-stage chip");
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
assert.strictEqual(deliveredModel.productionStageLabel, "");
assert(!deliveredHtml.includes("dco-card-stage"), "delivered cards must not repeat a production-stage chip");
assert(deliveredHtml.includes("dco-card-complete-state"));
assert(deliveredHtml.includes("تم التسليم"), "a delivered order must retain a non-interactive delivered state");
assert(!deliveredHtml.includes("dco-card-production-action"), "a delivered order must never render another workflow button");

assert.strictEqual(api.overviewStageLabel({ status: "At CNC", current_department: "CNC" }), "CNC");
assert.strictEqual(api.overviewStageLabel({ status: "Ready for Delivery" }), "جاهز للتسليم");
assert.strictEqual(api.overviewStageLabel({ status: "Delivered" }), "تم التسليم");
assert.strictEqual(api.productionStageLabel({ status: "At CNC", current_department: "CNC" }), "CNC");
assert.strictEqual(api.productionStageLabel({ status: "At Sharyoun", current_department: "شريون" }), "شريون");
assert.strictEqual(api.productionStageLabel({ status: "Ready for Delivery", current_department: "شريون" }), "");
assert.strictEqual(api.productionStageLabel({ status: "Delivered", current_department: "CNC" }), "");

const overviewCnc = {
    ...doc,
    status: "At CNC",
    current_department: "CNC",
    department_status: "بحاجة للعمل",
    __almdinaProductionActionContext: {
        stage: "PST-10",
        canStart: false,
        canHandoff: false,
        canDeliver: false,
        assignmentState: "completed",
        queueState: "completed",
        overview: true,
    },
};
const overviewCncModel = api.cardViewModel(overviewCnc);
const overviewCncHtml = api.buildCard(overviewCnc, false);
assert.strictEqual(overviewCncModel.state.key, "ready");
assert.strictEqual(overviewCncModel.overview, true);
assert.strictEqual(overviewCncModel.stageLabel, "CNC");
assert.strictEqual(overviewCncModel.productionStageLabel, "CNC");
assert(overviewCncHtml.includes("dco-card-stage"));
assert(!overviewCncHtml.includes("dco-mobile-order-card is-completed"));
assert(!overviewCncHtml.includes("تم الإنجاز"), "all-orders mobile cards must not treat unassigned work as worker-completed");
assert(overviewCncHtml.includes("dco-card-complete-state"));
assert(overviewCncHtml.includes("CNC"), "the all-orders footer must show the current stage name");
assert(!overviewCncHtml.includes("dco-card-production-action"));

const overviewReadyForDelivery = {
    ...readyForDelivery,
    __almdinaProductionActionContext: {
        ...readyForDelivery.__almdinaProductionActionContext,
        overview: true,
    },
};
const overviewReadyHtml = api.buildCard(overviewReadyForDelivery, false);
assert(overviewReadyHtml.includes("dco-card-complete-state"), "all-orders ready-for-delivery must keep the footer bar");
assert(overviewReadyHtml.includes("جاهز للتسليم"));
assert(!overviewReadyHtml.includes("dco-card-production-action"), "delivery capability must still come only from the server");

const overviewDelivered = {
    ...delivered,
    __almdinaProductionActionContext: {
        ...delivered.__almdinaProductionActionContext,
        overview: true,
    },
};
const overviewDeliveredHtml = api.buildCard(overviewDelivered, false);
assert(overviewDeliveredHtml.includes("dco-card-complete-state"));
assert(overviewDeliveredHtml.includes("تم التسليم"));
assert(!overviewDeliveredHtml.includes("dco-card-production-action"));

const overviewAuthorizedDelivery = {
    ...deliveryAuthorized,
    __almdinaProductionActionContext: {
        ...deliveryAuthorized.__almdinaProductionActionContext,
        overview: true,
    },
};
const overviewAuthorizedDeliveryHtml = api.buildCard(overviewAuthorizedDelivery, false);
assert(overviewAuthorizedDeliveryHtml.includes('data-action-kind="deliver"'), "an authorized delivery action must keep the button in all-orders view");
assert(!overviewAuthorizedDeliveryHtml.includes("dco-card-complete-state"), "the action button replaces the stage footer");

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
        flag: {
            assignment_state: "completed",
            completion_time: "2026-08-17 10:00:00",
            ready_for_delivery_time: "2026-08-17 14:00:00",
        },
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
        name: "IN-PROGRESS-OLDER-START",
        doc: { status: "At CNC", department_status: "قيد العمل" },
        flag: {
            assignment_state: "assigned",
            assignment_time: "2026-08-17 09:00:00",
            start_time: "2026-08-17 10:00:00",
        },
    },
    {
        name: "IN-PROGRESS-LATEST-START",
        doc: { status: "At CNC", department_status: "قيد العمل" },
        flag: {
            assignment_state: "assigned",
            assignment_time: "2026-08-17 07:00:00",
            start_time: "2026-08-17 11:00:00",
        },
    },
    {
        name: "COMPLETED-NEW",
        doc: { status: "At CNC", department_status: "مكتمل" },
        flag: { assignment_state: "completed", completion_time: "2026-08-17 12:00:00" },
    },
    {
        name: "READY-DELIVERY-OLD",
        doc: { status: "Ready for Delivery", department_status: "مكتمل" },
        flag: {
            assignment_state: "completed",
            completion_time: "2026-08-17 15:00:00",
            ready_for_delivery_time: "2026-08-17 13:00:00",
        },
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
        "IN-PROGRESS-LATEST-START",
        "IN-PROGRESS-OLDER-START",
        "READY-OLD",
        "READY-NEW",
        "READY-DELIVERY-NEW",
        "READY-DELIVERY-OLD",
        "COMPLETED-NEW",
        "COMPLETED-OLD",
        "DELIVERED-NEW",
        "DELIVERED-OLD",
    ],
    "mobile worker queue must use actual start time and final order completion time"
);

const desktopQueueItems = [
    {
        name: "READY",
        doc: { status: "At CNC", department_status: "بحاجة للعمل" },
        flag: { assignment_state: "assigned", assignment_time: "2026-08-17 09:00:00" },
    },
    {
        name: "IN-PROGRESS",
        doc: { status: "At CNC", department_status: "قيد العمل" },
        flag: { assignment_state: "assigned", assignment_time: "2026-08-17 08:00:00" },
    },
    {
        name: "READY-DELIVERY",
        doc: { status: "Ready for Delivery", department_status: "مكتمل" },
        flag: { assignment_state: "completed", completion_time: "2026-08-17 12:00:00" },
    },
    {
        name: "COMPLETED",
        doc: { status: "Completed", department_status: "مكتمل" },
        flag: { assignment_state: "completed", completion_time: "2026-08-17 11:00:00" },
    },
    {
        name: "DELIVERED",
        doc: { status: "Delivered", department_status: "مكتمل", modified: "2026-08-17 16:00:00" },
        flag: { assignment_state: "completed", completion_time: "2026-08-17 13:00:00" },
    },
];
assert.deepStrictEqual(
    Array.from(api.sortDesktopQueueItems(desktopQueueItems), item => item.name),
    ["IN-PROGRESS", "READY", "DELIVERED", "READY-DELIVERY", "COMPLETED"],
    "desktop table must preserve the legacy three-group ordering with all completed assignments newest-first"
);
assert(source.includes('const mobileLayout = root.classList.contains("dco-order-card-layout")'));
assert(source.includes("? sortPersonalQueueItems(queueItems)"));
assert(source.includes(": sortDesktopQueueItems(queueItems);"));

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

assert.strictEqual(
    api.desktopDeliveryRowState({ status: "Ready for Delivery" }),
    "ready_for_delivery"
);
assert.strictEqual(api.desktopDeliveryRowState({ status: "Delivered" }), "delivered");
assert.strictEqual(api.desktopDeliveryRowState({ status: "At CNC" }), "");
assert.strictEqual(api.desktopDeliveryRowState({ status: "Completed" }), "");
assert.strictEqual(
    api.desktopDeliveryRowState({ current_department: "جاهز للتسليم" }),
    "ready_for_delivery"
);
assert.strictEqual(
    api.desktopDeliveryRowState({ current_department: "تم التسليم" }),
    "delivered"
);

function mockClassList(initial = []) {
    const classes = new Set(initial);
    return {
        contains: name => classes.has(name),
        add(...names) { names.forEach(name => classes.add(name)); },
        remove(...names) { names.forEach(name => classes.delete(name)); },
        toggle(name, force) {
            const shouldHave = force === undefined ? !classes.has(name) : Boolean(force);
            if (shouldHave) classes.add(name);
            else classes.delete(name);
            return shouldHave;
        },
    };
}

function mockRow(name, extraClasses = []) {
    return {
        classList: mockClassList(["list-row-container", ...extraClasses]),
        dataset: { name },
        querySelector(selector) {
            if (selector === "[data-name]") return { dataset: { name } };
            if (selector === "a[href*='/door-cutting-order/']") return null;
            if (selector === ".dco-mobile-order-card") return null;
            return null;
        },
    };
}

function mockListview(rows, { cardLayout = false } = {}) {
    const result = {
        querySelectorAll(selector) {
            return selector === ".list-row-container" ? rows : [];
        },
    };
    const root = {
        nodeType: 1,
        classList: mockClassList(cardLayout ? ["dco-order-list", "dco-order-card-layout"] : ["dco-order-list"]),
        querySelector(selector) {
            return selector === ".result" ? result : null;
        },
    };
    return {
        page: { wrapper: root },
        data: [
            { name: "DCO-READY", status: "Ready for Delivery" },
            { name: "DCO-DELIVERED", status: "Delivered" },
            { name: "DCO-PROD", status: "At CNC" },
        ],
        _root: root,
    };
}

const readyRow = mockRow("DCO-READY", ["dco-list-row-completed"]);
const deliveredRow = mockRow("DCO-DELIVERED");
const productionRow = mockRow("DCO-PROD");
const desktopList = mockListview([readyRow, deliveredRow, productionRow]);
api.applyDesktopDeliveryRowColors(desktopList);
assert(
    readyRow.classList.contains("dco-list-row-ready-for-delivery"),
    "desktop ready-for-delivery rows must use the light-green delivery class"
);
assert(
    !readyRow.classList.contains("dco-list-row-completed"),
    "desktop ready-for-delivery must not keep worker-completed green"
);
assert(
    deliveredRow.classList.contains("dco-list-row-delivered"),
    "desktop delivered rows must use the dark-green delivery class"
);
assert(!productionRow.classList.contains("dco-list-row-ready-for-delivery"));
assert(!productionRow.classList.contains("dco-list-row-delivered"));

readyRow.classList.add("dco-list-row-ready-for-delivery");
deliveredRow.classList.add("dco-list-row-delivered");
const mobileList = mockListview([readyRow, deliveredRow, productionRow], { cardLayout: true });
api.applyDesktopDeliveryRowColors(mobileList);
assert(
    !readyRow.classList.contains("dco-list-row-ready-for-delivery"),
    "mobile card layout must not receive desktop delivery row colors"
);
assert(
    !deliveredRow.classList.contains("dco-list-row-delivered"),
    "mobile card layout must not receive desktop delivered row colors"
);

const desktopCssSource = fs.readFileSync(
    "almdina_erp/public/css/door_cutting_order_responsive.css",
    "utf8"
);
assert(
    desktopCssSource.includes(".dco-order-list:not(.dco-order-card-layout) .list-row-container.dco-list-row-ready-for-delivery"),
    "ready-for-delivery green is a desktop table style"
);
assert(
    desktopCssSource.includes(".dco-order-list:not(.dco-order-card-layout) .list-row-container.dco-list-row-delivered"),
    "delivered dark green is a desktop table style"
);
assert(desktopCssSource.includes(".list-row-container.dco-list-row-ready-for-delivery .level-right"));
assert(desktopCssSource.includes(".list-row-container.dco-list-row-delivered .level-right"));
assert(desktopCssSource.includes("background: #ecfdf3 !important;"));
assert(desktopCssSource.includes("background: #a7f3d0 !important;"));
assert(desktopCssSource.includes("border-color: #16a34a !important;"));
assert(desktopCssSource.includes("border-color: #047857 !important;"));

assert(cssSource.includes(".dco-card-header-meta"));
assert(cssSource.includes(".dco-card-stage"));
assert(cssSource.includes("#2563eb"), "ready/start must use the agreed blue identity");
assert(cssSource.includes("#f59e0b"), "in-progress/finish must use the agreed orange identity");
assert(cssSource.includes("#7c3aed"), "ready-for-delivery/deliver must use the agreed purple identity");
assert(cssSource.includes("#16a34a"), "completed must use the agreed green identity");
assert(cssSource.includes("#047857"), "delivered must use the agreed dark-green identity");
assert(cssSource.includes(".is-ready-for-delivery"));
assert(cssSource.includes(".is-delivered"));
assert(cssSource.includes(".is-deliver"));
assert(!source.includes("frappe.get_roles"), "mobile list presentation must remain capability-driven, never role-name-driven");

const expectedStatusKeys = [
    "Draft",
    "Pending Review",
    "Approved",
    "At Sharyoun",
    "At Drawing",
    "At CNC",
    "At Sanding",
    "Ready for Delivery",
    "Delivered",
    "Completed",
    "Rejected",
    "On Hold",
    "Cancelled",
];
const statusConfig = api.statusFilterConfig();
assert.strictEqual(statusConfig.fieldtype, "Select");
assert.strictEqual(statusConfig.fieldname, "status");
assert.strictEqual(statusConfig.condition, "=");
assert.strictEqual(statusConfig.label, "Status");
const statusOptions = api.statusFilterOptions();
assert.strictEqual(statusOptions[0].value, "");
assert.strictEqual(statusOptions[0].label, "كل الحالات");
assert.deepStrictEqual([...statusOptions.slice(1)], expectedStatusKeys);
assert.strictEqual(statusConfig.options[0].value, "");
assert.strictEqual(statusConfig.options[0].label, "كل الحالات");
assert.deepStrictEqual([...statusConfig.options.slice(1)], expectedStatusKeys);
assert(!statusOptions.some(option => option === "Cutting In Progress" || option && option.value === "Cutting In Progress"));
assert(!Object.isFrozen(statusConfig), "Frappe mutates custom_filter_configs onchange");

const listSettings = context.frappe.listview_settings["Door Cutting Order"];
assert(Array.isArray(listSettings.custom_filter_configs));
assert.strictEqual(listSettings.custom_filter_configs[0].fieldname, "status");

function mockNode(className = "") {
    const node = {
        nodeType: 1,
        className,
        children: [],
        parentNode: null,
        nextSibling: null,
        classList: {
            contains(name) {
                return String(node.className || "").split(/\s+/).includes(name);
            },
            add(name) {
                const names = new Set(String(node.className || "").split(/\s+/).filter(Boolean));
                names.add(name);
                node.className = [...names].join(" ");
            },
            toggle(name, force) {
                const enabled = force === undefined ? !this.contains(name) : Boolean(force);
                if (enabled) this.add(name);
                else {
                    const names = new Set(String(node.className || "").split(/\s+/).filter(Boolean));
                    names.delete(name);
                    node.className = [...names].join(" ");
                }
                return enabled;
            },
        },
        getBoundingClientRect() {
            return { width: Number(context.window.innerWidth) };
        },
        querySelector(selector) {
            return findAll(node, selector)[0] || null;
        },
        querySelectorAll(selector) {
            return findAll(node, selector);
        },
        appendChild(child) {
            if (child.parentNode) child.parentNode.removeChild(child);
            child.parentNode = node;
            node.children.push(child);
            syncSiblings(node);
            return child;
        },
        insertBefore(child, ref) {
            if (child.parentNode) child.parentNode.removeChild(child);
            child.parentNode = node;
            const idx = ref ? node.children.indexOf(ref) : -1;
            if (idx < 0) node.children.push(child);
            else node.children.splice(idx, 0, child);
            syncSiblings(node);
            return child;
        },
        removeChild(child) {
            const idx = node.children.indexOf(child);
            if (idx >= 0) node.children.splice(idx, 1);
            child.parentNode = null;
            syncSiblings(node);
            return child;
        },
    };
    return node;
}

function syncSiblings(parent) {
    parent.children.forEach((child, index) => {
        child.nextSibling = parent.children[index + 1] || null;
    });
}

function findAll(node, selector) {
    const wanted = String(selector || "").replace(/^\./, "");
    const found = [];
    node.children.forEach(child => {
        if (child.classList.contains(wanted)) found.push(child);
        found.push(...findAll(child, selector));
    });
    return found;
}

context.document.createElement = function createElement() {
    return mockNode();
};

function setViewport(width, height) {
    context.window.innerWidth = width;
    context.window.screen.width = width;
    context.window.screen.height = height;
    context.document.documentElement.clientWidth = width;
}

const root = mockNode("dco-order-list");
const pageForm = mockNode("page-form");
const standardSection = mockNode("standard-filter-section flex");
const filterSection = mockNode("filter-section flex");
const filterSelector = mockNode("filter-selector");
const statusWrapper = mockNode("frappe-control");
root.appendChild(pageForm);
pageForm.appendChild(standardSection);
pageForm.appendChild(filterSection);
filterSection.appendChild(filterSelector);
standardSection.appendChild(statusWrapper);

const listview = {
    page: {
        wrapper: root,
        fields_dict: { status: { wrapper: statusWrapper } },
    },
};

function assertBesideFrappeFilter(message) {
    const slot = root.querySelector(".dco-status-filter-slot");
    assert(slot, message);
    assert.strictEqual(statusWrapper.parentNode, slot);
    assert.strictEqual(slot.parentNode, filterSection);
    assert.strictEqual(filterSelector.nextSibling, slot);
}

setViewport(390, 844);
assert.strictEqual(api.reconcileStatusFilterLayout(listview), true);
assertBesideFrappeFilter("card layout must place the status select beside Frappe's filter button");
assert.strictEqual(api.reconcileStatusFilterLayout(listview), true);
assert.strictEqual(
    root.querySelectorAll(".dco-status-filter-slot").length,
    1,
    "refresh must not duplicate the status filter slot"
);
assert.strictEqual(statusWrapper.parentNode, root.querySelector(".dco-status-filter-slot"));

setViewport(1440, 900);
assert.strictEqual(api.reconcileStatusFilterLayout(listview), true);
assertBesideFrappeFilter("desktop must also place the status select beside Frappe's filter button");
assert.strictEqual(standardSection.children.filter(child => child === statusWrapper).length, 0);

console.log("Door Cutting Order five-state mobile-card simulation passed");
