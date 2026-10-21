"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const source = fs.readFileSync(
    path.resolve(__dirname, "../../public/js/door_cutting_order/cutting_plan/door_cutting_order_cutting_plan_renderer.js"),
    "utf8"
);
const geometrySource = fs.readFileSync(
    path.resolve(__dirname, "../../public/js/door_cutting_order/drawing/door_cutting_order_special_shape_geometry.js"),
    "utf8"
);
const contractSource = fs.readFileSync(
    path.resolve(__dirname, "../../public/js/door_cutting_order/drawing/door_cutting_order_shape_output_contract.js"),
    "utf8"
);
const pieceGeometrySource = fs.readFileSync(
    path.resolve(__dirname, "../../public/js/door_cutting_order/cutting_plan/door_cutting_order_piece_geometry.js"),
    "utf8"
);
const nestedGlassRegressionSnapshot = JSON.parse(fs.readFileSync(
    path.resolve(__dirname, "../fixtures/liner_extension_nested_glass_snapshot.json"),
    "utf8"
));

const fakeWindow = {};
const rendererDiagnostics = [];
const testConsole = Object.assign({}, console, {
    error: (...args) => rendererDiagnostics.push(args),
});
const context = vm.createContext({
    window: fakeWindow,
    console: testConsole,
    JSON,
    Number,
    String,
    Math,
    // Frappe identity-language translation still interpolates positional values.
    __: (message, values) => {
        let output = String(message);
        if (Array.isArray(values)) {
            values.forEach((value, index) => {
                output = output.split("{" + index + "}").join(String(value));
            });
        }
        return output;
    },
});
vm.runInContext(geometrySource, context, {
    filename: "door_cutting_order_special_shape_geometry.js",
});
vm.runInContext(contractSource, context, {
    filename: "door_cutting_order_shape_output_contract.js",
});
vm.runInContext(pieceGeometrySource, context, {
    filename: "door_cutting_order_piece_geometry.js",
});
vm.runInContext(source, context, {
    filename: "door_cutting_order_cutting_plan_renderer.js",
});

const renderer = fakeWindow.AlmdinaCuttingPlanRender;
assert.ok(renderer);
assert.equal(typeof renderer.build, "function");
assert.equal(typeof renderer.parse, "function");
assert.equal(typeof renderer.print, "function");

