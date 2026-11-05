"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const root = path.resolve(__dirname, "../..");

function loadEditor() {
    const files = [
        "public/js/board_editor/history.js",
        "public/js/board_editor/session_document.js",
        "public/js/board_editor/move_geometry.js",
        "public/js/board_editor/alignment_geometry.js",
        "public/js/board_editor/store.js",
    ];
    const context = {
        frappe: { utils: { escape_html: (value) => String(value) } },
        __: (message, replace) => {
            if (!Array.isArray(replace) || !replace.length) return message;
            return replace.reduce(
                (text, value, index) => text.replace(`{${index}}`, String(value)),
                message
            );
        },
        console,
    };
    context.window = context;
    context.globalThis = context;
    vm.createContext(context);
    files.forEach((relativePath) => {
        vm.runInContext(fs.readFileSync(path.join(root, relativePath), "utf8"), context);
    });
    return context.window.AlmdinaBoardEditor;
}

const {
    AlignmentGeometry,
    MoveGeometry,
    SessionDocument,
    History,
    createStore,
} = loadEditor();

assert.ok(AlignmentGeometry);
assert.equal(AlignmentGeometry.MODES.length, 6);

const projection = {
    board: { kerf_cm: 0.4 },
    sheets: [
        {
            sheet_no: 1,
            full_width_cm: 100,
            full_length_cm: 100,
            applied_trim_width_cm: 0,
            applied_trim_length_cm: 0,
        },
        {
            sheet_no: 2,
            full_width_cm: 100,
            full_length_cm: 100,
            applied_trim_width_cm: 0,
            applied_trim_length_cm: 0,
        },
    ],
    pieces: [
        {
            piece_id: 1,
            piece_instance_id: "pi-a",
            label: "A",
            sheet_no: 1,
            placement_cm: { x: 1, y: 1, w: 10, h: 8 },
        },
        {
            piece_id: 2,
            piece_instance_id: "pi-b",
            label: "B",
            sheet_no: 1,
            placement_cm: { x: 25, y: 20, w: 10, h: 8 },
        },
        {
            piece_id: 3,
            piece_instance_id: "pi-c",
            label: "C",
            sheet_no: 1,
            placement_cm: { x: 45, y: 40, w: 10, h: 8 },
        },
        {
            piece_id: 4,
            piece_instance_id: "pi-out-a",
            label: "OutA",
            sheet_no: null,
            placement_cm: { x: 0, y: 0, w: 8, h: 8 },
        },
        {
            piece_id: 5,
            piece_instance_id: "pi-out-b",
            label: "OutB",
            sheet_no: null,
            placement_cm: { x: 0, y: 0, w: 8, h: 8 },
        },
        {
            piece_id: 6,
            piece_instance_id: "pi-s2",
            label: "S2",
            sheet_no: 2,
            placement_cm: { x: 1, y: 1, w: 10, h: 10 },
        },
    ],
};

const layout = {
    positions: {
        1: { originX: 0, originY: 0 },
        2: { originX: 1400, originY: 0 },
    },
};

function freshStore() {
    const session = SessionDocument.buildFromProjection(projection, layout);
    // Place outside pieces in world space with separation.
    const outA = Object.values(session.pieces).find((p) => p.piece_instance_id === "pi-out-a");
    const outB = Object.values(session.pieces).find((p) => p.piece_instance_id === "pi-out-b");
    // Keep outside pieces far from board usable areas so resolveDropSheet
    // does not re-attach them during alignment.
    outA.sheet_no = null;
    outA.local_x_mm = -600;
    outA.local_y_mm = 50;
    outA.outline_mm = [[-600, 50], [-520, 50], [-520, 130], [-600, 130]];
    outB.sheet_no = null;
    outB.local_x_mm = -400;
    outB.local_y_mm = 80;
    outB.outline_mm = [[-400, 80], [-320, 80], [-320, 160], [-400, 160]];

    const hist = History.create(session);
    const store = createStore({ projection, order_name: "O", plan_name: "P" });
    store.attachSession(hist.get(), hist);
    return store;
}

function keyByInstance(session, instanceId) {
    return Object.keys(session.pieces).find(
        (key) => session.pieces[key].piece_instance_id === instanceId
    );
}

