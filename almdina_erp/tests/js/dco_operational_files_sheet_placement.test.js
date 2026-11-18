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
assert.ok(translations.includes("المصادم الأيسر (سم)"));
assert.ok(translations.includes("المصادم السفلي (سم)"));
assert.ok(translations.includes("موضع صفر العمل"));
assert.ok(!panel.includes("data-offset-left"));
assert.ok(!panel.includes("Distance from left (cm)"));
assert.ok(!panel.includes("Distance from bottom (cm)"));
assert.ok(translations.includes("ماكينات CNC"));

const workspace = {
    cnc_machines: [
        {
            name: "Router A",
            machine_name: "Router A",
            width_cm: 130,
            length_cm: 250,
            enabled: true,
            work_zero_position: "Bottom Left",
            width_stop_side: "Left Side",
            length_stop_side: "Bottom Side",
            left_stop_cm: 3,
            bottom_stop_cm: 4,
        },
        {
            name: "Router B",
            machine_name: "Router B",
            width_cm: 100,
            length_cm: 200,
            enabled: true,
            work_zero_position: "Bottom Left",
            width_stop_side: "Left Side",
            length_stop_side: "Bottom Side",
            left_stop_cm: 3,
            bottom_stop_cm: 4,
        },
        {
            name: "Router C",
            machine_name: "Router C",
            width_cm: 130,
            length_cm: 250,
            enabled: true,
            work_zero_position: "Bottom Left",
            width_stop_side: "",
            length_stop_side: "",
            left_stop_cm: null,
            bottom_stop_cm: null,
        },
    ],
};

const state = {
    cncMachine: "Router A",
    sheetWidthCm: 122,
    sheetLengthCm: 244,
};

assert.strictEqual(ux.validateSheetPlacementFits(workspace, state).ok, true);
assert.strictEqual(
    ux.validateSheetPlacementFits(workspace, { ...state, cncMachine: "Router B" }).code,
    "sheet_exceeds_machine_width"
);
const negative = {
    ...workspace,
    cnc_machines: workspace.cnc_machines.map(item => (
        item.name === "Router A" ? { ...item, bottom_stop_cm: -1 } : item
    )),
};
assert.strictEqual(ux.validateSheetPlacementFits(negative, state).ok, true);
assert.strictEqual(
    ux.validateSheetPlacementFits(workspace, { ...state, cncMachine: "Router C" }).code,
    "cnc_machine_stop_sides_required"
);
assert.strictEqual(
    ux.validateSheetPlacementFits(workspace, { ...state, cncMachine: "" }, { requireMachine: true }).code,
    "cnc_machine_required"
);
const tight = { ...state, cncMachine: "Router B" };
assert.strictEqual(ux.validateSheetPlacementFits(workspace, tight).code, "sheet_exceeds_machine_width");
assert.strictEqual(workspace.cnc_machines[1].left_stop_cm, 3);
assert.strictEqual(workspace.cnc_machines[1].bottom_stop_cm, 4);

const placement = ux.placementPreviewPayload(workspace, state);
assert.strictEqual(placement.machine_width_cm, 130);
assert.strictEqual(placement.offset_left_cm, 8);
assert.strictEqual(placement.offset_bottom_cm, 6);
assert.strictEqual(placement.horizontal_stop_cm, 8);
assert.strictEqual(placement.vertical_stop_cm, 6);
assert.strictEqual(Object.prototype.hasOwnProperty.call(placement, "cutter_travel_left_extension_mm"), false);

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
                    points: [[-2.5, 200], [110, 4002.5]],
                    motions: [
                        { kind: "travel", x_mm: -2.5, y_mm: 200, depth_mm: null },
                        { kind: "plunge", x_mm: -2.5, y_mm: 200, depth_mm: 6 },
                        { kind: "cut", x_mm: 110, y_mm: 4002.5, depth_mm: 6 },
                        { kind: "retract", x_mm: 110, y_mm: 4002.5, depth_mm: null },
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
const viewBox = markup.match(/viewBox="([^"]+)"/)[1].split(/\s+/).map(Number);
assert.ok(viewBox[0] <= 0 && viewBox[1] <= 0, "machine origin stays inside the frame");
assert.ok(viewBox[0] + viewBox[2] >= 1300 && viewBox[1] + viewBox[3] >= 2500, "machine far edges stay inside the frame");
assert.ok(viewBox[1] < 0, "cutter centre past the top of the bed stays inside the frame");
assert.ok(markup.includes("-2.5,200"));
assert.ok(markup.includes("110,4002.5"));
assert.ok(markup.includes("dco-cnc-cut-preview__void"));
assert.ok(markup.includes("dco-cnc-cut-preview__machine"));
assert.ok(!markup.includes("dco-cnc-cut-preview__travel"));
assert.ok(!markup.includes("The dashed line shows the configured cutter travel bounds."));
assert.ok(markup.includes("dco-cnc-cut-preview__sheet"));
assert.ok(!/class="dco-cnc-cut-preview__sheet"[^>]*\bstroke=/.test(markup));
assert.ok(!markup.includes("dco-cnc-cut-preview__frame"));
assert.ok(markup.includes('transform="translate(80,60)"'));
assert.ok(markup.includes('data-stop-badge="left"'));
assert.ok(markup.includes('data-stop-badge="bottom"'));
assert.ok(markup.includes('data-stop-arrow="left"'));
assert.ok(markup.includes('data-stop-arrow="bottom"'));
assert.ok(markup.includes('data-zero-anchor="bottom-left"'));
assert.ok(!markup.includes("data-placement-diagram"));
assert.ok(!markup.includes("dco-cnc-cut-preview__origin"));
assert.equal((markup.match(/dco-cnc-cut-preview__svg/g) || []).length, 1);