const plan = {
    usable_board_width_cm: 122,
    usable_board_length_cm: 244,
    full_board_width_cm: 122,
    full_board_length_cm: 244,
    kerf_cm: 0.3,
    trim_cm: 0.5,
    used_area_m2: 0.48,
    total_board_area_m2: 2.9768,
    waste_area_m2: 2.4968,
    method_label: "Auto Pro",
    sheets: [
        {
            sheet_no: 1,
            pieces: [
                {
                    x: 0,
                    y: 0,
                    w: 60,
                    h: 80,
                    original_w: 60,
                    original_h: 80,
                    area_m2: 0.48,
                    label: "1",
                    piece_type: "Regular",
                    rotated: false,
                },
                {
                    x: 60,
                    y: 0,
                    w: 62,
                    h: 80,
                    original_w: 62,
                    original_h: 80,
                    area_m2: 0.496,
                    label: "2",
                    piece_type: "Special",
                    rotated: false,
                    special_shape_geometry_json:
                        fakeWindow.AlmdinaSpecialShapeGeometry.serialize(
                            fakeWindow.AlmdinaSpecialShapeGeometry.create(
                                "single-slope",
                                62,
                                80
                            )
                        ),
                },
                {
                    id: 3,
                    x: 80,
                    y: 90,
                    w: 20,
                    h: 20,
                    original_w: 20,
                    original_h: 20,
                    area_m2: 0.03,
                    label: "3.1",
                    piece_type: "Special",
                    rotated: true,
                    edge_long_left: 1,
                    geometry: {
                        schema_version: 1,
                        unit: "mm",
                        coordinate_space: "usable_sheet",
                        outer: [[800, 900], [1000, 900], [1000, 1100], [800, 1100]],
                        holes: [[[860, 960], [940, 960], [940, 1040], [860, 1040]]],
                    },
                },
                {
                    id: 4,
                    x: 0,
                    y: 90,
                    w: 40,
                    h: 60,
                    original_w: 40,
                    original_h: 60,
                    area_m2: 0.24,
                    label: "4.1",
                    source_piece_no: 4,
                    piece_type: "Regular",
                    rotated: false,
                    geometry: {
                        schema_version: 1,
                        unit: "mm",
                        coordinate_space: "usable_sheet",
                        outer: [[0, 900], [400, 900], [400, 1500], [0, 1500]],
                        holes: [],
                    },
                    overlays: [
                        {
                            kind: "liner",
                            layer: "Liner",
                            geometry: {
                                schema_version: 1,
                                unit: "mm",
                                coordinate_space: "usable_sheet",
                                path: [[40, 940], [180, 940], [180, 1060], [40, 1060]],
                                closed: true,
                            },
                        },
                        {
                            kind: "back_groove",
                            layer: "Rear Groove",
                            geometry: {
                                schema_version: 1,
                                unit: "mm",
                                coordinate_space: "usable_sheet",
                                path: [[20, 1480], [380, 1480]],
                                closed: false,
                            },
                        },
                        {
                            kind: "recessed_handle_cutout",
                            layer: "Handle Recess",
                            geometry: {
                                schema_version: 1,
                                unit: "mm",
                                coordinate_space: "usable_sheet",
                                path: [[80, 980], [160, 980], [160, 1020], [80, 1020]],
                                closed: true,
                            },
                        },
                    ],
                },
            ],
        },
    ],
    unplaced: [],
};
const frm = {
    doc: {
        name: "DCO-2026-00999",
        customer: "زبون الاختبار",
        board_description: "MDF أبيض 18 مم",
        cutting_plan_json: JSON.stringify(plan),
        pieces: [{ width_cm: 60, length_cm: 80, qty: 1 }],
    },
};

