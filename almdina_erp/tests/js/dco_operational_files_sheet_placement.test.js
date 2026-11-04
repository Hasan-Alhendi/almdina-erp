"use strict";

const assert = require("assert");
const fs = require("fs");
const path = require("path");
const vm = require("vm");

const root = path.resolve(__dirname, "../..");
const panelPath = path.join(
    root,
    "public/js/door_cutting_order/cnc/door_cutting_order_operational_files_ux.js"
);
const cssPath = path.join(root, "public/css/door_cutting_order_operational_files.css");
const translationsPath = path.join(root, "translations/ar.csv");
const windowObject = {};
vm.runInNewContext(fs.readFileSync(panelPath, "utf8"), { window: windowObject }, { filename: panelPath });
const ux = windowObject.AlmdinaOperationalFilesUX;
const panel = fs.readFileSync(panelPath, "utf8");
const css = fs.readFileSync(cssPath, "utf8");
const translations = fs.readFileSync(translationsPath, "utf8");

assert.ok(typeof ux.validateSheetPlacementFits === "function");
assert.ok(typeof ux.placementPreviewPayload === "function");
assert.ok(typeof ux.cutPathPreviewMarkup === "function");
assert.ok(panel.includes("data-sheet-placement"));
assert.ok(panel.includes("dco-cnc-cut-preview__void"));
assert.ok(panel.includes("dco-cnc-cut-preview__machine"));
assert.ok(css.includes("dco-cnc-cut-preview__void") || css.includes("dco-operational-sheet__placement"));
assert.ok(translations.includes("تموضع اللوح على ماكينة CNC"));
assert.ok(translations.includes("البعد عن اليسار (سم)"));
assert.ok(translations.includes("البعد عن الأسفل (سم)"));
assert.ok(translations.includes("ماكينات CNC"));

const workspace = {
    cnc_machines: [
        { name: "Router A", machine_name: "Router A", width_cm: 130, length_cm: 250, enabled: true },
        { name: "Router B", machine_name: "Router B", width_cm: 100, length_cm: 200, enabled: true },
    ],
};

const state = {
    cncMachine: "Router A",
    offsetLeftCm: 3,
    offsetBottomCm: 4,
    sheetWidthCm: 122,
    sheetLengthCm: 244,
};

assert.strictEqual(ux.validateSheetPlacementFits(workspace, state).ok, true);
assert.strictEqual(
    ux.validateSheetPlacementFits(workspace, { ...state, offsetLeftCm: 10 }).code,
    "sheet_exceeds_machine_width"
);
assert.strictEqual(
    ux.validateSheetPlacementFits(workspace, { ...state, offsetBottomCm: -1 }).code,
    "offset_bottom_invalid"
);
assert.strictEqual(
    ux.validateSheetPlacementFits(workspace, { ...state, cncMachine: "" }, { requireMachine: true }).code,
    "cnc_machine_required"
);
// Changing to a smaller machine keeps offsets and reports overflow without rewriting them.
const tight = { ...state, cncMachine: "Router B", offsetLeftCm: 3, offsetBottomCm: 4 };
assert.strictEqual(ux.validateSheetPlacementFits(workspace, tight).code, "sheet_exceeds_machine_width");
assert.strictEqual(tight.offsetLeftCm, 3);
assert.strictEqual(tight.offsetBottomCm, 4);

const placement = ux.placementPreviewPayload(workspace, state);
assert.strictEqual(placement.machine_width_cm, 130);
assert.strictEqual(placement.offset_left_cm, 3);
assert.strictEqual(placement.offset_bottom_cm, 4);

const program = {
    sheet_width_mm: 1220,
    sheet_length_mm: 2440,
    geometry_ready: true,
    ready: true,
    issues: [],
    operations: [
        {
            operation_key: "cut_path",
            toolpaths: [
                {
                    path_key: "cut_path:demo",
                    operation_key: "cut_path",
                    closed: false,
                    ready: true,
                    issues: [],
                    points: [[100, 200], [110, 200]],
                    motions: [
                        { kind: "travel", x_mm: 100, y_mm: 200, depth_mm: null },
                        { kind: "plunge", x_mm: 100, y_mm: 200, depth_mm: 6 },
                        { kind: "cut", x_mm: 110, y_mm: 200, depth_mm: 6 },
                        { kind: "retract", x_mm: 110, y_mm: 200, depth_mm: null },
                    ],
                },
            ],
        },
    ],
};

const markup = ux.cutPathPreviewMarkup(program, {
    layout: "page",
    placement,
    zoom: 1,
});
assert.ok(markup.includes('viewBox="0 0 1300 2500"'));
assert.ok(markup.includes("dco-cnc-cut-preview__void"));
assert.ok(markup.includes("dco-cnc-cut-preview__machine"));
assert.ok(markup.includes('transform="translate(30,40)"'));
assert.ok(markup.includes("data-placement-caption"));
// Path numbers stay on sheet-local geometry; geometry points are not rewritten in the program.
assert.strictEqual(program.operations[0].toolpaths[0].motions[0].x_mm, 100);
assert.ok(markup.includes("data-path-number=\"1\"") || markup.includes("data-path-number='1'") || /data-path-number="1"/.test(markup));

const zoomed = ux.clampCutPreviewZoom(1.5);
assert.strictEqual(zoomed, ux.clampCutPreviewZoom(1.5));

console.log("dco_operational_files_sheet_placement.test.js passed");
