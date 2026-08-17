"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const source = fs.readFileSync(
    path.resolve(
        __dirname,
        "../../public/js/door_cutting_order/cutting_plan/door_cutting_order_plan_edit_session_ux.js"
    ),
    "utf8"
);

function loadModule({ allowed = true } = {}) {
    const fakeWindow = {
        AlmdinaPermissions: {
            canDocument(_frm, capability) {
                return allowed && capability === "edit_optimizer_settings";
            },
        },
        addEventListener() {},
        requestAnimationFrame() {},
    };
    const fakeFrappe = {
        ui: {
            form: {
                on() {},
            },
        },
    };

    const context = vm.createContext({
        window: fakeWindow,
        frappe: fakeFrappe,
        console,
        Object,
        Set,
        String,
        Number,
        Boolean,
        Promise,
    });
    vm.runInContext(source, context, {
        filename: "door_cutting_order_plan_edit_session_ux.js",
    });
    return fakeWindow.AlmdinaPlanEditSessionUX;
}

function form(overrides = {}) {
    return {
        doctype: "Door Cutting Order",
        is_new() {
            return false;
        },
        doc: {
            name: "DCO-2026-00005",
            docstatus: 0,
            approved_plan: null,
            revision_state: "Current",
            status: "At Drawing",
            production_path: "ROUTE-DRAWING",
            current_production_stage: null,
            ...overrides,
        },
    };
}

const authorized = loadModule({ allowed: true });
assert.equal(
    authorized.canEditPlanSettings(form()),
    true,
    "an authorized designer at At Drawing must see the plan edit action even when the form has no current_production_stage snapshot"
);

assert.equal(
    authorized.canEditPlanSettings(form({ status: "Completed" })),
    false,
    "a finished routed order must remain locked when there is no active stage"
);

assert.equal(
    authorized.canEditPlanSettings(form({ approved_plan: "CP-APPROVED-001" })),
    false,
    "an approved plan must remain locked"
);

const denied = loadModule({ allowed: false });
assert.equal(
    denied.canEditPlanSettings(form()),
    false,
    "At Drawing must not bypass edit_optimizer_settings"
);

console.log("plan edit session routed lifecycle simulation passed");
