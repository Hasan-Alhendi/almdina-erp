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
const translationsPath = path.join(root, "translations/ar.csv");
const windowObject = {};
vm.runInNewContext(fs.readFileSync(panelPath, "utf8"), { window: windowObject }, { filename: panelPath });
const ux = windowObject.AlmdinaOperationalFilesUX;
const panel = fs.readFileSync(panelPath, "utf8");
const translations = fs.readFileSync(translationsPath, "utf8");

assert.ok(typeof ux.collectPhysicalPaths === "function");
assert.ok(typeof ux.findPhysicalPath === "function");
assert.ok(typeof ux.highlightCutPreview === "function");
assert.ok(typeof ux.applyExecutionSelection === "function");
assert.ok(panel.includes("execution_path_id"));
assert.ok(panel.includes("data-execution-path-id"));
assert.ok(panel.includes("collectPhysicalPaths("));
assert.ok(translations.includes("المسار {0}"));
assert.ok(translations.includes("مسار مشترك"));
assert.ok(translations.includes("التمريرة {0}: العمق {1} مم"));

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

function makeCollisionProgram() {
    return {
        sheet_width_mm: 400,
        sheet_length_mm: 300,
        geometry_ready: true,
        ready: true,
        issues: [],
        operations: [
            {
                operation_key: "liner",
                toolpaths: [{
                    path_key: "liner:merged",
                    operation_key: "liner",
                    sequence: 1,
                    piece_label: "1.1",
                    piece_instance_id: "piece-a",
                    closed: false,
                    ready: true,
                    issues: [],
                    preset_name: "Liner",
                    motions: motionChain([[5, 5], [40, 5]], 3, false),
                }],
            },
            {
                operation_key: "recessed_handle_cutout",
                toolpaths: [{
                    path_key: "recessed_handle_cutout:a",
                    operation_key: "recessed_handle_cutout",
                    sequence: 1,
                    piece_label: "1.1",
                    piece_instance_id: "piece-a",
                    closed: true,
                    ready: true,
                    issues: [],
                    preset_name: "Handle",
                    motions: motionChain([[50, 40], [70, 40], [70, 60], [50, 60]], 4, true),
                }],
            },
            {
                operation_key: "back_groove",
                toolpaths: [{
                    path_key: "back_groove:a",
                    operation_key: "back_groove",
                    sequence: 1,
                    piece_label: "1.2",
                    piece_instance_id: "piece-b",
                    closed: false,
                    ready: true,
                    issues: [],
                    preset_name: "Groove",
                    motions: motionChain([[10, 90], [90, 90]], 2, false),
                }],
            },
            {
                operation_key: "cut_path",
                toolpaths: [
                    {
                        path_key: "cut_path:shared-key",
                        operation_key: "cut_path",
                        sequence: 1,
                        piece_label: "",
                        piece_instance_id: "",
                        closed: false,
                        ready: true,
                        issues: [],
                        preset_name: "Finish",
                        motions: motionChain([[20, 20], [80, 20], [80, 50]], 6, false),
                    },
                    {
                        path_key: "cut_path:shared-key",
                        operation_key: "cut_path",
                        sequence: 2,
                        piece_label: "",
                        piece_instance_id: "",
                        closed: false,
                        ready: true,
                        issues: [],
                        preset_name: "Finish",
                        motions: motionChain([[20, 20], [20, 70], [60, 70]], 6, false),
                    },
                    {
                        path_key: "cut_path:multi-depth",
                        operation_key: "cut_path",
                        sequence: 3,
                        piece_label: "2.1",
                        piece_instance_id: "piece-c",
                        closed: true,
                        ready: true,
                        issues: [],
                        preset_name: "Finish",
                        motions: [
                            ...motionChain([[100, 20], [140, 20], [140, 60], [100, 60]], 6, true),
                            ...motionChain([[100, 20], [140, 20], [140, 60], [100, 60]], 12, true),
                            ...motionChain([[100, 20], [140, 20], [140, 60], [100, 60]], 18, true),
                        ],
                    },
                    {
                        path_key: "cut_path:connected-a",
                        operation_key: "cut_path",
                        sequence: 4,
                        piece_label: "2.2",
                        piece_instance_id: "piece-d",
                        closed: false,
                        ready: true,
                        issues: [],
                        preset_name: "Finish",
                        motions: [
                            ...motionChain([[160, 10], [190, 10]], 8, false),
                            ...motionChain([[190, 10], [190, 40]], 8, false),
                        ],
                    },
                ],
            },
        ],
    };
}

