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

const windowObject = {
    document: { documentElement: { getAttribute() { return "rtl"; } } },
};
const calls = [];
windowObject.frappe = {
    call(options) {
        calls.push(options && options.args ? options.args : {});
        // Record the request only. Preview DOM painting is covered separately.
    },
};
vm.runInNewContext(
    fs.readFileSync(panelPath, "utf8"),
    { window: windowObject, frappe: windowObject.frappe },
    { filename: panelPath }
);
const ux = windowObject.AlmdinaOperationalFilesUX;
const panel = fs.readFileSync(panelPath, "utf8");
const css = fs.readFileSync(cssPath, "utf8");
const translations = fs.readFileSync(translationsPath, "utf8");

function motionChain(points, depth, closed) {
    const start = points[0];
    const motions = [
        { kind: "travel", x_mm: start[0], y_mm: start[1], depth_mm: null },
        { kind: "plunge", x_mm: start[0], y_mm: start[1], depth_mm: depth },
    ];
    points.slice(1).forEach(point => {
        motions.push({ kind: "cut", x_mm: point[0], y_mm: point[1], depth_mm: depth });
    });
    if (closed) {
        motions.push({ kind: "cut", x_mm: start[0], y_mm: start[1], depth_mm: depth });
    }
    const end = closed ? start : points[points.length - 1];
    motions.push({ kind: "retract", x_mm: end[0], y_mm: end[1], depth_mm: null });
    return motions;
}

function makeSeparateProgram() {
    return {
        sheet_width_mm: 1220,
        sheet_length_mm: 2440,
        operations: [{
            operation_key: "cut_path",
            toolpaths: [{
                path_key: "cut_path:a:outer",
                closed: true,
                ready: true,
                issues: [],
                piece_label: "A",
                piece_instance_id: "A",
                sequence: 1,
                motions: motionChain([[0, 0], [100, 0], [100, 80], [0, 80]], 6, true),
            }],
        }],
    };
}

function makeConnectedProgram() {
    return {
        sheet_width_mm: 1220,
        sheet_length_mm: 2440,
        operations: [
            {
                operation_key: "sheet_perimeter",
                toolpaths: [{
                    path_key: ux.SHEET_PERIMETER_PATH_KEY,
                    closed: true,
                    ready: true,
                    issues: [],
                    piece_label: "",
                    piece_instance_id: "",
                    sequence: 1,
                    motions: motionChain([[0, 0], [200, 0], [200, 120], [0, 120]], 6, true),
                }],
            },
            {
                operation_key: "cut_path",
                toolpaths: [{
                    path_key: "cut_path:center:internal",
                    closed: false,
                    ready: true,
                    issues: [],
                    piece_label: "",
                    piece_instance_id: "",
                    sequence: 1,
                    motions: motionChain([[50, 0], [50, 40]], 6, false),
                }],
            },
        ],
    };
}

assert.equal(ux.SHEET_PERIMETER_PATH_KEY, "cut_path:sheet_perimeter");
assert.equal(ux.SHEET_PERIMETER_OPERATION_KEY, "sheet_perimeter");
assert.equal(ux.CUT_PATH_INTERNAL_SEQUENCE_KEY, "cut_path:internals");
assert.deepEqual(
    ux.deriveCutPathSequenceFromOrder(["sheet_perimeter", "cut_path"]),
    [ux.SHEET_PERIMETER_PATH_KEY, ux.CUT_PATH_INTERNAL_SEQUENCE_KEY]
);
assert.ok(panel.includes("_cncSheetInteractionsBound"));
assert.ok(panel.includes("paintPerimeterJoinControls("));
assert.ok(panel.includes("applyPerimeterJoinMode("));
assert.ok(panel.includes("ensureSheetPerimeterOperation("));
assert.ok(!panel.includes("existing.outerHTML = markup"));
assert.ok(panel.includes("data-perimeter-join-mode"));

