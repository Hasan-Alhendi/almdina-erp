"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const root = path.resolve(__dirname, "../..");

function load() {
    const files = [
        "public/js/board_editor/history.js",
        "public/js/board_editor/session_document.js",
        "public/js/board_editor/move_geometry.js",
        "public/js/board_editor/snap_geometry.js",
        "public/js/board_editor/rotation_geometry.js",
        "public/js/board_editor/rotation_interaction.js",
        "public/js/board_editor/store.js",
    ];
    const listeners = new Map();
    const context = {
        frappe: { utils: { escape_html: (value) => String(value) } },
        __: (message) => message,
        console,
        addEventListener(type, fn) {
            if (!listeners.has(type)) listeners.set(type, new Set());
            listeners.get(type).add(fn);
        },
        removeEventListener(type, fn) {
            if (listeners.has(type)) listeners.get(type).delete(fn);
        },
        dispatch(type, event) {
            const set = listeners.get(type);
            if (!set) return;
            set.forEach((fn) => fn(event || {}));
        },
        _listeners: listeners,
    };
    context.window = context;
    context.globalThis = context;
    vm.createContext(context);
    files.forEach((relative) => {
        vm.runInContext(fs.readFileSync(path.join(root, relative), "utf8"), context);
    });
    return { editor: context.window.AlmdinaBoardEditor, windowHost: context };
}

function rect(x, y, w, h) {
    return [[x, y], [x + w, y], [x + w, y + h], [x, y + h]];
}

function piece(key, opts) {
    const x = opts.x;
    const y = opts.y;
    const w = opts.w;
    const h = opts.h;
    const outline = opts.outline || rect(x, y, w, h);
    return {
        piece_key: key,
        piece_id: opts.piece_id,
        piece_instance_id: key.replace(/^instance:/, ""),
        sheet_no: 1,
        local_x_mm: x,
        local_y_mm: y,
        placement_cm: { x: x / 10, y: y / 10, w: w / 10, h: h / 10, rotated: false },
        outline_mm: outline,
        base_outline_mm: outline.map((row) => row.slice()),
        pivot_mm: { x: x + w / 2, y: y + h / 2 },
        entry_pivot_mm: { x: x + w / 2, y: y + h / 2 },
        rotation_deg: opts.rotation_deg != null ? opts.rotation_deg : 0,
        editable: opts.editable !== false,
        allow_rotation: opts.allow !== false,
        allow_rotation_proven: true,
        glass_host_key: opts.host || null,
        glass_hole_local_mm: opts.hole || null,
        base_hole_mm: opts.hole ? opts.hole.map((row) => row.slice()) : null,
        piece_type: opts.piece_type || "Regular",
        apply_rotated_to_geometry: false,
        source_orientation_applied: true,
        source_rotated_dims: false,
    };
}

function baseSession(pieces) {
    return {
        boards: {
            1: {
                sheet_no: 1,
                origin_x_mm: 0,
                origin_y_mm: 0,
                width_mm: 2000,
                height_mm: 2000,
                trim_x_mm: 0,
                trim_y_mm: 0,
                usable_width_mm: 2000,
                usable_length_mm: 2000,
                title_band_mm: 0,
            },
        },
        pieces,
        kerf_mm: 4,
        stale_cut_path_sheets: [],
        stale_unbound_text_sheets: [],
    };
}

const loaded = load();
const editor = loaded.editor;
const windowHost = loaded.windowHost;
const {
    RotationGeometry,
    RotationInteractionMath,
    createStore,
    History,
    createRotationInteraction,
} = editor;

const {
    SHIFT_SNAP_DEG,
    signedAngleDelta,
    applyRotationSteps,
    constrainShiftRotation,
} = RotationInteractionMath;

assert.equal(SHIFT_SNAP_DEG, 15);

