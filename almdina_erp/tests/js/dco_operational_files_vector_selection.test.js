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
assert.ok(uncalculated.includes("max-inline-size:260px"));

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
    const groups = [groupA, groupShared, groupSharedAgain, hidden];
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
    return { body, source, count, hitA, groupA, groupShared, groupSharedAgain, hitHidden };
}

const state = { artcamForm: { source: "selected_vectors" }, vectorSelection: [] };
const dom = board();
assert.equal(ux.boardVectorHit(dom.hitHidden), null);
ux.applyBoardVectorClick({ shiftKey: true, target: dom.hitA, preventDefault() {} }, dom.body, state);
assert.deepEqual(state.vectorSelection, ["cut_path:a"]);
assert.ok(dom.groupA.classList.contains("is-vector-picked"));
assert.equal(dom.count.textContent, "1 Vectors Selected");
ux.applyBoardVectorClick({
    shiftKey: true,
    target: dom.groupShared,
    preventDefault() {},
}, dom.body, state);
assert.deepEqual(state.vectorSelection, ["cut_path:a", "cut_path:shared"]);
assert.ok(dom.groupShared.classList.contains("is-vector-picked"));
assert.ok(dom.groupSharedAgain.classList.contains("is-vector-picked"));
ux.applyBoardVectorClick({ shiftKey: true, target: dom.hitA, preventDefault() {} }, dom.body, state);
assert.deepEqual(state.vectorSelection, ["cut_path:shared"]);
assert.ok(!dom.groupA.classList.contains("is-vector-picked"));
dom.source.value = "";
state.artcamForm.source = "";
ux.applyBoardVectorClick({ shiftKey: true, target: dom.groupShared, preventDefault() {} }, dom.body, state);
assert.deepEqual(state.vectorSelection, ["cut_path:shared"]);

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

console.log("dco_operational_files_vector_selection.test.js passed");
