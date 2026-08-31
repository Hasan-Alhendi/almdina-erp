"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const source = fs.readFileSync(
    path.resolve(__dirname, "../../public/js/door_cutting_order/cutting_plan/secure_dxf_export.js"),
    "utf8"
);

let nextPlan = null;
let downloadedDxf = "";

class FakeBlob {
    constructor(parts) {
        this.parts = parts;
    }
}

const fakeDocument = {
    documentElement: { lang: "en" },
    body: {
        appendChild() {},
        removeChild() {},
    },
    createElement() {
        return {
            href: "",
            download: "",
            click() {},
        };
    },
};

const fakeFrappe = {
    boot: { lang: "en" },
    almdina: {},
    ui: { form: { on() {} } },
    provide() {
        this.almdina = this.almdina || {};
    },
    call() {
        return Promise.resolve({ message: { plan: nextPlan } });
    },
    show_alert() {},
    throw(message) {
        throw new Error(message);
    },
};

const fakeWindow = {
    frappe: fakeFrappe,
    AlmdinaPermissions: {
        can() { return true; },
        canDocument() { return true; },
    },
};

const context = vm.createContext({
    window: fakeWindow,
    frappe: fakeFrappe,
    document: fakeDocument,
    console,
    JSON,
    Number,
    String,
    Math,
    Object,
    Array,
    Error,
    Promise,
    Blob: FakeBlob,
    URL: {
        createObjectURL(blob) {
            downloadedDxf = blob.parts.join("");
            return "blob:test";
        },
        revokeObjectURL() {},
    },
    setTimeout(callback) {
        callback();
        return 1;
    },
    MutationObserver: class {
        observe() {}
    },
    __: value => value,
    $: () => ({
        find() { return this; },
        filter() { return this; },
        each() { return this; },
        closest() { return { length: 0 }; },
        hasClass() { return false; },
        text() { return ""; },
        remove() {},
    }),
});

vm.runInContext(source, context, { filename: "secure_dxf_export.js" });

function geometry(outer, holes = []) {
    return {
        schema_version: 1,
        unit: "mm",
        coordinate_space: "usable_sheet",
        outer,
        holes,
    };
}

function cutPathLineCount(dxf) {
    return (dxf.match(/8\r\nCUT_PATH\r\n/g) || []).length;
}

async function run() {
    nextPlan = {
        full_board_width_cm: 100,
        full_board_length_cm: 100,
        usable_board_width_cm: 99,
        usable_board_length_cm: 99,
        trim_cm: 0.5,
        sheets: [
            {
                sheet_no: 1,
                full_width_cm: 100,
                full_length_cm: 100,
                pieces: [
                    {
                        id: 1,
                        label: "1.1",
                        x: 0,
                        y: 0,
                        w: 10,
                        h: 10,
                        geometry: geometry(
                            [[0, 0], [100, 0], [100, 100], [0, 100]],
                            [[[20, 20], [80, 20], [80, 80], [20, 80]]]
                        ),
                    },
                    {
                        id: 2,
                        label: "2.1",
                        x: 3,
                        y: 3,
                        w: 2,
                        h: 2,
                        geometry: geometry(
                            [[30, 30], [50, 30], [50, 50], [30, 50]]
                        ),
                    },
                ],
            },
        ],
    };

    downloadedDxf = "";
    await fakeFrappe.almdina.export_order_dxf("DCO-TOPOLOGY", "custom");
    assert.ok(downloadedDxf);
    // Owner outer + owner hole + nested outer = 12 CUT_PATH LINE entities.
    assert.equal(cutPathLineCount(downloadedDxf), 12);
    // Top-left usable-sheet [0,0] becomes physical DXF [5,995] with 5 mm trim.
    assert.match(downloadedDxf, /10\r\n5\r\n20\r\n995\r\n/);
    // Hole geometry must survive into the emitted DXF rather than rectangle fallback.
    assert.match(downloadedDxf, /10\r\n25\r\n20\r\n975\r\n/);

    nextPlan = {
        full_board_width_cm: 100,
        full_board_length_cm: 100,
        trim_cm: 0,
        sheets: [
            {
                sheet_no: 1,
                full_width_cm: 100,
                full_length_cm: 100,
                pieces: [{ id: 1, x: 1, y: 1, w: 10, h: 10 }],
            },
        ],
    };
    downloadedDxf = "";
    await fakeFrappe.almdina.export_order_dxf("DCO-LEGACY", "custom");
    assert.equal(cutPathLineCount(downloadedDxf), 4);

    nextPlan = {
        full_board_width_cm: 100,
        full_board_length_cm: 100,
        trim_cm: 0,
        sheets: [
            {
                sheet_no: 1,
                full_width_cm: 100,
                full_length_cm: 100,
                pieces: [
                    {
                        id: 1,
                        x: 0,
                        y: 0,
                        w: 10,
                        h: 10,
                        geometry: {
                            schema_version: 1,
                            unit: "mm",
                            coordinate_space: "usable_sheet",
                            outer: [[0, 0], [100, 0], [100, 100], [0, 100]],
                            holes: "invalid",
                        },
                    },
                ],
            },
        ],
    };
    downloadedDxf = "";
    await assert.rejects(
        fakeFrappe.almdina.export_order_dxf("DCO-MALFORMED", "custom"),
        /DXF export failed its compatibility self-check/
    );
    assert.equal(downloadedDxf, "");

    console.log("Secure DXF topology export simulation passed");
}

run().catch(error => {
    console.error(error);
    process.exitCode = 1;
});