const cornerState = { cncMachine: "Router A", sheetWidthCm: 120, sheetLengthCm: 240 };
const cornerWorkspace = {
    cnc_machines: [{
        name: "Router A",
        machine_name: "Router A",
        width_cm: 200,
        length_cm: 400,
        enabled: true,
        work_zero_position: "Bottom Right",
        width_stop_side: "Right Side",
        length_stop_side: "Bottom Side",
        left_stop_cm: 99,
        right_stop_cm: 5,
        bottom_stop_cm: 10,
        top_stop_cm: 99,
    }],
};
const cornerPlacement = ux.placementPreviewPayload(cornerWorkspace, cornerState);
assert.strictEqual(cornerPlacement.offset_left_cm, 0);
assert.strictEqual(cornerPlacement.offset_bottom_cm, 160);
assert.strictEqual(cornerPlacement.right_clearance_cm, 80);
const cornerMarkup = ux.cutPathPreviewMarkup(program, { layout: "page", placement: cornerPlacement, zoom: 1 });
assert.ok(cornerMarkup.includes('transform="translate(0,1600)"'));
assert.ok(cornerMarkup.includes('data-stop-badge="right"'));
assert.ok(cornerMarkup.includes('data-stop-badge="bottom"'));
assert.ok(cornerMarkup.includes('data-stop-arrow="right"'));
assert.ok(cornerMarkup.includes('data-stop-arrow="bottom"'));
assert.ok(!cornerMarkup.includes('data-stop-badge="left"'));
assert.ok(!cornerMarkup.includes('data-stop-badge="top"'));
assert.ok(cornerMarkup.includes('data-zero-anchor="bottom-right"'));
assert.ok(cornerMarkup.includes('data-svg-x="2000"'));
assert.ok(cornerMarkup.includes('data-svg-y="4000"'));
assert.ok(cornerMarkup.includes("(0,0)"));
assert.ok(cornerMarkup.includes("80 cm") || cornerMarkup.includes("80 سم"));
assert.ok(!cornerMarkup.includes("<input"));
assert.ok(!cornerMarkup.includes("data-placement-diagram"));
assert.equal((cornerMarkup.match(/dco-cnc-cut-preview__svg/g) || []).length, 1);
assert.ok(!cornerMarkup.includes("Left Stop"));
assert.ok(!cornerMarkup.includes("Right Stop"));
assert.strictEqual(ux.validateSheetPlacementFits({
    cnc_machines: [{ ...cornerWorkspace.cnc_machines[0], work_zero_position: "Center" }],
}, cornerState).code, "work_zero_center_retired");
assert.ok(markup.includes("data-placement-caption"));
assert.ok(!markup.includes("dco-cnc-cut-preview__dim"));
assert.ok(!markup.includes("Left offset"));
// Path numbers stay on sheet-local geometry; geometry points are not rewritten in the program.
assert.strictEqual(program.operations[0].toolpaths[0].motions[0].x_mm, -2.5);
assert.ok(markup.includes("data-path-number=\"1\"") || markup.includes("data-path-number='1'") || /data-path-number="1"/.test(markup));

