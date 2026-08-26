"use strict";

const assert = require("node:assert/strict");

global.window = global;
global.__ = value => value;
global.frappe = {
    utils: {
        escape_html(value) {
            return String(value)
                .replaceAll("&", "&amp;")
                .replaceAll("<", "&lt;")
                .replaceAll(">", "&gt;")
                .replaceAll('"', "&quot;");
        },
    },
};
window.AlmdinaShopFloorInboxViewModel = {
    quickActionContext(row) {
        return row;
    },
};
window.AlmdinaShopFloorQuickActions = {
    actionFor() {
        return null;
    },
};

require("../../public/js/shop_floor_inbox/renderer.js");
const renderer = window.AlmdinaShopFloorInboxRenderer;

function shell() {
    let html = "";
    return {
        target: {
            $content: {
                html(value) {
                    html = String(value);
                },
            },
        },
        html: () => html,
    };
}

const assigned = [{
    name: "stage-active",
    door_cutting_order: "DCO-1",
    status: "Pending",
    stage_type: "Cutting",
    department_label: "القص",
    customer: "عميل",
}];
const completed = [{
    name: "stage-completed",
    door_cutting_order: "DCO-2",
    status: "Completed",
    stage_type: "Cutting",
    department_label: "القص",
    customer: "عميل",
}];

const denied = shell();
renderer.renderList(denied.target, {
    assigned,
    completed: [],
    canViewHistory: false,
});
assert.match(denied.html(), /طلباتك التشغيلية/);
assert.doesNotMatch(denied.html(), /الطلبات المنتهية/);
assert.doesNotMatch(denied.html(), />منتهية</);
assert.doesNotMatch(denied.html(), /راجع ما أنهيته/);

const allowed = shell();
renderer.renderList(allowed.target, {
    assigned,
    completed,
    canViewHistory: true,
});
assert.match(allowed.html(), /الطلبات المنتهية/);
assert.match(allowed.html(), />منتهية</);
assert.match(allowed.html(), /راجع ما أنهيته/);

console.log("shop_floor history renderer simulation: ok");
