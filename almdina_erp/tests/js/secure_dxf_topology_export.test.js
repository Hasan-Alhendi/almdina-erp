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
        if (lastCallMethod.includes("normalize_dxf_for_autocad")) {
            const clientDxf = Buffer.from(String((opts.args && opts.args.content_b64) || ""), "base64").toString("utf8");
            if (process.env.LINER_DXF_OUT && clientDxf.includes("0\r\nLWPOLYLINE\r\n") && clientDxf.includes("8\r\nLiner\r\n")) {
                fs.writeFileSync(process.env.LINER_DXF_OUT, clientDxf);
            }
            if (
                process.env.SQUARE_LINER_DXF_OUT
                && opts.args
                && opts.args.order_name === "26-00105"
            ) {
                fs.writeFileSync(process.env.SQUARE_LINER_DXF_OUT, clientDxf);
            }
            return Promise.resolve({
                message: {
                    filename: "cutting_plan_DCO-TOPOLOGY_AutoCAD2011_2026.dxf",
                    content_b64: Buffer.from(
                        clientDxf.replace("AC1009", "AC1024").replace("AC1015", "AC1024"),
                        "utf8"
                    ).toString("base64"),
                },
            });
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
    btoa,
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
    assert.match(lastCallMethod, /normalize_dxf_for_autocad/);
    // Owner outer + owner hole + nested outer = 12 CUT_PATH LINE entities.
    assert.equal(cutPathLineCount(downloadedDxf), 12);
    // Top-left usable-sheet [0,0] becomes physical DXF [5,995] with 5 mm trim.
    assert.match(downloadedDxf, /10\r\n5\r\n20\r\n995\r\n/);
    // Hole geometry must survive into the emitted DXF rather than rectangle fallback.
    assert.match(downloadedDxf, /10\r\n25\r\n20\r\n975\r\n/);
    assert.match(downloadedName, /_AutoCAD2011_2026\.dxf$/);

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

    nextPlan.sheets[0].pieces[0].resource_kind = "OFFCUT";
    downloadedDxf = "";
    await fakeFrappe.almdina.export_order_dxf("DCO-OFFCUT", "system");
    assert.match(downloadedDxf, /8\r\nOFFCUT\r\n/);
    assert.equal((downloadedDxf.match(/8\r\nOFFCUT\r\n/g) || []).length, 4);

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
    assert.match(lastCallMethod, /normalize_dxf_for_autocad/);
    assert.match(downloadedDxf, /\$ACADVER\r\n1\r\nAC1024/);

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
                        label: "1.1",
                        piece_type: "Special",
                        extra_double: 1,
                        extra_full_door_double: 1,
                        x: 0,
                        y: 0,
                        w: 40,
                        h: 60,
                        geometry: geometry(
                            [[0, 0], [400, 0], [400, 600], [0, 600]]
                        ),
                        overlays: [
                            {
                                kind: "liner",
                                layer: "Liner",
                                geometry: geometry(
                                    [[40, 40], [180, 40], [180, 160], [40, 160]]
                                ),
                            },
                            {
                                kind: "back_groove",
                                layer: "Rear Groove",
                                geometry: {
                                    schema_version: 1,
                                    unit: "mm",
                                    coordinate_space: "usable_sheet",
                                    path: [[360, 40], [360, 560]],
                                    closed: false,
                                },
                            },
                        ],
                    },
                ],
            },
        ],
    };
    downloadedDxf = "";
    lastCallMethod = "";
    await fakeFrappe.almdina.export_order_dxf("DCO-EXTRA-OVERLAY", "system");
    assert.match(lastCallMethod, /normalize_dxf_for_autocad/);
    assert.match(downloadedDxf, /2\r\nLiner\r\n/);
    assert.match(downloadedDxf, /2\r\nRear Groove\r\n/);
    assert.equal((downloadedDxf.match(/8\r\nLiner\r\n/g) || []).length, 4);
    assert.equal((downloadedDxf.match(/8\r\nRear Groove\r\n/g) || []).length, 1);
    assert.equal(cutPathLineCount(downloadedDxf), 4);
    assert.match(downloadedDxf, /2\r\ntext\r\n/);
    assert.match(downloadedDxf, /0\r\nTEXT\r\n/);
    assert.match(downloadedDxf, /1\r\n1\r\n/);
    assert.equal((downloadedDxf.match(/0\r\nTEXT\r\n/g) || []).length, 3);
    assert.match(
        downloadedDxf,
        /1\r\n\\U\+062F\\U\+0628\\U\+0644 \\U\+0627\\U\+0644\\U\+0642\\U\+0634\\U\+0627\\U\+0637\r\n/
    );
    assert.match(
        downloadedDxf,
        /1\r\n\\U\+062F\\U\+0628\\U\+0644 \\U\+0643\\U\+0627\\U\+0645\\U\+0644\r\n/
    );
    assert.doesNotMatch(downloadedDxf, /Double Edge Banding/);
    assert.doesNotMatch(downloadedDxf, /Full Door Double/);
    assert.doesNotMatch(downloadedDxf, /1\r\nDouble\r\n/);

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
                    { id: 1, label: "1.1", x: 0, y: 0, w: 10, h: 10 },
                    { id: 2, label: "2.2", x: 20, y: 0, w: 10, h: 10 },
                    { id: 50, label: "50.1", x: 40, y: 0, w: 10, h: 10 },
                    { id: 51, label: "51.1", x: 60, y: 0, w: 10, h: 10 },
                ],
            },
        ],
    };
    downloadedDxf = "";
    await fakeFrappe.almdina.export_order_dxf("DCO-TEXT-NUMBERS", "system");
    assert.equal((downloadedDxf.match(/0\r\nTEXT\r\n/g) || []).length, 4);
    assert.match(downloadedDxf, /8\r\ntext\r\n/);
    assert.match(downloadedDxf, /1\r\n1\r\n/);
    assert.match(downloadedDxf, /1\r\n2\r\n/);
    assert.match(downloadedDxf, /1\r\n50\r\n/);
    assert.match(downloadedDxf, /1\r\n51\r\n/);

    const linerSource = fs.readFileSync(
        path.resolve(__dirname, "../../public/js/door_cutting_order/drawing/door_cutting_order_liner_geometry.js"),
        "utf8"
    );
    vm.runInContext(linerSource, context, { filename: "door_cutting_order_liner_geometry.js" });

    function linerVertices(dxf) {
        const entities = dxf.split("0\r\nLWPOLYLINE\r\n").filter(part => part.includes("8\r\nLiner\r\n"));
        assert.equal(entities.length, 1);
        const lines = entities[0].split("\r\n");
        let count = null;
        let flags = null;
        const points = [];
        for (let index = 0; index + 1 < lines.length; index += 2) {
            const code = lines[index];
            const value = lines[index + 1];
            if (code === "0") break;
            if (code === "90") count = Number(value);
            if (code === "70") flags = value;
            if (code === "10") {
                assert.equal(lines[index + 2], "20");
                points.push([Number(value), Number(lines[index + 3])]);
                index += 2;
            }
        }
        assert.equal(flags, "0");
        assert.equal(points.length, count);
        return points;
    }

    const orderForm = {
        is_new() { return false; },
        doc: {
            name: "26-00103",
            kerf_mm: 5,
            pieces: [{
                extra_liner: 1,
                liner_reference_side: "edge_width_top",
                liner_offset_cm: 0,
                liner_width_cm: 1.8,
                piece_type: "Regular",
                width_cm: 40,
                length_cm: 60,
            }],
        },
    };
    function linerPlan(kerf) {
        return {
            full_board_width_cm: 122,
            full_board_length_cm: 244,
            usable_board_width_cm: 121,
            usable_board_length_cm: 243,
            trim_cm: 0.5,
            ...kerf,
            sheets: [{
                sheet_no: 1,
                full_width_cm: 122,
                full_length_cm: 244,
                pieces: [{
                    id: 1,
                    label: "1.1",
                    piece_type: "Regular",
                    extra_liner: 1,
                    liner_reference_side: "edge_width_top",
                    liner_offset_cm: 0,
                    liner_width_cm: 1.8,
                    x: 5,
                    y: 5,
                    w: 40,
                    h: 60,
                    width_cm: 40,
                    length_cm: 60,
                    geometry: geometry([[50, 50], [450, 50], [450, 650], [50, 650]]),
                }],
            }],
        };
    }

    async function assertOpenLinerToolpath(plan, exportCall) {
        nextPlan = plan;
        downloadedDxf = "";
        await exportCall();
        const exported = linerVertices(downloadedDxf);
        assert.equal(exported.length, 8);
        const span = axis => Math.max(...exported.map(point => point[axis])) - Math.min(...exported.map(point => point[axis]));
        const spans = [span(0), span(1)].sort((left, right) => left - right);
        assert.equal(Math.round(spans[0] * 10) / 10, 13);
        assert.equal(Math.round(spans[1] * 10) / 10, 405);
        assert.match(downloadedDxf, /0\r\nLWPOLYLINE\r\n100\r\nAcDbEntity\r\n8\r\nLiner\r\n/);
        assert.match(downloadedDxf, /70\r\n0\r\n/);
    }

    const savedPlanExport = () => fakeFrappe.almdina.export_order_dxf("26-00103", "system");
    await assertOpenLinerToolpath(linerPlan({ kerf_cm: 0.5 }), savedPlanExport);
    await assertOpenLinerToolpath(linerPlan({ kerf_mm: 5 }), savedPlanExport);
    await assertOpenLinerToolpath(linerPlan({ kerf_mm: 5, kerf_cm: 0.5 }), savedPlanExport);

    const openOrderPlan = linerPlan({ kerf_cm: 0.5 });
    delete openOrderPlan.sheets[0].pieces[0].extra_liner;
    delete openOrderPlan.sheets[0].pieces[0].liner_reference_side;
    delete openOrderPlan.sheets[0].pieces[0].liner_offset_cm;
    delete openOrderPlan.sheets[0].pieces[0].liner_width_cm;
    await assertOpenLinerToolpath(
        openOrderPlan,
        () => fakeFrappe.almdina.export_validated_dxf(orderForm)
    );

    nextPlan = linerPlan({ kerf_mm: 5, kerf_cm: 0.3 });
    downloadedDxf = "";
    await assert.rejects(savedPlanExport(), /متعارضة/);
    assert.equal(downloadedDxf, "");

    nextPlan = linerPlan({});
    downloadedDxf = "";
    await assert.rejects(savedPlanExport(), /حدّد سماكة الشفرة/);
    assert.equal(downloadedDxf, "");

    nextPlan = {
        full_board_width_cm: 122,
        full_board_length_cm: 244,
        usable_board_width_cm: 121,
        usable_board_length_cm: 243,
        trim_cm: 0.5,
        kerf_mm: 5,
        kerf_cm: 0.5,
        sheets: [{
            sheet_no: 1,
            full_width_cm: 122,
            full_length_cm: 244,
            pieces: [{
                id: 1,
                label: "1",
                piece_type: "Regular",
                extra_liner: 1,
                liner_reference_side: "edge_long_right",
                liner_offset_cm: 10,
                liner_width_cm: 1.8,
                x: 0,
                y: 193,
                w: 50,
                h: 50,
                width_cm: 50,
                length_cm: 50,
                geometry: geometry([[0, 1930], [500, 1930], [500, 2430], [0, 2430]]),
            }],
        }],
    };
    downloadedDxf = "";
    await fakeFrappe.almdina.export_order_dxf("26-00105", "system");
    assert.match(downloadedDxf, /0\r\nLWPOLYLINE\r\n/);
    assert.match(downloadedDxf, /8\r\nLiner\r\n/);
    assert.match(downloadedDxf, /10\r\n402\.5\r\n20\r\n507\.5\r\n/);
    assert.match(downloadedDxf, /10\r\n389\.5\r\n20\r\n2\.5\r\n/);

    console.log("Secure DXF topology export simulation passed");
}

run().catch(error => {
    console.error(error);
    process.exitCode = 1;
});