{
    // Pure math: directional steps from 37°.
    assert.equal(applyRotationSteps(37, 1), 45);
    assert.equal(applyRotationSteps(37, 2), 60);
    assert.equal(applyRotationSteps(37, 3), 75);
    assert.equal(applyRotationSteps(37, -1), 30);
    assert.equal(applyRotationSteps(37, -2), 15);
    assert.equal(applyRotationSteps(37, -3), 0);

    assert.equal(constrainShiftRotation(37, 37, 37), 37);
    assert.equal(constrainShiftRotation(37.5, 37, 37), 45);
    assert.equal(constrainShiftRotation(37 + 15, 37, 37), 60);
    assert.equal(constrainShiftRotation(37 + 30, 37, 37), 75);
    assert.equal(constrainShiftRotation(36.5, 37, 37), 30);
    assert.equal(constrainShiftRotation(37 - 15, 37, 37), 15);
    assert.equal(constrainShiftRotation(37 - 30, 37, 37), 0);

    // Reverse after climbing: back through prior steps.
    assert.equal(constrainShiftRotation(37 + 30, 37, 37), 75);
    assert.equal(constrainShiftRotation(37 + 15, 37, 37), 60);
    assert.equal(constrainShiftRotation(37 + 1, 37, 37), 45);
    assert.equal(constrainShiftRotation(37, 37, 37), 37);
    assert.equal(constrainShiftRotation(37 - 1, 37, 37), 30);

    // Wrap across 0/360 in both directions.
    assert.equal(constrainShiftRotation(5, 5, 5), 5);
    assert.equal(constrainShiftRotation(5.2, 5, 5), 15);
    assert.equal(constrainShiftRotation(4.8, 5, 5), 0);
    assert.equal(constrainShiftRotation(5 - 15, 5, 5), -15);
    assert.ok(Math.abs(signedAngleDelta(350, 10) - 20) < 1e-9);
    assert.ok(Math.abs(signedAngleDelta(10, 350) - (-20)) < 1e-9);
    assert.equal(constrainShiftRotation(350 + 1, 350, 350), 360);
    assert.equal(constrainShiftRotation(350 + 16, 350, 350), 375);
    assert.equal(constrainShiftRotation(10 - 1, 10, 10), 0);
    assert.equal(constrainShiftRotation(10 - 16, 10, 10), -15);
}

function almostEqual(a, b, eps) {
    assert.ok(Math.abs(a - b) <= (eps == null ? 1e-6 : eps), `${a} ~= ${b}`);
}

function pointAtAngle(pivot, angleDeg, radius) {
    const rad = (angleDeg * Math.PI) / 180;
    // Matches RotationGeometry.angleFromPointer (Y-down atan2).
    return {
        x: pivot.x + radius * Math.cos(rad),
        y: pivot.y + radius * Math.sin(rad),
    };
}