const zoomed = ux.clampCutPreviewZoom(1.5);
assert.strictEqual(zoomed, ux.clampCutPreviewZoom(1.5));

assert.ok(!panel.includes("placementDiagramMarkup"));
assert.ok(!panel.includes("data-placement-diagram"));
assert.ok(panel.includes("data-sheet-placement"));
assert.ok(css.includes(".dco-cnc-cut-preview__stop-badge"));
assert.ok(css.includes("font-size: 12px"));
assert.ok(!css.includes(".dco-cnc-cut-preview__stop-badge") || !/\.dco-cnc-cut-preview__stop-badge\s*\{[^}]*--cut-zoom/.test(css));

const comboProgram = {
    sheet_width_mm: 1830,
    sheet_length_mm: 2800,
    geometry_ready: true,
    ready: true,
    issues: [],
    operations: program.operations,
};
const zeroPoints = {
    "Bottom Left": ["0", "3100", "bottom-left"],
    "Bottom Right": ["2100", "3100", "bottom-right"],
    "Top Left": ["0", "0", "top-left"],
    "Top Right": ["2100", "0", "top-right"],
};
["Bottom Left", "Bottom Right", "Top Left", "Top Right"].forEach(zero => {
    ["Left Side", "Right Side"].forEach(widthSide => {
        ["Bottom Side", "Top Side"].forEach(lengthSide => {
            const combo = ux.placementPreviewPayload({
                cnc_machines: [{
                    name: "Router A",
                    machine_name: "Router A",
                    width_cm: 210,
                    length_cm: 310,
                    enabled: true,
                    work_zero_position: zero,
                    width_stop_side: widthSide,
                    length_stop_side: lengthSide,
                }],
            }, { cncMachine: "Router A", sheetWidthCm: 183, sheetLengthCm: 280 });
            const html = ux.cutPathPreviewMarkup(comboProgram, { layout: "page", placement: combo });
            const [zeroX, zeroY, anchor] = zeroPoints[zero];
            assert.ok(html.includes(`data-zero-anchor="${anchor}"`), zero);
            assert.ok(html.includes(`data-svg-x="${zeroX}"`), `${zero} x`);
            assert.ok(html.includes(`data-svg-y="${zeroY}"`), `${zero} y`);
            assert.ok(html.includes("(0,0)"));
            assert.equal(html.includes('data-stop-badge="left"'), widthSide === "Left Side");
            assert.equal(html.includes('data-stop-badge="right"'), widthSide === "Right Side");
            assert.equal(html.includes('data-stop-badge="bottom"'), lengthSide === "Bottom Side");
            assert.equal(html.includes('data-stop-badge="top"'), lengthSide === "Top Side");
            assert.equal(html.includes('data-stop-arrow="left"'), widthSide === "Left Side");
            assert.equal(html.includes('data-stop-arrow="right"'), widthSide === "Right Side");
            assert.equal(html.includes('data-stop-arrow="bottom"'), lengthSide === "Bottom Side");
            assert.equal(html.includes('data-stop-arrow="top"'), lengthSide === "Top Side");
            assert.ok(html.includes("27 cm") || html.includes("27 سم"));
            assert.ok(html.includes("30 cm") || html.includes("30 سم"));
            assert.ok(!html.includes("<input"));
            assert.ok(!html.includes("data-placement-diagram"));
            assert.equal((html.match(/dco-cnc-cut-preview__svg/g) || []).length, 1);
        });
    });
});

const overlayNodes = [{
    svgX: 2100,
    svgY: 3100,
    style: {},
    getAttribute(name) {
        return name === "data-svg-x" ? String(this.svgX) : String(this.svgY);
    },
}];
const measure = { viewBox: "", setAttribute(name, value) { this[name] = value; } };
const overlayHost = {
    querySelector(selector) {
        if (selector === "[data-placement-overlay]") {
            return { querySelectorAll() { return overlayNodes; } };
        }
        if (selector === "[data-measure-layer]") return measure;
        return null;
    },
};
const zoomedSvg = {
    box: "400 600 800 1200",
    getAttribute() { return this.box; },
};
ux.syncPlacementOverlay(overlayHost, zoomedSvg);
assert.strictEqual(measure.viewBox, "400 600 800 1200");
assert.strictEqual(overlayNodes[0].style.left, "212.5%");
assert.strictEqual(overlayNodes[0].style.top, "208.33333333333334%");
assert.ok(!String(overlayNodes[0].style.transform || "").includes("scale"));

console.log("dco_operational_files_sheet_placement.test.js passed");
