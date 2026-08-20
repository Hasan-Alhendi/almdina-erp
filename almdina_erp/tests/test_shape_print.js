"use strict";

const assert = require("node:assert/strict");
const path = require("node:path");

global.window = {};

require(path.resolve(
    __dirname,
    "../public/js/door_cutting_order/drawing/door_cutting_order_special_shape_geometry.js"
));
require(path.resolve(
    __dirname,
    "../public/js/door_cutting_order/drawing/door_cutting_order_shape_output_contract.js"
));
require(path.resolve(
    __dirname,
    "../public/js/door_cutting_order/printing/door_cutting_order_shape_print.js"
));

const renderer = window.AlmdinaShapePrint;

const classicPiece = {
    piece_type: "Special",
    special_shape_drawing_json: JSON.stringify({
        schema: "almdina.special-shape-documentation",
        version: 1,
        canvas: { widthMm: 800, heightMm: 2100 },
        reference: null,
        elements: [
            {
                id: "outline",
                type: "stroke",
                style: { color: "#172033", width: 3 },
                points: [
                    { xMm: 100, yMm: 100 },
                    { xMm: 700, yMm: 100 },
                    { xMm: 750, yMm: 1900 },
                    { xMm: 100, yMm: 1900 },
                    { xMm: 100, yMm: 100 },
                ],
                closed: true,
            },
            {
                id: "dimension",
                type: "dimension",
                style: { color: "#1769aa", width: 2 },
                start: { xMm: 100, yMm: 2000 },
                end: { xMm: 750, yMm: 2000 },
                valueMm: 650,
                unit: "mm",
            },
            {
                id: "note",
                type: "text",
                style: { color: "url(javascript:alert(1))" },
                position: { xMm: 380, yMm: 1000 },
                text: "<script>قص مائل</script>",
                font_size: 32,
            },
        ],
        notes: "",
        source: "pen",
        templateId: null,
    }),
};

assert.equal(renderer.hasVisual(classicPiece), true);
const classicSvg = renderer.svg(classicPiece, { label: "رسمة اختبار" });
assert.match(classicSvg, /<svg /);
assert.match(classicSvg, /<path /);
assert.match(classicSvg, /<line /);
assert.match(classicSvg, /&lt;script&gt;قص مائل/);
assert.match(classicSvg, /data-dco-readable-note="1"/);
assert.match(classicSvg, /font-size="32"/);
assert.match(classicSvg, /text-anchor="end"/);
assert.match(classicSvg, /paint-order="stroke"/);
assert.doesNotMatch(classicSvg, /fill="#fff8c9"/);
assert.doesNotMatch(classicSvg, /<script>/);
assert.doesNotMatch(classicSvg, /url\(javascript:/);

const classicCell = renderer.notesCell(
    classicPiece,
    "ملاحظة <b>آمنة</b>",
    { label: "رسمة الدرفة رقم 1" }
);
assert.match(classicCell, /dco-piece-sketch/);
assert.match(classicCell, /ملاحظة &lt;b&gt;آمنة&lt;\/b&gt;/);
assert.match(classicCell, /رسمة الدرفة/);

const geometryPiece = {
    piece_type: "Special",
    special_shape_geometry_json: JSON.stringify({
        version: 1,
        kind: "polygon",
        units: "cm",
        blank_width_cm: 80,
        blank_length_cm: 200,
        points: [[15, 0], [80, 0], [80, 200], [0, 200]],
    }),
};
assert.equal(renderer.hasVisual(geometryPiece), true);
assert.match(renderer.svg(geometryPiece), /<polygon /);

const documentedGeometryPiece = {
    ...geometryPiece,
    special_shape_drawing_json: classicPiece.special_shape_drawing_json,
};
assert.match(renderer.svg(documentedGeometryPiece), /<path /);
assert.doesNotMatch(
    renderer.svg(documentedGeometryPiece),
    /<polygon /,
    "Customer documents must prefer the operator drawing over the CNC fallback"
);

const regularPiece = { piece_type: "Regular" };
assert.equal(renderer.hasVisual(regularPiece), false);
assert.equal(renderer.notesCell(regularPiece, ""), "—");
assert.equal(renderer.notesCell(regularPiece, "درفة عادية"), "درفة عادية");

assert.match(renderer.css, /page-break-inside:avoid/);
assert.match(renderer.css, /tr\.dco-row-with-sketch/);

console.log("Printable door drawing SVG, fallback geometry, and safe notes checks passed");
