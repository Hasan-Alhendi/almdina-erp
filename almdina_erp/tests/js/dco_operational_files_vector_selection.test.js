"use strict";

const assert = require("assert");
const fs = require("fs");
const path = require("path");
const vm = require("vm");

const root = path.resolve(__dirname, "../..");
const windowObject = {};
vm.runInNewContext(
    fs.readFileSync(path.join(root, "public/js/door_cutting_order/cnc/door_cutting_order_operational_files_ux.js"), "utf8"),
    { window: windowObject },
    { filename: "door_cutting_order_operational_files_ux.js" }
);
vm.runInNewContext(
    fs.readFileSync(path.join(root, "public/js/cnc/artcam_machining_ux.js"), "utf8"),
    { window: windowObject },
    { filename: "artcam_machining_ux.js" }
);
const ux = windowObject.AlmdinaOperationalFilesUX;
const artcam = windowObject.AlmdinaArtcamMachining;
const artcamSource = fs.readFileSync(path.join(root, "public/js/cnc/artcam_machining_ux.js"), "utf8");
assert.ok(artcamSource.includes("silent: true"), "handled server errors must not open Frappe's second popup");

function element(attrs, parent) {
    const node = {
        attrs,
        parent,
        className: attrs.class || "",
        getAttribute(name) {
            return Object.prototype.hasOwnProperty.call(attrs, name) ? String(attrs[name]) : null;
        },
        classList: {
            contains(name) {
                return node.className.split(/\s+/).includes(name);
            },
            toggle(name, force) {
                const parts = new Set(node.className.split(/\s+/).filter(Boolean));
                const enabled = force == null ? !parts.has(name) : Boolean(force);
                if (enabled) parts.add(name);
                else parts.delete(name);
                node.className = Array.from(parts).join(" ");
            },
        },
    };
    return node;
}

function viewBoxOf(markup) {
    return markup.match(/viewBox="([^"]+)"/)[1].split(/\s+/).map(Number);
}

const open = [[0, 0], [10, 0], [10, 5]];
const openId = ux.geometryFingerprint(open, false);
assert.equal(openId, ux.geometryFingerprint([[10, 5], [10, 0], [0, 0]], false));
assert.equal(
    ux.buildExecutionPathId("cut_path", "cut_path:open", 1, openId, 0),
    ux.buildExecutionPathId("cut_path", "cut_path:open", 1, ux.geometryFingerprint(open.slice().reverse(), false), 0)
);
const closed = [[0, 0], [4, 0], [4, 4], [0, 0]];
assert.equal(
    ux.geometryFingerprint(closed, true),
    ux.geometryFingerprint([[4, 4], [4, 0], [0, 0], [4, 4]], true)
);
assert.notEqual(openId, ux.geometryFingerprint([[0, 0], [8, 0]], false));

const uncalculated = ux.cutPathPreviewMarkup({
    sheet_width_mm: 120,
    sheet_length_mm: 80,
    geometry_ready: true,
    ready: true,
    operations: [{
        operation_key: "cut_path",
        toolpaths: [{
            path_key: "cut_path:raw",
            operation_key: "cut_path",
            closed: false,
            ready: false,
            points: [[-6, 4], [30, 4]],
            motions: [],
        }],
    }],
}, { layout: "page" });
assert.ok(uncalculated.includes('data-vector-id="cut_path:raw"'));
assert.ok(uncalculated.includes("-6,4"));
const rawBox = viewBoxOf(uncalculated);
assert.ok(rawBox[0] < -6, "a cutter path left of the sheet stays inside the viewBox");
assert.ok(uncalculated.includes("max-inline-size:390px"));

const tall = ux.cutPathPreviewMarkup({
    sheet_width_mm: 100,
    sheet_length_mm: 400,
    geometry_ready: true,
    operations: [{
        operation_key: "cut_path",
        toolpaths: [{ path_key: "cut_path:tall", closed: false, points: [[10, 10], [10, 390]], motions: [] }],
    }],
}, { layout: "page" });
const wide = ux.cutPathPreviewMarkup({
    sheet_width_mm: 400,
    sheet_length_mm: 100,
    geometry_ready: true,
    operations: [{
        operation_key: "cut_path",
        toolpaths: [{ path_key: "cut_path:wide", closed: false, points: [[10, 10], [390, 10]], motions: [] }],
    }],
}, { layout: "page" });
const tallBox = viewBoxOf(tall);
const wideBox = viewBoxOf(wide);
assert.ok(tallBox[3] > tallBox[2]);
assert.ok(wideBox[2] > wideBox[3]);
assert.ok(tall.includes(`aspect-ratio:${tallBox[2]} / ${tallBox[3]}`));

