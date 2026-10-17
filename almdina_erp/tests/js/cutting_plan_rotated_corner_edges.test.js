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

const systemIgnoringMirror = {
    ...systemPiece,
    corner_mirrored: 1,
    corner_rotation_quarter_turns: 3,
};
assert.deepEqual(
    polylines(renderer.build(frm, planFor(systemIgnoringMirror))),
    systemBands,
    "system plans keep the boolean rotation and ignore imported mirror metadata"
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