function applyAlign(store, keys, mode) {
    const proposal = AlignmentGeometry.proposeAlignment(store.snapshot().session, keys, mode);
    if (!proposal.ok) return proposal;
    if (proposal.unchanged) return proposal;
    let next = store.snapshot().session;
    proposal.commands.forEach((command) => {
        next = MoveGeometry.applyPieceMove(next, command);
    });
    store.commitSession(next);
    return { ok: true, unchanged: false };
}

{
    const store = freshStore();
    const session = store.snapshot().session;
    const keyA = keyByInstance(session, "pi-a");
    const keyB = keyByInstance(session, "pi-b");
    assert.equal(AlignmentGeometry.alignmentEligibility(session, [keyA]).enabled, false);
    assert.equal(AlignmentGeometry.alignmentEligibility(session, [keyA, keyB]).enabled, true);
}

{
    const store = freshStore();
    const session = store.snapshot().session;
    const keyA = keyByInstance(session, "pi-a");
    const keyB = keyByInstance(session, "pi-b");
    const beforeA = MoveGeometry.worldFootprint(session.pieces[keyA], session.boards).bounds;
    const beforeB = MoveGeometry.worldFootprint(session.pieces[keyB], session.boards).bounds;
    const groupMinX = Math.min(beforeA.x, beforeB.x);
    assert.equal(applyAlign(store, [keyA, keyB], "align_left").ok, true);
    const after = store.snapshot().session;
    const afterA = MoveGeometry.worldFootprint(after.pieces[keyA], after.boards).bounds;
    const afterB = MoveGeometry.worldFootprint(after.pieces[keyB], after.boards).bounds;
    assert.ok(Math.abs(afterA.x - groupMinX) < 1e-6);
    assert.ok(Math.abs(afterB.x - groupMinX) < 1e-6);
    assert.equal(store.snapshot().canUndo, true);
    store.undo();
    const undone = store.snapshot().session;
    assert.ok(Math.abs(
        MoveGeometry.worldFootprint(undone.pieces[keyB], undone.boards).bounds.x - beforeB.x
    ) < 1e-6);
    store.redo();
    const redone = store.snapshot().session;
    assert.ok(Math.abs(
        MoveGeometry.worldFootprint(redone.pieces[keyB], redone.boards).bounds.x - groupMinX
    ) < 1e-6);
}

{
    const store = freshStore();
    const session = store.snapshot().session;
    const keyA = keyByInstance(session, "pi-a");
    const keyB = keyByInstance(session, "pi-b");
    const beforeA = MoveGeometry.worldFootprint(session.pieces[keyA], session.boards).bounds;
    const beforeB = MoveGeometry.worldFootprint(session.pieces[keyB], session.boards).bounds;
    const groupMaxX = Math.max(beforeA.x + beforeA.w, beforeB.x + beforeB.w);
    assert.equal(applyAlign(store, [keyA, keyB], "align_right").ok, true);
    const after = store.snapshot().session;
    const afterA = MoveGeometry.worldFootprint(after.pieces[keyA], after.boards).bounds;
    const afterB = MoveGeometry.worldFootprint(after.pieces[keyB], after.boards).bounds;
    assert.ok(Math.abs((afterA.x + afterA.w) - groupMaxX) < 1e-6);
    assert.ok(Math.abs((afterB.x + afterB.w) - groupMaxX) < 1e-6);
}

{
    const store = freshStore();
    const session = store.snapshot().session;
    const keyA = keyByInstance(session, "pi-a");
    const keyB = keyByInstance(session, "pi-b");
    const beforeA = MoveGeometry.worldFootprint(session.pieces[keyA], session.boards).bounds;
    const beforeB = MoveGeometry.worldFootprint(session.pieces[keyB], session.boards).bounds;
    const center = (
        Math.min(beforeA.x, beforeB.x)
        + Math.max(beforeA.x + beforeA.w, beforeB.x + beforeB.w)
    ) / 2;
    assert.equal(applyAlign(store, [keyA, keyB], "align_center_x").ok, true);
    const after = store.snapshot().session;
    const afterA = MoveGeometry.worldFootprint(after.pieces[keyA], after.boards).bounds;
    const afterB = MoveGeometry.worldFootprint(after.pieces[keyB], after.boards).bounds;
    assert.ok(Math.abs((afterA.x + afterA.w / 2) - center) < 1e-6);
    assert.ok(Math.abs((afterB.x + afterB.w / 2) - center) < 1e-6);
}

