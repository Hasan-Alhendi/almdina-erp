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

const croppedReferencePiece = JSON.parse(JSON.stringify(classicPiece));
const croppedReferenceDrawing = JSON.parse(croppedReferencePiece.special_shape_drawing_json);
croppedReferenceDrawing.reference = {
    fileUrl: "/private/files/a4-scan.jpg",
    opacity: 0.72,
    rotationDeg: 0,
    locked: true,
    crop: { x: 0.2, y: 0.1, width: 0.5, height: 0.6 },
    imageSize: { widthPx: 2480, heightPx: 3508 },
};
croppedReferencePiece.special_shape_drawing_json = JSON.stringify(croppedReferenceDrawing);
const croppedReferenceSvg = renderer.svg(croppedReferencePiece);
assert.match(croppedReferenceSvg, /data-reference-crop="1"/);
assert.match(croppedReferenceSvg, /overflow="hidden"/);
assert.match(croppedReferenceSvg, /href="\/private\/files\/a4-scan\.jpg"/);
assert.match(croppedReferenceSvg, /opacity="1"/);
assert.doesNotMatch(croppedReferenceSvg, /opacity="0\.72"/);
assert.match(renderer.css, /\.dco-piece-sketch>svg\{/);
assert.doesNotMatch(
    renderer.css,
    /\.dco-piece-sketch svg\{/,
    "The outer sketch style must not force nested crop SVG overflow to visible"
);
assert.match(renderer.css, /\.dco-reference-crop\{overflow:hidden\}/);

const imageOnlyPiece = {
    piece_type: "Special",
    special_shape_drawing_json: JSON.stringify({
        schema: "almdina.special-shape-documentation",
        version: 1,
        canvas: { widthMm: 200, heightMm: 700 },
        reference: {
            fileUrl: "/private/files/a4-scan.jpg",
            opacity: 0.72,
            rotationDeg: 0,
            locked: true,
            crop: { x: 0.2, y: 0.1, width: 0.5, height: 0.6 },
            imageSize: { widthPx: 2480, heightPx: 3508 },
        },
        elements: [],
        notes: "",
        source: "image",
        templateId: null,
    }),
};
const imageOnlySvg = renderer.svg(imageOnlyPiece);
const imageOnlyViewBox = imageOnlySvg.match(/viewBox="([^"]+)"/)[1].split(" ").map(Number);
assert.ok(imageOnlyViewBox[2] > 239 && imageOnlyViewBox[2] < 241, "the visible crop must use the available door width plus print padding");
assert.ok(imageOnlyViewBox[3] > 379 && imageOnlyViewBox[3] < 381, "the print view must fit the cropped image height rather than the 700 mm door height");
assert.ok(imageOnlyViewBox[2] / imageOnlyViewBox[3] > 0.6, "a cropped reference must no longer inherit the narrow door aspect ratio");
assert.match(imageOnlySvg, /data-reference-fit="visible-content"/);

const rotatedImageOnlyPiece = JSON.parse(JSON.stringify(imageOnlyPiece));
const rotatedDrawing = JSON.parse(rotatedImageOnlyPiece.special_shape_drawing_json);
rotatedDrawing.reference.rotationDeg = 90;
rotatedImageOnlyPiece.special_shape_drawing_json = JSON.stringify(rotatedDrawing);
const rotatedViewBox = renderer.svg(rotatedImageOnlyPiece).match(/viewBox="([^"]+)"/)[1].split(" ").map(Number);
assert.ok(rotatedViewBox[2] > 379 && rotatedViewBox[2] < 381, "print bounds must include the rotated crop width");
assert.ok(rotatedViewBox[3] > 239 && rotatedViewBox[3] < 241, "print bounds must include the rotated crop height");

const freeWorkspacePiece = JSON.parse(JSON.stringify(classicPiece));
const freeWorkspaceDrawing = JSON.parse(freeWorkspacePiece.special_shape_drawing_json);
freeWorkspaceDrawing.elements.push({
    id: "outside-door-frame",
    type: "line",
    start: { xMm: -250, yMm: -120 },
    end: { xMm: 1200, yMm: 2350 },
    style: { color: "#1463e6", width: 3 },
});
freeWorkspacePiece.special_shape_drawing_json = JSON.stringify(freeWorkspaceDrawing);
const freeWorkspaceSvg = renderer.svg(freeWorkspacePiece);
const freeViewBox = freeWorkspaceSvg.match(/viewBox="([^"]+)"/)[1].split(" ").map(Number);
assert.ok(freeViewBox[0] < -250 && freeViewBox[1] < -120, "print view must include free-canvas content before the nominal door origin");
assert.ok(freeViewBox[0] + freeViewBox[2] > 1200 && freeViewBox[1] + freeViewBox[3] > 2350, "print view must include free-canvas content beyond the nominal door dimensions");

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

global.__ = value => value;
global.document = {
    addEventListener() {},
    getElementById() { return null; },
};
global.frappe = {
    datetime: { now_datetime() { return "2026-08-27 12:00:00"; } },
    utils: {
        escape_html(value) {
            return String(value)
                .replaceAll("&", "&amp;")
                .replaceAll("<", "&lt;")
                .replaceAll(">", "&gt;")
                .replaceAll('"', "&quot;")
                .replaceAll("'", "&#39;");
        },
    },
    ui: { form: { on() {} } },
};
window.AlmdinaMultiEdgeBanding = { details() { return []; } };
window.AlmdinaOrderDocumentPrintTheme = {
    headerHtml() { return "<header>Test</header>"; },
    css(_mode, extra) { return extra; },
};
window.AlmdinaFactoryPrintIdentity = { fallback() { return {}; } };

require(path.resolve(
    __dirname,
    "../public/js/door_cutting_order/printing/door_cutting_order_document_print_presenter.js"
));

const staleFullDrawing = JSON.parse(croppedReferencePiece.special_shape_drawing_json);
staleFullDrawing.reference.crop = { x: 0, y: 0, width: 1, height: 1 };
const staleFullPiece = {
    ...croppedReferencePiece,
    name: "ROW-SPECIAL-1",
    special_shape_drawing_json: JSON.stringify(staleFullDrawing),
};
const invoiceHtml = window.AlmdinaOrderDocumentPrint.html(
    {
        doc: {
            name: "DCO-CROP-PRINT-1",
            pieces: [staleFullPiece],
        },
    },
    "invoice",
    {},
    {
        kind: "customer_invoice",
        order_name: "DCO-CROP-PRINT-1",
        measurements: [{
            piece_name: "ROW-SPECIAL-1",
            special_shape_drawing_json: croppedReferencePiece.special_shape_drawing_json,
        }],
        lines: [],
        totals: [],
    }
);
assert.match(
    invoiceHtml,
    /data-reference-crop="1"/,
    "Customer invoice must prefer the authoritative saved crop over stale form documentation"
);

console.log("Printable door drawing SVG, fallback geometry, and safe notes checks passed");
