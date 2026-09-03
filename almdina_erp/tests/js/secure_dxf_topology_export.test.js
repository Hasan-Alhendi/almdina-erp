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
let originalUpload = null;
let lastCallMethod = "";
let downloadedDxf = "";
let downloadedName = "";

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
            click() {
                downloadedName = this.download;
            },
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
    call(opts) {
        lastCallMethod = String((opts && opts.method) || "");
        if (lastCallMethod.includes("download_uploaded_dxf")) {
            return Promise.resolve({ message: originalUpload });
        }
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
    Uint8Array,
    atob,
    Buffer,
    Blob: FakeBlob,
    URL: {
    createObjectURL(blob) {
        const part = blob.parts[0];
        if (part instanceof Uint8Array) {
            downloadedDxf = Buffer.from(part).toString("utf8");
        } else {
            downloadedDxf = blob.parts.join("");
        }
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
    downloadedName = "";
    lastCallMethod = "";
    await fakeFrappe.almdina.export_order_dxf("DCO-TOPOLOGY", "system");
    assert.ok(downloadedDxf);
    assert.match(lastCallMethod, /get_validated_dxf_plan/);
    // Owner outer + owner hole + nested outer = 12 CUT_PATH LINE entities.
    assert.equal(cutPathLineCount(downloadedDxf), 12);
    // Top-left usable-sheet [0,0] becomes physical DXF [5,995] with 5 mm trim.
    assert.match(downloadedDxf, /10\r\n5\r\n20\r\n995\r\n/);
    // Hole geometry must survive into the emitted DXF rather than rectangle fallback.
    assert.match(downloadedDxf, /10\r\n25\r\n20\r\n975\r\n/);
    assert.match(downloadedName, /_AutoCAD2020_R12\.dxf$/);

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
    lastCallMethod = "";
    await fakeFrappe.almdina.export_order_dxf("DCO-LEGACY", "system");
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
        fakeFrappe.almdina.export_order_dxf("DCO-MALFORMED", "system"),
        /DXF export failed its compatibility self-check/
    );
    assert.equal(downloadedDxf, "");

    const originalDxf = "0\nSECTION\n8\nalong\n8\nCUT_PATH\n0\nEOF\n";
    originalUpload = {
        filename: "cutting_plan_DCO-2026-00018_corrected.dxf",
        content_b64: Buffer.from(originalDxf, "utf8").toString("base64"),
    };
    downloadedDxf = "";
    downloadedName = "";
    lastCallMethod = "";
    await fakeFrappe.almdina.export_order_dxf("DCO-2026-00018", "custom");
    assert.match(lastCallMethod, /download_uploaded_dxf/);
    assert.equal(downloadedDxf, originalDxf);
    assert.equal(downloadedName, "cutting_plan_DCO-2026-00018_corrected.dxf");
    assert.doesNotMatch(downloadedDxf, /\$ACADVER\r\n1\r\nAC1009/);

    downloadedDxf = "";
    lastCallMethod = "";
    await fakeFrappe.almdina.export_order_dxf("DCO-APPROVED-UPLOAD", "approved", {
        hasOriginalFile: true,
    });
    assert.match(lastCallMethod, /download_uploaded_dxf/);
    assert.equal(downloadedDxf, originalDxf);

    downloadedDxf = "";
    lastCallMethod = "";
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
    await fakeFrappe.almdina.export_order_dxf("DCO-APPROVED-SYSTEM", "approved");
    assert.match(lastCallMethod, /get_validated_dxf_plan/);
    assert.match(downloadedDxf, /\$ACADVER\r\n1\r\nAC1009/);

    console.log("Secure DXF topology export simulation passed");
}

run().catch(error => {
    console.error(error);
    process.exitCode = 1;
});
