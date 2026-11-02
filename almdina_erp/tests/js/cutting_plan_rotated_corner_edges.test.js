"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const root = path.resolve(__dirname, "../../public/js/door_cutting_order");

function read(relativePath) {
    return fs.readFileSync(path.join(root, relativePath), "utf8");
}

function elementFrom(html) {
    const node = {
        innerHTML: html,
        dataset: {},
        style: { setProperty() {} },
        get outerHTML() { return this.innerHTML; },
        querySelector() { return null; },
        querySelectorAll() { return []; },
        cloneNode() { return elementFrom(this.innerHTML); },
    };
    return node;
}

const fakeWindow = {};
const documentStub = {
    documentElement: {
        lang: "ar",
        getAttribute(name) { return name === "dir" ? "rtl" : name === "lang" ? this.lang : null; },
    },
    getElementById() { return null; },
    createElement() { return elementFrom(""); },
    head: { appendChild() {} },
};
const frappe = {
    boot: { lang: "ar" },
    msgprint() {},
    ui: { form: { on() {} } },
    utils: { escape_html(value) { return String(value ?? ""); } },
};
const context = vm.createContext({
    window: fakeWindow,
    document: documentStub,
    frappe,
    console,
    JSON,
    Number,
    String,
    Math,
    Object,
    Array,
    Set,
    Map,
    WeakMap,
    Promise,
    Boolean,
    Error,
    __: (value) => value,
});

[
    "drawing/door_cutting_order_special_shape_geometry.js",
    "drawing/door_cutting_order_shape_output_contract.js",
    "drawing/door_cutting_order_clipped_corner_ux.js",
    "drawing/door_cutting_order_liner_geometry.js",
    "drawing/door_cutting_order_liner_ux.js",
    "cutting_plan/door_cutting_order_piece_geometry.js",
    "cutting_plan/door_cutting_order_cutting_plan_renderer.js",
].forEach((relativePath) => {
    vm.runInContext(read(relativePath), context, { filename: relativePath });
});

const geometry = fakeWindow.AlmdinaClippedCornerGeometry;
const renderer = fakeWindow.AlmdinaCuttingPlanRender;
const frm = { doc: { name: "DCO-CORNER", customer: "عميل", pieces: [] } };

function planFor(piece) {
    return {
        usable_board_width_cm: 122,
        usable_board_length_cm: 244,
        full_board_width_cm: 122,
        full_board_length_cm: 244,
        sheets: [{ sheet_no: 1, pieces: [piece] }],
    };
}

function basePiece(pieceType) {
    return {
        id: "corner-1",
        x: 0,
        y: 0,
        w: 40,
        h: 80,
        original_w: 40,
        original_h: 80,
        area_m2: 0.32,
        label: "1.1",
        piece_type: pieceType,
        clipped_corner_position: "Top Right",
        clipped_corner_width_cm: 8,
        clipped_corner_length_cm: 16,
        rotated: false,
        edge_width_top: 1,
        edge_width_bottom: 0,
        edge_long_right: 0,
        edge_long_left: 1,
        edge_break: 1,
        edge_break_only: 0,
    };
}

function rotateClockwise(points, width, height) {
    return {
        points: points.map(([x, y]) => [height - y, x]),
        width: height,
        height: width,
    };
}

function samePointSet(actual, expected) {
    assert.equal(actual.length, expected.length);
    const unused = expected.map((point) => point.slice());
    actual.forEach((point) => {
        const index = unused.findIndex((candidate) => (
            Math.hypot(candidate[0] - point[0], candidate[1] - point[1]) <= 0.05
        ));
        assert.ok(index >= 0, `rotated vertex ${point} is not on the geometric contour`);
        unused.splice(index, 1);
    });
}

function polylines(html) {
    return [...String(html).matchAll(/points="([^"]+)"/g)].map((match) => match[1]);
}

