"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

function source(filename) {
    return fs.readFileSync(path.resolve(__dirname, "../../public/js", filename), "utf8");
}

(async () => {
    const invalidations = [];
    let uploaderOptions = null;
    let reloaded = 0;
    let printedPlan = null;

    const fakeWindow = {
        AlmdinaPermissions: {
            canDocument() {
                return true;
            },
            can() {
                return true;
            },
        },
        AlmdinaPlanWorkspaceState: {
            invalidate(frm, reason) {
                invalidations.push({ frm, reason });
                return true;
            },
        },
        AlmdinaCuttingPlanRender: {
            print(frm, plan) {
                printedPlan = plan;
            },
        },
    };

    const fakeFrappe = {
        almdina: {},
        provide() {
            this.almdina = this.almdina || {};
        },
        ui: {
            FileUploader: function FileUploader(options) {
                uploaderOptions = options;
                this.options = options;
            },
        },
        call() {
            return Promise.resolve({ message: { ok: true } });
        },
        show_alert() {},
        msgprint() {},
        utils: {
            escape_html(value) {
                return String(value);
            },
        },
    };

    const context = vm.createContext({
        window: fakeWindow,
        frappe: fakeFrappe,
        console,
        Promise,
        Object,
        Array,
        String,
        Number,
        Boolean,
        Map,
        Set,
        __: value => value,
    });

    vm.runInContext(
        source("door_cutting_order/cutting_plan/door_cutting_order_plan_tabs_ux.js"),
        context
    );
    vm.runInContext(
        source("door_cutting_order/cutting_plan/secure_dxf_upload.js"),
        context
    );

    const uploadedPlan = {
        sheets: [{
            sheet_no: 1,
            pieces: [{
                id: 1,
                piece_type: "Special",
                geometry: {
                    schema_version: 1,
                    unit: "mm",
                    coordinate_space: "usable_sheet",
                    outer: [[0, 0], [629, 0], [629, 300], [300, 300], [300, 629], [0, 629]],
                    holes: [],
                },
            }],
        }],
    };
    const systemPlan = {
        sheets: [{ sheet_no: 1, pieces: [{ id: 1, piece_type: "Special" }] }],
    };
    const frm = {
        doc: {
            name: "DCO-DXF",
            production_dxf: null,
            custom_plan_json: uploadedPlan,
            system_plan_json: systemPlan,
            cutting_plan_json: systemPlan,
            approved_plan: null,
        },
        fields_dict: {},
        is_new() {
            return false;
        },
        reload_doc() {
            reloaded += 1;
            return Promise.resolve();
        },
    };

    assert.equal(
        fakeWindow.AlmdinaPlanTabsUX.defaultTab(frm),
        "Custom",
        "an accepted uploaded DXF must be the first plan shown when no explicit tab is selected"
    );

    fakeWindow.AlmdinaPlanTabsUX.printActivePlan(frm);
    assert.equal(
        printedPlan,
        uploadedPlan,
        "printing from the default uploaded tab must use the geometry-bearing uploaded snapshot"
    );

    frm.__almdina_active_plan_tab = "System";
    assert.equal(
        fakeWindow.AlmdinaPlanTabsUX.defaultTab(frm),
        "System",
        "an explicit operator choice of System must remain respected within the current form session"
    );

    delete frm.__almdina_active_plan_tab;
    frm.doc.approved_plan = "PLAN-APPROVED";
    assert.equal(
        fakeWindow.AlmdinaPlanTabsUX.defaultTab(frm),
        "Approved",
        "an approved production snapshot remains higher priority than a draft uploaded DXF"
    );
    frm.doc.approved_plan = null;

    const uploader = fakeFrappe.almdina.upload_production_dxf(frm);
    assert.ok(uploaderOptions, "secure DXF uploader must be created");
    await uploader.options.on_success({ file_url: "/private/files/corrected.dxf" });

    assert.equal(frm.__almdina_active_plan_tab, "Custom");
    assert.equal(reloaded, 1, "the order must reload after the server accepts the DXF");
    assert.equal(invalidations.length, 1, "the previous plan workspace snapshot must be invalidated");
    assert.equal(invalidations[0].reason, "dxf_uploaded");

    console.log("Uploaded DXF plan activation simulation passed");
})().catch(error => {
    console.error(error);
    process.exitCode = 1;
});