const sheetSeparate = ux.sheetState({
    operations: [{ operation_key: "cut_path", tool_preset: "Finish", preset_source: "factory", factory_preset: "Finish" }],
    paths: [{ path_key: "cut_path:a:outer", operation_key: "cut_path", tool_preset: "" }],
});
assert.equal(sheetSeparate.perimeterJoinMode, "separate");
assert.deepEqual(sheetSeparate.cutPathSequence, []);
assert.ok(!sheetSeparate.order.includes("sheet_perimeter"));

const sheetConnected = ux.sheetState({
    operations: [
        { operation_key: "cut_path", tool_preset: "Finish", preset_source: "factory", factory_preset: "Finish" },
    ],
    paths: [
        { path_key: "cut_path:a:outer", operation_key: "cut_path", tool_preset: "" },
        { path_key: ux.SHEET_PERIMETER_PATH_KEY, operation_key: "sheet_perimeter", is_sheet_perimeter: true },
    ],
    perimeter_join_mode: "connected",
    cut_path_sequence: [ux.CUT_PATH_INTERNAL_SEQUENCE_KEY, ux.SHEET_PERIMETER_PATH_KEY],
});
assert.ok(sheetConnected.order.includes("sheet_perimeter"));
assert.ok(sheetConnected.order.indexOf("sheet_perimeter") < sheetConnected.order.indexOf("cut_path"));
assert.deepEqual(
    sheetConnected.cutPathSequence,
    [ux.SHEET_PERIMETER_PATH_KEY, ux.CUT_PATH_INTERNAL_SEQUENCE_KEY]
);

const args = ux.sheetGenerateArgs(
    { doc: { name: "DCO-1" } },
    { cutting_plan: "PLAN-1", plan_revision: 3 },
    { sheet_no: 1 },
    sheetConnected
);
assert.equal(args.perimeter_join_mode, "connected");
assert.deepEqual(
    args.cut_path_sequence,
    [ux.SHEET_PERIMETER_PATH_KEY, ux.CUT_PATH_INTERNAL_SEQUENCE_KEY]
);
assert.ok(args.operation_order.includes("sheet_perimeter"));
assert.equal(
    ux.sheetGenerateArgs(
        { doc: { name: "DCO-1" } },
        { cutting_plan: "PLAN-1", plan_revision: 3 },
        { sheet_no: 1 },
        sheetSeparate
    ).cut_path_sequence,
    null
);

const reordered = Object.assign({}, sheetConnected, {
    order: ["cut_path", "sheet_perimeter"],
});
ux.syncCutPathSequence(reordered);
assert.deepEqual(
    reordered.cutPathSequence,
    [ux.CUT_PATH_INTERNAL_SEQUENCE_KEY, ux.SHEET_PERIMETER_PATH_KEY]
);

const separatePaths = ux.collectPhysicalPaths(makeSeparateProgram());
const connectedPaths = ux.collectPhysicalPaths(makeConnectedProgram());
assert.equal(separatePaths.length, 1);
assert.equal(connectedPaths.length, 2);
assert.ok(connectedPaths.some(item => item.path_key === ux.SHEET_PERIMETER_PATH_KEY));
assert.equal(
    connectedPaths.find(item => item.is_sheet_perimeter).operation_key,
    "sheet_perimeter"
);
assert.equal(
    ux.pathDisplayLabel(connectedPaths.find(item => item.is_sheet_perimeter)),
    "Sheet Perimeter Cut"
);

const preview = ux.cutPathPreviewMarkup(makeConnectedProgram(), {
    selectedExecutionPathId: connectedPaths.find(item => item.is_sheet_perimeter).execution_path_id,
});
assert.ok(preview.includes(String(connectedPaths.find(item => item.is_sheet_perimeter).path_number)));