function turnedGeometry(pieceType, turns) {
    const base = basePiece(pieceType);
    let points = geometry.points({ ...base, rotated: false }, 400, 800);
    let width = 400;
    let height = 800;
    for (let index = 0; index < turns; index += 1) {
        const rotated = rotateClockwise(points, width, height);
        points = rotated.points;
        width = rotated.width;
        height = rotated.height;
    }
    const visual = {
        ...base,
        w: width / 10,
        h: height / 10,
        rotated: turns % 2 === 1,
        corner_rotation_quarter_turns: turns,
    };
    const oriented = geometry.pieceForQuarterTurns(visual, turns);
    samePointSet(geometry.points(oriented, width, height), points);
    samePointSet(geometry.points(visual, width, height), points);
    return {
        visual,
        oriented,
        outer: points.map(([x, y]) => [x + 100, y + 200]),
        width,
        height,
    };
}

["L-Shaped Corner", "Clipped Corner"].forEach((pieceType) => {
    const turnMarkup = {};
    [0, 1, 2, 3].forEach((turns) => {
        const turned = turnedGeometry(pieceType, turns);
        const piece = {
            ...turned.visual,
            geometry: {
                schema_version: 1,
                unit: "mm",
                coordinate_space: "usable_sheet",
                outer: turned.outer,
                holes: [],
            },
        };
        const reversed = {
            ...piece,
            id: `${piece.id}-reversed`,
            geometry: { ...piece.geometry, outer: [...turned.outer].reverse() },
        };
        const html = renderer.build(frm, planFor(piece));
        const expected = polylines(geometry.edgeBandSvgMarkup(turned.oriented, 100, 100, { inheritStroke: true }));
        assert.equal(html.includes('data-geometry-source="dxf"'), true, `${pieceType} ${turns}`);
        assert.deepEqual(polylines(html), expected, `${pieceType} turn ${turns} bands`);
        assert.deepEqual(polylines(renderer.build(frm, planFor(reversed))), expected, `${pieceType} turn ${turns} ignores vertex order`);
        assert.match(html, /dco-edge-break-svg/, `${pieceType} turn ${turns} keeps the corner strap`);
        turnMarkup[turns] = expected.join("|");
    });
    assert.notEqual(turnMarkup[0], turnMarkup[1]);
    assert.notEqual(turnMarkup[0], turnMarkup[2]);
    assert.notEqual(turnMarkup[1], turnMarkup[3]);
});

const systemPiece = { ...basePiece("L-Shaped Corner"), w: 80, h: 40, rotated: true };
const systemBands = polylines(renderer.build(frm, planFor(systemPiece)));
const mixedLDoublePiece = {
    ...basePiece("L-Shaped Corner"),
    edge_width_top: 0,
    edge_long_left: 0,
    edge_long_right: 1,
    edge_break: 0,
    extra_double: 1,
    extra_double_reference_sides: '["edge_break", "edge_long_right"]',
};
const mixedLDoubleHtml = renderer.build(frm, planFor(mixedLDoublePiece));
assert.equal((mixedLDoubleHtml.match(/dco-edge-break-svg/g) || []).length, 2);
assert.ok((mixedLDoubleHtml.match(/stroke="#5a2d82"/g) || []).length >= 2);
assert.match(mixedLDoubleHtml, /stroke="#d00000"/);
const breakOnlyPurplePaths = (html) => [...html.matchAll(
    /class="dco-edge-line-svg dco-edge-break-svg"[^>]*stroke="#5a2d82"[^>]*points="([^"]+)"/g,
)].map(match => match[1]);
const breakWithNormalHtml = renderer.build(frm, planFor({
    ...mixedLDoublePiece,
    edge_break: 1,
}));
assert.equal(breakOnlyPurplePaths(mixedLDoubleHtml).length, 2);
assert.equal(breakOnlyPurplePaths(breakWithNormalHtml).length, 2);
assert.notDeepEqual(
    breakOnlyPurplePaths(mixedLDoubleHtml),
    breakOnlyPurplePaths(breakWithNormalHtml),
    "the L break edge uses its own normal-band state",
);
const lRightDoublePiece = {
    ...basePiece("L-Shaped Corner"),
    edge_width_top: 0,
    edge_long_left: 0,
    edge_long_right: 1,
    edge_break: 0,
    extra_double: 1,
    extra_double_reference_sides: '["edge_long_right"]',
};
const lRightDoubleHtml = renderer.build(frm, planFor(lRightDoublePiece));
assert.doesNotMatch(lRightDoubleHtml, /dco-edge-break-svg/);
assert.ok((lRightDoubleHtml.match(/stroke="#5a2d82"/g) || []).length >= 2);

