"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const source = fs.readFileSync(
    path.resolve(__dirname, "../../public/js/door_cutting_order/core/door_cutting_order_permission_refresh_ux.js"),
    "utf8"
);

async function main() {
    const handlers = {};
    const listeners = {};
    const callbacks = [];
    let createAllowed = true;
    let isNew = true;
    let refreshFieldsCount = 0;
    const sharedDcoPermission = { read: 1, create: 1, write: 0 };
    const sharedPermissions = {
        doctype_perm: { "Door Cutting Order": [sharedDcoPermission] },
    };

    const window = {
        cur_frm: null,
        setTimeout(callback) {
            callbacks.push(callback);
            return callbacks.length;
        },
        addEventListener(name, callback) {
            listeners[name] = callback;
        },
    };
    const frappe = {
        ui: {
            form: {
                on(doctype, mapping) {
                    assert.equal(doctype, "Door Cutting Order");
                    Object.assign(handlers, mapping);
                },
            },
        },
        perm: sharedPermissions,
    };
    const context = vm.createContext({ window, frappe, Object, String, Number, Boolean, JSON, Date, Promise, console });
    vm.runInContext(source, context, { filename: "door_cutting_order_permission_refresh_ux.js" });

    const controlPrototype = {
        get_status() { return this.nativeStatus(); },
        refresh() { this.disp_status = this.get_status(); },
    };

    function control(fieldname, df, nativeStatus) {
        return Object.assign(Object.create(controlPrototype), {
            frm: null,
            df: { fieldname, permlevel: 0, fieldtype: "Data", ...df },
            disp_status: "None",
            nativeStatus,
        });
    }

    const customer = control("customer", { fieldtype: "Link" }, () => "None");
    const financial = control("total_cost_usd", { permlevel: 1 }, () => "Read");
    const conditionalReadonly = control(
        "customer_reference",
        { read_only_depends_on: "eval:doc.lock_customer_reference", read_only: 1 },
        () => "Read"
    );
    const customReadonly = control("custom_lock", {}, () => "Write");
    customReadonly.get_status = () => "Read";
    const explicitlyReadOnly = control("packing_method", { read_only: 1 }, () => "Read");
    const explicitlyHidden = control("legacy", { hidden: 1 }, () => "None");
    const frm = {
        doctype: "Door Cutting Order",
        doc: { name: "new-door-cutting-order-1" },
        perm: [{ read: 1, create: 1, write: 0 }, { read: 1, write: 0 }],
        fields_dict: {
            customer,
            financial,
            conditionalReadonly,
            customReadonly,
            explicitlyReadOnly,
            explicitlyHidden,
        },
        is_new: () => isNew,
        has_perm: permission => permission === "create" && createAllowed,
        refresh_fields() {
            refreshFieldsCount += 1;
            Object.values(this.fields_dict).forEach(field => field.refresh());
        },
    };
    Object.values(frm.fields_dict).forEach(field => { field.frm = frm; });
    window.cur_frm = frm;
    window.AlmdinaPermissions = {
        refresh: () => Promise.resolve(),
        snapshot: () => ({ capabilities: { create_order: createAllowed } }),
        canDocument: (candidate, capability) => (
            candidate === frm && capability === "create_order" && createAllowed
                && candidate.has_perm("create")
        ),
        can: () => false,
    };

    await window.AlmdinaOrderPermissionRefreshUX.refreshPermissions(frm, { force: true });
    assert.equal(customer.disp_status, "Write", "CREATE_ORDER should expose blank p0 NEW fields");
    assert.equal(financial.disp_status, "Read", "permlevel 1 cost fields stay read-only");
    assert.equal(
        conditionalReadonly.disp_status,
        "Read",
        "an active read_only_depends_on result remains authoritative"
    );
    assert.equal(customReadonly.disp_status, "Read", "custom instance get_status rules remain authoritative");
    assert.equal(explicitlyReadOnly.disp_status, "Read", "DocField read_only remains authoritative");
    assert.equal(explicitlyHidden.disp_status, "None", "hidden DocFields remain hidden");
    assert.equal(frm.has_perm("write"), false, "the form UI projection must not grant native write");
    assert.equal(frm.perm[0].write, 0, "frm permission rights must remain unmodified");
    assert.equal(sharedPermissions.doctype_perm["Door Cutting Order"][0].write, 0);
    assert.equal(refreshFieldsCount, 1);

    frm.perm[0].create = 0;
    await window.AlmdinaOrderPermissionRefreshUX.refreshPermissions(frm, { force: true });
    assert.equal(customer.disp_status, "None", "native Frappe create denial blocks field entry");
    frm.perm[0].create = 1;
    await window.AlmdinaOrderPermissionRefreshUX.refreshPermissions(frm, { force: true });
    assert.equal(customer.disp_status, "Write", "the active CREATE_ORDER form regains field entry");

    // Frappe evaluates read_only_depends_on into df.read_only before refreshing
    // the control. When the condition becomes false, normal CREATE_ORDER entry
    // affordance can apply again.
    conditionalReadonly.df.read_only = 0;
    conditionalReadonly.refresh();
    assert.equal(conditionalReadonly.disp_status, "Write");

    createAllowed = false;
    await window.AlmdinaOrderPermissionRefreshUX.refreshPermissions(frm, { force: true });
    assert.equal(customer.disp_status, "None", "revoked CREATE_ORDER removes field entry affordance");
    assert.equal(frm.__almdinaCreateOrderFieldEntry, false);

    createAllowed = true;
    isNew = false;
    await window.AlmdinaOrderPermissionRefreshUX.refreshPermissions(frm, { force: true });
    assert.equal(customer.disp_status, "None", "saved documents do not inherit create-form entry rights");
    assert.equal(frm.__almdinaCreateOrderFieldEntry, false);
    assert.equal(sharedDcoPermission.write, 0);

    console.log("dco_create_form_permissions: ok");
}

main().catch(error => {
    console.error(error);
    process.exitCode = 1;
});