const above = ux.cutPathPreviewMarkup({
    sheet_width_mm: 100,
    sheet_length_mm: 80,
    geometry_ready: true,
    operations: [{
        operation_key: "cut_path",
        toolpaths: [{ path_key: "cut_path:above", closed: false, points: [[10, 90], [20, 90]], motions: [] }],
    }],
}, { layout: "page" });
assert.ok(viewBoxOf(above)[1] < 0, "geometry above the sheet is not clipped");

const sourceLineProgram = {
    sheet_width_mm: 100,
    sheet_length_mm: 80,
    geometry_ready: true,
    operations: [{
        operation_key: "recessed_handle_cutout",
        toolpaths: [{
            path_key: "recessed_handle_cutout:a:primary",
            operation_key: "recessed_handle_cutout",
            closed: false,
            ready: true,
            display_paths: [[[10, 40], [70, 40]]],
            points: [[10, 30], [70, 30], [70, 50], [10, 50]],
            motions: [
                { kind: "plunge", x_mm: 10, y_mm: 30, depth_mm: 3 },
                { kind: "cut", x_mm: 70, y_mm: 30, depth_mm: 3 },
                { kind: "cut", x_mm: 70, y_mm: 50, depth_mm: 3 },
                { kind: "cut", x_mm: 10, y_mm: 50, depth_mm: 3 },
                { kind: "retract", x_mm: 10, y_mm: 50, depth_mm: null },
            ],
        }],
    }],
};
const sourceLinePhysical = ux.collectPhysicalPaths(sourceLineProgram)[0];
assert.deepEqual(sourceLinePhysical.points, [[10, 30], [70, 30], [70, 50], [10, 50]]);
assert.deepEqual(sourceLinePhysical.display_paths, [[[10, 40], [70, 40]]]);
const sourceLineMarkup = ux.cutPathPreviewMarkup(sourceLineProgram, { layout: "page" });
assert.ok(!sourceLineMarkup.includes('points="10,40 70,40"'));
assert.ok(sourceLineMarkup.includes('points="10,30 70,30 70,50 10,50"'));
assert.ok(!sourceLineMarkup.includes("is-dxf-display-geometry"));
sourceLineProgram.operations[0].toolpaths[0].ready = false;
const pendingDxfMarkup = ux.cutPathPreviewMarkup(sourceLineProgram, { layout: "page" });
assert.ok(pendingDxfMarkup.includes('points="10,40 70,40"'));
assert.ok(!pendingDxfMarkup.includes('points="10,30 70,30 70,50 10,50"'));
assert.ok(pendingDxfMarkup.includes("is-dxf-display-geometry"));