function parsePolyline(points) {
    return String(points || "").trim().split(/\s+/).filter(Boolean).map(pair => pair.split(",").map(Number));
}

function distanceToPath(point, path) {
    let best = Infinity;
    for (let index = 0; index < path.length - 1; index += 1) {
        const start = path[index];
        const end = path[index + 1];
        const dx = end[0] - start[0];
        const dy = end[1] - start[1];
        const lengthSq = (dx * dx) + (dy * dy);
        if (lengthSq <= 1e-9) {
            best = Math.min(best, Math.hypot(point[0] - start[0], point[1] - start[1]));
            continue;
        }
        const ratio = Math.max(0, Math.min(1, (((point[0] - start[0]) * dx) + ((point[1] - start[1]) * dy)) / lengthSq));
        best = Math.min(best, Math.hypot(point[0] - (start[0] + (dx * ratio)), point[1] - (start[1] + (dy * ratio))));
    }
    return best;
}

function parallelGap(inner, outer) {
    const samples = inner.slice();
    for (let index = 0; index < inner.length - 1; index += 1) {
        samples.push([
            (inner[index][0] + inner[index + 1][0]) / 2,
            (inner[index][1] + inner[index + 1][1]) / 2,
        ]);
    }
    const distances = samples.map(point => distanceToPath(point, outer));
    return {
        min: Math.min(...distances),
        max: Math.max(...distances),
    };
}

function purpleBreakPaths(html) {
    return [...String(html).matchAll(
        /data-double-edge-side="edge_break"[\s\S]*?<polyline[^>]*stroke="#5a2d82"[^>]*points="([^"]+)"/g,
    )].map(match => parsePolyline(match[1]));
}

function redBreakPath(html) {
    const match = String(html).match(
        /<svg class="dco-piece-edge-svg"[\s\S]*?<polyline class="dco-edge-line-svg dco-edge-break-svg"[^>]*points="([^"]+)"/,
    );
    return match ? parsePolyline(match[1]) : null;
}

const bandedBreak = purpleBreakPaths(breakWithNormalHtml);
const redBreak = redBreakPath(breakWithNormalHtml);
assert.equal(bandedBreak.length, 2);
assert.ok(redBreak, "the normal L strap is drawn in the same viewBox");
const firstGap = parallelGap(bandedBreak[0], redBreak);
const secondGap = parallelGap(bandedBreak[1], redBreak);
assert.ok(firstGap.min > 2.4, `first purple line stays clear of the strap (${firstGap.min})`);
assert.ok(secondGap.min > firstGap.min + 1.5, "the two purple lines stay apart");
assert.ok(firstGap.max - firstGap.min < 1.5, "both legs of the L use the same viewBox offset");
assert.doesNotMatch(breakWithNormalHtml, /stroke="#e00000"/);
assert.doesNotMatch(breakWithNormalHtml, /transform="scale\(/);

const unbandedBreak = purpleBreakPaths(mixedLDoubleHtml);
assert.equal(unbandedBreak.length, 2);
const unbandedSpread = parallelGap(unbandedBreak[1], unbandedBreak[0]);
assert.ok(unbandedSpread.min > 1.8, "two purple lines stay apart without a strap");
assert.ok(
    parallelGap(unbandedBreak[0], bandedBreak[0]).min > 1,
    "a break without a strap is not pushed out by the other edge's strap",
);

const smallL = {
    ...basePiece("L-Shaped Corner"),
    w: 12,
    h: 18,
    edge_width_top: 0,
    edge_long_left: 0,
    edge_long_right: 0,
    edge_break: 1,
    extra_double: 1,
    extra_double_reference_sides: '["edge_break"]',
};
const smallHtml = renderer.build(frm, planFor(smallL));
const smallPurple = purpleBreakPaths(smallHtml);
const smallRed = redBreakPath(smallHtml);
assert.equal(smallPurple.length, 2);
assert.ok(parallelGap(smallPurple[0], smallRed).min > 4, "a small L keeps a visible gap after the viewBox conversion");
assert.ok(parallelGap(smallPurple[1], smallPurple[0]).min > 2, "a small L keeps the two lines apart");

const manySides = {
    ...basePiece("L-Shaped Corner"),
    edge_width_top: 1,
    edge_long_left: 0,
    edge_long_right: 0,
    edge_width_bottom: 0,
    edge_break: 0,
    extra_double: 1,
    extra_double_reference_sides: '["edge_width_top","edge_long_left","edge_break"]',
};
const manyHtml = renderer.build(frm, planFor(manySides));
["edge_width_top", "edge_long_left", "edge_break"].forEach(side => {
    assert.equal((manyHtml.match(new RegExp(`data-double-edge-side="${side}"`, "g")) || []).length, 2, side);
});
assert.equal((manyHtml.match(/data-double-edge-side="edge_long_right"/g) || []).length, 0);
const topDouble = manyHtml.match(/data-double-edge-side="edge_width_top"[\s\S]*?points="([^"]+)"/);
const leftDouble = manyHtml.match(/data-double-edge-side="edge_long_left"[\s\S]*?points="([^"]+)"/);
assert.notEqual(topDouble[1], leftDouble[1], "a banded side and an unbanded side do not share an offset");