// In-place perimeter control updates must keep the fieldset node (event host) alive.
const radios = {
    separate: {
        value: "separate",
        checked: true,
        disabled: false,
        getAttribute(name) {
            return name === "data-perimeter-join-mode" ? "separate" : null;
        },
    },
    connected: {
        value: "connected",
        checked: false,
        disabled: false,
        getAttribute(name) {
            return name === "data-perimeter-join-mode" ? "connected" : null;
        },
    },
};
const fieldset = {
    id: "perimeter-host",
    replaced: 0,
    warning: null,
    querySelector(selector) {
        if (selector === "[data-perimeter-early-warning]") return this.warning;
        if (selector === "[data-perimeter-confirm]" && this.warning) {
            return this.warning.querySelector("[data-perimeter-confirm]");
        }
        return null;
    },
    querySelectorAll(selector) {
        if (selector === "[data-perimeter-join-mode]") return [radios.separate, radios.connected];
        return [];
    },
    insertAdjacentHTML(position, html) {
        if (String(html).includes("data-perimeter-early-warning")) {
            this.warning = {
                html: String(html),
                querySelector(sel) {
                    if (sel === "[data-perimeter-confirm]") {
                        return {
                            checked: String(html).includes("checked"),
                            disabled: String(html).includes("disabled"),
                        };
                    }
                    return null;
                },
            };
        }
    },
};
const article = {
    fieldset,
    querySelector(selector) {
        if (selector === "[data-perimeter-join]") return this.fieldset;
        if (selector === ".dco-operational-layer__head") return { insertAdjacentHTML() {} };
        if (selector === ".dco-operational-layer__paths") return { hidden: false };
        if (selector === "[data-toggle-layer]") {
            return { setAttribute() {}, textContent: "" };
        }
        return null;
    },
};
Object.defineProperty(fieldset, "outerHTML", {
    set() {
        fieldset.replaced += 1;
    },
    get() {
        return "<fieldset data-perimeter-join></fieldset>";
    },
});

const state = Object.assign({}, sheetSeparate, {
    perimeterJoinMode: "separate",
    cutPathSequence: [],
    expanded: { cut_path: true },
    program: makeSeparateProgram(),
    overrides: {},
    customizing: {},
    selectedPathKey: "",
    selectedExecutionPathId: "",
});
ux.paintPerimeterJoinControls(article, state, true);
assert.equal(fieldset.replaced, 0);
assert.equal(radios.separate.checked, true);
assert.equal(radios.connected.checked, false);

const dialog = {
    fields_dict: {
        body: {
            $wrapper: [{
                querySelector(selector) {
                    if (selector === '.dco-operational-layer[data-layer="cut_path"]') return article;
                    if (selector === "[data-sheet-preview]") {
                        return {
                            __cutPreviewZoom: 1.25,
                            __cutPreviewPan: { x: 12, y: -4 },
                            getAttribute() { return "page"; },
                            __cutPreviewLayout: "page",
                            __cutPreviewHidden: [],
                            set innerHTML(value) { this._html = value; },
                            get innerHTML() { return this._html || ""; },
                        };
                    }
                    return null;
                },
            }],
        },
    },
    _almdinaSheet: null,
    _cncProgramPreviewRequest: 0,
};
const workspace = {
    can_prepare: true,
    cutting_plan: "PLAN-1",
    plan_revision: 1,
    presets: [{ name: "Finish", enabled: 1, tool_diameter_mm: 5 }],
};
const sheet = {
    sheet_no: 1,
    status: "Draft",
    operations: [{ operation_key: "cut_path", dxf_layer: "CUT_PATH", path_count: 1 }],
    paths: [{ path_key: "cut_path:a:outer", operation_key: "cut_path" }],
};
const frm = { doc: { name: "DCO-1" } };