function board() {
    const preview = element({ "data-sheet-preview": "" }, null);
    const groupA = element({
        "data-execution-path": "cut_path:a",
        "data-vector-id": "cut_path:a",
        "data-execution-path-id": "exec-a",
        class: "dco-cnc-cut-preview__execution",
    }, preview);
    const hitA = element({
        "data-execution-path": "cut_path:a",
        "data-vector-id": "cut_path:a",
        class: "dco-cnc-cut-preview__hit",
    }, groupA);
    const groupLiner = element({
        "data-execution-path": "liner:a",
        "data-vector-id": "liner:a",
        "data-execution-path-id": "exec-liner-a",
        class: "dco-cnc-cut-preview__execution",
    }, preview);
    const hitLiner = element({
        "data-execution-path": "liner:a",
        "data-vector-id": "liner:a",
        class: "dco-cnc-cut-preview__hit",
    }, groupLiner);
    const groupHandle = element({
        "data-execution-path": "recessed_handle_cutout:a",
        "data-vector-id": "recessed_handle_cutout:a",
        "data-execution-path-id": "exec-handle-a",
        class: "dco-cnc-cut-preview__execution",
    }, preview);
    const hitHandle = element({
        "data-execution-path": "recessed_handle_cutout:a",
        "data-vector-id": "recessed_handle_cutout:a",
        class: "dco-cnc-cut-preview__hit",
    }, groupHandle);
    const groupPerimeter = element({
        "data-execution-path": "cut_path:sheet_perimeter",
        "data-vector-id": "cut_path:sheet_perimeter",
        "data-execution-path-id": "exec-sheet-perimeter",
        class: "dco-cnc-cut-preview__execution",
    }, preview);
    const hitPerimeter = element({
        "data-execution-path": "cut_path:sheet_perimeter",
        "data-vector-id": "cut_path:sheet_perimeter",
        class: "dco-cnc-cut-preview__hit",
    }, groupPerimeter);
    const groupShared = element({
        "data-execution-path": "cut_path:shared",
        "data-vector-id": "cut_path:shared",
        "data-execution-path-id": "exec-shared-1",
        class: "dco-cnc-cut-preview__execution",
    }, preview);
    const groupSharedAgain = element({
        "data-execution-path": "cut_path:shared",
        "data-vector-id": "cut_path:shared",
        "data-execution-path-id": "exec-shared-2",
        class: "dco-cnc-cut-preview__execution",
    }, preview);
    const hidden = element({
        "data-execution-path": "cut_path:hidden",
        "data-vector-id": "cut_path:hidden",
        "data-execution-path-id": "exec-hidden",
        class: "dco-cnc-cut-preview__execution is-association-hidden",
    }, preview);
    const hitHidden = element({
        "data-execution-path": "cut_path:hidden",
        "data-vector-id": "cut_path:hidden",
    }, hidden);
    const groups = [groupA, groupLiner, groupHandle, groupPerimeter, groupShared, groupSharedAgain, hidden];
    preview.querySelectorAll = () => groups;
    const source = { value: "selected_vectors" };
    const count = { textContent: "" };
    const body = {
        querySelector(selector) {
            if (selector === "[data-sheet-preview]") return preview;
            if (selector === "[data-artcam-editor] [data-field=\"source\"]") return source;
            if (selector === "[data-vector-count]") return count;
            return null;
        },
    };
    return {
        body,
        source,
        count,
        hitA,
        groupA,
        hitLiner,
        groupLiner,
        hitHandle,
        groupHandle,
        hitPerimeter,
        groupPerimeter,
        groupShared,
        groupSharedAgain,
        hitHidden,
    };
}

const state = { artcamForm: { source: "selected_vectors" }, vectorSelection: [] };
const dom = board();
assert.equal(ux.boardVectorHit(dom.hitHidden), null);
assert.equal(ux.applyBoardVectorClick({ target: dom.hitLiner, preventDefault() {} }, dom.body, state), false);
assert.deepEqual(state.vectorSelection, []);
ux.applyBoardVectorClick({ shiftKey: true, target: dom.hitLiner, preventDefault() {} }, dom.body, state);
assert.deepEqual(state.vectorSelection, ["liner:a"]);
assert.ok(dom.groupLiner.classList.contains("is-vector-picked"));
ux.applyBoardVectorClick({ shiftKey: true, target: dom.hitHandle, preventDefault() {} }, dom.body, state);
assert.deepEqual(state.vectorSelection, ["liner:a", "recessed_handle_cutout:a"]);
assert.ok(dom.groupHandle.classList.contains("is-vector-picked"));
ux.applyBoardVectorClick({ shiftKey: true, target: dom.hitPerimeter, preventDefault() {} }, dom.body, state);
assert.deepEqual(state.vectorSelection, ["liner:a", "recessed_handle_cutout:a", "cut_path:sheet_perimeter"]);
assert.ok(dom.groupPerimeter.classList.contains("is-vector-picked"));
ux.applyBoardVectorClick({ shiftKey: true, target: dom.hitA, preventDefault() {} }, dom.body, state);
assert.deepEqual(state.vectorSelection, ["liner:a", "recessed_handle_cutout:a", "cut_path:sheet_perimeter", "cut_path:a"]);
assert.ok(dom.groupA.classList.contains("is-vector-picked"));
assert.equal(dom.count.textContent, "4 Vectors Selected");
ux.applyBoardVectorClick({
    shiftKey: true,
    target: dom.groupShared,
    preventDefault() {},
}, dom.body, state);
assert.deepEqual(state.vectorSelection, ["liner:a", "recessed_handle_cutout:a", "cut_path:sheet_perimeter", "cut_path:a", "cut_path:shared"]);
assert.ok(dom.groupShared.classList.contains("is-vector-picked"));
assert.ok(dom.groupSharedAgain.classList.contains("is-vector-picked"));
ux.applyBoardVectorClick({ shiftKey: true, target: dom.hitA, preventDefault() {} }, dom.body, state);
assert.deepEqual(state.vectorSelection, ["liner:a", "recessed_handle_cutout:a", "cut_path:sheet_perimeter", "cut_path:shared"]);
assert.ok(!dom.groupA.classList.contains("is-vector-picked"));
dom.source.value = "";
state.artcamForm.source = "";
ux.applyBoardVectorClick({ shiftKey: true, target: dom.groupShared, preventDefault() {} }, dom.body, state);
assert.deepEqual(state.vectorSelection, ["liner:a", "recessed_handle_cutout:a", "cut_path:sheet_perimeter", "cut_path:shared"]);