function createDomFromMarkup(markup) {
    const selected = new Set();
    const nodes = [];
    const attributePattern = /<([a-zA-Z0-9]+)([^>]*)>/g;
    let match = attributePattern.exec(markup);
    while (match) {
        const attrs = match[2] || "";
        const getAttribute = name => {
            const found = attrs.match(new RegExp(`${name}="([^"]*)"`));
            return found ? found[1] : null;
        };
        const classAttr = getAttribute("class") || "";
        const node = {
            tagName: match[1],
            className: classAttr,
            classList: {
                toggle(name, force) {
                    const parts = new Set(String(node.className || "").split(/\s+/).filter(Boolean));
                    if (force) parts.add(name);
                    else parts.delete(name);
                    node.className = Array.from(parts).join(" ");
                    const id = getAttribute("data-execution-path-id");
                    if (name === "is-cnc-path-selected" && id) {
                        if (force) selected.add(id);
                        else selected.delete(id);
                    }
                },
                contains(name) {
                    return String(node.className || "").split(/\s+/).includes(name);
                },
            },
            getAttribute,
        };
        if (getAttribute("data-execution-path-id")) nodes.push(node);
        match = attributePattern.exec(markup);
    }
    return {
        markup,
        nodes,
        querySelectorAll(selector) {
            if (selector === "[data-execution-path-id]") return nodes.slice();
            return [];
        },
        querySelector(selector) {
            if (selector === "[data-sheet-preview]") return this;
            return null;
        },
        selectedIds() {
            return Array.from(selected);
        },
        litIds() {
            return nodes
                .filter(node => node.classList.contains("is-cnc-path-selected"))
                .map(node => node.getAttribute("data-execution-path-id"));
        },
    };
}

const program = makeCollisionProgram();
const executions = ux.collectCutExecutions(program);
const physical = ux.collectPhysicalPaths(program);

assert.equal(executions.length, 10, "raw plunge cycles stay available for NC-order inspection");
assert.equal(physical.length, 8, "multi-depth collapses; retract-separated geometries stay split");

const ten = physical.find(item => item.sequence === 1 && item.operation_key === "cut_path");
const eleven = physical.find(item => item.sequence === 2 && item.operation_key === "cut_path");
assert.ok(ten, "path 10 geometry exists");
assert.ok(eleven, "path 11 geometry exists");
assert.equal(ten.path_key, eleven.path_key, "settings identity can be shared");
assert.notEqual(ten.execution_path_id, eleven.execution_path_id, "geometric identities must differ");
assert.notEqual(ten.path_number, eleven.path_number);
assert.equal(ten.shared, true);
assert.equal(eleven.shared, true);

const multiDepth = physical.find(item => item.path_key === "cut_path:multi-depth");
assert.ok(multiDepth);
assert.equal(multiDepth.pass_count, 3);
assert.deepEqual(
    multiDepth.passes.map(pass => pass.depth_mm),
    [6, 12, 18],
    "depth-pass order is preserved"
);

const connected = physical.filter(item => item.path_key === "cut_path:connected-a");
assert.equal(connected.length, 2, "retract between segments keeps separate physical paths");
assert.deepEqual(connected[0].end, connected[1].start, "endpoint-to-start continuity must not merge executions");
assert.notEqual(connected[0].execution_path_id, connected[1].execution_path_id);

const sameStartDistinct = physical.filter(item => (
    item.operation_key === "cut_path"
    && Number(item.start[0]) === 20
    && Number(item.start[1]) === 20
));
assert.equal(sameStartDistinct.length, 2);
assert.notEqual(sameStartDistinct[0].execution_path_id, sameStartDistinct[1].execution_path_id);

assert.ok(physical.some(item => item.operation_key === "liner"));
assert.ok(physical.some(item => item.operation_key === "recessed_handle_cutout"));
assert.ok(physical.some(item => item.operation_key === "back_groove"));