{
    const store = freshStore();
    let session = store.snapshot().session;
    const keyA = keyByInstance(session, "pi-a");
    const keyB = keyByInstance(session, "pi-b");
    // Put B on the same Y band as A so Align Left would overlap / violate kerf.
    const fpA = MoveGeometry.footprint(session.pieces[keyA]);
    const fpB = MoveGeometry.footprint(session.pieces[keyB]);
    const dy = fpA.bounds.y - fpB.bounds.y;
    session.pieces[keyB].local_y_mm = Number(session.pieces[keyB].local_y_mm) + dy;
    if (Array.isArray(session.pieces[keyB].outline_mm)) {
        session.pieces[keyB].outline_mm = session.pieces[keyB].outline_mm.map((pt) => [
            Number(pt[0]),
            Number(pt[1]) + dy,
        ]);
    }
    const hist = History.create(session);
    store.attachSession(hist.get(), hist);
    session = store.snapshot().session;
    const before = JSON.stringify(session.pieces[keyB]);
    const undoBefore = store.snapshot().canUndo;
    const rejected = AlignmentGeometry.proposeAlignment(
        session,
        [keyA, keyB],
        "align_left"
    );
    assert.equal(rejected.ok, false, rejected.reason || "expected collision reject");
    assert.equal(JSON.stringify(store.snapshot().session.pieces[keyB]), before);
    assert.equal(store.snapshot().canUndo, undoBefore);
}

{
    const store = freshStore();
    const session = store.snapshot().session;
    const outA = keyByInstance(session, "pi-out-a");
    const outB = keyByInstance(session, "pi-out-b");
    const beforeA = MoveGeometry.worldFootprint(session.pieces[outA], session.boards).bounds;
    const beforeB = MoveGeometry.worldFootprint(session.pieces[outB], session.boards).bounds;
    const groupMinX = Math.min(beforeA.x, beforeB.x);
    assert.equal(applyAlign(store, [outA, outB], "align_left").ok, true);
    const after = store.snapshot().session;
    assert.equal(after.pieces[outA].sheet_no, null);
    assert.equal(after.pieces[outB].sheet_no, null);
    const afterA = MoveGeometry.worldFootprint(after.pieces[outA], after.boards).bounds;
    const afterB = MoveGeometry.worldFootprint(after.pieces[outB], after.boards).bounds;
    assert.ok(Math.abs(afterA.x - groupMinX) < 1e-6);
    assert.ok(Math.abs(afterB.x - groupMinX) < 1e-6);
}

{
    const store = freshStore();
    const session = store.snapshot().session;
    const keyA = keyByInstance(session, "pi-a");
    const outA = keyByInstance(session, "pi-out-a");
    const keyS2 = keyByInstance(session, "pi-s2");
    assert.equal(
        AlignmentGeometry.alignmentEligibility(session, [keyA, outA]).enabled,
        false
    );
    assert.equal(
        AlignmentGeometry.alignmentEligibility(session, [keyA, keyS2]).enabled,
        false
    );
}

{
    const store = freshStore();
    const session = store.snapshot().session;
    const keyA = keyByInstance(session, "pi-a");
    const keyB = keyByInstance(session, "pi-b");
    session.pieces[keyB].editable = false;
    assert.equal(
        AlignmentGeometry.alignmentEligibility(session, [keyA, keyB]).enabled,
        false
    );
}

{
    const store = freshStore();
    const session = store.snapshot().session;
    const keyA = keyByInstance(session, "pi-a");
    const keyB = keyByInstance(session, "pi-b");
    const before = MoveGeometry.worldFootprint(session.pieces[keyA], session.boards).bounds.y;
    // Already top-aligned after moving B to A's minY via center? Use align_top then unchanged.
    const first = applyAlign(store, [keyA, keyB], "align_top");
    assert.equal(first.ok, true);
    const undoBefore = store.snapshot().canUndo;
    const second = AlignmentGeometry.proposeAlignment(
        store.snapshot().session,
        [keyA, keyB],
        "align_top"
    );
    assert.equal(second.ok, true);
    assert.equal(second.unchanged, true);
    assert.equal(store.snapshot().canUndo, undoBefore);
    assert.ok(Math.abs(
        MoveGeometry.worldFootprint(store.snapshot().session.pieces[keyA], store.snapshot().session.boards).bounds.y
        - before
    ) < 50);
}

