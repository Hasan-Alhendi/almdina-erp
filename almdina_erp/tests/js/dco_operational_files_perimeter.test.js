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
const css = fs.readFileSync(cssPath, "utf8");
const translations = fs.readFileSync(translationsPath, "utf8");

assert.equal(ux.SHEET_PERIMETER_PATH_KEY, "cut_path:sheet_perimeter");
assert.equal(ux.normalizePerimeterJoinMode(""), "separate");
assert.equal(ux.normalizePerimeterJoinMode("connected"), "connected");

const sheetSeparate = ux.sheetState({
    operations: [{ operation_key: "cut_path", tool_preset: "Finish", preset_source: "factory", factory_preset: "Finish" }],
    paths: [{ path_key: "cut_path:a:outer", operation_key: "cut_path", tool_preset: "" }],
    cut_path_early_confirmed: 0,
});
assert.equal(sheetSeparate.perimeterJoinMode, "separate");
assert.deepEqual(sheetSeparate.cutPathSequence, []);

const sheetConnected = ux.sheetState({
    operations: [{ operation_key: "cut_path", tool_preset: "Finish", preset_source: "factory", factory_preset: "Finish" }],
    paths: [
        { path_key: "cut_path:a:outer", operation_key: "cut_path", tool_preset: "" },
        { path_key: ux.SHEET_PERIMETER_PATH_KEY, operation_key: "cut_path", tool_preset: "", is_sheet_perimeter: true },
    ],
    perimeter_join_mode: "connected",
    cut_path_sequence: ["cut_path:a:outer", ux.SHEET_PERIMETER_PATH_KEY],
    perimeter_cut_early_confirmed: 0,
});
assert.equal(sheetConnected.perimeterJoinMode, "connected");
assert.deepEqual(sheetConnected.cutPathSequence, ["cut_path:a:outer", ux.SHEET_PERIMETER_PATH_KEY]);

const markup = ux.dialogMarkup(
    { can_prepare: true, presets: [{ name: "Finish", enabled: 1, tool_diameter_mm: 5 }] },
    {
        sheet_no: 1,
        status: "Draft",
        operations: [{ operation_key: "cut_path", dxf_layer: "CUT_PATH", path_count: 2 }],
        paths: sheetConnected.paths || [
            { path_key: "cut_path:a:outer", operation_key: "cut_path" },
            { path_key: ux.SHEET_PERIMETER_PATH_KEY, operation_key: "cut_path", is_sheet_perimeter: true },
        ],
    },
    sheetConnected
);
assert.ok(markup.includes("data-perimeter-join"));
assert.ok(markup.includes("data-perimeter-join-mode=\"separate\""));
assert.ok(markup.includes("data-perimeter-join-mode=\"connected\""));
assert.ok(markup.includes("Sheet perimeter cut method"));
assert.ok(markup.includes("Connected perimeter"));
assert.ok(markup.includes("Disconnected perimeter"));

sheetConnected.cutPathSequence = [ux.SHEET_PERIMETER_PATH_KEY, "cut_path:a:outer"];
const earlyMarkup = ux.perimeterJoinControlsMarkup(sheetConnected, true);
assert.ok(earlyMarkup.includes("data-perimeter-confirm"));
assert.ok(earlyMarkup.includes("Cutting the sheet perimeter first"));

ux.moveCutPathSequence(sheetConnected, ux.SHEET_PERIMETER_PATH_KEY, 1);
assert.deepEqual(sheetConnected.cutPathSequence, ["cut_path:a:outer", ux.SHEET_PERIMETER_PATH_KEY]);
assert.equal(ux.perimeterIsEarly(sheetConnected.cutPathSequence), false);

const program = {
    sheet_width_mm: 1220,
    sheet_length_mm: 2440,
    operations: [
        {
            operation_key: "cut_path",
            toolpaths: [
                {
                    path_key: "cut_path:a:outer",
                    closed: true,
                    ready: true,
                    issues: [],
                    piece_label: "A",
                    piece_instance_id: "A",
                    sequence: 1,
                    motions: [
                        { kind: "travel", x_mm: 0, y_mm: 0, depth_mm: null },
                        { kind: "plunge", x_mm: 0, y_mm: 0, depth_mm: 6 },
                        { kind: "cut", x_mm: 100, y_mm: 0, depth_mm: 6 },
                        { kind: "cut", x_mm: 100, y_mm: 80, depth_mm: 6 },
                        { kind: "cut", x_mm: 0, y_mm: 80, depth_mm: 6 },
                        { kind: "cut", x_mm: 0, y_mm: 0, depth_mm: 6 },
                        { kind: "retract", x_mm: 0, y_mm: 0, depth_mm: null },
                    ],
                },
                {
                    path_key: ux.SHEET_PERIMETER_PATH_KEY,
                    closed: true,
                    ready: true,
                    issues: [],
                    piece_label: "",
                    piece_instance_id: "",
                    sequence: 2,
                    motions: [
                        { kind: "travel", x_mm: 0, y_mm: 0, depth_mm: null },
                        { kind: "plunge", x_mm: 0, y_mm: 0, depth_mm: 6 },
                        { kind: "cut", x_mm: 200, y_mm: 0, depth_mm: 6 },
                        { kind: "cut", x_mm: 200, y_mm: 120, depth_mm: 6 },
                        { kind: "cut", x_mm: 0, y_mm: 120, depth_mm: 6 },
                        { kind: "cut", x_mm: 0, y_mm: 0, depth_mm: 6 },
                        { kind: "retract", x_mm: 0, y_mm: 0, depth_mm: null },
                    ],
                },
            ],
        },
    ],
};

const physical = ux.collectPhysicalPaths(program);
const perimeter = physical.find(item => item.path_key === ux.SHEET_PERIMETER_PATH_KEY);
assert.ok(perimeter);
assert.equal(perimeter.is_sheet_perimeter, true);
assert.equal(ux.pathDisplayLabel(perimeter), "Sheet perimeter — Perimeter Cut");
assert.equal(perimeter.pass_count, 1);

const state = Object.assign({}, sheetConnected, {
    program,
    selectedExecutionPathId: "",
    selectedPathKey: "",
    overrides: {},
    customizing: {},
    expanded: { cut_path: true },
});
ux.syncCutPathSequence(state, physical);
assert.ok(state.cutPathSequence.includes(ux.SHEET_PERIMETER_PATH_KEY));

const row = ux.pathDisplayLabel
    ? physical.map(path => path.path_key)
    : [];
assert.ok(row.includes(ux.SHEET_PERIMETER_PATH_KEY));

const preview = ux.cutPathPreviewMarkup(program, {
    selectedExecutionPathId: perimeter.execution_path_id,
    selectedPathKey: perimeter.path_key,
});
assert.ok(preview.includes(perimeter.execution_path_id));
assert.ok(preview.includes("is-cnc-path-selected") || preview.includes(String(perimeter.path_number)));

assert.ok(css.includes(".dco-operational-perimeter"));
assert.ok(translations.includes("طريقة قص محيط اللوح"));
assert.ok(translations.includes("محيط متصل"));
assert.ok(translations.includes("محيط غير متصل"));
assert.ok(translations.includes("محيط اللوح — Perimeter Cut"));

console.log("dco_operational_files_perimeter.test.js: ok");