function makeHarness(session, pieceKey) {
    const history = History.create(session);
    const store = createStore({ projection: { sheets: [], pieces: [], elements: [] }, order_name: "O", plan_name: "P" });
    store.attachSession(history.get(), history);

    const stage = {
        classList: {
            _set: new Set(),
            add(name) { this._set.add(name); },
            remove(name) { this._set.delete(name); },
            contains(name) { return this._set.has(name); },
        },
        style: { cursor: "" },
    };
    const svg = {
        getBoundingClientRect: () => ({ left: 0, top: 0, right: 2000, bottom: 2000, width: 2000, height: 2000 }),
    };
    const target = {
        setPointerCapture() {},
        releasePointerCapture() {},
    };

    const previews = [];
    const committed = [];
    const rejected = [];

    const interaction = createRotationInteraction({
        store,
        getStageEl: () => stage,
        getSvgEl: () => svg,
        getWorldMetrics: () => ({ minX: 0, minY: 0, width: 2000, height: 2000 }),
        getScale: () => 1,
        onPreview: (preview) => {
            if (preview) previews.push(preview);
        },
        onRejected: (message) => rejected.push(message),
        onCommitted: (key, angle) => committed.push({ key, angle }),
        isPanKey: () => false,
    });

    const pieceRow = store.snapshot().session.pieces[pieceKey];
    RotationGeometry.ensureBaseGeometry(pieceRow);
    const pivot = {
        x: Number(pieceRow.pivot_mm.x) || 0,
        y: Number(pieceRow.pivot_mm.y) || 0,
    };
    const startPointerAngle = Number(pieceRow.rotation_deg) || 0;
    let lastPointerDelta = 0;

    function pointer(clientX, clientY, opts) {
        return {
            button: 0,
            pointerId: 1,
            pointerType: "mouse",
            clientX,
            clientY,
            shiftKey: Boolean(opts && opts.shiftKey),
            currentTarget: target,
            target,
            stopPropagation() {},
            preventDefault() {},
        };
    }

    function begin(shiftKey) {
        lastPointerDelta = 0;
        const p = pointAtAngle(pivot, startPointerAngle, 120);
        return interaction.beginHandleGesture(pieceKey, pointer(p.x, p.y, { shiftKey }));
    }

    function moveToPieceDelta(deltaDeg, shiftKey) {
        // Pointer angle = startPointerAngle + delta keeps free piece angle ≈ start + delta.
        lastPointerDelta = deltaDeg;
        const pointerAngle = startPointerAngle + deltaDeg;
        const p = pointAtAngle(pivot, pointerAngle, 120);
        interaction.onPointerMove(pointer(p.x, p.y, { shiftKey }));
    }

    function up(shiftKey) {
        // Keep the last pointer pose so pointerup does not invent an extra delta.
        const p = pointAtAngle(pivot, startPointerAngle + lastPointerDelta, 120);
        interaction.onPointerUp(pointer(p.x, p.y, { shiftKey }));
    }

    return {
        interaction,
        store,
        pivot,
        previews,
        committed,
        rejected,
        begin,
        moveToPieceDelta,
        up,
        lastPreview() {
            return previews[previews.length - 1] || null;
        },
    };
}

{
    // Free rotation without Shift matches continuous pointer delta.
    const session = baseSession({
        "instance:a": piece("instance:a", { piece_id: 1, x: 100, y: 100, w: 200, h: 100, rotation_deg: 10 }),
    });
    const h = makeHarness(session, "instance:a");
    assert.equal(h.begin(false), true);
    h.moveToPieceDelta(17, false);
    almostEqual(h.lastPreview().display_deg, 27);
    almostEqual(h.lastPreview().rotation_deg, 27);
    assert.equal(h.lastPreview().valid, true);
}

{
    // From 37° with Shift: positive direction -> 45, 60, 75.
    const session = baseSession({
        "instance:a": piece("instance:a", {
            piece_id: 1, x: 400, y: 400, w: 120, h: 80, rotation_deg: 37,
        }),
    });
    const h = makeHarness(session, "instance:a");
    assert.equal(h.begin(true), true);
    almostEqual(h.lastPreview().display_deg, 37);

    h.moveToPieceDelta(1, true);
    almostEqual(h.lastPreview().display_deg, 45);
    almostEqual(h.lastPreview().rotation_deg, 45);

    h.moveToPieceDelta(16, true);
    almostEqual(h.lastPreview().display_deg, 60);

    h.moveToPieceDelta(31, true);
    almostEqual(h.lastPreview().display_deg, 75);
}

{
    // From 37° with Shift: negative direction -> 30, 15, 0.
    const session = baseSession({
        "instance:a": piece("instance:a", {
            piece_id: 1, x: 400, y: 400, w: 120, h: 80, rotation_deg: 37,
        }),
    });
    const h = makeHarness(session, "instance:a");
    assert.equal(h.begin(true), true);
    h.moveToPieceDelta(-1, true);
    almostEqual(h.lastPreview().display_deg, 30);
    h.moveToPieceDelta(-16, true);
    almostEqual(h.lastPreview().display_deg, 15);
    h.moveToPieceDelta(-31, true);
    almostEqual(h.lastPreview().display_deg, 0);
}

