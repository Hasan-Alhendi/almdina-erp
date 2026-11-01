"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const root = path.resolve(__dirname, "../..");

function load() {
    const files = [
        "public/js/door_cutting_order/drawing/door_cutting_order_clipped_corner_ux.js",
        "public/js/board_editor/history.js",
        "public/js/board_editor/session_document.js",
        "public/js/board_editor/move_geometry.js",
        "public/js/board_editor/snap_geometry.js",
        "public/js/board_editor/rotation_geometry.js",
        "public/js/door_cutting_order/cutting_plan/door_cutting_order_edge_display.js",
        "public/js/board_editor/plan_display_style.js",
        "public/js/board_editor/plan_edge_marks.js",
        "public/js/board_editor/store.js",
        "public/js/board_editor/canvas_renderer.js",
    ];
    const context = {
        frappe: { utils: { escape_html: (value) => String(value) }, ui: { form: { on() {} } } },
        __: (message) => message,
        document: {
            createElementNS: () => ({
                setAttribute() {},
                style: {},
                appendChild() {},
            }),
        },
    };
    context.window = context;
    context.globalThis = context;
    vm.createContext(context);
    files.forEach((relative) => {
        vm.runInContext(fs.readFileSync(path.join(root, relative), "utf8"), context);
    });
    return context.window;
}

function makeHost() {
    const stage = {
        clientWidth: 1100,
        clientHeight: 700,
        scrollLeft: 0,
        scrollTop: 0,
        classList: { add() {}, remove() {}, toggle() {}, contains() { return false; } },
        style: {},
        addEventListener() {},
        querySelector() { return null; },
        setPointerCapture() {},
        releasePointerCapture() {},
        getBoundingClientRect() {
            return { left: 0, top: 0, width: 1100, height: 700, right: 1100, bottom: 700 };
        },
    };
    const host = {
        clientWidth: 1100,
        clientHeight: 760,
        style: {},
        __html: "",
        set innerHTML(value) { this.__html = String(value); },
        get innerHTML() { return this.__html; },
        querySelector(sel) {
            if (sel === "[data-abe-stage]") return stage;
            return {
                onclick: null,
                addEventListener() {},
                querySelector() { return null; },
                querySelectorAll() { return []; },
                appendChild() {},
                getBoundingClientRect() {
                    return { left: 0, top: 0, width: 800, height: 600, right: 800, bottom: 600 };
                },
            };
        },
        querySelectorAll() { return []; },
    };
    return host;
}

function sheet() {
    return {
        sheet_no: 1,
        full_width_cm: 122,
        full_length_cm: 244,
        applied_trim_width_cm: 0,
        applied_trim_length_cm: 0,
        usable_width_cm: 122,
        usable_length_cm: 244,
    };
}

function parseBands(html) {
    const bands = [];
    const re = /<polyline class="abe-edge-band"([^>]*)>/g;
    let match = re.exec(html);
    while (match) {
        const attrs = match[1];
        const side = (attrs.match(/data-edge-side="([^"]*)"/) || [])[1] || "";
        const stroke = (attrs.match(/stroke="([^"]+)"/) || [])[1] || "";
        const dash = /stroke-dasharray=/.test(attrs);
        const points = ((attrs.match(/points="([^"]+)"/) || [])[1] || "").trim().split(/\s+/).map((pair) => {
            const [x, y] = pair.split(",").map(Number);
            return [x, y];
        });
        bands.push({ side, stroke, dash, points, pointerNone: /pointer-events="none"/.test(attrs) });
        match = re.exec(html);
    }
    return bands;
}

function sizeText(html) {
    const match = html.match(/class="abe-piece-size"[^>]*>([^<]+)</);
    return match ? match[1] : "";
}

function measurePx(html) {
    const match = html.match(/data-measure-px="([^"]+)"/);
    return match ? Number(match[1]) : 0;
}

function fontMm(html) {
    const match = html.match(/class="abe-piece-size"[^>]*font-size="([^"]+)"/);
    return match ? Number(match[1]) : 0;
}