const rotatedDouble = {
    ...basePiece("L-Shaped Corner"),
    w: 80,
    h: 40,
    rotated: true,
    edge_break: 1,
    extra_double: 1,
    extra_double_reference_sides: '["edge_break"]',
};
const rotatedHtml = renderer.build(frm, planFor(rotatedDouble));
const uprightHtml = renderer.build(frm, planFor({
    ...basePiece("L-Shaped Corner"),
    edge_break: 1,
    extra_double: 1,
    extra_double_reference_sides: '["edge_break"]',
}));
assert.notEqual(purpleBreakPaths(rotatedHtml).join("|"), purpleBreakPaths(uprightHtml).join("|"));
assert.ok(parallelGap(purpleBreakPaths(rotatedHtml)[0], redBreakPath(rotatedHtml)).min > 2.4);

const mirrorSource = {
    ...basePiece("L-Shaped Corner"),
    clipped_corner_width_cm: 10,
    clipped_corner_length_cm: 24,
};
let mirroredPoints = reflectX(geometry.points(mirrorSource, 400, 800), 400);
let mirroredWidth = 400;
let mirroredHeight = 800;
const mirroredTurn = rotateClockwise(mirroredPoints, mirroredWidth, mirroredHeight);
mirroredPoints = mirroredTurn.points;
mirroredWidth = mirroredTurn.width;
mirroredHeight = mirroredTurn.height;
const mirroredPiece = {
    ...mirrorSource,
    w: mirroredWidth / 10,
    h: mirroredHeight / 10,
    rotated: true,
    corner_rotation_quarter_turns: 1,
    corner_mirrored: 1,
    edge_break: 1,
    edge_long_left: 1,
    extra_double: 1,
    extra_double_reference_sides: '["edge_break","edge_long_left"]',
    geometry: {
        schema_version: 1,
        unit: "mm",
        coordinate_space: "usable_sheet",
        outer: mirroredPoints.map(([x, y]) => [x + 100, y + 200]),
        holes: [],
    },
};
const mirroredUprightHtml = renderer.build(frm, planFor({
    ...mirrorSource,
    edge_break: 1,
    extra_double: 1,
    extra_double_reference_sides: '["edge_break"]',
}));
const mirroredHtml = renderer.build(frm, planFor(mirroredPiece));
assert.equal(purpleBreakPaths(mirroredHtml).length, 2);
assert.notEqual(purpleBreakPaths(mirroredHtml).join("|"), purpleBreakPaths(mirroredUprightHtml).join("|"));
assert.ok(parallelGap(purpleBreakPaths(mirroredHtml)[0], redBreakPath(mirroredHtml)).min > 2);
assert.equal((mirroredHtml.match(/data-double-edge-side="edge_long_left"/g) || []).length, 0,
    "mirroring moves the selected semantic left edge onto its visual side");
assert.equal((mirroredHtml.match(/data-double-edge-side="edge_width_bottom"/g) || []).length, 2);

const bevel = {
    ...basePiece("Clipped Corner"),
    edge_width_top: 0,
    edge_long_left: 0,
    edge_long_right: 0,
    edge_break: 1,
    edge_break_only: 0,
    extra_double: 1,
    extra_double_reference_sides: '["edge_break"]',
};
const bevelHtml = renderer.build(frm, planFor(bevel));
const bevelPurple = purpleBreakPaths(bevelHtml);
assert.equal(bevelPurple.length, 2);
assert.ok(parallelGap(bevelPurple[0], redBreakPath(bevelHtml)).min > 2.4);
assert.ok(parallelGap(bevelPurple[1], bevelPurple[0]).min > 1.5);