{
    // Reverse direction while Shift is held returns through prior steps.
    const session = baseSession({
        "instance:a": piece("instance:a", {
            piece_id: 1, x: 400, y: 400, w: 120, h: 80, rotation_deg: 37,
        }),
    });
    const h = makeHarness(session, "instance:a");
    h.begin(true);
    h.moveToPieceDelta(31, true);
    almostEqual(h.lastPreview().display_deg, 75);
    h.moveToPieceDelta(16, true);
    almostEqual(h.lastPreview().display_deg, 60);
    h.moveToPieceDelta(1, true);
    almostEqual(h.lastPreview().display_deg, 45);
    h.moveToPieceDelta(0, true);
    almostEqual(h.lastPreview().display_deg, 37);
    h.moveToPieceDelta(-1, true);
    almostEqual(h.lastPreview().display_deg, 30);
}

{
    // Crossing 0°/360° while constrained.
    const session = baseSession({
        "instance:a": piece("instance:a", {
            piece_id: 1, x: 400, y: 400, w: 120, h: 80, rotation_deg: 5,
        }),
    });
    const h = makeHarness(session, "instance:a");
    h.begin(true);
    h.moveToPieceDelta(-1, true);
    almostEqual(h.lastPreview().display_deg, 0);
    almostEqual(h.lastPreview().rotation_deg, 0);
    h.moveToPieceDelta(-16, true);
    almostEqual(h.lastPreview().display_deg, -15);
    almostEqual(h.lastPreview().rotation_deg, 345);

    const session2 = baseSession({
        "instance:a": piece("instance:a", {
            piece_id: 1, x: 400, y: 400, w: 120, h: 80, rotation_deg: 350,
        }),
    });
    const h2 = makeHarness(session2, "instance:a");
    h2.begin(true);
    h2.moveToPieceDelta(1, true);
    almostEqual(h2.lastPreview().display_deg, 360);
    almostEqual(h2.lastPreview().rotation_deg, 0);
    h2.moveToPieceDelta(16, true);
    almostEqual(h2.lastPreview().display_deg, 375);
    almostEqual(h2.lastPreview().rotation_deg, 15);
}

{
    // Enable Shift during free rotate: no jump; then constrain.
    const session = baseSession({
        "instance:a": piece("instance:a", {
            piece_id: 1, x: 400, y: 400, w: 120, h: 80, rotation_deg: 20,
        }),
    });
    const h = makeHarness(session, "instance:a");
    h.begin(false);
    h.moveToPieceDelta(12, false);
    almostEqual(h.lastPreview().display_deg, 32);
    const beforeShift = h.lastPreview().display_deg;
    h.moveToPieceDelta(12, true); // same pointer delta, Shift engaged on this frame
    // Mode switch rebases pointer: display stays, then zero delta on engage frame.
    almostEqual(h.lastPreview().display_deg, beforeShift);
    h.moveToPieceDelta(13, true);
    almostEqual(h.lastPreview().display_deg, 45);
}

{
    // Release Shift during constrained rotate: no jump; then free again.
    const session = baseSession({
        "instance:a": piece("instance:a", {
            piece_id: 1, x: 400, y: 400, w: 120, h: 80, rotation_deg: 37,
        }),
    });
    const h = makeHarness(session, "instance:a");
    h.begin(true);
    h.moveToPieceDelta(16, true);
    almostEqual(h.lastPreview().display_deg, 60);
    const snapped = h.lastPreview().display_deg;
    h.moveToPieceDelta(16, false); // release Shift on this frame
    almostEqual(h.lastPreview().display_deg, snapped);
    h.moveToPieceDelta(21, false);
    almostEqual(h.lastPreview().display_deg, snapped + 5);
}