function worldScale(html) {
    const match = html.match(/class="abe-world"[^>]*transform="[^"]*scale\(([^)]+)\)"/);
    return match ? Number(match[1]) : 0;
}

function nearly(actual, expected, tolerance, label) {
    assert.ok(Math.abs(actual - expected) <= tolerance, `${label}: ${actual} vs ${expected}`);
}

function translate(points, dx, dy) {
    return points.map((point) => [point[0] + dx, point[1] + dy]);
}

function samePoints(actual, expected, tolerance) {
    assert.equal(actual.length, expected.length);
    actual.forEach((point, index) => {
        nearly(point[0], expected[index][0], tolerance, `x${index}`);
        nearly(point[1], expected[index][1], tolerance, `y${index}`);
    });
}

const windowRef = load();
const editor = windowRef.AlmdinaBoardEditor;
const geometry = windowRef.AlmdinaClippedCornerGeometry;
const {
    CanvasRenderer, SessionDocument, createStore, History, MoveGeometry, RotationGeometry, PlanEdgeMarks,
} = editor;

assert.equal(typeof geometry.clippedEdgePaths, "function");
assert.equal(typeof PlanEdgeMarks.bandsForPiece, "function");

function renderPiece(piece, extra, viewport, defaultEdgeType) {
    const projection = {
        edge_display: { default_edge_type: defaultEdgeType || "" },
        board: { kerf_cm: 0.4, usable_width_cm: 122, usable_length_cm: 244 },
        layers: [{ match_key: "GEOMETRY", original_name: "GEOMETRY", aci_color: 7 }],
        sheets: [sheet()],
        pieces: [piece],
        elements: [
            {
                element_id: "sheet:1",
                kind: "sheet_outline",
                layer_match_key: "SHEET",
                sheet_no: 1,
                payload: {
                    full_width_cm: 122,
                    full_length_cm: 244,
                    usable_width_cm: 122,
                    usable_length_cm: 244,
                    applied_trim_width_cm: 0,
                    applied_trim_length_cm: 0,
                },
            },
            extra,
        ],
    };
    const layout = CanvasRenderer.sheetLayout(projection.sheets, 1);
    const session = SessionDocument.buildFromProjection(projection, layout);
    const history = History.create(session);
    const store = createStore({ projection, orderName: "ORD", planName: "PLAN" });
    store.attachSession(history.get(), history);
    store.setViewport(viewport);
    const host = makeHost();
    CanvasRenderer.render(host, store.snapshot(), {});
    return { host, store, history, session, projection, layout };
}

const regularEdges = {
    edge_width_top: 1,
    edge_width_bottom: 0,
    edge_long_left: 1,
    edge_long_right: 1,
    edge_long_right_type_override: "Blue PVC",
    edge_long_type: "",
    edge_width_type: "",
};
const regularPiece = {
    piece_id: 1,
    piece_instance_id: "pi-reg",
    label: "1.1",
    sheet_no: 1,
    piece_type: "Regular",
    fill_role: "regular",
    original_w: 40,
    original_h: 80,
    placement_cm: { x: 10, y: 20, w: 80, h: 40, rotated: false },
    display_edges: regularEdges,
    allow_rotation: true,
    allow_rotation_proven: true,
};
const regularElement = {
    element_id: "p1:rect",
    kind: "placement_rect",
    layer_match_key: "GEOMETRY",
    sheet_no: 1,
    piece_id: 1,
    piece_instance_id: "pi-reg",
    payload: {
        placement_cm: regularPiece.placement_cm,
        display_edges: regularEdges,
        geometry_source: "placement_rect",
        fill_role: "regular",
    },
};

