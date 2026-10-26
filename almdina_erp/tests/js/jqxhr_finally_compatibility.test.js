"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

const root = path.resolve(__dirname, "../..");

function functionSource(file, name) {
    const source = fs.readFileSync(path.join(root, file), "utf8");
    const start = source.indexOf(`function ${name}(`);
    assert.notEqual(start, -1, `${name} remains in its owning module`);
    const open = source.indexOf("{", start);
    let depth = 0;
    for (let index = open; index < source.length; index += 1) {
        if (source[index] === "{") depth += 1;
        if (source[index] === "}") depth -= 1;
        if (depth === 0) return source.slice(start, index + 1);
    }
    throw new Error(`Unclosed function ${name}`);
}

function jqXHR(promise) {
    return {
        then(onFulfilled, onRejected) {
            return jqXHR(promise.then(onFulfilled, onRejected));
        },
        catch(onRejected) {
            return jqXHR(promise.catch(onRejected));
        },
    };
}

async function main() {
    const roleListview = {
        data: [{ name: "DCO-1" }],
        _dcoRoleFlagGeneration: 0,
    };
    const payload = { personal_view: true, can_view_history: false, orders: {} };
    const roleCall = () => jqXHR(Promise.resolve({ message: payload }));
    const roleRequest = new Function(
        "window", "frappe", "METHODS", "roleFlagNames", "clearOperationalRoleRows",
        "applyOperationalRolePresentation", "applyDesktopDeliveryRowColors", "console",
        `return (${functionSource(
            "public/js/door_cutting_order/list_view/door_cutting_order_list.js",
            "requestOperationalRoleFlags",
        )})`,
    )(
        { frappe: { call: roleCall } },
        { call: roleCall },
        { roleFlags: "get_role_flags" },
        listview => listview.data.map(row => row.name),
        () => {},
        () => {},
        () => {},
        console,
    );
    const received = await Promise.resolve().then(() => roleRequest(roleListview));
    assert.deepEqual(received, payload);
    assert.equal(roleListview._dcoRoleFlagsPayload, payload);
    assert.equal(roleListview._dcoRoleFlagsPendingPromise, null);

    const rows = [{ name: "STAGE-1" }];
    const frm = { doc: { name: "DCO-1" } };
    const revertCall = () => jqXHR(Promise.resolve({ message: rows }));
    const ensureRevertTargets = new Function(
        "frappe", "revertTargetsKey", "canCheckRevertTargets", "capture", "isCurrent",
        `return (${functionSource(
            "public/js/door_cutting_order/production/shop_floor_order_ux.js",
            "ensureRevertTargets",
        )})`,
    )(
        { call: revertCall },
        () => "DCO-1::At CNC::route::STAGE-1",
        () => true,
        () => ({ identity: "DCO-1" }),
        () => true,
    );
    const result = await Promise.resolve().then(() => ensureRevertTargets(frm));
    assert.deepEqual(result, rows);
    assert.equal(frm.__almdinaRevertTargets, rows);
    assert.equal(frm.__almdinaRevertTargetsPromise, null);

    console.log("Frappe jqXHR cleanup compatibility passed");
}

main().catch(error => {
    console.error(error);
    process.exitCode = 1;
});