const saved = artcam.orderedAssociations(
    [
        { association_id: "a", name: "A" },
        { association_id: "b", name: "B" },
        { association_id: "c", name: "C" },
    ],
    { association_id: "b", name: "B edited" }
);
assert.deepEqual(saved.map(row => row.association_id), ["a", "b", "c"]);
assert.equal(saved[1].name, "B edited");
const created = artcam.orderedAssociations(saved, { association_id: "d", name: "D" });
assert.deepEqual(created.map(row => row.association_id), ["a", "b", "c", "d"]);
artcam.loadAssociation(state, {
    association_id: "b",
    name: "B edited",
    profile_id: "profile-1",
    selection: { kind: "selected_vectors", vector_ids: ["cut_path:shared"] },
});
assert.deepEqual(state.vectorSelection, ["cut_path:shared"]);
assert.equal(state.artcamForm.association_id, "b");
assert.equal(state.artcamForm.source, "selected_vectors");
assert.equal(state.artcamForm.toolOpen, true);

const blankEditor = artcam.markup({ presets: [] }, { machining: { profiles: [], associations: [] } }, {});
assert.ok(blankEditor.includes('data-field="profile_id"'));
assert.ok(!blankEditor.includes('data-field="final_depth_mm"'));
assert.ok(!blankEditor.includes('data-field="replacement_tool"'));
assert.ok(!blankEditor.includes("data-artcam-tool"));

const unavailableSources = artcam.markup({}, {
    machining: {
        profiles: [],
        associations: [
            { association_id: "cut-owner", vector_ids: ["cut_path:a"] },
            { association_id: "perimeter-owner", vector_ids: ["cut_path:sheet_perimeter"] },
        ],
        availability: {
            layers: [
                { operation_key: "cut_path", dxf_layer: "CUT_PATH", disabled: false },
                { operation_key: "liner", dxf_layer: "LINER", disabled: false },
            ],
            sheet_perimeter: { vector_id: "cut_path:sheet_perimeter", disabled: false },
        },
    },
}, { perimeterJoinMode: "connected" });
assert.ok(!unavailableSources.includes('value="layer:cut_path"'));
assert.ok(!unavailableSources.includes('value="sheet_perimeter"'));
assert.ok(unavailableSources.includes('value="layer:liner"'));

const availablePerimeter = artcam.markup({}, {
    machining: {
        profiles: [],
        associations: [],
        availability: {
            layers: [],
            sheet_perimeter: { vector_id: "cut_path:sheet_perimeter", disabled: false },
        },
    },
}, {});
assert.ok(availablePerimeter.includes('value="sheet_perimeter"'));

const retainedForm = artcam.formAfterCalculation({
    association_id: "association:old",
    name: "Cut path",
    source: "layer:cut_path",
    profile_id: "profile-1",
    tool_preset: "Finish",
    fields: { final_depth_mm: 12, safe_z_mm: 4, home_x_mm: 1 },
    tool: { tool_number: 9, diameter_mm: 5 },
    toolOpen: true,
});
assert.notEqual(retainedForm.association_id, "association:old");
assert.equal(retainedForm.name, "");
assert.equal(retainedForm.source, "");
assert.equal(retainedForm.profile_id, "profile-1");
assert.equal(retainedForm.tool_preset, "Finish");
assert.deepEqual(retainedForm.fields, { final_depth_mm: 12, safe_z_mm: 4, home_x_mm: 1 });
assert.deepEqual(retainedForm.tool, { tool_number: 9, diameter_mm: 5 });