const regularMixed = {
    id: "regular-mixed",
    x: 10,
    y: 10,
    w: 30,
    h: 50,
    original_w: 30,
    original_h: 50,
    area_m2: 0.15,
    label: "9.1",
    piece_type: "Regular",
    edge_width_top: 1,
    edge_long_left: 0,
    extra_double: 1,
    extra_double_reference_sides: '["edge_width_top","edge_long_left"]',
};
const regularMixedHtml = renderer.build(frm, planFor(regularMixed));
assert.match(regularMixedHtml, /top:8px;[^"]*border-top:1\.4px solid #5a2d82/);
assert.match(regularMixedHtml, /top:11px;[^"]*border-top:1\.4px solid #5a2d82/);
assert.match(regularMixedHtml, /left:4\.5px;[^"]*border-left:1\.4px solid #5a2d82/);
assert.match(regularMixedHtml, /left:7\.5px;[^"]*border-left:1\.4px solid #5a2d82/);
assert.doesNotMatch(regularMixedHtml, /<svg class="dco-piece-double-edge-svg[\s\S]*?<text/);

const doubleSvg = mixedLDoubleHtml.match(/<svg class="dco-piece-double-edge-svg[\s\S]*?<\/svg>/);
assert.ok(doubleSvg);
assert.doesNotMatch(doubleSvg[0], /<text|دبل قشاط|دبل ضلع|دبل القشاط/);
assert.match(mixedLDoubleHtml, /Double Edge/);
assert.match(
    read("cutting_plan/door_cutting_order_cutting_plan_renderer.js"),
    /\.dco-piece-double-edge-svg \.dco-edge-line-svg[\s\S]*?#5a2d82 !important/,
);

const previewRow = {
    piece_type: "L-Shaped Corner",
    width_cm: 40,
    length_cm: 80,
    clipped_corner_position: "Top Right",
    clipped_corner_width_cm: 8,
    clipped_corner_length_cm: 16,
    edge_long_right: 1,
    edge_break: 0,
    extra_double: 1,
};
const previewPiece = fakeWindow.AlmdinaLinerGeometry.pieceFromRow(previewRow);
const previewDraft = {
    piece: previewPiece,
    row: previewRow,
    kind: "liner",
    enabled: false,
    side: "edge_break",
    offsetCm: 0,
    widthCm: 1,
    startCm: 0,
    lengthCm: 0,
    fullLength: true,
};
const previewHtml = fakeWindow.AlmdinaLinerEditor.previewSvg(previewDraft, {
    multi: true,
    doubleSides: ["edge_break", "edge_long_right"],
});
const previewBanded = fakeWindow.AlmdinaLinerEditor.previewSvg({
    ...previewDraft,
    row: { ...previewRow, edge_break: 1 },
}, {
    multi: true,
    doubleSides: ["edge_break", "edge_long_right"],
});
function previewSidePoints(html, side) {
    const block = String(html).match(new RegExp(`<g data-double-edge-side="${side}">([\\s\\S]*?)</g>`));
    assert.ok(block, side);
    return [...block[1].matchAll(/points="([^"]+)"/g)].map(match => match[1]);
}
assert.equal(previewSidePoints(previewHtml, "edge_break").length, 2);
assert.equal(previewSidePoints(previewHtml, "edge_long_right").length, 2);
assert.notEqual(
    previewSidePoints(previewHtml, "edge_break").join("|"),
    previewSidePoints(previewBanded, "edge_break").join("|"),
    "preview offsets each L edge from its own strap",
);
assert.equal(
    previewSidePoints(previewHtml, "edge_long_right").join("|"),
    previewSidePoints(previewBanded, "edge_long_right").join("|"),
);
assert.match(previewHtml, /stroke="#5a2d82"/);
assert.doesNotMatch(previewHtml, /<text[^>]*>[^<]*دبل/);
const legacyPiece = {
    ...systemPiece,
    edge_width_top: systemPiece.edge_long_left,
    edge_width_bottom: systemPiece.edge_long_right,
    edge_long_right: systemPiece.edge_width_top,
    edge_long_left: systemPiece.edge_width_bottom,
};
assert.deepEqual(
    systemBands,
    polylines(geometry.edgeBandSvgMarkup(legacyPiece, 100, 100, { inheritStroke: true })),
    "system-plan 90° banding stays on the existing rotated corner model"
);
const dxfQuarterTurn = turnedGeometry("L-Shaped Corner", 1);
assert.deepEqual(
    systemBands,
    polylines(geometry.edgeBandSvgMarkup(dxfQuarterTurn.oriented, 100, 100, { inheritStroke: true })),
    "a DXF quarter-turn uses the same visual edges as the system plan"
);

const unresolved = {
    ...dxfQuarterTurn.visual,
    rotated: true,
    geometry: {
        schema_version: 1,
        unit: "mm",
        coordinate_space: "usable_sheet",
        outer: dxfQuarterTurn.outer,
        holes: [],
    },
};
delete unresolved.corner_rotation_quarter_turns;
const unresolvedHtml = renderer.build(frm, planFor(unresolved));
assert.equal(polylines(unresolvedHtml).length, 0, "DXF corner bands are omitted when the quarter-turn is unknown");
assert.equal(unresolvedHtml.includes('data-geometry-source="dxf"'), true);

const rectangle = {
    id: "rect-1",
    x: 0,
    y: 0,
    w: 40,
    h: 80,
    original_w: 40,
    original_h: 80,
    area_m2: 0.32,
    label: "2.1",
    piece_type: "Regular",
    rotated: true,
    edge_long_left: 1,
    geometry: {
        schema_version: 1,
        unit: "mm",
        coordinate_space: "usable_sheet",
        outer: [[0, 0], [800, 0], [800, 400], [0, 400]],
        holes: [],
    },
};
const rectangleHtml = renderer.build(frm, planFor(rectangle));
assert.match(rectangleHtml, /border-top:3px solid #d00000/, "a rotated rectangle keeps the bbox edge marker");
assert.doesNotMatch(rectangleHtml, /dco-edge-break-svg/);

function reflectX(points, width) {
    return points.map(([x, y]) => [width - x, y]);
}

["L-Shaped Corner", "Clipped Corner"].forEach((pieceType) => {
    const plain = turnedGeometry(pieceType, 0);
    [0, 1, 2, 3].forEach((turns) => {
        let points = reflectX(geometry.points({ ...basePiece(pieceType), rotated: false }, 400, 800), 400);
        let width = 400;
        let height = 800;
        for (let index = 0; index < turns; index += 1) {
            const rotated = rotateClockwise(points, width, height);
            points = rotated.points;
            width = rotated.width;
            height = rotated.height;
        }
        const visual = {
            ...basePiece(pieceType),
            w: width / 10,
            h: height / 10,
            rotated: turns % 2 === 1,
            corner_rotation_quarter_turns: turns,
            corner_mirrored: 1,
            edge_profiles: {
                width_top: { side: "width_top", edge_type: "TOP", thickness_mm: 1.1 },
                long_left: { side: "long_left", edge_type: "LEFT", thickness_mm: 2.2 },
            },
            edge_width_top_type_override: "TOP",
            edge_long_left_type_override: "LEFT",
        };
        const oriented = geometry.pieceForQuarterTurns(visual, turns, 1);
        samePointSet(geometry.points(oriented, width, height), points);
        samePointSet(geometry.points(visual, width, height), points);
        const storedOuter = points.map(([x, y]) => [x + 100, y + 200]);
        const piece = {
            ...visual,
            geometry: {
                schema_version: 1,
                unit: "mm",
                coordinate_space: "usable_sheet",
                outer: storedOuter,
                holes: [],
            },
        };
        const html = renderer.build(frm, planFor(piece));
        const expected = polylines(geometry.edgeBandSvgMarkup(oriented, 100, 100, { inheritStroke: true }));
        assert.deepEqual(polylines(html), expected, `${pieceType} mirror turn ${turns} bands`);
        assert.equal(piece.geometry.outer, storedOuter, `${pieceType} mirror turn ${turns} does not rewrite DXF`);
        assert.match(html, /dco-edge-break-svg/, `${pieceType} mirror turn ${turns} keeps the corner strap`);
        if (turns === 0) {
            assert.notEqual(expected.join("|"), polylines(geometry.edgeBandSvgMarkup(plain.oriented, 100, 100, { inheritStroke: true })).join("|"));
            assert.equal(oriented.edge_profiles.long_right.edge_type, "LEFT");
            assert.equal(oriented.edge_profiles.long_right.thickness_mm, 2.2);
            assert.equal(oriented.edge_profiles.width_top.edge_type, "TOP");
            assert.equal(oriented.edge_profiles.width_top.thickness_mm, 1.1);
            assert.equal(oriented.edge_long_right_type_override, "LEFT");
            assert.equal(oriented.edge_width_top_type_override, "TOP");
            assert.equal(oriented.edge_long_left, 0);
            assert.equal(oriented.edge_long_right, 1);
        }
    });
});

const storedTurns = {
    ...basePiece("L-Shaped Corner"),
    w: 80,
    h: 40,
    rotated: true,
    corner_mirrored: 1,
    corner_rotation_quarter_turns: 3,
};
const drawnTurns = geometry.pieceForQuarterTurns(storedTurns, 3, true);
assert.deepEqual(
    polylines(renderer.build(frm, planFor(storedTurns))),
    polylines(renderer.build(frm, planFor(drawnTurns))),
    "a system plan draws the stored quarter-turn and mirror once"
);
assert.equal(geometry.pieceForQuarterTurns(basePiece("L-Shaped Corner"), 0, "sideways"), null);

const clippedChord = {
    ...basePiece("Clipped Corner"),
    edge_break: 0,
    edge_break_only: 1,
    edge_width_top: 0,
    edge_width_bottom: 0,
    edge_long_left: 0,
    edge_long_right: 0,
};
const lNotch = {
    ...basePiece("L-Shaped Corner"),
    edge_break: 1,
    edge_width_top: 0,
    edge_width_bottom: 0,
    edge_long_left: 0,
    edge_long_right: 0,
};
const chordPlain = geometry.edgeBandSvgMarkup(geometry.pieceForQuarterTurns(clippedChord, 0, false), 400, 800, { inheritStroke: true });
const chordMirror = geometry.edgeBandSvgMarkup(geometry.pieceForQuarterTurns(clippedChord, 0, true), 400, 800, { inheritStroke: true });
const notchPlain = geometry.edgeBandSvgMarkup(geometry.pieceForQuarterTurns(lNotch, 0, false), 400, 800, { inheritStroke: true });
const notchMirror = geometry.edgeBandSvgMarkup(geometry.pieceForQuarterTurns(lNotch, 0, true), 400, 800, { inheritStroke: true });
assert.match(chordPlain, /dco-edge-break-only-svg/);
assert.match(notchPlain, /dco-edge-break-svg/);
assert.notEqual(polylines(chordPlain).join("|"), polylines(chordMirror).join("|"), "the clipped diagonal follows the reflection");
assert.notEqual(polylines(notchPlain).join("|"), polylines(notchMirror).join("|"), "the L notch follows the reflection");

const previewBandPiece = {
    ...basePiece("Clipped Corner"),
    edge_break: 0,
    edge_break_only: 0,
    edge_width_top: 1,
    edge_width_bottom: 0,
    edge_long_left: 0,
    edge_long_right: 1,
};
const insetReference = geometry.clippedEdgePaths(previewBandPiece, 400, 800, { insetPx: 4 });
const insetPreview = geometry.edgeBandSvgMarkup(previewBandPiece, 400, 800, {
    inheritStroke: false,
    insetPx: 4,
    endTrimPx: 6,
});
const previewLines = polylines(insetPreview).map(line => line.split(" ").map(point => point.split(",").map(Number)));
assert.equal(previewLines.length, 2);
assert.ok(Math.abs(previewLines[0][0][0] - insetReference.top[0][0] - 6) < 0.1);
assert.ok(Math.abs(previewLines[0].at(-1)[0] - insetReference.top.at(-1)[0] + 6) < 0.1);
assert.ok(Math.abs(previewLines[1][0][1] - insetReference.right[0][1] - 6) < 0.1);
assert.ok(Math.abs(previewLines[1].at(-1)[1] - insetReference.right.at(-1)[1] + 6) < 0.1);
