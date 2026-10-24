"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const source = fs.readFileSync(
    path.resolve(__dirname, "../../public/js/door_cutting_order/cutting_plan/secure_dxf_export.js"),
    "utf8"
);
const nestedGlassRegressionSnapshot = JSON.parse(fs.readFileSync(
    path.resolve(__dirname, "../fixtures/liner_extension_nested_glass_snapshot.json"),
    "utf8"
));

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
            if (
                process.env.LINER_DXF_OUT
                && opts.args
                && opts.args.order_name === "26-00105"
                && clientDxf.includes("0\r\nLWPOLYLINE\r\n")
                && clientDxf.includes("8\r\nLiner\r\n")
            ) {
                fs.writeFileSync(process.env.LINER_DXF_OUT, clientDxf);
            }
            if (
                process.env.SQUARE_LINER_DXF_OUT
                && opts.args
                && opts.args.order_name === "26-00105"
            ) {
                fs.writeFileSync(process.env.SQUARE_LINER_DXF_OUT, clientDxf);
            }
            if (
                process.env.L_NOTCH_DXF_OUT
                && opts.args
                && opts.args.order_name === "26-L-NOTCH"
            ) {
                fs.writeFileSync(process.env.L_NOTCH_DXF_OUT, clientDxf);
            }
            if (
                process.env.SAW_CENTER_DXF_OUT
                && opts.args
                && opts.args.order_name === "26-SAW-CENTER"
            ) {
                fs.writeFileSync(process.env.SAW_CENTER_DXF_OUT, clientDxf);
            }
            if (
                process.env.FULL_BOARD_DXF_OUT
                && opts.args
                && opts.args.order_name === "26-FULL-BOARD"
            ) {
                fs.writeFileSync(process.env.FULL_BOARD_DXF_OUT, clientDxf);
            }
            if (
                process.env.TRIM_GAPS_DXF_OUT
                && opts.args
                && opts.args.order_name === "26-TRIM-GAPS"
            ) {
                fs.writeFileSync(process.env.TRIM_GAPS_DXF_OUT, clientDxf);
            }
            if (
                process.env.KERF3_DXF_OUT
                && opts.args
                && opts.args.order_name === "26-KERF3-TRIM"
            ) {
                fs.writeFileSync(process.env.KERF3_DXF_OUT, clientDxf);
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
        const source = String((opts.args && opts.args.plan_source) || "").toLowerCase();
        const explicit = nextPlan && Object.prototype.hasOwnProperty.call(nextPlan, "include_saw_centers")
            ? Boolean(nextPlan.include_saw_centers)
            : null;
        return Promise.resolve({
            message: {
                plan: nextPlan,
                include_saw_centers: explicit === null ? source === "approved" : explicit,
            },
        });
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
    Set,
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
    // Standalone DXF simulations do not load Frappe dictionaries, but
    // identity-language translation must still interpolate {0}, {1}, etc.
    __: (message, values) => {
        let output = String(message);
        if (Array.isArray(values)) {
            values.forEach((value, index) => {
                output = output.split("{" + index + "}").join(String(value));
            });
        }
        return output;
    },
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
for (const relativePath of [
    "../../public/js/door_cutting_order/drawing/door_cutting_order_liner_geometry.js",
    "../../public/js/door_cutting_order/drawing/door_cutting_order_machining_overlay.js",
    "../../public/js/door_cutting_order/drawing/door_cutting_order_clipped_corner_ux.js",
]) {
    vm.runInContext(
        fs.readFileSync(path.resolve(__dirname, relativePath), "utf8"),
        context,
        { filename: relativePath }
    );
}
fakeWindow.AlmdinaMultiEdgeBanding = {
    calculate() {
        return { sides: {} };
    },
    thicknessForType() {
        return 1;
    },
};

function geometry(outer, holes = []) {
    return {
        schema_version: 1,
        unit: "mm",
        coordinate_space: "usable_sheet",
        outer,
        holes,
    };
}

function cutPathEntityCount(dxf) {
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
    await fakeFrappe.almdina.export_order_dxf("DCO-TOPOLOGY", "approved");
    assert.ok(downloadedDxf);
    assert.match(lastCallMethod, /normalize_dxf_for_autocad/);
    // Owner outer + owner hole + nested outer = three independent contours.
    assert.equal(cutPathEntityCount(downloadedDxf), 3);
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
    await fakeFrappe.almdina.export_order_dxf("DCO-LEGACY", "approved");
    assert.equal(cutPathEntityCount(downloadedDxf), 1);

    nextPlan = {
        full_board_width_cm: 100,
        full_board_length_cm: 100,
        trim_cm: 0,
        sheets: [{
            sheet_no: 1,
            full_width_cm: 100,
            full_length_cm: 100,
            pieces: [{
                id: 1,
                x: 1,
                y: 1,
                w: 52.1,
                h: 72.5,
                piece_type: "Glass",
                glass_hole_local_mm: [[65, 65], [456, 65], [456, 660], [65, 660]],
            }],
        }],
    };
    downloadedDxf = "";
    await fakeFrappe.almdina.export_order_dxf("DCO-GLASS", "approved");
    assert.equal(cutPathEntityCount(downloadedDxf), 2);
    assert.match(downloadedDxf, /10\r\n75\r\n20\r\n925\r\n/);
    assert.match(downloadedDxf, /10\r\n466\r\n20\r\n330\r\n/);

    nextPlan = {
        full_board_width_cm: 200,
        full_board_length_cm: 100,
        trim_cm: 0,
        kerf_cm: 0,
        sheets: [{
            sheet_no: 1,
            full_width_cm: 200,
            full_length_cm: 100,
            pieces: [0, 1].map(index => ({
                id: index + 1,
                x: 1 + index * 60,
                y: 1,
                w: 52.1,
                h: 72.5,
                piece_type: "Glass",
                piece_instance_id: `door-8:${index + 1}`,
                glass_margin_mm: 65,
                glass_hole_local_mm: [[65, 65], [456, 65], [456, 660], [65, 660]],
            })),
        }],
    };
    downloadedDxf = "";
    await fakeFrappe.almdina.export_order_dxf("DCO-GLASS-TWO", "approved");
    assert.equal(cutPathEntityCount(downloadedDxf), 4);

    nextPlan = {
        full_board_width_cm: 100,
        full_board_length_cm: 100,
        trim_cm: 0,
        kerf_cm: 0,
        sheets: [{
            sheet_no: 1,
            full_width_cm: 100,
            full_length_cm: 100,
            pieces: [
                {
                    id: 1,
                    label: "1.1",
                    source_piece_no: 1,
                    x: 0,
                    y: 0,
                    w: 40,
                    h: 40,
                    piece_type: "Glass",
                    glass_margin_mm: 50,
                    glass_hole_local_mm: [[50, 50], [350, 50], [350, 350], [50, 350]],
                },
                {
                    id: 2,
                    label: "2.1",
                    source_piece_no: 2,
                    x: 6,
                    y: 6,
                    w: 10,
                    h: 10,
                    piece_type: "Regular",
                    glass_host_piece_id: 1,
                },
                {
                    id: 3,
                    label: "3.1",
                    source_piece_no: 3,
                    x: 17,
                    y: 6,
                    w: 8,
                    h: 8,
                    piece_type: "Regular",
                    glass_host_piece_id: 1,
                },
                {
                    id: 4,
                    label: "4.1",
                    source_piece_no: 4,
                    x: 6,
                    y: 17,
                    w: 7,
                    h: 7,
                    piece_type: "Regular",
                    glass_host_piece_id: 1,
                },
            ],
        }],
    };
    downloadedDxf = "";
    await fakeFrappe.almdina.export_order_dxf("DCO-GLASS-THREE-NESTED", "approved");
    // Finished GEOMETRY and CUT_PATH keep every owned ring independently.
    // Glass outer + opening + three guest rectangles = 20 GEOMETRY LINE entities.
    assert.equal((downloadedDxf.match(/8\r\nGEOMETRY\r\n/g) || []).length, 20);
    assert.ok(cutPathEntityCount(downloadedDxf) >= 5);
    assert.match(downloadedDxf, /10\r\n0\r\n20\r\n1000\r\n/);
    assert.match(downloadedDxf, /10\r\n50\r\n20\r\n950\r\n/);
    assert.match(downloadedDxf, /10\r\n60\r\n20\r\n840\r\n/);
    assert.match(downloadedDxf, /10\r\n170\r\n20\r\n860\r\n/);
    assert.match(downloadedDxf, /10\r\n60\r\n20\r\n760\r\n/);

    nextPlan = {
        full_board_width_cm: 100,
        full_board_length_cm: 100,
        trim_cm: 0,
        kerf_cm: 0,
        sheets: [{
            sheet_no: 1,
            full_width_cm: 100,
            full_length_cm: 100,
            pieces: [
                {
                    id: 1,
                    label: "1.1",
                    source_piece_no: 1,
                    x: 0,
                    y: 0,
                    w: 50,
                    h: 50,
                    piece_type: "Glass",
                    glass_margin_mm: 50,
                    glass_hole_local_mm: [[50, 50], [450, 50], [450, 450], [50, 450]],
                },
                {
                    id: 2,
                    label: "2.1",
                    source_piece_no: 2,
                    x: 6,
                    y: 6,
                    w: 30,
                    h: 30,
                    piece_type: "Glass",
                    glass_margin_mm: 50,
                    glass_hole_local_mm: [[50, 50], [250, 50], [250, 250], [50, 250]],
                    glass_host_piece_id: 1,
                },
                {
                    id: 3,
                    label: "3.1",
                    source_piece_no: 3,
                    x: 12,
                    y: 12,
                    w: 10,
                    h: 10,
                    piece_type: "Regular",
                    glass_host_piece_id: 2,
                },
            ],
        }],
    };
    downloadedDxf = "";
    await fakeFrappe.almdina.export_order_dxf("DCO-GLASS-IN-GLASS", "approved");
    // Outer glass + hole + inner glass + hole + regular = 20 GEOMETRY LINE entities.
    assert.equal((downloadedDxf.match(/8\r\nGEOMETRY\r\n/g) || []).length, 20);
    assert.ok(cutPathEntityCount(downloadedDxf) >= 5);
    // Board Y is flipped: piece (x,y,h) → DXF (x*10, board_h - (y+h)*10).
    assert.match(downloadedDxf, /10\r\n0\r\n20\r\n1000\r\n/);
    assert.match(downloadedDxf, /10\r\n50\r\n20\r\n950\r\n/);
    assert.match(downloadedDxf, /10\r\n60\r\n20\r\n640\r\n/);
    assert.match(downloadedDxf, /10\r\n110\r\n20\r\n690\r\n/);
    assert.match(downloadedDxf, /10\r\n120\r\n20\r\n780\r\n/);

    nextPlan = {
        full_board_width_cm: 100,
        full_board_length_cm: 100,
        trim_cm: 0,
        sheets: [{
            sheet_no: 1,
            full_width_cm: 100,
            full_length_cm: 100,
            pieces: [{
                id: 1,
                x: 1,
                y: 1,
                w: 52.1,
                h: 72.5,
                piece_type: "Glass",
            }],
        }],
    };
    downloadedDxf = "";
    await fakeFrappe.almdina.export_order_dxf("DCO-GLASS-HISTORICAL", "approved");
    assert.equal(cutPathEntityCount(downloadedDxf), 1);

    nextPlan = {
        full_board_width_cm: 100,
        full_board_length_cm: 100,
        trim_cm: 0,
        sheets: [{
            sheet_no: 1,
            full_width_cm: 100,
            full_length_cm: 100,
            pieces: [{
                id: 1,
                x: 1,
                y: 1,
                w: 52.1,
                h: 72.5,
                piece_type: "Glass",
                glass_margin_mm: 65,
            }],
        }],
    };
    downloadedDxf = "";
    await assert.rejects(
        fakeFrappe.almdina.export_order_dxf("DCO-GLASS-MISSING", "system"),
        /The Glass opening is missing from this cutting plan/
    );
    assert.equal(downloadedDxf, "");

    nextPlan = {
        full_board_width_cm: 100,
        full_board_length_cm: 100,
        trim_cm: 0,
        sheets: [{
            sheet_no: 1,
            full_width_cm: 100,
            full_length_cm: 100,
            pieces: [{ id: 1, x: 1, y: 1, w: 10, h: 10, resource_kind: "OFFCUT" }],
        }],
    };
    downloadedDxf = "";
    await fakeFrappe.almdina.export_order_dxf("DCO-OFFCUT", "approved");
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
    await fakeFrappe.almdina.export_order_dxf("DCO-EXTRA-OVERLAY", "approved");
    assert.match(lastCallMethod, /normalize_dxf_for_autocad/);
    assert.match(downloadedDxf, /2\r\nLiner\r\n/);
    assert.match(downloadedDxf, /2\r\nRear Groove\r\n/);
    assert.equal((downloadedDxf.match(/8\r\nLiner\r\n/g) || []).length, 4);
    assert.equal((downloadedDxf.match(/8\r\nRear Groove\r\n/g) || []).length, 1);
    // The door is flush to the board on the left and the top, so those edges are not cuts.
    assert.equal(cutPathEntityCount(downloadedDxf), 2);
    assert.match(downloadedDxf, /2\r\nTEXT\r\n/);
    assert.match(downloadedDxf, /2\r\nGEOMETRY\r\n/);
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
    assert.doesNotMatch(downloadedDxf, /Double Edge/);
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
    assert.match(downloadedDxf, /8\r\nTEXT\r\n/);
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
    await assert.rejects(savedPlanExport(), /Saw blade thickness conflict/);
    assert.equal(downloadedDxf, "");

    nextPlan = linerPlan({});
    downloadedDxf = "";
    await assert.rejects(savedPlanExport(), /Specify a saw blade thickness/);
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

    function cutPathLengths(dxf) {
        const lines = dxf.split("\r\n");
        const lengths = [];
        for (let index = 0; index < lines.length - 12; index += 1) {
            if (lines[index] !== "LINE" || lines[index + 2] !== "GEOMETRY") continue;
            const x1 = Number(lines[index + 4]);
            const y1 = Number(lines[index + 6]);
            const x2 = Number(lines[index + 10]);
            const y2 = Number(lines[index + 12]);
            lengths.push(Math.round(Math.hypot(x2 - x1, y2 - y1) * 1000) / 1000);
        }
        return lengths;
    }

    const lOrder = {
        is_new() { return false; },
        doc: {
            name: "26-L-NOTCH",
            default_edge_type: "band-1",
            pieces: [{
                piece_instance_id: "l-1",
                piece_type: "L-Shaped Corner",
                width_cm: 40,
                length_cm: 40,
                cut_width_cm: 40,
                cut_length_cm: 40,
                qty: 1,
                allow_rotation: 0,
                clipped_corner_position: "Top Right",
                clipped_corner_width_cm: 20,
                clipped_corner_length_cm: 30,
                edge_break: 1,
                extra_liner: 1,
                liner_reference_side: "edge_break",
                liner_offset_cm: 2,
                liner_width_cm: 1.5,
                liner_start_cm: 0,
                liner_length_cm: 0,
            }],
        },
    };
    nextPlan = {
        full_board_width_cm: 122,
        full_board_length_cm: 244,
        kerf_mm: 3,
        trim_cm: 0.5,
        sheets: [{
            sheet_no: 1,
            full_width_cm: 122,
            full_length_cm: 244,
            pieces: [{
                id: 1,
                label: "1.1",
                piece_type: "L-Shaped Corner",
                clipped_corner_position: "Top Right",
                clipped_corner_width_cm: 20,
                clipped_corner_length_cm: 30,
                x: 0,
                y: 0,
                w: 40,
                h: 40,
                extra_liner: 1,
                liner_reference_side: "edge_break",
                liner_offset_cm: 2,
                liner_width_cm: 1.5,
            }],
        }],
    };
    downloadedDxf = "";
    await fakeFrappe.almdina.export_validated_dxf(lOrder);
    let lengths = cutPathLengths(downloadedDxf);
    assert.ok(lengths.includes(199), lengths.join(","));
    assert.ok(lengths.includes(99), lengths.join(","));
    assert.equal(lengths.includes(200), false);
    assert.equal(lengths.includes(100), false);
    downloadedDxf = "";
    await fakeFrappe.almdina.export_validated_dxf(lOrder);
    lengths = cutPathLengths(downloadedDxf);
    assert.ok(lengths.includes(199));
    assert.ok(lengths.includes(99));
    assert.equal(lengths.includes(200), false);

    nextPlan = {
        full_board_width_cm: 122,
        full_board_length_cm: 244,
        kerf_mm: 5,
        trim_cm: 1,
        sheets: [{
            sheet_no: 1,
            full_width_cm: 122,
            full_length_cm: 244,
            pieces: [
                {
                    id: 1,
                    label: "1.1",
                    piece_type: "Regular",
                    x: 0,
                    y: 0,
                    w: 20,
                    h: 50,
                    width_cm: 20,
                    length_cm: 50,
                    extra_liner: 1,
                    liner_reference_side: "edge_long_left",
                    liner_offset_cm: 2,
                    liner_width_cm: 1.8,
                    liner_start_cm: 0,
                    liner_length_cm: 0,
                },
                {
                    id: 2,
                    label: "2.1",
                    piece_type: "Regular",
                    x: 20.5,
                    y: 0,
                    w: 30,
                    h: 40,
                    width_cm: 30,
                    length_cm: 40,
                },
            ],
        }],
    };
    downloadedDxf = "";
    await fakeFrappe.almdina.export_order_dxf("26-SAW-CENTER", "approved");
    const sawLines = layerEdges(downloadedDxf, "CUT_PATH");
    const finishedLines = layerLines(downloadedDxf, "GEOMETRY");
    assert.ok(finishedLines.some(edge => edge.x1 === 10 && edge.x2 === 210));
    assert.ok(finishedLines.some(edge => edge.x1 === 215 && edge.x2 === 515));
    const shared = sawLines.filter(edge => Math.abs(edge.x1 - 212.5) < 0.02 && Math.abs(edge.x2 - 212.5) < 0.02);
    // Multi Offset keeps the coincident side in each door's closed contour.
    assert.equal(shared.length, 2);
    assert.ok(Math.abs(Math.min(shared[0].y1, shared[0].y2) - 1927.5) < 0.02);
    assert.ok(Math.abs(Math.max(shared[0].y1, shared[0].y2) - 2432.5) < 0.02);
    const trimCenters = sawLines.filter(edge => Math.abs(edge.x1 - 7.5) < 0.02 && Math.abs(edge.x2 - 7.5) < 0.02);
    assert.equal(trimCenters.length, 1);
    assert.equal(sawLines.some(edge => Math.abs(edge.x1 - 5) < 0.02 && Math.abs(edge.x2 - 5) < 0.02), false);
    const linerPoints = polylinePoints(downloadedDxf, "Liner");
    const linerYs = linerPoints.map(point => point[1]);
    assert.ok(Math.min(...linerYs) <= 1927.5 + 0.05);
    assert.ok(Math.max(...linerYs) >= 2432.5 - 0.05);
    assert.match(downloadedDxf, /8\r\nSHEET_OUTLINE\r\n/);
    assert.match(downloadedDxf, /8\r\nTEXT\r\n/);
    assert.doesNotMatch(downloadedDxf, /8\r\n0\r\n/);

    function linerDoor(fields) {
        return Object.assign({
            id: 1,
            label: "1.1",
            piece_type: "Regular",
            extra_liner: 1,
            liner_reference_side: "edge_width_top",
            liner_offset_cm: 0,
            liner_width_cm: 1.8,
            x: 0,
            y: 0,
            w: 40,
            h: 50,
            width_cm: 40,
            length_cm: 50,
        }, fields);
    }
    function linerEndPlan(pieces, trimCm) {
        const trim = trimCm || 0;
        return {
            full_board_width_cm: 122,
            full_board_length_cm: 244,
            usable_board_width_cm: 122 - (trim * 2),
            usable_board_length_cm: 244 - (trim * 2),
            applied_trim_width_cm: trim,
            applied_trim_length_cm: trim,
            trim_cm: trim,
            kerf_mm: 5,
            kerf_cm: 0.5,
            sheets: [{
                sheet_no: 1,
                full_width_cm: 122,
                full_length_cm: 244,
                applied_trim_width_cm: trim,
                applied_trim_length_cm: trim,
                pieces,
            }],
        };
    }
    nextPlan = linerEndPlan([linerDoor({ w: 122, width_cm: 122 })]);
    downloadedDxf = "";
    await fakeFrappe.almdina.export_order_dxf("26-LINER-ENDS", "approved");
    const boardEdgeXs = polylinePoints(downloadedDxf, "Liner").map(point => point[0]);
    assert.equal(Math.round(Math.min(...boardEdgeXs) * 10) / 10, -2.5);
    assert.equal(Math.round(Math.max(...boardEdgeXs) * 10) / 10, 1222.5);
    assert.equal(constantAxisRuns(polylinePoints(downloadedDxf, "Liner"), 0, 10), 2);
    const shortDoorCuts = layerEdges(downloadedDxf, "CUT_PATH");
    assert.equal(shortDoorCuts.length, 1);
    assert.ok(shortDoorCuts.every(edge => Math.abs(edge.y1 - 1937.5) < 0.02 && Math.abs(edge.y2 - 1937.5) < 0.02));

    nextPlan = linerEndPlan([linerDoor({
        w: 122,
        h: 244,
        width_cm: 122,
        length_cm: 244,
    })]);
    downloadedDxf = "";
    await fakeFrappe.almdina.export_order_dxf("26-FULL-BOARD", "approved");
    assert.equal(layerEdges(downloadedDxf, "CUT_PATH").length, 0);
    assert.ok(layerLines(downloadedDxf, "GEOMETRY").some(edge => (
        Math.abs(edge.x1) < 0.02 && Math.abs(edge.x2 - 1220) < 0.02
        && Math.abs(edge.y1) < 0.02 && Math.abs(edge.y2) < 0.02
    )));
    assert.ok(layerLines(downloadedDxf, "SHEET_OUTLINE").some(edge => (
        Math.abs(edge.x1) < 0.02 && Math.abs(edge.x2 - 1220) < 0.02
    )));
    const fullLiner = polylinePoints(downloadedDxf, "Liner");
    const fullXs = fullLiner.map(point => point[0]);
    assert.equal(Math.round(Math.min(...fullXs) * 10) / 10, -2.5);
    assert.equal(Math.round(Math.max(...fullXs) * 10) / 10, 1222.5);
    assert.equal(constantAxisRuns(fullLiner, 0, 10), 2);
    assert.equal((downloadedDxf.match(/8\r\nLiner\r\n/g) || []).length, 1);
    assert.equal((downloadedDxf.match(/0\r\nLINE\r\n8\r\nLiner\r\n/g) || []).length, 0);

    nextPlan = linerEndPlan([
        linerDoor({
            id: 1,
            label: "1.1",
            x: 0,
            y: 203,
            w: 40,
            h: 40,
            width_cm: 40,
            length_cm: 40,
            extra_liner: 0,
            liner_reference_side: "",
        }),
        linerDoor({
            id: 2,
            label: "2.1",
            x: 40.5,
            y: 203,
            w: 40,
            h: 40,
            width_cm: 40,
            length_cm: 40,
            extra_liner: 0,
            liner_reference_side: "",
        }),
        linerDoor({
            id: 3,
            label: "3.1",
            x: 81,
            y: 203,
            w: 40,
            h: 40,
            width_cm: 40,
            length_cm: 40,
            extra_liner: 0,
            liner_reference_side: "",
        }),
    ], 0.5);
    downloadedDxf = "";
    await fakeFrappe.almdina.export_order_dxf("26-TRIM-GAPS", "approved");
    const trimGapCuts = layerEdges(downloadedDxf, "CUT_PATH");
    const onVertical = (value) => trimGapCuts.filter(edge => (
        Math.abs(edge.x1 - value) < 0.02 && Math.abs(edge.x2 - value) < 0.02
    ));
    const onHorizontal = (value) => trimGapCuts.filter(edge => (
        Math.abs(edge.y1 - value) < 0.02 && Math.abs(edge.y2 - value) < 0.02
    ));
    assert.equal(onVertical(2.5).length, 1);
    assert.equal(onVertical(407.5).length, 2);
    assert.equal(onVertical(812.5).length, 2);
    assert.equal(onVertical(1217.5).length, 1);
    assert.equal(onHorizontal(2.5).length, 3);
    assert.equal(onVertical(0).length, 0);
    assert.equal(onVertical(1220).length, 0);
    assert.equal(onHorizontal(0).length, 0);

    nextPlan = {
        full_board_width_cm: 122,
        full_board_length_cm: 244,
        usable_board_width_cm: 122,
        usable_board_length_cm: 244,
        applied_trim_width_cm: 0,
        applied_trim_length_cm: 0,
        trim_cm: 0.5,
        kerf_mm: 3,
        kerf_cm: 0.3,
        sheets: [{
            sheet_no: 2,
            full_width_cm: 122,
            full_length_cm: 244,
            usable_width_cm: 121,
            usable_length_cm: 243,
            pieces: [
                linerDoor({ id: 1, label: "2.1", x: 0, y: 203, w: 40, h: 40, width_cm: 40, length_cm: 40, extra_liner: 0, liner_reference_side: "" }),
                linerDoor({ id: 2, label: "3.1", x: 40.3, y: 203, w: 40, h: 40, width_cm: 40, length_cm: 40, extra_liner: 0, liner_reference_side: "" }),
                linerDoor({ id: 3, label: "4.1", x: 80.6, y: 203, w: 40, h: 40, width_cm: 40, length_cm: 40, extra_liner: 0, liner_reference_side: "" }),
            ],
        }],
    };
    downloadedDxf = "";
    await fakeFrappe.almdina.export_order_dxf("26-KERF3-TRIM", "approved");
    const kerf3Cuts = layerEdges(downloadedDxf, "CUT_PATH");
    const kerf3Vertical = (value) => kerf3Cuts.filter(edge => (
        Math.abs(edge.x1 - value) < 0.02 && Math.abs(edge.x2 - value) < 0.02
    ));
    const kerf3Horizontal = (value) => kerf3Cuts.filter(edge => (
        Math.abs(edge.y1 - value) < 0.02 && Math.abs(edge.y2 - value) < 0.02
    ));
    assert.equal(kerf3Vertical(3.5).length, 1);
    assert.equal(kerf3Vertical(406.5).length, 2);
    assert.equal(kerf3Vertical(809.5).length, 2);
    assert.equal(kerf3Vertical(1212.5).length, 1);
    assert.equal(kerf3Horizontal(3.5).length, 3);
    assert.equal(kerf3Vertical(0).length, 0);
    assert.equal(kerf3Vertical(1220).length, 0);
    const kerf3Geometry = layerLines(downloadedDxf, "GEOMETRY");
    const geometryXs = kerf3Geometry.flatMap(edge => [edge.x1, edge.x2]);
    assert.ok(Math.abs(Math.min(...geometryXs) - 5) < 0.02);
    assert.ok(Math.abs(Math.max(...geometryXs) - 1211) < 0.02);

    nextPlan = linerEndPlan([linerDoor({ x: 5, w: 40, width_cm: 40 })]);
    downloadedDxf = "";
    await fakeFrappe.almdina.export_order_dxf("26-LINER-ENDS", "approved");
    const insetXs = polylinePoints(downloadedDxf, "Liner").map(point => point[0]);
    assert.equal(Math.round(Math.min(...insetXs) * 10) / 10, 47.5);
    assert.equal(Math.round(Math.max(...insetXs) * 10) / 10, 452.5);
    assert.ok(layerEdges(downloadedDxf, "CUT_PATH").some(edge => Math.abs(edge.x1 - 47.5) < 0.02 && Math.abs(edge.x2 - 47.5) < 0.02));

    nextPlan = linerEndPlan([linerDoor({ w: 40, width_cm: 40 })]);
    downloadedDxf = "";
    await fakeFrappe.almdina.export_order_dxf("26-LINER-ENDS", "approved");
    const flushXs = polylinePoints(downloadedDxf, "Liner").map(point => point[0]);
    assert.equal(Math.round(Math.min(...flushXs) * 10) / 10, -2.5);
    assert.equal(Math.round(Math.max(...flushXs) * 10) / 10, 402.5);
    assert.equal(layerEdges(downloadedDxf, "CUT_PATH").some(edge => (
        Math.abs(edge.x1 + 2.5) < 0.02 && Math.abs(edge.x2 + 2.5) < 0.02
    )), false);

    nextPlan = linerEndPlan([
        linerDoor({ id: 1, label: "1.1", w: 40, width_cm: 40 }),
        linerDoor({ id: 2, label: "2.1", x: 40.5, w: 40, width_cm: 40, extra_liner: 0, liner_reference_side: "" }),
    ]);
    downloadedDxf = "";
    await fakeFrappe.almdina.export_order_dxf("26-LINER-ENDS", "approved");
    const kerfCuts = layerEdges(downloadedDxf, "CUT_PATH").filter(edge => (
        Math.abs(edge.x1 - 402.5) < 0.02 && Math.abs(edge.x2 - 402.5) < 0.02
    ));
    assert.equal(kerfCuts.length, 1);
    const kerfXs = polylinePoints(downloadedDxf, "Liner").map(point => point[0]);
    assert.equal(Math.round(Math.min(...kerfXs) * 10) / 10, -2.5);
    assert.equal(Math.round(Math.max(...kerfXs) * 10) / 10, 402.5);

    nextPlan = linerEndPlan([linerDoor({
        w: 120,
        h: 242,
        width_cm: 120,
        length_cm: 242,
    })], 1);
    downloadedDxf = "";
    await fakeFrappe.almdina.export_order_dxf("26-LINER-ENDS", "approved");
    const trimXs = polylinePoints(downloadedDxf, "Liner").map(point => point[0]);
    assert.equal(Math.round(Math.min(...trimXs) * 10) / 10, 7.5);
    assert.equal(Math.round(Math.max(...trimXs) * 10) / 10, 1212.5);
    assert.ok(layerEdges(downloadedDxf, "CUT_PATH").some(edge => Math.abs(edge.x1 - 7.5) < 0.02 && Math.abs(edge.x2 - 7.5) < 0.02));

    nextPlan = linerEndPlan([
        linerDoor({ id: 1, label: "1.1", x: 20, w: 40, width_cm: 40 }),
        linerDoor({ id: 2, label: "2.1", x: 0, w: 19.5, width_cm: 19.5, extra_liner: 0, liner_reference_side: "" }),
        linerDoor({ id: 3, label: "3.1", x: 60.5, w: 30, width_cm: 30, extra_liner: 0, liner_reference_side: "" }),
    ]);
    downloadedDxf = "";
    await fakeFrappe.almdina.export_order_dxf("26-LINER-ENDS", "approved");
    assert.equal((downloadedDxf.match(/8\r\nLiner\r\n/g) || []).length, 1);

    nextPlan = linerEndPlan([
        linerDoor({ id: 1, label: "1.1", w: 40, width_cm: 40 }),
        linerDoor({ id: 2, label: "2.1", x: 40.1, w: 30, width_cm: 30, extra_liner: 0, liner_reference_side: "" }),
    ]);
    downloadedDxf = "";
    await assert.rejects(
        fakeFrappe.almdina.export_order_dxf("26-LINER-ENDS", "approved"),
        /overlaps an adjacent piece/
    );

    // Kerf-clear door 5 with a neighbour whose order width_cm is larger than
    // placed w (missing rotation) must still export — obstacle uses w/h.
    nextPlan = linerEndPlan([
        linerDoor({
            id: 5,
            label: "5",
            x: 40.5,
            y: 0,
            w: 30,
            h: 50,
            width_cm: 30,
            length_cm: 50,
            liner_reference_side: "edge_long_left",
        }),
        linerDoor({
            id: 4,
            label: "4",
            x: 0,
            y: 0,
            w: 40,
            h: 50,
            width_cm: 50,
            length_cm: 40,
            rotated: 0,
            extra_liner: 0,
            liner_reference_side: "",
        }),
    ]);
    downloadedDxf = "";
    await fakeFrappe.almdina.export_order_dxf("26-LINER-DOOR5", "system");
    assert.equal(cutPathEntityCount(downloadedDxf), 0);
    assert.ok(polylinePoints(downloadedDxf, "Liner").length >= 2);
    downloadedDxf = "";
    await fakeFrappe.almdina.export_order_dxf("26-LINER-DOOR5", "approved");
    assert.ok(cutPathEntityCount(downloadedDxf) > 0);
    assert.ok(polylinePoints(downloadedDxf, "Liner").length >= 2);

    // Real persisted regression CP-2026-00092 / DCO 26-00112: door 5.1 is
    // nested inside the opening of Glass door 1.1. The 3 mm Kerf leaves its
    // liner extension exactly one cutter radius (1.5 mm) from the Glass
    // material, so the opening must remain void rather than a solid obstacle.
    nextPlan = JSON.parse(JSON.stringify(nestedGlassRegressionSnapshot));
    downloadedDxf = "";
    await fakeFrappe.almdina.export_order_dxf("26-00112", "system");
    assert.equal(cutPathEntityCount(downloadedDxf), 0);
    assert.ok(polylinePoints(downloadedDxf, "Liner").length >= 2);
    downloadedDxf = "";
    await fakeFrappe.almdina.export_order_dxf("26-00112", "approved");
    assert.ok(cutPathEntityCount(downloadedDxf) > 0);
    const nestedLinerDxfPoints = polylinePoints(downloadedDxf, "Liner");
    assert.ok(nestedLinerDxfPoints.length >= 2);
    assert.ok(nestedLinerDxfPoints.some(point => (
        Math.abs(point[0] - 85.5) < 0.001 && Math.abs(point[1] - 1942.5) < 0.001
    )));

    nextPlan = linerEndPlan([linerDoor({
        w: 122,
        width_cm: 122,
        liner_start_cm: 10,
        liner_length_cm: 20,
    })]);
    downloadedDxf = "";
    await fakeFrappe.almdina.export_order_dxf("26-LINER-ENDS", "approved");
    const partialPoints = polylinePoints(downloadedDxf, "Liner");
    const partialXs = partialPoints.map(point => point[0]);
    assert.ok(Math.min(...partialXs) > 100);
    assert.ok(Math.max(...partialXs) < 300);
    let closedSpan = 0;
    let run = [partialPoints[0]];
    for (let index = 1; index < partialPoints.length; index += 1) {
        if (Math.abs(partialPoints[index][0] - partialPoints[index - 1][0]) <= 0.05) {
            run.push(partialPoints[index]);
            continue;
        }
        if (run.length >= 2) {
            closedSpan = Math.max(closedSpan, Math.abs(run[run.length - 1][1] - run[0][1]));
        }
        run = [partialPoints[index]];
    }
    if (run.length >= 2) {
        closedSpan = Math.max(closedSpan, Math.abs(run[run.length - 1][1] - run[0][1]));
    }
    assert.ok(closedSpan > 10);
    const geometryRegion = polylinePoints(downloadedDxf, "GEOMETRY");
    let regionEdge = 0;
    for (let index = 1; index < geometryRegion.length; index += 1) {
        regionEdge = Math.max(regionEdge, Math.hypot(
            geometryRegion[index][0] - geometryRegion[index - 1][0],
            geometryRegion[index][1] - geometryRegion[index - 1][1]
        ));
    }
    assert.ok(Math.abs(regionEdge - 200) < 0.2, regionEdge);
    assert.equal((downloadedDxf.match(/LWPOLYLINE\r\n100\r\nAcDbEntity\r\n8\r\nGEOMETRY\r\n/g) || []).length, 1);
    assert.ok((downloadedDxf.match(/8\r\nLiner\r\n/g) || []).length >= 1);

    nextPlan = linerEndPlan([linerDoor({
        w: 100,
        h: 80,
        width_cm: 100,
        length_cm: 80,
        liner_offset_cm: 10,
        liner_width_cm: 1.8,
        liner_start_cm: 20,
        liner_length_cm: 30,
        extra_back_groove: 1,
        back_groove_reference_side: "edge_long_right",
        back_groove_offset_cm: 4,
        back_groove_width_cm: 1.8,
        back_groove_start_cm: 10,
        back_groove_length_cm: 25,
        extra_recessed_handle_cutout: 1,
        recessed_handle_reference_side: "edge_width_bottom",
        recessed_handle_offset_cm: 2,
        recessed_handle_width_cm: 1.8,
        recessed_handle_start_cm: 15,
        recessed_handle_length_cm: 20,
    })]);
    downloadedDxf = "";
    await fakeFrappe.almdina.export_order_dxf("26-LINER-ENDS", "approved");
    const regionRings = polylineRings(downloadedDxf, "GEOMETRY");
    assert.equal(regionRings.length, 3);
    const regionLengths = regionRings.map(ring => ring.reduce((longest, point, index) => {
        const previous = ring[index - 1];
        if (!previous) return longest;
        return Math.max(longest, Math.hypot(point[0] - previous[0], point[1] - previous[1]));
    }, 0)).sort((left, right) => left - right);
    assert.ok(Math.abs(regionLengths[0] - 200) < 0.2, regionLengths.join(","));
    assert.ok(Math.abs(regionLengths[1] - 250) < 0.2, regionLengths.join(","));
    assert.ok(Math.abs(regionLengths[2] - 300) < 0.2, regionLengths.join(","));
    assert.ok(polylinePoints(downloadedDxf, "Liner").length >= 2);
    assert.ok(polylinePoints(downloadedDxf, "Rear Groove").length >= 2);
    assert.ok(polylinePoints(downloadedDxf, "Handle Recess").length >= 2);

    for (const pieceType of ["Clipped Corner", "L-Shaped Corner"]) {
        nextPlan = linerEndPlan([linerDoor({
            piece_type: pieceType,
            w: 100,
            h: 80,
            width_cm: 100,
            length_cm: 80,
            clipped_corner_position: "Top Right",
            clipped_corner_width_cm: 20,
            clipped_corner_length_cm: 30,
            liner_reference_side: "edge_break",
            liner_offset_cm: 1,
            liner_width_cm: 0.8,
        })]);
        downloadedDxf = "";
        await fakeFrappe.almdina.export_order_dxf("26-LINER-ENDS", "approved");
        assert.ok(polylinePoints(downloadedDxf, "Liner").length > 2);
    }

    // Design export (system tab) must keep door geometry and overlays but omit
    // separation/trim CUT_PATH until Production Cutting Plan approval.
    nextPlan = {
        full_board_width_cm: 122,
        full_board_length_cm: 244,
        kerf_mm: 5,
        trim_cm: 1,
        sheets: [{
            sheet_no: 1,
            full_width_cm: 122,
            full_length_cm: 244,
            pieces: [
                {
                    id: 1,
                    label: "1.1",
                    piece_type: "Regular",
                    x: 0,
                    y: 0,
                    w: 20,
                    h: 50,
                    width_cm: 20,
                    length_cm: 50,
                    extra_liner: 1,
                    liner_reference_side: "edge_long_left",
                    liner_offset_cm: 2,
                    liner_width_cm: 1.8,
                },
                {
                    id: 2,
                    label: "2.1",
                    piece_type: "Regular",
                    x: 20.5,
                    y: 0,
                    w: 30,
                    h: 40,
                    width_cm: 30,
                    length_cm: 40,
                },
            ],
        }],
    };
    downloadedDxf = "";
    await fakeFrappe.almdina.export_order_dxf("26-DESIGN-NO-SAW", "system");
    assert.equal(cutPathEntityCount(downloadedDxf), 0);
    assert.ok(layerLines(downloadedDxf, "GEOMETRY").length > 0);
    assert.ok(polylinePoints(downloadedDxf, "Liner").length >= 2);
    // Layer table still declares CUT_PATH; no entity uses group-code 8 yet.
    assert.match(downloadedDxf, /2\r\nCUT_PATH\r\n/);

    nextPlan.include_saw_centers = true;
    downloadedDxf = "";
    await fakeFrappe.almdina.export_order_dxf("26-DESIGN-NO-SAW", "system");
    const forcedSaw = cutPathEntityCount(downloadedDxf);
    assert.ok(forcedSaw > 0);

    delete nextPlan.include_saw_centers;
    downloadedDxf = "";
    await fakeFrappe.almdina.export_order_dxf("26-MFG-AFTER-APPROVAL", "approved");
    const approvedSaw = cutPathEntityCount(downloadedDxf);
    assert.equal(approvedSaw, forcedSaw);

    downloadedDxf = "";
    await fakeFrappe.almdina.export_order_dxf("26-MFG-AFTER-APPROVAL", "approved");
    assert.equal(cutPathEntityCount(downloadedDxf), approvedSaw);

    // Approved upload without saw centers must regenerate manufacturing DXF.
    originalUpload = {
        filename: "design-only.dxf",
        content_b64: Buffer.from("0\nSECTION\n8\nGEOMETRY\n0\nEOF\n", "utf8").toString("base64"),
    };
    downloadedDxf = "";
    downloadedName = "";
    lastCallMethod = "";
    await fakeFrappe.almdina.export_order_dxf("DCO-APPROVED-ABSENT", "approved", {
        hasOriginalFile: true,
        preferOriginalUpload: false,
    });
    assert.match(lastCallMethod, /normalize_dxf_for_autocad/);
    assert.ok(cutPathEntityCount(downloadedDxf) > 0);

    // Custom tab before approval: keep the original designer file.
    downloadedDxf = "";
    lastCallMethod = "";
    await fakeFrappe.almdina.export_order_dxf("DCO-CUSTOM-DRAFT", "custom", {
        hasOriginalFile: true,
        preferOriginalUpload: true,
    });
    assert.match(lastCallMethod, /download_uploaded_dxf/);
    assert.equal(downloadedDxf, "0\nSECTION\n8\nGEOMETRY\n0\nEOF\n");

    // Custom tab after the same upload was approved without saw centers:
    // regenerate manufacturing DXF instead of shipping the design file.
    nextPlan.include_saw_centers = true;
    downloadedDxf = "";
    lastCallMethod = "";
    await fakeFrappe.almdina.export_order_dxf("DCO-CUSTOM-APPROVED-ABSENT", "custom", {
        hasOriginalFile: true,
        preferOriginalUpload: false,
    });
    assert.match(lastCallMethod, /normalize_dxf_for_autocad/);
    assert.ok(cutPathEntityCount(downloadedDxf) > 0);
    const customApprovedSaw = cutPathEntityCount(downloadedDxf);
    downloadedDxf = "";
    await fakeFrappe.almdina.export_order_dxf("DCO-CUSTOM-APPROVED-ABSENT", "custom", {
        hasOriginalFile: true,
        preferOriginalUpload: false,
    });
    assert.equal(cutPathEntityCount(downloadedDxf), customApprovedSaw);

    // Custom tab when a different plan is approved: still the uploaded original.
    delete nextPlan.include_saw_centers;
    downloadedDxf = "";
    lastCallMethod = "";
    await fakeFrappe.almdina.export_order_dxf("DCO-CUSTOM-OTHER-APPROVED", "custom", {
        hasOriginalFile: true,
        preferOriginalUpload: true,
    });
    assert.match(lastCallMethod, /download_uploaded_dxf/);
    assert.equal(downloadedDxf, "0\nSECTION\n8\nGEOMETRY\n0\nEOF\n");

    // Approved upload that already has saw centers keeps the original bytes.
    originalUpload = {
        filename: "ready-cut-paths.dxf",
        content_b64: Buffer.from("0\nSECTION\n8\nCUT_PATH\n0\nEOF\n", "utf8").toString("base64"),
    };
    downloadedDxf = "";
    lastCallMethod = "";
    await fakeFrappe.almdina.export_order_dxf("DCO-CUSTOM-APPROVED-PRESENT", "custom", {
        hasOriginalFile: true,
        preferOriginalUpload: true,
    });
    assert.match(lastCallMethod, /download_uploaded_dxf/);
    assert.equal(downloadedDxf, "0\nSECTION\n8\nCUT_PATH\n0\nEOF\n");

    console.log("Secure DXF topology export simulation passed");
}

function layerLines(dxf, layerName) {
    const lines = dxf.split("\r\n");
    const edges = [];
    for (let index = 0; index < lines.length - 12; index += 1) {
        if (lines[index] !== "LINE" || lines[index + 2] !== layerName) continue;
        edges.push({
            x1: Number(lines[index + 4]),
            y1: Number(lines[index + 6]),
            x2: Number(lines[index + 10]),
            y2: Number(lines[index + 12]),
        });
    }
    return edges;
}

function layerEdges(dxf, layerName) {
    const edges = layerLines(dxf, layerName);
    polylineRings(dxf, layerName).forEach(ring => {
        ring.forEach((point, index) => {
            const next = ring[(index + 1) % ring.length];
            edges.push({ x1: point[0], y1: point[1], x2: next[0], y2: next[1] });
        });
    });
    return edges;
}

function constantAxisRuns(points, axis, minimum) {
    let count = 0;
    let run = [points[0]];
    function commit(span) {
        if (span.length >= 2 && Math.abs(span[span.length - 1][1 - axis] - span[0][1 - axis]) > minimum) count += 1;
    }
    for (let index = 1; index < points.length; index += 1) {
        if (Math.abs(points[index][axis] - points[index - 1][axis]) <= 0.05) {
            run.push(points[index]);
            continue;
        }
        commit(run);
        run = [points[index]];
    }
    commit(run);
    return count;
}

function polylineRings(dxf, layerName) {
    const lines = dxf.split("\r\n");
    const rings = [];
    for (let index = 0; index < lines.length; index += 1) {
        if (lines[index] !== "LWPOLYLINE" || lines[index + 4] !== layerName) continue;
        const count = Number(lines[index + 8]);
        const ring = [];
        let cursor = index + 11;
        for (let point = 0; point < count; point += 1) {
            ring.push([Number(lines[cursor + 1]), Number(lines[cursor + 3])]);
            cursor += 4;
        }
        rings.push(ring);
    }
    return rings;
}

function polylinePoints(dxf, layerName) {
    const lines = dxf.split("\r\n");
    const points = [];
    for (let index = 0; index < lines.length; index += 1) {
        if (lines[index] !== "LWPOLYLINE" || lines[index + 4] !== layerName) continue;
        const count = Number(lines[index + 8]);
        let cursor = index + 11;
        for (let point = 0; point < count; point += 1) {
            points.push([Number(lines[cursor + 1]), Number(lines[cursor + 3])]);
            cursor += 4;
        }
    }
    return points;
}

run().catch(error => {
    console.error(error);
    process.exitCode = 1;
});