const markupTen = ux.cutPathPreviewMarkup(program, {
    selectedExecutionPathId: ten.execution_path_id,
    markerScope: "cnc-id-ten",
});
const markupEleven = ux.cutPathPreviewMarkup(program, {
    selectedExecutionPathId: eleven.execution_path_id,
    markerScope: "cnc-id-eleven",
});
assert.ok(markupTen.includes(`data-execution-path-id="${ten.execution_path_id}"`));
assert.ok(markupEleven.includes(`data-execution-path-id="${eleven.execution_path_id}"`));
assert.ok(markupTen.includes(`<span>${ten.path_number}</span>`));
assert.ok(markupEleven.includes(`<span>${eleven.path_number}</span>`));
assert.ok(markupTen.includes("is-cnc-path-selected"));
assert.ok(markupEleven.includes("is-cnc-path-selected"));

const selectedInTen = [...markupTen.matchAll(/class="([^"]*is-cnc-path-selected[^"]*)"[^>]*data-execution-path-id="([^"]+)"/g)]
    .map(match => match[2]);
const selectedInTenAlt = [...markupTen.matchAll(/data-execution-path-id="([^"]+)"[^>]*class="([^"]*is-cnc-path-selected[^"]*)"/g)]
    .map(match => match[1]);
const litTen = new Set([...selectedInTen, ...selectedInTenAlt]);
assert.ok(litTen.has(ten.execution_path_id));
assert.ok(!litTen.has(eleven.execution_path_id), "selecting 10 must not light 11");

const selectedInEleven = new Set([
    ...[...markupEleven.matchAll(/class="([^"]*is-cnc-path-selected[^"]*)"[^>]*data-execution-path-id="([^"]+)"/g)].map(m => m[2]),
    ...[...markupEleven.matchAll(/data-execution-path-id="([^"]+)"[^>]*class="([^"]*is-cnc-path-selected[^"]*)"/g)].map(m => m[1]),
]);
assert.ok(selectedInEleven.has(eleven.execution_path_id));
assert.ok(!selectedInEleven.has(ten.execution_path_id), "selecting 11 must not light 10");

const host = { innerHTML: "" };
ux.paintCutPathPreview(host, {
    status: "ready",
    program,
    selectedExecutionPathId: ten.execution_path_id,
});
const previewDom = createDomFromMarkup(host.innerHTML);
ux.highlightCutPreview(previewDom, { selectedExecutionPathId: ten.execution_path_id });
assert.deepEqual(
    Array.from(new Set(previewDom.litIds())),
    [ten.execution_path_id],
    "DOM highlight lights only the selected execution identity"
);
ux.highlightCutPreview(previewDom, { selectedExecutionPathId: eleven.execution_path_id });
assert.deepEqual(
    Array.from(new Set(previewDom.litIds())),
    [eleven.execution_path_id],
    "switching selection clears the previous geometric path"
);

const listBody = {
    rows: [],
    querySelector(selector) {
        if (selector === ".dco-operational-sheet__selection") {
            return { textContent: "" };
        }
        if (selector === "[data-sheet-preview]") {
            return previewDom;
        }
        const layerMatch = String(selector).match(/data-layer="([^"]+)"/);
        if (layerMatch) {
            const key = layerMatch[1];
            return {
                querySelector(inner) {
                    if (inner === ".dco-operational-layer__paths") {
                        return {
                            get innerHTML() {
                                return this._html || "";
                            },
                            set innerHTML(value) {
                                this._html = value;
                                listBody.rows = listBody.rows.filter(row => row.operation !== key);
                                const rowMatches = [...String(value).matchAll(/data-execution-path-id="([^"]+)"/g)];
                                rowMatches.forEach(match => {
                                    listBody.rows.push({
                                        operation: key,
                                        execution_path_id: match[1],
                                        className: "",
                                        getAttribute(name) {
                                            if (name === "data-execution-path-id") return this.execution_path_id;
                                            return null;
                                        },
                                        classList: {
                                            toggle(token, force) {
                                                this.parent.className = force ? token : "";
                                            },
                                        },
                                        parent: null,
                                        scrollIntoView() {
                                            listBody.scrolledTo = this.execution_path_id;
                                        },
                                    });
                                    const row = listBody.rows[listBody.rows.length - 1];
                                    row.classList.toggle = row.classList.toggle.bind({ parent: row });
                                });
                            },
                        };
                    }
                    if (inner === ".dco-operational-layer__head span") {
                        return { textContent: "" };
                    }
                    return null;
                },
            };
        }
        return null;
    },
    querySelectorAll(selector) {
        if (selector === ".dco-operational-path") return listBody.rows;
        if (selector === ".dco-operational-path[data-execution-path-id]") return listBody.rows;
        return [];
    },
};

