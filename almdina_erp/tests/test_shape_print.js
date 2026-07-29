"use strict";

const assert = require("node:assert/strict");
const path = require("node:path");

global.window = {};

require(path.resolve(
    __dirname,
    "../public/js/door_cutting_order_shape_print.js"
));

const renderer = window.AlmdinaShapePrint;

const classicPiece = {
    piece_type: "Special",
    special_shape_drawing_json: JSON.stringify({
        version: 1,
        canvas: { width: 1000, height: 650 },
        elements: [
            {
                id: "outline",
                type: "pen",
                color: "#172033",
                points: [[100, 100], [800, 100], [850, 520], [100, 520], [100, 100]],
            },
            {
                id: "dimension",
                type: "dimension",
                color: "#1769aa",
                x1: 100,
                y1: 570,
                x2: 850,
                y2: 570,
                text: "75 سم",
            },
            {
                id: "note",
                type: "note",
                color: "url(javascript:alert(1))",
                x: 380,
                y: 330,
                text: "<script>قص مائل</script>",
            },
        ],
    }),
};

assert.equal(renderer.hasVisual(classicPiece), true);
const classicSvg = renderer.svg(classicPiece, { label: "رسمة اختبار" });
assert.match(classicSvg, /<svg /);
assert.match(classicSvg, /<path /);
assert.match(classicSvg, /<line /);
assert.match(classicSvg, /&lt;script&gt;قص مائل/);
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

const regularPiece = { piece_type: "Regular" };
assert.equal(renderer.hasVisual(regularPiece), false);
assert.equal(renderer.notesCell(regularPiece, ""), "—");
assert.equal(renderer.notesCell(regularPiece, "درفة عادية"), "درفة عادية");

assert.match(renderer.css, /page-break-inside:avoid/);
assert.match(renderer.css, /tr\.dco-row-with-sketch/);

console.log("Printable door drawing SVG, fallback geometry, and safe notes checks passed");