const opened = renderPiece(regularPiece, regularElement, {
    scale: 0.25,
    opened: true,
    userAdjusted: true,
    columns: 1,
    scrollX: 0,
    scrollY: 0,
    fitted: false,
    cameraToken: 1,
});
const regularHtml = opened.host.innerHTML;
assert.equal(sizeText(regularHtml), "40*80");
assert.equal(measurePx(regularHtml), 10);
nearly(fontMm(regularHtml) * worldScale(regularHtml), 10, 0.05, "screen px at 0.25");
assert.match(regularHtml, /class="abe-board-title"[^>]*data-screen-px="11.5"/);
nearly(
    Number((regularHtml.match(/class="abe-board-title"[^>]*font-size="([^"]+)"/) || [])[1]) * worldScale(regularHtml),
    11.5,
    0.05,
    "board title screen px"
);
assert.match(regularHtml, /class="abe-board-stats"[^>]*data-screen-px="9"/);
assert.match(regularHtml, /abe-piece-caption[^>]*pointer-events="none"/);

const bands = parseBands(regularHtml);
assert.equal(bands.length, 3);
bands.forEach((band) => assert.equal(band.pointerNone, true));
const left = bands.find((band) => band.side === "left");
const right = bands.find((band) => band.side === "right");
const top = bands.find((band) => band.side === "top");
assert.ok(left && right && top);
assert.equal(left.stroke, "#d00000");
assert.equal(left.dash, false);
assert.equal(right.stroke, "#1d4ed8");
assert.equal(right.dash, true);
assert.equal(bands.some((band) => band.side === "bottom"), false);

const origin = opened.session.boards["1"];
const dx = origin.origin_x_mm + origin.trim_x_mm;
const dy = origin.origin_y_mm + origin.trim_y_mm;
const localBands = PlanEdgeMarks.bandsForPiece(
    regularPiece,
    regularEdges,
    0.25,
    "placement_rect",
    ""
);
const leftLocal = localBands.find((band) => band.side === "left");
samePoints(left.points, translate(leftLocal.points, dx, dy), 0.05);
assert.ok(left.points.every((point) => point[0] > 100 + dx + 1), "left band must sit inside the material");
assert.ok(Math.abs(left.points[0][0] - (100 + dx)) > 1, "left band must not lie on the outline");

const zoomed = renderPiece(regularPiece, regularElement, {
    scale: 2,
    opened: true,
    userAdjusted: true,
    columns: 1,
    scrollX: 0,
    scrollY: 0,
    fitted: false,
    cameraToken: 2,
});
assert.equal(measurePx(zoomed.host.innerHTML), 10);
nearly(fontMm(zoomed.host.innerHTML) * 2, 10, 0.05, "screen px when zoomed in");

const opening = renderPiece(regularPiece, regularElement, {
    scale: 0,
    opened: false,
    userAdjusted: false,
    columns: 1,
    scrollX: 0,
    scrollY: 0,
    fitted: false,
    cameraToken: 3,
});
assert.equal(measurePx(opening.host.innerHTML), 10);
nearly(fontMm(opening.host.innerHTML) * worldScale(opening.host.innerHTML), 10, 0.05, "opening screen px");

const smallPiece = {
    ...regularPiece,
    piece_instance_id: "pi-small",
    original_w: 2,
    original_h: 8,
    placement_cm: { x: 10, y: 20, w: 2, h: 8, rotated: false },
};
const small = renderPiece(smallPiece, {
    ...regularElement,
    piece_instance_id: "pi-small",
    payload: {
        ...regularElement.payload,
        placement_cm: smallPiece.placement_cm,
    },
}, {
    scale: 0.25,
    opened: true,
    userAdjusted: true,
    columns: 1,
    scrollX: 0,
    scrollY: 0,
    fitted: false,
    cameraToken: 4,
});
const smallPx = measurePx(small.host.innerHTML);
assert.ok(smallPx > 0 && smallPx < 10, `small measurement px ${smallPx}`);
assert.match(small.host.innerHTML, /class="abe-piece-size"/);
assert.ok(fontMm(small.host.innerHTML) < 20, "small-piece text stays within the short side");

function classified(piece, edges, fallback) {
    const display = windowRef.AlmdinaEdgeDisplay;
    const subject = Object.assign({}, edges, {
        rotated: Boolean(piece.placement_cm && piece.placement_cm.rotated),
        rotation_quarter_turns: piece.rotation_quarter_turns,
    });
    return display.pieceEdgeCustomFlags(subject, fallback || "", null);
}

const inheritedEdges = {
    edge_long_left: 1,
    edge_long_right: 1,
    edge_width_top: 1,
    edge_width_bottom: 1,
    edge_long_type: "PVC Default",
    edge_width_type: "PVC Default",
    edge_type: "PVC Default",
    edge_long_left_type_override: "",
    edge_long_right_type_override: "",
    edge_width_top_type_override: "",
    edge_width_bottom_type_override: "",
};
const inheritedPiece = {
    ...regularPiece,
    piece_instance_id: "pi-inherited",
    placement_cm: { x: 10, y: 20, w: 40, h: 80, rotated: false },
    display_edges: inheritedEdges,
};
const inherited = renderPiece(inheritedPiece, {
    ...regularElement,
    piece_instance_id: "pi-inherited",
    payload: { ...regularElement.payload, placement_cm: inheritedPiece.placement_cm, display_edges: inheritedEdges },
}, opened.store ? {
    scale: 0.25, opened: true, userAdjusted: true, columns: 1, scrollX: 0, scrollY: 0, fitted: false, cameraToken: 8,
} : {}, "PVC Default");
const inheritedBands = parseBands(inherited.host.innerHTML);
assert.equal(inheritedBands.length, 4);
inheritedBands.forEach((band) => {
    assert.equal(band.stroke, "#d00000", band.side);
    assert.equal(band.dash, false, band.side);
});
assert.equal(classified(inheritedPiece, inheritedEdges, "PVC Default").left, 0);

const explicitDefault = {
    ...inheritedEdges,
    edge_width_top_type_override: "PVC Default",
};
assert.equal(classified(inheritedPiece, explicitDefault, "PVC Default").top, 0);
const explicitView = renderPiece({
    ...inheritedPiece,
    piece_instance_id: "pi-explicit",
    display_edges: explicitDefault,
}, {
    ...regularElement,
    piece_instance_id: "pi-explicit",
    payload: { ...regularElement.payload, display_edges: explicitDefault, placement_cm: inheritedPiece.placement_cm },
}, {
    scale: 0.25, opened: true, userAdjusted: true, columns: 1, scrollX: 0, scrollY: 0, fitted: false, cameraToken: 9,
}, "PVC Default");
assert.equal(parseBands(explicitView.host.innerHTML).find((band) => band.side === "top").stroke, "#d00000");

const mixedEdges = {
    ...inheritedEdges,
    edge_long_left_type_override: "ABS Special",
};
const mixedFlags = classified(inheritedPiece, mixedEdges, "PVC Default");
assert.equal(mixedFlags.left, 1);
assert.equal(mixedFlags.right, 0);
assert.equal(mixedFlags.top, 0);
const mixedView = renderPiece({
    ...inheritedPiece,
    piece_instance_id: "pi-mixed",
    display_edges: mixedEdges,
}, {
    ...regularElement,
    piece_instance_id: "pi-mixed",
    payload: { ...regularElement.payload, display_edges: mixedEdges, placement_cm: inheritedPiece.placement_cm },
}, {
    scale: 0.25, opened: true, userAdjusted: true, columns: 1, scrollX: 0, scrollY: 0, fitted: false, cameraToken: 10,
}, "PVC Default");
const mixedBands = parseBands(mixedView.host.innerHTML);
assert.equal(mixedBands.find((band) => band.side === "left").stroke, "#1d4ed8");
assert.equal(mixedBands.find((band) => band.side === "left").dash, true);
assert.equal(mixedBands.find((band) => band.side === "right").stroke, "#d00000");
assert.equal(mixedBands.find((band) => band.side === "top").dash, false);

const rotatedPiece = {
    ...inheritedPiece,
    piece_instance_id: "pi-rot",
    placement_cm: { x: 10, y: 20, w: 80, h: 40, rotated: true },
    display_edges: mixedEdges,
};
const rotatedFlags = classified(rotatedPiece, mixedEdges, "PVC Default");
assert.equal(rotatedFlags.top, 1, "physical left custom moves to the placed top");
assert.equal(rotatedFlags.left, 0);
const rotatedView = renderPiece(rotatedPiece, {
    ...regularElement,
    piece_instance_id: "pi-rot",
    payload: {
        ...regularElement.payload,
        display_edges: mixedEdges,
        placement_cm: rotatedPiece.placement_cm,
    },
}, {
    scale: 0.25, opened: true, userAdjusted: true, columns: 1, scrollX: 0, scrollY: 0, fitted: false, cameraToken: 11,
}, "PVC Default");
const rotatedBands = parseBands(rotatedView.host.innerHTML);
assert.equal(rotatedBands.find((band) => band.side === "top").stroke, "#1d4ed8");
assert.equal(rotatedBands.find((band) => band.side === "bottom").stroke, "#d00000");

const breakPiece = cornerPiece({
    display_edges: {
        edge_width_top: 1,
        edge_long_right: 0,
        edge_long_left: 0,
        edge_width_bottom: 0,
        edge_break: 1,
        edge_break_only: 0,
        edge_type: "PVC Default",
        edge_width_top_type_override: "",
    },
});
const breakView = renderPiece(breakPiece, cornerElement(breakPiece), {
    scale: 0.3, opened: true, userAdjusted: true, columns: 1, scrollX: 0, scrollY: 0, fitted: false, cameraToken: 12,
}, "PVC Default");
const breakBands = parseBands(breakView.host.innerHTML);
assert.equal(breakBands.find((band) => band.side === "break").stroke, "#d00000");
assert.equal(breakBands.find((band) => band.side === "break").dash, false);
assert.equal(breakBands.find((band) => band.side === "top").stroke, "#d00000");

const edgeSheet = renderPiece({
    ...regularPiece,
    piece_instance_id: "pi-edge",
    placement_cm: { x: 0, y: 20, w: 40, h: 80, rotated: false },
}, {
    ...regularElement,
    piece_instance_id: "pi-edge",
    payload: {
        ...regularElement.payload,
        placement_cm: { x: 0, y: 20, w: 40, h: 80, rotated: false },
    },
}, {
    scale: 0.25, opened: true, userAdjusted: true, columns: 1, scrollX: 0, scrollY: 0, fitted: false, cameraToken: 13,
}, "PVC Default");
assert.match(edgeSheet.host.innerHTML, /class="abe-board-original-edges"[^>]*data-screen-px="9"/);
assert.match(edgeSheet.host.innerHTML, /Original edge · left/);
nearly(
    Number((edgeSheet.host.innerHTML.match(/class="abe-board-original-edges"[^>]*font-size="([^"]+)"/) || [])[1]) * 0.25,
    9,
    0.05,
    "original edge screen px"
);

function cornerPiece(overrides) {
    return {
        piece_id: 2,
        piece_instance_id: "pi-corner",
        label: "2.1",
        sheet_no: 1,
        piece_type: "Clipped Corner",
        fill_role: "clipped_corner",
        original_w: 40,
        original_h: 60,
        placement_cm: { x: 40, y: 50, w: 40, h: 60, rotated: false },
        clipped_corner_position: "Top Right",
        clipped_corner_width_cm: 12,
        clipped_corner_length_cm: 18,
        display_edges: {
            edge_width_top: 1,
            edge_long_right: 1,
            edge_break: 1,
            edge_break_only: 0,
            edge_long_left: 0,
            edge_width_bottom: 0,
            edge_type: "Special Blue",
        },
        allow_rotation: true,
        allow_rotation_proven: true,
        ...overrides,
    };
}

function cornerElement(piece) {
    const local = geometry.points(piece, 100, 100).map((point) => [
        piece.placement_cm.x * 10 + (point[0] / 100) * piece.placement_cm.w * 10,
        piece.placement_cm.y * 10 + (point[1] / 100) * piece.placement_cm.h * 10,
    ]);
    return {
        element_id: "p2:outer",
        kind: "finished_outline",
        layer_match_key: "GEOMETRY",
        sheet_no: 1,
        piece_id: piece.piece_id,
        piece_instance_id: piece.piece_instance_id,
        payload: {
            fill_role: piece.fill_role,
            geometry_source: piece.geometry_source || "placed_parametric_polygon",
            display_edges: piece.display_edges,
            piece_type: piece.piece_type,
        },
        geometry: { outer: local, holes: [] },
    };
}

const clipped = cornerPiece();
const clippedView = renderPiece(clipped, cornerElement(clipped), {
    scale: 0.3,
    opened: true,
    userAdjusted: true,
    columns: 1,
    scrollX: 0,
    scrollY: 0,
    fitted: false,
    cameraToken: 5,
});
const clippedBands = parseBands(clippedView.host.innerHTML);
assert.deepEqual(clippedBands.map((band) => band.side).sort(), ["break", "right", "top"]);
const breakBand = clippedBands.find((band) => band.side === "break");
assert.equal(breakBand.stroke, "#1d4ed8");
assert.equal(breakBand.dash, true);
const plain = clippedBands.find((band) => band.side === "top");
assert.equal(plain.stroke, "#d00000");
assert.equal(plain.dash, false);
const expectedClipped = PlanEdgeMarks.cornerBands(clipped, clipped.display_edges, "placed_parametric_polygon");
const clipOrigin = clippedView.session.boards["1"];
samePoints(
    plain.points,
    translate(expectedClipped.find((band) => band.side === "top").points, clipOrigin.origin_x_mm, clipOrigin.origin_y_mm),
    0.05
);
assert.ok(plain.points[0][1] > clipped.placement_cm.y * 10 + clipOrigin.origin_y_mm + 1);

const lPiece = cornerPiece({
    piece_type: "L-Shaped Corner",
    fill_role: "l_shaped",
    piece_instance_id: "pi-l-band",
    display_edges: {
        edge_long_left: 1,
        edge_break: 1,
        edge_width_top: 0,
        edge_width_bottom: 0,
        edge_long_right: 0,
        edge_break_only: 0,
        edge_type: "",
    },
});
const lView = renderPiece(lPiece, cornerElement(lPiece), {
    scale: 0.3,
    opened: true,
    userAdjusted: true,
    columns: 1,
    scrollX: 0,
    scrollY: 0,
    fitted: false,
    cameraToken: 6,
});
const lBands = parseBands(lView.host.innerHTML);
assert.deepEqual(lBands.map((band) => band.side).sort(), ["break", "left"]);
lBands.forEach((band) => {
    assert.equal(band.stroke, "#d00000");
    assert.equal(band.dash, false);
});

const imported = cornerPiece({
    piece_instance_id: "pi-import",
    geometry_source: "persisted_dxf",
    corner_mirrored: true,
    corner_rotation_quarter_turns: 1,
    display_edges: {
        edge_long_left: 1,
        edge_width_top: 0,
        edge_width_bottom: 0,
        edge_long_right: 0,
        edge_break: 0,
        edge_break_only: 0,
    },
});
const importedView = renderPiece(imported, {
    ...cornerElement(imported),
    payload: {
        ...cornerElement(imported).payload,
        geometry_source: "persisted_dxf",
    },
}, {
    scale: 0.3,
    opened: true,
    userAdjusted: true,
    columns: 1,
    scrollX: 0,
    scrollY: 0,
    fitted: false,
    cameraToken: 7,
});
const importedBands = parseBands(importedView.host.innerHTML);
const turned = geometry.pieceForQuarterTurns(Object.assign({}, imported.display_edges, imported), 1, true);
const expectedSides = ["top", "bottom", "left", "right"].filter((side) => {
    const flag = {
        top: "edge_width_top",
        bottom: "edge_width_bottom",
        left: "edge_long_left",
        right: "edge_long_right",
    }[side];
    return Boolean(turned[flag]);
});
assert.deepEqual(importedBands.map((band) => band.side).sort(), expectedSides.sort());
assert.equal(importedBands.some((band) => band.side === "left"), false);

function live(view) {
    const key = `instance:${view.projection.pieces[0].piece_instance_id}`;
    let session = view.history.get();
    const before = parseBands(view.host.innerHTML);
    session = RotationGeometry.applyPieceRotation(session, key, 90);
    view.store.commitSession(session);
    CanvasRenderer.render(view.host, view.store.snapshot(), {});
    const at90 = parseBands(view.host.innerHTML);
    const pivot = MoveGeometry.pivotInWorld(view.store.snapshot().session.pieces[key], view.store.snapshot().session.boards);
    at90.forEach((band) => {
        const source = before.find((row) => row.side === band.side);
        const rotated = source.points.map((point) => RotationGeometry.rotatePoint(point, pivot, 90));
        samePoints(band.points, rotated, 0.2);
    });
    session = view.store.snapshot().session;
    session = RotationGeometry.applyPieceRotation(session, key, 37);
    view.store.commitSession(session);
    CanvasRenderer.render(view.host, view.store.snapshot(), {});
    const at37 = parseBands(view.host.innerHTML);
    assert.equal(at37.length, before.length);
    const pivot37 = MoveGeometry.pivotInWorld(view.store.snapshot().session.pieces[key], view.store.snapshot().session.boards);
    at37.forEach((band) => {
        const source = at90.find((row) => row.side === band.side);
        const rotated = source.points.map((point) => RotationGeometry.rotatePoint(point, pivot37, 37 - 90));
        samePoints(band.points, rotated, 0.2);
    });
    const caption = view.host.innerHTML.match(/abe-piece-caption[^>]*transform="rotate\(([^ ]+)/);
    assert.ok(caption);
    nearly(Number(caption[1]), 37, 0.01, "caption rotation");
    const footprint = MoveGeometry.worldFootprint(view.store.snapshot().session.pieces[key], view.store.snapshot().session.boards);
    const inside = MoveGeometry.proposePieceDrop(view.store.snapshot().session, key, footprint.bounds.x + 30, footprint.bounds.y + 15);
    assert.equal(inside.ok, true);
    const movedIn = MoveGeometry.applyPieceMove(view.store.snapshot().session, inside);
    view.store.commitSession(movedIn);
    CanvasRenderer.render(view.host, view.store.snapshot(), {});
    const movedBands = parseBands(view.host.innerHTML);
    const movedPivot = MoveGeometry.pivotInWorld(view.store.snapshot().session.pieces[key], view.store.snapshot().session.boards);
    nearly(movedPivot.x - pivot37.x, movedBands[0].points[0][0] - at37[0].points[0][0], 0.2, "move dx");
    nearly(movedPivot.y - pivot37.y, movedBands[0].points[0][1] - at37[0].points[0][1], 0.2, "move dy");
    const outside = MoveGeometry.proposePieceDrop(view.store.snapshot().session, key, 4000, 80);
    assert.equal(outside.ok, true);
    view.store.commitSession(MoveGeometry.applyPieceMove(view.store.snapshot().session, outside));
    CanvasRenderer.render(view.host, view.store.snapshot(), {});
    assert.equal(parseBands(view.host.innerHTML).length, before.length);
    assert.equal((view.host.innerHTML.match(/class="abe-edge-band"/g) || []).length, before.length);
    view.store.setLayerVisible("GEOMETRY", false);
    CanvasRenderer.render(view.host, view.store.snapshot(), {});
    assert.equal(parseBands(view.host.innerHTML).length, 0);
    view.store.setLayerVisible("GEOMETRY", true);
    CanvasRenderer.render(view.host, view.store.snapshot(), {});
    const restoredLayer = parseBands(view.host.innerHTML);
    assert.equal(restoredLayer.length, before.length);
    view.store.undo();
    CanvasRenderer.render(view.host, view.store.snapshot(), {});
    view.store.redo();
    CanvasRenderer.render(view.host, view.store.snapshot(), {});
    assert.equal(parseBands(view.host.innerHTML).length, before.length);
    view.store.restoreEntry();
    CanvasRenderer.render(view.host, view.store.snapshot(), {});
    const restored = parseBands(view.host.innerHTML);
    assert.equal(restored.length, before.length);
    samePoints(restored[0].points, before.find((band) => band.side === restored[0].side).points, 0.2);
    const marks = (view.host.innerHTML.match(new RegExp(`data-piece-key="${key}"`, "g")) || []).length;
    assert.equal(marks, 1);
}

live(clippedView);

console.log("board_editor_edge_marks.test.js: ok");