assert.equal(renderer.parse(frm).sheets.length, 1);
const html = renderer.build(frm, renderer.parse(frm));
assert.match(html, /DCO-2026-00999/);
assert.match(html, /زبون الاختبار/);
assert.match(html, /MDF أبيض 18 مم/);
assert.match(html, /dco-cutting-plan/);
assert.match(html, /dco-sheet-board/);
assert.match(html, /dco-board-waste-hatch[\s\S]*repeating-linear-gradient\(45deg,rgba\(71,85,105,\.18\) 0 1px,transparent 1px 8px\)/);
assert.ok(html.indexOf("dco-board-waste-hatch") < html.indexOf("dco-usable-sheet"));
assert.equal(html.split("dco-board-waste-hatch").length - 1, 1);
assert.match(html, /background:#e4f5ff/);
assert.match(html, /fill="#ffe5ad"/);
assert.match(html, /dco-special-exact-piece/);
assert.match(html, /Special door · geometric path/);
assert.match(html, /<path d="/);
assert.match(html, /data-geometry-source="manual-special"/);
assert.match(html, /data-geometry-source="dxf"/);
assert.match(html, /dco-extra-overlay/);
assert.match(html, /data-overlay-layer="Liner"/);
assert.match(html, /data-overlay-kind="liner"[^>]*stroke-width="0.7"/);
assert.match(html, /data-overlay-kind="back_groove"[^>]*stroke-width="0.7"/);
assert.match(html, /data-overlay-kind="liner"[^>]*stroke="#1d6fbf"/);
assert.match(html, /data-overlay-kind="liner"[^>]*stroke-dasharray="3 2.2"/);
assert.match(html, /data-overlay-kind="liner"[^>]*d="M[\d.-]+ [\d.-]+ L[\d.-]+ [\d.-]+"/);
assert.doesNotMatch(html, /data-overlay-kind="liner"[^>]* Z"/);
assert.match(html, /<rect class="dco-extra-overlay-path dco-extra-overlay-handle"/);
assert.match(html, /data-overlay-kind="recessed_handle_cutout"[^>]*stroke-width="0.65"/);
assert.doesNotMatch(html, /stroke-width="1.75"/);
assert.match(html, /dco-extra-addon-legend/);
assert.match(html, /Door add-on symbols/);
assert.match(html, /Double Edge/);
assert.match(html, /Full door double/);
assert.doesNotMatch(html, /dco-extra-addon-marks/);
assert.match(html, /data-geometry-id="pg-/);
assert.match(html, /fill-rule="evenodd"/);
assert.match(html, /clip-rule="evenodd"/);
assert.match(html, /dco-edge-line-svg/);
assert.doesNotMatch(html, /undefined/);

const doubledFrm = {
    doc: {
        ...frm.doc,
        pieces: [
            {
                width_cm: 60,
                length_cm: 80,
                qty: 3,
                extra_full_door_double: 1,
                piece_type: "Special",
            },
        ],
    },
};
const doubledHtml = renderer.build(doubledFrm, renderer.parse(doubledFrm));
assert.match(doubledHtml, /Qty 6/);

const extraAddonFrm = {
    doc: {
        ...frm.doc,
        pieces: [
            { width_cm: 60, length_cm: 80, qty: 1, piece_type: "Regular", extra_full_door_double: 1 },
            { width_cm: 62, length_cm: 80, qty: 1, piece_type: "Special" },
            { width_cm: 20, length_cm: 20, qty: 1, piece_type: "Special" },
            {
                width_cm: 40,
                length_cm: 60,
                qty: 1,
                piece_type: "L-Shaped Corner",
                extra_double: 1,
                extra_liner: 1,
            },
        ],
    },
};
const extraAddonHtml = renderer.build(extraAddonFrm, renderer.parse(extraAddonFrm));
assert.match(extraAddonHtml, /dco-extra-addon-marks/);
assert.match(extraAddonHtml, /dco-extra-addon-text[^>]*data-addon-kind="double"/);
assert.match(extraAddonHtml, /dco-extra-addon-text[^>]*data-addon-kind="full_door_double"/);
assert.match(extraAddonHtml, /data-addon-kind="double"/);
assert.match(extraAddonHtml, /data-addon-kind="full_door_double"/);
assert.match(extraAddonHtml, /data-addon-slot="top-end"/);
assert.match(extraAddonHtml, /data-addon-slot="top-start"/);
assert.match(extraAddonHtml, /dco-extra-addon-mark/);
assert.match(extraAddonHtml, /Double Edge/);
assert.match(extraAddonHtml, /Full door double/);
assert.doesNotMatch(extraAddonHtml, /dco-extra-addon-icon/);
assert.match(extraAddonHtml, /dco-extra-overlay/);
assert.match(extraAddonHtml, /data-overlay-layer="Liner"/);
assert.match(extraAddonHtml, /dco-extra-addon-legend/);
assert.match(extraAddonHtml, /#5a2d82/);
assert.match(extraAddonHtml, /data-double-edge-lines="1"/);

const regularOnlyFrm = {
    doc: {
        ...frm.doc,
        pieces: [
            {
                width_cm: 60,
                length_cm: 80,
                qty: 1,
                piece_type: "Regular",
                extra_full_door_double: 1,
            },
        ],
    },
};
const regularOnlyPlan = {
    ...plan,
    sheets: [
        {
            sheet_no: 1,
            pieces: [plan.sheets[0].pieces[0]],
        },
    ],
};
const regularOnlyHtml = renderer.build(regularOnlyFrm, regularOnlyPlan);
assert.match(regularOnlyHtml, /dco-extra-addon-marks/);
assert.match(regularOnlyHtml, /data-addon-kind="full_door_double"/);
assert.match(regularOnlyHtml, /dco-extra-addon-legend/);
assert.doesNotMatch(regularOnlyHtml, /dco-sheet-text-labels/);
assert.match(regularOnlyHtml, /dco-piece-number/);

const selectedDoublePlan = {
    ...regularOnlyPlan,
    sheets: [{
        sheet_no: 1,
        pieces: [{
            ...plan.sheets[0].pieces[0],
            piece_type: "Regular",
            extra_double: 1,
            extra_double_reference_sides: '["edge_width_top"]',
        }],
    }],
};
const selectedDoubleHtml = renderer.build(regularOnlyFrm, selectedDoublePlan);
assert.match(selectedDoubleHtml, /data-double-edge-side="edge_width_top"/);
assert.doesNotMatch(selectedDoubleHtml, /data-double-edge-side="edge_long_left"/);
assert.equal((selectedDoubleHtml.match(/data-double-edge-line-index="1"/g) || []).length, 1);
assert.match(selectedDoubleHtml, /border-top:1\.4px solid #5a2d82/);

const pastFiftyPlan = {
    ...plan,
    sheets: [
        {
            sheet_no: 2,
            pieces: [
                {
                    x: 0,
                    y: 0,
                    w: 40,
                    h: 50,
                    original_w: 40,
                    original_h: 50,
                    area_m2: 0.2,
                    label: "50.1",
                    source_piece_no: 50,
                    piece_type: "Regular",
                    rotated: false,
                },
                {
                    x: 40,
                    y: 0,
                    w: 40,
                    h: 50,
                    original_w: 40,
                    original_h: 50,
                    area_m2: 0.2,
                    label: "51.1",
                    source_piece_no: 51,
                    piece_type: "Regular",
                    rotated: false,
                },
            ],
        },
        {
            sheet_no: 1,
            pieces: [
                {
                    x: 0,
                    y: 0,
                    w: 40,
                    h: 50,
                    original_w: 40,
                    original_h: 50,
                    area_m2: 0.2,
                    label: "1.1",
                    source_piece_no: 1,
                    piece_type: "Regular",
                    rotated: false,
                },
            ],
        },
    ],
};
const pastFiftyFrm = {
    doc: {
        ...frm.doc,
        pieces: Array.from({ length: 51 }, (_, index) => ({
            width_cm: 40,
            length_cm: 50,
            qty: 1,
            piece_type: "Regular",
            piece_no: index + 1,
        })),
    },
};
const pastFiftyHtml = renderer.build(pastFiftyFrm, pastFiftyPlan);
assert.match(pastFiftyHtml, />50</);
assert.match(pastFiftyHtml, />51</);
assert.match(pastFiftyHtml, /Board 2/);
assert.match(pastFiftyHtml, /Board 1/);
assert.ok(pastFiftyHtml.indexOf("Board 2") < pastFiftyHtml.indexOf("Board 1"));
assert.doesNotMatch(html, /dco-sheet-board-has-trim/);
assert.doesNotMatch(html, /#e4dfd8/);

const trimmedPlan = {
    ...plan,
    full_board_width_cm: 122,
    full_board_length_cm: 244,
    usable_board_width_cm: 120,
    usable_board_length_cm: 243.6,
    applied_trim_width_cm: 1,
    applied_trim_length_cm: 0.2,
    sheets: [
        {
            sheet_no: 1,
            pieces: [
                {
                    x: 0,
                    y: 0,
                    w: 40,
                    h: 50,
                    area_m2: 0.2,
                    label: "1.1",
                    piece_type: "Regular",
                    rotated: false,
                },
            ],
        },
    ],
};
const trimmedHtml = renderer.build(frm, trimmedPlan);
const widthInset = (1 / 122) * 100;
const lengthInset = (0.2 / 244) * 100;
const usableWidth = (120 / 122) * 100;
const usableLength = (243.6 / 244) * 100;
assert.doesNotMatch(trimmedHtml, /dco-sheet-board-has-trim/);
assert.doesNotMatch(trimmedHtml, /#e4dfd8/);
assert.doesNotMatch(trimmedHtml, /border:1px dashed/);
assert.match(trimmedHtml, new RegExp(`data-trim-width-cm="1"`));
assert.match(trimmedHtml, new RegExp(`data-trim-length-cm="0.2"`));
assert.match(trimmedHtml, new RegExp(`left:${widthInset}%;top:${lengthInset}%;width:${usableWidth}%;height:${usableLength}%`));
assert.match(trimmedHtml, /dco-usable-sheet[\s\S]*dco-piece[\s\S]*left:0%;top:0%/);

vm.runInContext(
    fs.readFileSync(
        path.resolve(__dirname, "../../public/js/door_cutting_order/drawing/door_cutting_order_liner_geometry.js"),
        "utf8"
    ),
    context,
    { filename: "door_cutting_order_liner_geometry.js" }
);
const linerPlan = {
    usable_board_width_cm: 122,
    usable_board_length_cm: 244,
    full_board_width_cm: 122,
    full_board_length_cm: 244,
    trim_cm: 0.5,
    kerf_mm: 5,
    sheets: [{
        sheet_no: 1,
        pieces: [{
            x: 5,
            y: 5,
            w: 40,
            h: 60,
            original_w: 40,
            original_h: 60,
            label: "1.1",
            piece_type: "Regular",
            rotated: false,
        }],
    }],
};
const linerFrm = {
    doc: {
        name: "26-00103",
        kerf_mm: 5,
        pieces: [{
            extra_liner: 1,
            liner_reference_side: "edge_width_top",
            liner_offset_cm: 0,
            liner_width_cm: 1.8,
            piece_type: "Regular",
            width_cm: 40,
            length_cm: 60,
        }],
    },
};
const linerHtml = renderer.build(linerFrm, linerPlan);
const linerPath = linerHtml.match(/data-overlay-kind="liner"[^>]*d="([^"]+)"/);
assert.ok(linerPath, linerHtml);
assert.equal((linerPath[1].match(/L/g) || []).length, 1);
assert.match(linerPath[1], /^M[\d.]+ [\d.]+ L[\d.]+ [\d.]+$/);
assert.match(linerHtml, /data-overlay-kind="liner"[^>]*stroke-dasharray="3 2.2"/);
assert.doesNotMatch(linerHtml, /data-overlay-kind="liner"[^>]* Z"/);
assert.doesNotMatch(linerHtml, /data-liner-toolpath-error/);
assert.match(linerHtml, /<div class="dco-sheet-card"[\s\S]*data-overlay-kind="liner"/);
const linerYs = linerPath[1].match(/[\d.]+/g).filter((_, index) => index % 2 === 1).map(Number);
assert.equal(linerYs[0], linerYs[1]);
assert.ok(Math.abs(linerYs[0] - 1.5) < 0.05);

vm.runInContext(
    fs.readFileSync(
        path.resolve(__dirname, "../../public/js/door_cutting_order/drawing/door_cutting_order_machining_overlay.js"),
        "utf8"
    ),
    context,
    { filename: "door_cutting_order_machining_overlay.js" }
);

// Real persisted regression CP-2026-00092 / DCO 26-00112. Preview and DXF
// consume this same usable-sheet snapshot. Door 5.1 is inside the opening of
// rotated Glass door 1.1; the opening is void, not obstacle material.
const previewHost = nestedGlassRegressionSnapshot.sheets[0].pieces.find(piece => piece.label === "5.1");
const previewObstacles = fakeWindow.AlmdinaLinerGeometry.sheetObstaclesMm(
    nestedGlassRegressionSnapshot.sheets[0],
    Object.assign({}, previewHost)
);
assert.equal(previewObstacles.length, nestedGlassRegressionSnapshot.sheets[0].pieces.length - 1);
assert.equal(previewObstacles.some(obstacle => obstacle.diagnostic.pieceId === previewHost.id), false);
const previewGlassObstacle = previewObstacles.find(obstacle => obstacle.diagnostic.label === "1.1");
assert.equal(previewGlassObstacle.diagnostic.geometrySource, "placement_with_glass_hole");
assert.equal(previewGlassObstacle.holes.length, 1);

const previewFrm = {
    doc: {
        name: "26-00112",
        // Deliberately different: the frozen plan Kerf (3 mm) is authoritative.
        kerf_mm: 9,
        pieces: [
            {}, {}, {}, {},
            {
                // Deliberately different: a live order edit must not rewrite
                // the already-frozen plan path consumed by Preview and DXF.
                extra_liner: 1,
                liner_reference_side: "edge_width_bottom",
                liner_offset_cm: 1,
                liner_width_cm: 1.8,
                piece_type: "Regular",
                width_cm: 10,
                length_cm: 10,
            },
        ],
    },
};
for (const approvalStatus of ["Draft", "Approved"]) {
    const previewPlan = JSON.parse(JSON.stringify(nestedGlassRegressionSnapshot));
    previewPlan.approval_status = approvalStatus;
    previewPlan.saw_center_status = approvalStatus === "Approved" ? "Generated" : "Absent";
    const previewHtml = renderer.build(previewFrm, previewPlan);
    assert.match(previewHtml, /data-overlay-kind="liner"/);
    assert.doesNotMatch(previewHtml, /data-liner-toolpath-error="liner_extension_hits_piece"/);
    assert.doesNotMatch(previewHtml, /CUT_PATH/);
}

const trueCollisionPlan = JSON.parse(JSON.stringify(nestedGlassRegressionSnapshot));
const trueCollisionGlass = trueCollisionPlan.sheets[0].pieces.find(piece => piece.label === "1.1");
trueCollisionGlass.glass_hole_local_mm = [
    [100, 59], [939, 59], [939, 1939], [100, 1939],
];
rendererDiagnostics.length = 0;
const trueCollisionHtml = renderer.build(previewFrm, trueCollisionPlan);
assert.match(trueCollisionHtml, /data-liner-toolpath-error="liner_extension_hits_piece"/);
const trueCollisionDiagnostic = rendererDiagnostics
    .map(args => args[1])
    .find(item => item && item.host && item.host.label === "5.1"
        && item.neighbour && item.neighbour.label === "1.1");
assert.ok(trueCollisionDiagnostic);
assert.equal(trueCollisionDiagnostic.neighbour.geometrySource, "placement_with_glass_hole");
assert.equal(trueCollisionDiagnostic.cutterRadiusMm, 1.5);
assert.equal(JSON.stringify(trueCollisionDiagnostic.linerPathMm[0]), JSON.stringify([80.5, 492.5]));
assert.ok(Number.isFinite(trueCollisionDiagnostic.minimumDistanceMm));
assert.ok([
    "endpoint_in_material",
    "segment_crosses_material_boundary",
    "clearance_below_cutter_radius",
].includes(trueCollisionDiagnostic.rejectCondition));
assert.ok(Array.isArray(trueCollisionDiagnostic.linerPathMm));

const symbolPlan = {
    usable_board_width_cm: 122,
    usable_board_length_cm: 244,
    full_board_width_cm: 122,
    full_board_length_cm: 244,
    trim_cm: 0,
    kerf_mm: 5,
    sheets: [{
        sheet_no: 1,
        pieces: [{
            x: 0,
            y: 0,
            w: 100,
            h: 80,
            original_w: 100,
            original_h: 80,
            label: "1.1",
            piece_type: "Regular",
            rotated: false,
        }],
    }],
};
const symbolFrm = {
    doc: {
        name: "26-SYMBOLS",
        kerf_mm: 5,
        pieces: [{
            extra_liner: 1,
            liner_reference_side: "edge_width_top",
            liner_offset_cm: 10,
            liner_width_cm: 1.8,
            liner_start_cm: 20,
            liner_length_cm: 30,
            extra_back_groove: 1,
            back_groove_reference_side: "edge_long_right",
            back_groove_offset_cm: 4,
            back_groove_width_cm: 0.5,
            back_groove_start_cm: 10,
            back_groove_length_cm: 25,
            extra_recessed_handle_cutout: 1,
            recessed_handle_reference_side: "edge_width_bottom",
            recessed_handle_offset_cm: 2,
            recessed_handle_width_cm: 1.5,
            recessed_handle_start_cm: 15,
            recessed_handle_length_cm: 20,
            piece_type: "Regular",
            width_cm: 100,
            length_cm: 80,
        }],
    },
};
const symbolHtml = renderer.build(symbolFrm, symbolPlan);
const linerSymbol = symbolHtml.match(/data-overlay-kind="liner"[^>]*d="([^"]+)"/);
const grooveSymbol = symbolHtml.match(/data-overlay-kind="back_groove"[^>]*d="([^"]+)"/);
const handleSymbol = symbolHtml.match(/<rect class="dco-extra-overlay-path dco-extra-overlay-handle"[^>]*>/);
assert.ok(linerSymbol);
assert.ok(grooveSymbol);
assert.ok(handleSymbol);
assert.match(symbolHtml, /data-overlay-kind="liner"[^>]*stroke="#1d6fbf"/);
assert.match(symbolHtml, /data-overlay-kind="back_groove"[^>]*stroke="#2a7d4f"/);
assert.match(symbolHtml, /data-overlay-kind="recessed_handle_cutout"[^>]*stroke="#c45c12"/);
assert.doesNotMatch(symbolHtml, /dco-liner-toolpath/);
function pathSpan(path) {
    const values = path.match(/-?[\d.]+/g).map(Number);
    const xs = values.filter((_, index) => index % 2 === 0);
    const ys = values.filter((_, index) => index % 2 === 1);
    return {
        dx: Math.max(...xs) - Math.min(...xs),
        dy: Math.max(...ys) - Math.min(...ys),
    };
}
const linerSpan = pathSpan(linerSymbol[1]);
assert.ok(Math.abs(linerSpan.dx - 30) < 0.2, linerSymbol[1]);
assert.ok(linerSpan.dy < 0.2);
const grooveSpan = pathSpan(grooveSymbol[1]);
assert.ok(Math.abs(grooveSpan.dy - 31.25) < 0.3, grooveSymbol[1]);
assert.ok(grooveSpan.dx < 0.2);
assert.match(handleSymbol[0], /width="20"/);
assert.doesNotMatch(handleSymbol[0], /width="100"/);

const diagonalPlan = {
    ...symbolPlan,
    sheets: [{
        sheet_no: 1,
        pieces: [{
            x: 0,
            y: 0,
            w: 40,
            h: 60,
            original_w: 40,
            original_h: 60,
            label: "1.1",
            piece_type: "Clipped Corner",
            clipped_corner_position: "Top Right",
            clipped_corner_width_cm: 10,
            clipped_corner_length_cm: 16,
            rotated: false,
        }],
    }],
};
const diagonalFrm = {
    doc: {
        name: "26-DIAGONAL",
        kerf_mm: 5,
        pieces: [{
            extra_liner: 1,
            liner_reference_side: "edge_break_only",
            liner_offset_cm: 1,
            liner_width_cm: 0.8,
            liner_start_cm: 2,
            liner_length_cm: 4,
            piece_type: "Clipped Corner",
            clipped_corner_position: "Top Right",
            clipped_corner_width_cm: 10,
            clipped_corner_length_cm: 16,
            width_cm: 40,
            length_cm: 60,
        }],
    },
};
const diagonalHtml = renderer.build(diagonalFrm, diagonalPlan);
const diagonalPath = diagonalHtml.match(/data-overlay-kind="liner"[^>]*d="([^"]+)"/);
assert.ok(diagonalPath);
const diagonalSpan = pathSpan(diagonalPath[1]);
assert.ok(diagonalSpan.dx > 1 && diagonalSpan.dy > 1, diagonalPath[1]);

const marginPlan = {
    applied_trim_width_cm: 0,
    applied_trim_length_cm: 0,
    trim_cm: 0.5,
    full_board_width_cm: 122,
    full_board_length_cm: 244,
    sheets: [
        {
            sheet_no: 1,
            full_width_cm: 122,
            full_length_cm: 244,
            usable_width_cm: 122,
            usable_length_cm: 244,
            applied_trim_width_cm: 0,
            applied_trim_length_cm: 0,
            pieces: [{ x: 0, y: 0, w: 122, h: 244 }],
        },
        {
            sheet_no: 2,
            full_width_cm: 122,
            full_length_cm: 244,
            usable_width_cm: 121,
            usable_length_cm: 243,
            pieces: [
                { x: 0, y: 203, w: 40, h: 40 },
                { x: 40.3, y: 203, w: 40, h: 40 },
                { x: 80.6, y: 203, w: 40, h: 40 },
            ],
        },
    ],
};
assert.equal(
    JSON.stringify(renderer.originalEdges(marginPlan, marginPlan.sheets[0])),
    JSON.stringify(["right", "left", "top", "bottom"])
);
assert.equal(JSON.stringify(renderer.originalEdges(marginPlan, marginPlan.sheets[1])), "[]");
assert.equal(JSON.stringify(renderer.physicalMarginsMm(marginPlan, marginPlan.sheets[1])), JSON.stringify({
    left: 5,
    right: 9,
    top: 2035,
    bottom: 5,
}));
const marginHtml = renderer.build({ doc: { name: "26-00107" } }, marginPlan);
const trimWidths = [...marginHtml.matchAll(/data-trim-width-cm="([^"]+)"/g)].map(match => match[1]);
assert.deepEqual(trimWidths, ["0", "0.5"]);

const nestedGlassPlan = {
    usable_board_width_cm: 100,
    usable_board_length_cm: 100,
    full_board_width_cm: 100,
    full_board_length_cm: 100,
    kerf_cm: 0.3,
    trim_cm: 0,
    sheets: [{
        sheet_no: 1,
        // Adversarial order: guests before hosts must still paint above openings.
        pieces: [
            {
                id: 3,
                label: "3.1",
                x: 12,
                y: 12,
                w: 10,
                h: 10,
                original_w: 10,
                original_h: 10,
                piece_type: "Regular",
                glass_host_piece_id: 2,
            },
            {
                id: 2,
                label: "2.1",
                x: 6,
                y: 6,
                w: 30,
                h: 30,
                original_w: 30,
                original_h: 30,
                piece_type: "Glass",
                glass_margin_mm: 50,
                glass_hole_local_mm: [[50, 50], [250, 50], [250, 250], [50, 250]],
                glass_host_piece_id: 1,
            },
            {
                id: 4,
                label: "4.1",
                x: 18,
                y: 8,
                w: 8,
                h: 8,
                original_w: 8,
                original_h: 8,
                piece_type: "Regular",
                glass_host_piece_id: 1,
            },
            {
                id: 1,
                label: "1.1",
                x: 0,
                y: 0,
                w: 50,
                h: 50,
                original_w: 50,
                original_h: 50,
                piece_type: "Glass",
                glass_margin_mm: 50,
                glass_hole_local_mm: [[50, 50], [450, 50], [450, 450], [50, 450]],
            },
        ],
    }],
};
const nestedHtml = renderer.build({ doc: { name: "DCO-NEST-PREVIEW" } }, nestedGlassPlan);
assert.equal((nestedHtml.match(/data-piece-type="Glass"/g) || []).length, 2);
assert.equal((nestedHtml.match(/data-piece-type="Regular"/g) || []).length, 2);
assert.match(nestedHtml, /data-glass-host="2"/);
assert.match(nestedHtml, /data-glass-host="1"/);
assert.match(nestedHtml, /data-nest-depth="0"/);
assert.match(nestedHtml, /data-nest-depth="1"/);
assert.match(nestedHtml, /data-nest-depth="2"/);
assert.match(nestedHtml, /z-index:2;/);
assert.match(nestedHtml, /z-index:3;/);
assert.match(nestedHtml, /z-index:4;/);
assert.match(nestedHtml, /fill-rule="evenodd"/);
assert.match(nestedHtml, /dco-vector-piece/);
assert.match(nestedHtml, /dco-piece-number/);
assert.equal((nestedHtml.match(/dco-shaped-piece-outline/g) || []).length, 2);
assert.doesNotMatch(nestedHtml, /undefined/);

const nestedPrintRoot = renderer.build({ doc: { name: "DCO-NEST-PRINT" } }, nestedGlassPlan);
assert.match(nestedPrintRoot, /data-glass-host="1"/);
assert.match(nestedPrintRoot, /data-nest-depth="2"/);
assert.equal((nestedPrintRoot.match(/data-piece-type="/g) || []).length, 4);

console.log("Cutting-plan renderer simulation passed");