const chosenEditor = artcam.markup({
    presets: [{ name: "Finish", tool_number: 9, tool_diameter_mm: 5 }],
}, {
    machining: {
        profiles: [{ profile_id: "profile-1", name: "Profile 1" }],
        associations: [],
    },
}, state);
assert.ok(chosenEditor.includes('data-field="final_depth_mm"'));
assert.ok(chosenEditor.includes('data-field="replacement_tool"'));
assert.ok(!chosenEditor.includes('data-field="diameter_mm"'), "tool values stay hidden until a tool is selected");

state.artcamForm.tool_preset = "Finish";
state.artcamForm.tool = { tool_number: 9, diameter_mm: 5 };
state.artcamForm.toolOpen = true;
const toolEditor = artcam.markup({
    presets: [{ name: "Finish", tool_number: 9, tool_diameter_mm: 5 }],
}, {
    machining: {
        profiles: [{ profile_id: "profile-1", name: "Profile 1" }],
        associations: [],
    },
}, state);
assert.ok(toolEditor.includes('<option value="Finish" selected>'));
assert.ok(toolEditor.includes('data-field="diameter_mm" value="5"'));

const lockedState = { artcamForm: { source: "selected_vectors" }, vectorSelection: [] };
const lockedDom = board();
lockedDom.body.querySelector("[data-sheet-preview]").__cutSheet = {
    machining: { associations: [{ association_id: "existing", vector_ids: ["cut_path:shared"] }] },
};
ux.applyBoardVectorClick({
    shiftKey: true,
    target: lockedDom.groupShared,
    preventDefault() {},
}, lockedDom.body, lockedState);
assert.deepEqual(lockedState.vectorSelection, []);
lockedDom.groupShared.className += " is-assigned";
assert.equal(ux.boardVectorHit(lockedDom.groupShared), null);

const lockedProgram = {
    operations: [{
        operation_key: "cut_path",
        toolpaths: [{
            path_key: "cut_path:shared",
            vector_id: "cut_path:shared",
            operation_key: "cut_path",
            closed: false,
            points: [[0, 0], [10, 0]],
            motions: [],
        }],
    }],
};
const lockedPhysical = ux.collectPhysicalPaths(lockedProgram)[0];
lockedState.program = lockedProgram;
assert.equal(ux.applyExecutionSelection(
    null,
    {},
    lockedDom.body.querySelector("[data-sheet-preview]").__cutSheet,
    lockedState,
    lockedPhysical.execution_path_id
), false);

const previewArgs = ux.sheetGenerateArgs(
    { doc: { name: "DCO-1" } },
    { cutting_plan: "PLAN-1", plan_revision: 1 },
    {
        sheet_no: 1,
        machining: {
            profiles: [{
                profile_id: "profile-1",
                tool_preset: "Finish",
                final_depth_mm: 10,
                safe_z_mm: 5,
                home_x_mm: 0,
                home_y_mm: 0,
                home_z_mm: 5,
                tool_values: { description: "Finish", diameter_mm: 8 },
            }],
            associations: [],
        },
    },
    {
        operations: {},
        overrides: {},
        order: [],
        perimeterJoinMode: "separate",
        artcamForm: {
            association_id: "association-1",
            name: "Liner",
            source: "layer:liner",
            profile_id: "profile-1",
            tool_preset: "Finish",
            fields: { final_depth_mm: 10, safe_z_mm: 5, home_x_mm: 0, home_y_mm: 0, home_z_mm: 5 },
            tool: { description: "Finish", diameter_mm: 8 },
        },
        vectorSelection: [],
    }
);
assert.equal(Object.prototype.hasOwnProperty.call(previewArgs, "vector_associations"), false);
assert.equal(Object.prototype.hasOwnProperty.call(previewArgs, "machining_profiles"), false);