const state = {
    order: ["liner", "recessed_handle_cutout", "back_groove", "cut_path"],
    operations: {
        liner: "Liner",
        recessed_handle_cutout: "Handle",
        back_groove: "Groove",
        cut_path: "Finish",
    },
    overrides: {},
    expanded: {},
    selectedPathKey: "",
    selectedExecutionPathId: "",
    program: null,
    customizing: {},
};
const workspace = { can_prepare: true, presets: [] };
const sheet = { paths: [], operations: [] };

ux.syncPhysicalPathList(listBody, workspace, sheet, state, program, null);
assert.equal(state.program, program);
assert.ok(listBody.rows.some(row => row.execution_path_id === ten.execution_path_id));
assert.ok(listBody.rows.some(row => row.execution_path_id === eleven.execution_path_id));

assert.equal(
    ux.applyExecutionSelection(listBody, workspace, sheet, state, ten.execution_path_id),
    true
);
assert.equal(state.selectedExecutionPathId, ten.execution_path_id);
assert.equal(state.selectedPathKey, ten.path_key);
assert.equal(listBody.scrolledTo, ten.execution_path_id);
assert.deepEqual(Array.from(new Set(previewDom.litIds())), [ten.execution_path_id]);

assert.equal(
    ux.applyExecutionSelection(listBody, workspace, sheet, state, eleven.execution_path_id),
    true
);
assert.equal(state.selectedExecutionPathId, eleven.execution_path_id);
assert.deepEqual(Array.from(new Set(previewDom.litIds())), [eleven.execution_path_id]);

const hidden = ux.cutPathPreviewMarkup(program, {
    selectedExecutionPathId: ten.execution_path_id,
    hiddenOperations: ["liner"],
    markerScope: "cnc-id-hidden",
});
assert.ok(!hidden.includes('data-operation-key="liner"') || hidden.includes('data-cut-layer="liner"'));
assert.ok(hidden.includes(`data-execution-path-id="${ten.execution_path_id}"`));

const zoomHost = {
    innerHTML: "",
    getAttribute() { return "page"; },
    querySelector(selector) {
        if (selector === "[data-cut-stage]") {
            const match = this.innerHTML.match(/data-cut-stage[^>]*style="([^"]*)"/);
            const styleText = (match && match[1]) || "";
            const props = {};
            styleText.split(";").forEach(part => {
                const [key, value] = part.split(":");
                if (key && value) props[key.trim()] = value.trim();
            });
            return {
                style: {
                    getPropertyValue(name) { return props[name] || ""; },
                    setProperty(name, value) { props[name] = String(value); },
                    transform: "",
                },
            };
        }
        if (selector === '[data-cut-zoom="out"]' || selector === '[data-cut-zoom="in"]') {
            return { disabled: false, addEventListener() {} };
        }
        return null;
    },
    querySelectorAll() { return []; },
};
ux.paintCutPathPreview(zoomHost, {
    status: "ready",
    program,
    layout: "page",
    selectedExecutionPathId: ten.execution_path_id,
    zoom: 0.85,
});
assert.equal(zoomHost.__cutPreviewZoom, 0.85);
ux.paintCutPathPreview(zoomHost, {
    status: "ready",
    program,
    layout: "page",
    selectedExecutionPathId: eleven.execution_path_id,
});
assert.equal(zoomHost.__cutPreviewZoom, 0.85, "selection repaint preserves zoom");
assert.ok(zoomHost.innerHTML.includes(eleven.execution_path_id));
assert.ok(!zoomHost.innerHTML.includes(`is-cnc-path-selected" data-execution-path-id="${ten.execution_path_id}"`)
    || zoomHost.innerHTML.includes(`data-execution-path-id="${eleven.execution_path_id}"`));

const afterPreset = ux.collectPhysicalPaths(program);
assert.deepEqual(
    afterPreset.map(item => item.execution_path_id),
    physical.map(item => item.execution_path_id),
    "preset/UI identity rebuild must not invent new NC geometry"
);
assert.equal(ux.collectCutExecutions(program).length, executions.length);

assert.ok(!panel.includes("cutter_center_paths"));
assert.ok(panel.includes("selectedExecutionPathId"));

console.log("dco_operational_files_path_identity.test.js passed");