{
    // Multiple mode toggles during one drag keep continuity.
    const session = baseSession({
        "instance:a": piece("instance:a", {
            piece_id: 1, x: 400, y: 400, w: 120, h: 80, rotation_deg: 8,
        }),
    });
    const h = makeHarness(session, "instance:a");
    h.begin(false);
    h.moveToPieceDelta(10, false);
    almostEqual(h.lastPreview().display_deg, 18);
    h.moveToPieceDelta(10, true);
    almostEqual(h.lastPreview().display_deg, 18);
    h.moveToPieceDelta(11, true);
    almostEqual(h.lastPreview().display_deg, 30);
    h.moveToPieceDelta(11, false);
    almostEqual(h.lastPreview().display_deg, 30);
    h.moveToPieceDelta(14, false);
    almostEqual(h.lastPreview().display_deg, 33);
    h.moveToPieceDelta(14, true);
    almostEqual(h.lastPreview().display_deg, 33);
    h.moveToPieceDelta(15, true);
    almostEqual(h.lastPreview().display_deg, 45);
}

function svgRotatePoint(point, pivot, angleDeg) {
    const rad = (Number(angleDeg) * Math.PI) / 180;
    const cosA = Math.cos(rad);
    const sinA = Math.sin(rad);
    const x = point[0] - pivot.x;
    const y = point[1] - pivot.y;
    return [pivot.x + x * cosA - y * sinA, pivot.y + x * sinA + y * cosA];
}

function assertPreviewCommitApply(label, opts) {
    const start = opts.startDeg;
    const delta = opts.deltaDeg;
    const shift = Boolean(opts.shift);
    const expectedDisplay = opts.expectedDisplay;
    const expectedCommit = opts.expectedCommit != null
        ? opts.expectedCommit
        : RotationGeometry.normalizeAngleDeg(expectedDisplay);

    const session = baseSession({
        "instance:a": piece("instance:a", {
            piece_id: 1, x: 400, y: 400, w: 120, h: 80, rotation_deg: start,
        }),
    });
    const baseOutline = session.pieces["instance:a"].base_outline_mm.map((row) => row.slice());
    const pivotLocal = {
        x: session.pieces["instance:a"].pivot_mm.x,
        y: session.pieces["instance:a"].pivot_mm.y,
    };
    const h = makeHarness(session, "instance:a");
    assert.equal(h.begin(shift), true, label);
    if (Array.isArray(delta)) {
        delta.forEach((step) => h.moveToPieceDelta(step, shift));
    } else {
        h.moveToPieceDelta(delta, shift);
    }
    const preview = h.lastPreview();
    assert.ok(preview && preview.valid, `${label}: preview valid`);
    almostEqual(preview.display_deg, expectedDisplay);
    almostEqual(preview.rotation_deg, expectedCommit);

    h.up(shift);
    assert.equal(h.committed.length, 1, `${label}: committed once`);
    almostEqual(h.committed[0].angle, expectedCommit);
    almostEqual(h.committed[0].angle, RotationGeometry.normalizeAngleDeg(preview.rotation_deg));

    const applied = RotationGeometry.applyPieceRotation(session, "instance:a", h.committed[0].angle);
    almostEqual(applied.pieces["instance:a"].rotation_deg, expectedCommit);
    applied.pieces["instance:a"].outline_mm.forEach((point, index) => {
        const want = svgRotatePoint(baseOutline[index], pivotLocal, expectedCommit);
        assert.ok(
            Math.abs(point[0] - want[0]) < 1e-6 && Math.abs(point[1] - want[1]) < 1e-6,
            `${label}: outline[${index}] matches SVG rotate of commit angle`
        );
    });
}