const css = fs.readFileSync(path.join(root, "public/css/board_editor.css"), "utf8");
const page = fs.readFileSync(path.join(root, "almdina_erp/page/board_editor/board_editor.js"), "utf8");
const controller = fs.readFileSync(path.join(root, "public/js/board_editor/controller.js"), "utf8");
const right = fs.readFileSync(path.join(root, "public/js/board_editor/right_sidebar_renderer.js"), "utf8");
const canvas = fs.readFileSync(path.join(root, "public/js/board_editor/canvas_renderer.js"), "utf8");
const arCsv = fs.readFileSync(path.join(root, "translations/ar.csv"), "utf8");

assert.match(css, /--abe-right-sidebar-width:\s*240px/);
assert.match(css, /grid-template-areas:\s*"sidebar canvas inspector"/);
assert.doesNotMatch(css, /\.abe-right-sidebar\s*\{[^}]*grid-template-rows:\s*minmax\(0,\s*1fr\)\s+auto/);
assert.match(page, /alignment_geometry\.js\?v=1/);
assert.match(page, /right_sidebar_renderer\.js\?v=3/);
assert.match(page, /board_editor\.css\?v=35/);
assert.match(controller, /RightSidebarRenderer/);
assert.match(controller, /applyAlignment/);
assert.match(right, /data-abe-align/);
assert.match(right, /data-abe-position-bar/);
assert.match(right, /alignmentSectionHtml\(storeView\)[\s\S]*propertiesSectionHtml\(storeView\)/);
assert.doesNotMatch(canvas, /data-abe-position-bar/);
assert.match(canvas, /abe-float-tools/);
[
    "Piece properties",
    "Alignment",
    "Align left",
    "Align pieces on the same board only, or pieces outside all boards.",
].forEach((key) => {
    assert.ok(arCsv.includes(key), `missing ar.csv key: ${key}`);
});

// Alignment icons stay mounted for every selection state; only disabled toggles.
{
    function inspectorHost() {
        return {
            __html: "",
            set innerHTML(value) { this.__html = String(value); },
            get innerHTML() { return this.__html; },
            querySelector() {
                return {
                    querySelectorAll: () => [],
                    querySelector: () => null,
                    addEventListener() {},
                };
            },
            querySelectorAll() { return []; },
        };
    }
    function loadUi() {
        const files = [
            "public/js/board_editor/history.js",
            "public/js/board_editor/session_document.js",
            "public/js/board_editor/move_geometry.js",
            "public/js/board_editor/position_geometry.js",
            "public/js/board_editor/alignment_geometry.js",
            "public/js/board_editor/right_sidebar_renderer.js",
        ];
        const context = {
            frappe: { utils: { escape_html: (value) => String(value) } },
            __: (message) => message,
            console,
        };
        context.window = context;
        context.globalThis = context;
        vm.createContext(context);
        files.forEach((relativePath) => {
            vm.runInContext(fs.readFileSync(path.join(root, relativePath), "utf8"), context);
        });
        return context.window.AlmdinaBoardEditor;
    }
    const ui = loadUi();
    const session = SessionDocument.buildFromProjection(projection, layout);
    const keyA = keyByInstance(session, "pi-a");
    const keyB = keyByInstance(session, "pi-b");
    function paint(keys) {
        const host = inspectorHost();
        ui.RightSidebarRenderer.render(host, {
            session,
            selectedPieceKeys: keys,
        }, {});
        return host.innerHTML;
    }
    const emptyHtml = paint([]);
    const oneHtml = paint([keyA]);
    const twoHtml = paint([keyA, keyB]);
    assert.equal((emptyHtml.match(/data-abe-align="/g) || []).length, 6);
    assert.equal((oneHtml.match(/data-abe-align="/g) || []).length, 6);
    assert.equal((twoHtml.match(/data-abe-align="/g) || []).length, 6);
    assert.match(emptyHtml, /data-abe-align="align_left"[^>]*\sdisabled(?:\s|>)/);
    assert.match(oneHtml, /data-abe-align="align_left"[^>]*\sdisabled(?:\s|>)/);
    assert.match(twoHtml, /data-abe-align="align_left"[^>]*aria-disabled="false"/);
    assert.doesNotMatch(twoHtml, /data-abe-align="align_left"[^>]*\sdisabled(?:\s|>)/);
    const alignAt = emptyHtml.indexOf('data-abe-align-section="1"');
    const propsAt = emptyHtml.indexOf("abe-inspector-props-block");
    assert.ok(alignAt >= 0 && propsAt > alignAt, "alignment must stack above properties");
}

console.log("board_editor_alignment.test.js: ok");
