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

assert.ok(typeof ux.collectCutExecutions === "function");
assert.ok(typeof ux.cutPathPreviewMarkup === "function");
assert.ok(typeof ux.paintCutPathPreview === "function");
assert.ok(panel.includes("requestSheetProgramPreview("));
assert.ok(panel.includes("get_cnc_sheet_program"));
assert.ok(panel.includes("collectCutExecutions("));
assert.ok(!/bindDialog[\s\S]{0,400}mountBoard\(preview/.test(panel));
assert.ok(css.includes(".dco-cnc-cut-preview"));
assert.ok(translations.includes("جارٍ تحميل مسارات القص"));
assert.ok(translations.includes("لا توجد مسارات قص متاحة لمعاينة هذا اللوح"));
assert.ok(translations.includes("معاينة مسارات القص غير مكتملة"));

function closedSquareMotions(depths) {
    const points = [
        [10, 10],
        [90, 10],
        [90, 90],
        [10, 90],
        [10, 10],
    ];
    const motions = [];
    depths.forEach(depth => {
        motions.push({ kind: "travel", x_mm: 10, y_mm: 10, depth_mm: null });
        motions.push({ kind: "plunge", x_mm: 10, y_mm: 10, depth_mm: depth });
        points.slice(1).forEach(point => {
            motions.push({ kind: "cut", x_mm: point[0], y_mm: point[1], depth_mm: depth });
        });
        motions.push({ kind: "retract", x_mm: 10, y_mm: 10, depth_mm: null });
    });
    return { points, motions };
}

const sharedClosed = closedSquareMotions([6, 12]);
const openPathMotions = (() => {
    const motions = [
        { kind: "travel", x_mm: 20, y_mm: 40, depth_mm: null },
        { kind: "plunge", x_mm: 20, y_mm: 40, depth_mm: 8 },
        { kind: "cut", x_mm: 60, y_mm: 40, depth_mm: 8 },
        { kind: "cut", x_mm: 60, y_mm: 70, depth_mm: 8 },
        { kind: "cut", x_mm: 100, y_mm: 70, depth_mm: 8 },
        { kind: "retract", x_mm: 100, y_mm: 70, depth_mm: null },
        { kind: "travel", x_mm: 30, y_mm: 80, depth_mm: null },
        { kind: "plunge", x_mm: 30, y_mm: 80, depth_mm: 8 },
        { kind: "cut", x_mm: 80, y_mm: 80, depth_mm: 8 },
        { kind: "retract", x_mm: 80, y_mm: 80, depth_mm: null },
    ];
    return motions;
})();

const program = {
    sheet_width_mm: 200,
    sheet_length_mm: 300,
    geometry_ready: true,
    ready: true,
    issues: [],
    operations: [
        {
            operation_key: "liner",
            toolpaths: [
                {
                    path_key: "liner:a",
                    operation_key: "liner",
                    closed: false,
                    ready: true,
                    issues: [],
                    points: [[1, 1], [2, 2]],
                    motions: [
                        { kind: "travel", x_mm: 1, y_mm: 1, depth_mm: null },
                        { kind: "plunge", x_mm: 1, y_mm: 1, depth_mm: 3 },
                        { kind: "cut", x_mm: 2, y_mm: 2, depth_mm: 3 },
                        { kind: "retract", x_mm: 2, y_mm: 2, depth_mm: null },
                    ],
                },
            ],
        },
        {
            operation_key: "cut_path",
            toolpaths: [
                {
                    path_key: "cut_path:shared",
                    operation_key: "cut_path",
                    closed: true,
                    ready: true,
                    issues: [],
                    points: sharedClosed.points,
                    motions: sharedClosed.motions,
                },
                {
                    path_key: "cut_path:open-a",
                    operation_key: "cut_path",
                    closed: false,
                    ready: true,
                    issues: [],
                    points: [[20, 40], [60, 40], [60, 70], [100, 70]],
                    motions: openPathMotions.slice(0, 6),
                },
                {
                    path_key: "cut_path:open-b",
                    operation_key: "cut_path",
                    closed: false,
                    ready: true,
                    issues: [],
                    points: [[30, 80], [80, 80]],
                    motions: openPathMotions.slice(6),
                },
            ],
        },
    ],
};

const executions = ux.collectCutExecutions(program);
assert.equal(executions.length, 4, "each plunge-to-retract cut cycle is one execution");
assert.equal(executions[0].path_key, "cut_path:shared");
assert.equal(executions[0].execution, 1);
assert.equal(executions[0].depth_mm, 6);
assert.equal(executions[1].execution, 2);
assert.equal(executions[1].depth_mm, 12);
assert.equal(executions[1].path_key, "cut_path:shared");
assert.equal(executions[2].path_key, "cut_path:open-a");
assert.equal(executions[2].points.length, 4, "connected cuts without raise stay one execution");
assert.equal(executions[3].path_key, "cut_path:open-b");
assert.ok(executions.every(item => item.operation_key === "cut_path"));
assert.ok(!executions.some(item => item.path_key.startsWith("liner:")));

const pointCount = sharedClosed.points.length + 4 + 2;
assert.notEqual(executions.length, pointCount, "execution count must not equal raw point count");

const labels = ux.groupCutExecutionLabels(executions);
const sharedLabel = labels.find(group => group.path_key === "cut_path:shared");
assert.ok(sharedLabel);
assert.equal(sharedLabel.items.length, 2, "depth passes at the same start share one label anchor");

const scoped = ux.cutPathPreviewMarkup(program, {
    selectedPathKey: "cut_path:open-a",
    markerScope: "cnc-cut-test-scope",
});
assert.ok(scoped.includes("dco-cnc-cut-preview__frame"));
assert.ok(scoped.includes("dco-cnc-cut-preview__path"));
assert.ok(scoped.includes('marker-end="url(#cnc-cut-test-scope-arrow-1)"'));
assert.ok(scoped.includes("dco-cnc-cut-preview__badge"));
assert.ok(scoped.includes(">1,2<") || scoped.includes("<span>1,2</span>"));
assert.ok(scoped.includes('data-execution-path="cut_path:open-a"'));
assert.ok(scoped.includes("is-cnc-path-selected"));
assert.ok(!scoped.includes("dco-piece"));
assert.ok(!scoped.includes("GEOMETRY"));
assert.ok(!scoped.includes("SHEET_OUTLINE"));
assert.ok(!scoped.includes('id="cnc-cut-arrow-1"'));

const incomplete = ux.cutPathPreviewMarkup({
    sheet_width_mm: 100,
    sheet_length_mm: 200,
    geometry_ready: false,
    ready: false,
    issues: [{ code: "geometry_invalid", message: "This path geometry cannot be used." }],
    operations: [
        {
            operation_key: "cut_path",
            toolpaths: [
                {
                    path_key: "cut_path:bad",
                    operation_key: "cut_path",
                    closed: false,
                    ready: false,
                    issues: ["geometry_invalid"],
                    points: [[0, 0], [10, 0], [10, 10]],
                    motions: [],
                },
            ],
        },
    ],
});
assert.ok(incomplete.includes("Cutting path preview is incomplete."));
assert.ok(incomplete.includes("No cutting paths are available for this sheet preview."));
assert.ok(!incomplete.includes("0,0 10,0 10,10"), "do not invent strokes from points without motions");

const host = { innerHTML: "" };
ux.paintCutPathPreview(host, { status: "loading" });
assert.ok(host.innerHTML.includes("Loading cutting paths..."));
ux.paintCutPathPreview(host, { status: "error" });
assert.ok(host.innerHTML.includes("Cutting paths could not be loaded."));
ux.paintCutPathPreview(host, { status: "ready", program, selectedPathKey: "cut_path:shared" });
assert.ok(host.innerHTML.includes("dco-cnc-cut-preview__execution"));
assert.ok(host.innerHTML.includes('data-execution-path="cut_path:shared"'));

const arrow = ux.cutExecutionArrowSegment([[0, 0], [10, 0], [10, 10], [0, 10], [0, 0]], true);
assert.ok(arrow);
assert.ok(arrow.from[0] !== arrow.to[0] || arrow.from[1] !== arrow.to[1]);

const dialog = ux.dialogMarkup(
    { can_prepare: true, presets: [] },
    {
        sheet_no: 1,
        status: "Not Generated",
        operations: [{ operation_key: "cut_path", dxf_layer: "CUT_PATH", path_count: 1 }],
        paths: [{ path_key: "cut_path:a", operation_key: "cut_path", piece_label: "1.1" }],
    },
    {
        order: ["cut_path"],
        operations: { cut_path: "Finish" },
        sources: { cut_path: "factory" },
        overrides: {},
        confirmed: false,
        expanded: {},
        selectedPathKey: "",
        customizing: {},
        factoryPresets: { cut_path: "Finish" },
    }
);
assert.ok(dialog.includes("data-sheet-preview"));
assert.ok(!dialog.includes("dco-piece"));

console.log("dco_operational_files_cut_preview.test.js passed");