const preservedPreview = {
    __cutPreviewProgram: { sheet_width_mm: 100, sheet_length_mm: 80 },
    innerHTML: "<svg data-existing-path></svg>",
    attrs: {},
    setAttribute(name, value) { this.attrs[name] = String(value); },
    removeAttribute(name) { delete this.attrs[name]; },
};
ux.paintCutPathPreview(preservedPreview, { status: "loading" });
assert.equal(preservedPreview.innerHTML, "<svg data-existing-path></svg>");
assert.equal(preservedPreview.attrs["aria-busy"], "true");
ux.paintCutPathPreview(preservedPreview, { status: "error" });
assert.equal(preservedPreview.innerHTML, "<svg data-existing-path></svg>");
assert.equal(preservedPreview.attrs["data-preview-error"], "true");

assert.equal(ux.PROGRAM_COLORS.liner, "#C62828");
assert.equal(ux.PROGRAM_COLORS.recessed_handle_cutout, "#C62828");
assert.equal(ux.PROGRAM_COLORS.back_groove, "#C62828");
const highlighted = ux.cutPathPreviewMarkup({
    sheet_width_mm: 100,
    sheet_length_mm: 80,
    geometry_ready: true,
    operations: [
        { operation_key: "liner", toolpaths: [{ path_key: "liner:a", operation_key: "liner", closed: false, points: [[10, 10], [80, 10]], motions: [] }] },
        { operation_key: "cut_path", toolpaths: [{ path_key: "cut_path:a", operation_key: "cut_path", closed: false, points: [[10, 40], [80, 40]], motions: [] }] },
        { operation_key: "sheet_perimeter", toolpaths: [{ path_key: "cut_path:sheet_perimeter", operation_key: "sheet_perimeter", closed: true, points: [[0, 0], [100, 0], [100, 80], [0, 0]], motions: [] }] },
    ],
}, {
    selectedVectorIds: ["cut_path:a"],
    assignedVectorIds: ["liner:a"],
    activeOperation: "sheet_perimeter",
});
assert.ok(highlighted.includes("is-vector-picked"));
assert.ok(highlighted.includes("is-assigned"));
assert.ok(highlighted.includes("is-layer-active"));
assert.ok(highlighted.includes('data-operation-key="liner"'));
assert.ok(highlighted.includes('data-operation-key="sheet_perimeter"'));
assert.ok(!highlighted.includes("data-clear-reverse"));
assert.ok(!highlighted.includes("Clear saved direction"));
const css = fs.readFileSync(path.join(root, "public/css/door_cutting_order_operational_files.css"), "utf8");
assert.ok(css.includes(".dco-operational-sheet .dco-cnc-cut-preview__arrow"));
assert.ok(css.includes("display: none"));
assert.ok(css.includes("#F59E0B"));
assert.ok(css.includes("#EC4899"));

function zoned(marker, parent) {
    const node = {
        parent: parent || null,
        getAttribute(name) {
            return name === marker ? "1" : null;
        },
        closest(selector) {
            const name = String(selector || "").match(/\[([^\]=]+)/);
            let current = node;
            while (current) {
                if (name && current.getAttribute(name[1]) != null) return current;
                current = current.parent;
            }
            return null;
        },
    };
    return node;
}

const geometry = zoned("data-sheet-geometry");
const pathNode = zoned("data-execution-path", geometry);
const menu = zoned("data-path-menu", geometry);
const reverse = zoned("data-reverse-path", menu);
const control = zoned("data-artcam-root");
assert.equal(ux.boardPointerZone(reverse), "menu");
assert.equal(ux.boardPointerZone(pathNode), "board");
assert.equal(ux.boardPointerZone(control), "control");
assert.equal(ux.boardPointerZone(zoned("data-page")), "outside");
const shaped = ux.cutPathPreviewMarkup({
    sheet_width_mm: 100,
    sheet_length_mm: 80,
    operations: [{
        operation_key: "cut_path",
        toolpaths: [{
            path_key: "cut_path:shared",
            shape_id: "shape-b",
            operation_key: "cut_path",
            closed: false,
            points: [[0, 0], [10, 0]],
            motions: [],
        }],
    }],
});
assert.ok(shaped.includes('data-shape-id="shape-b"'));
assert.ok(shaped.includes('data-shape-id="shape-b"'));

console.log("dco_operational_files_vector_selection.test.js passed");