state.order = ["cut_path"];
state.operations = { cut_path: "Finish" };
state.sources = { cut_path: "factory" };
state.factoryPresets = { cut_path: "Finish" };
const beforeCalls = calls.length;
ux.applyPerimeterJoinMode(frm, dialog, workspace, sheet, state, "connected");
assert.equal(state.perimeterJoinMode, "connected");
assert.ok(state.order.includes("sheet_perimeter"));
assert.deepEqual(
    state.cutPathSequence,
    [ux.SHEET_PERIMETER_PATH_KEY, ux.CUT_PATH_INTERNAL_SEQUENCE_KEY]
);
assert.equal(radios.connected.checked, true);
assert.equal(radios.separate.checked, false);
assert.equal(fieldset.replaced, 0, "radio host must survive join-mode updates");
assert.ok(calls.length > beforeCalls);
assert.equal(calls[calls.length - 1].perimeter_join_mode, "connected");
assert.deepEqual(
    calls[calls.length - 1].cut_path_sequence,
    [ux.SHEET_PERIMETER_PATH_KEY, ux.CUT_PATH_INTERNAL_SEQUENCE_KEY]
);

// Second toggle after another in-place paint (async sync equivalent).
ux.paintPerimeterJoinControls(article, state, true);
ux.applyPerimeterJoinMode(frm, dialog, workspace, sheet, state, "separate");
assert.equal(state.perimeterJoinMode, "separate");
assert.deepEqual(state.cutPathSequence, []);
assert.ok(!state.order.includes("sheet_perimeter"));
assert.equal(calls[calls.length - 1].perimeter_join_mode, "separate");
assert.equal(calls[calls.length - 1].cut_path_sequence, null);
assert.equal(fieldset.replaced, 0);

const layerRows = {};
const listBody = {
    rows: [],
    querySelector(selector) {
        if (selector === ".dco-operational-sheet__selection") return { textContent: "" };
        if (selector === "[data-sheet-preview]") return null;
        const layerMatch = String(selector).match(/data-layer="([^"]+)"/);
        if (!layerMatch) return null;
        const layerKey = layerMatch[1];
        return {
            querySelector(inner) {
                if (inner === ".dco-operational-layer__paths") {
                    return {
                        set innerHTML(value) {
                            this._html = value;
                            layerRows[layerKey] = [...String(value).matchAll(/data-path-key="([^"]+)"[^>]*data-path-number="([^"]+)"/g)]
                                .map(match => ({
                                    path_key: match[1],
                                    number: match[2],
                                }));
                            listBody.rows = Object.keys(layerRows)
                                .sort()
                                .flatMap(key => layerRows[key]);
                        },
                        get innerHTML() { return this._html || ""; },
                    };
                }
                if (inner === ".dco-operational-layer__head span") return { textContent: "" };
                if (inner === "[data-perimeter-join]") return fieldset;
                if (inner === ".dco-operational-layer__head") return { insertAdjacentHTML() {} };
                return null;
            },
        };
    },
    querySelectorAll() {
        return [];
    },
};
state.order = ["sheet_perimeter", "cut_path"];
ux.syncPhysicalPathList(listBody, workspace, sheet, state, makeConnectedProgram(), null);
assert.equal(fieldset.replaced, 0, "syncPhysicalPathList must not replace perimeter radios");
assert.ok(layerRows.sheet_perimeter.some(row => row.path_key === ux.SHEET_PERIMETER_PATH_KEY));
assert.ok(layerRows.cut_path.every(row => row.path_key !== ux.SHEET_PERIMETER_PATH_KEY));
assert.deepEqual(
    [...(layerRows.sheet_perimeter || []), ...(layerRows.cut_path || [])].map(row => row.number),
    ux.collectPhysicalPaths(makeConnectedProgram()).map(item => String(item.path_number))
);

assert.ok(css.includes(".dco-operational-perimeter"));
assert.ok(translations.includes("طريقة قص محيط اللوح"));
assert.ok(translations.includes("محيط متصل"));
assert.ok(translations.includes("محيط غير متصل"));
assert.ok(translations.includes("قص محيط اللوح"));

console.log("dco_operational_files_perimeter.test.js: ok");