{
    // Preview angle == committed angle == SVG-applied geometry (regression for release flip).
    assertPreviewCommitApply("free +25", { startDeg: 0, deltaDeg: 25, expectedDisplay: 25 });
    assertPreviewCommitApply("free -25", { startDeg: 0, deltaDeg: -25, expectedDisplay: -25, expectedCommit: 335 });
    assertPreviewCommitApply("free +15", { startDeg: 0, deltaDeg: 15, expectedDisplay: 15 });
    assertPreviewCommitApply("free -15", { startDeg: 0, deltaDeg: -15, expectedDisplay: -15, expectedCommit: 345 });
    assertPreviewCommitApply("shift 37->45", {
        startDeg: 37, deltaDeg: 1, shift: true, expectedDisplay: 45,
    });
    assertPreviewCommitApply("shift 37->30", {
        startDeg: 37, deltaDeg: -1, shift: true, expectedDisplay: 30,
    });
    assertPreviewCommitApply("shift reverse 75->45", {
        startDeg: 37, deltaDeg: [31, 1], shift: true, expectedDisplay: 45,
    });
    assertPreviewCommitApply("wrap below 0", {
        startDeg: 5, deltaDeg: -16, shift: true, expectedDisplay: -15, expectedCommit: 345,
    });
    assertPreviewCommitApply("wrap above 360", {
        startDeg: 350, deltaDeg: 16, shift: true, expectedDisplay: 375, expectedCommit: 15,
    });
}

{
    // Toggle Shift mid-drag, then commit the last previewed angle.
    const session = baseSession({
        "instance:a": piece("instance:a", {
            piece_id: 1, x: 400, y: 400, w: 120, h: 80, rotation_deg: 20,
        }),
    });
    const h = makeHarness(session, "instance:a");
    h.begin(false);
    h.moveToPieceDelta(12, false);
    almostEqual(h.lastPreview().display_deg, 32);
    h.moveToPieceDelta(12, true);
    almostEqual(h.lastPreview().display_deg, 32);
    h.moveToPieceDelta(13, true);
    almostEqual(h.lastPreview().rotation_deg, 45);
    const previewAngle = h.lastPreview().rotation_deg;
    h.up(true);
    almostEqual(h.committed[0].angle, previewAngle);
    const applied = RotationGeometry.applyPieceRotation(session, "instance:a", h.committed[0].angle);
    almostEqual(applied.pieces["instance:a"].rotation_deg, 45);
}

{
    // Pointer up commits the last displayed valid angle.
    const session = baseSession({
        "instance:a": piece("instance:a", {
            piece_id: 1, x: 400, y: 400, w: 120, h: 80, rotation_deg: 37,
        }),
    });
    const h = makeHarness(session, "instance:a");
    h.begin(true);
    h.moveToPieceDelta(16, true);
    almostEqual(h.lastPreview().display_deg, 60);
    h.up(true);
    assert.equal(h.committed.length, 1);
    almostEqual(h.committed[0].angle, 60);
    assert.equal(h.interaction.isActive(), false);
}

{
    // Escape / cancel / pointercancel / blur abort without commit.
    function abortCase(run) {
        const session = baseSession({
            "instance:a": piece("instance:a", {
                piece_id: 1, x: 400, y: 400, w: 120, h: 80, rotation_deg: 12,
            }),
        });
        const h = makeHarness(session, "instance:a");
        h.begin(false);
        h.moveToPieceDelta(20, false);
        run(h);
        assert.equal(h.committed.length, 0);
        assert.equal(h.interaction.isActive(), false);
        assert.equal(h.store.snapshot().dragPreview, null);
    }
    abortCase((h) => h.interaction.cancel());
    abortCase((h) => h.interaction.onPointerCancel());
    abortCase(() => {
        windowHost.dispatch("keydown", {
            key: "Escape",
            preventDefault() {},
        });
    });
    abortCase(() => {
        windowHost.dispatch("blur", {});
    });
}

{
    // Non-rotatable pieces remain blocked by eligibility.
    const session = baseSession({
        "instance:locked": piece("instance:locked", {
            piece_id: 9, x: 100, y: 100, w: 80, h: 80, allow: false,
        }),
    });
    const h = makeHarness(session, "instance:locked");
    assert.equal(h.begin(false), false);
    assert.equal(h.interaction.isActive(), false);
    assert.equal(
        RotationGeometry.pieceRotationEligibility(session, "instance:locked").rotatable,
        false
    );
}

console.log("board_editor_rotation_interaction.test.js: ok");
