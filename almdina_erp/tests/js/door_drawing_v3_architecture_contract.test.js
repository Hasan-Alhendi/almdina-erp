"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

const entry = fs.readFileSync(path.resolve(__dirname, "../../public/js/door_cutting_order_special_shape_ux.js"), "utf8");
const geometry = fs.readFileSync(path.resolve(__dirname, "../../public/js/door_drawing_v3/domain/geometry.js"), "utf8");
const snapping = fs.readFileSync(path.resolve(__dirname, "../../public/js/door_drawing_v3/application/snapping.js"), "utf8");
const handles = fs.readFileSync(path.resolve(__dirname, "../../public/js/door_drawing_v3/application/shape_handles.js"), "utf8");
const precision = fs.readFileSync(path.resolve(__dirname, "../../public/js/door_drawing_v3/application/precision_input.js"), "utf8");
const view = fs.readFileSync(path.resolve(__dirname, "../../public/js/door_drawing_v3/presentation/canvas_view.js"), "utf8");
const editor = fs.readFileSync(path.resolve(__dirname, "../../public/js/door_drawing_v3/application/editor_stage2.js"), "utf8");
const magnetic = fs.readFileSync(path.resolve(__dirname, "../../public/js/door_drawing_v3/application/magnetic_connection.js"), "utf8");
const css = fs.readFileSync(path.resolve(__dirname, "../../public/css/door_drawing_v3.css"), "utf8");
const precisionCss = fs.readFileSync(path.resolve(__dirname, "../../public/css/door_drawing_v3_precision.css"), "utf8");
const magneticCss = fs.readFileSync(path.resolve(__dirname, "../../public/css/door_drawing_v3_magnetic.css"), "utf8");

for (const modulePath of [
    "door_drawing_v3/domain/geometry.js",
    "door_drawing_v3/domain/document.js",
    "door_drawing_v3/application/history.js",
    "door_drawing_v3/infrastructure/persistence_adapter.js",
    "door_drawing_v3/application/snapping.js",
    "door_drawing_v3/application/shape_handles.js",
    "door_drawing_v3/application/precision_input.js",
    "door_drawing_v3/presentation/canvas_view.js",
    "door_drawing_v3/application/editor_stage2.js",
    "door_drawing_v3/application/magnetic_connection.js",
]) assert.match(entry, new RegExp(modulePath.replaceAll("/", "\\/").replaceAll(".", "\\.")));
assert.match(entry, /door_drawing_v3_precision\.css/);
assert.match(entry, /door_drawing_v3_magnetic\.css/);
assert.match(entry, /__doorDrawingV3:\s*true/);
assert.match(entry, /__doorDrawingV3Shapes:\s*true/);
assert.match(entry, /__doorDrawingV3Snapping:\s*true/);
assert.match(entry, /__doorDrawingV3Handles:\s*true/);
assert.match(entry, /__doorDrawingV3PrecisionInput:\s*true/);
assert.match(entry, /__doorDrawingV3MagneticConnection:\s*true/);
assert.doesNotMatch(entry, /AlmdinaSketchEngine|AlmdinaExactLineModel|AlmdinaSketchHistory/);

for (const tool of ["line", "rectangle", "circle", "arc"]) assert.match(view, new RegExp(`data-ddv3-tool=\\"${tool}\\"`));
assert.match(view, /field\("Length",\s*"length"/);
assert.match(view, /field\("Radius",\s*"radius"/);
assert.match(view, /field\("Sweep",\s*"sweep"/);
assert.match(view, /function arcPath/);
assert.match(view, /function snapMarkup/);
assert.match(view, /function handlesMarkup/);
assert.match(view, /data-ddv3-handle/);
assert.match(view, /function displayObject/);
assert.match(view, /ddv3-snap-indicator/);
assert.match(view, /Ctrl\+Shift\+Z/);

assert.match(editor, /function handleArcClick/);
assert.match(editor, /function handleCandidate/);
assert.match(editor, /function updatePrecisionPreview/);
assert.match(editor, /function commitPrecision/);
assert.match(editor, /function handlePrecisionKey/);
assert.match(editor, /clickDraft/);
assert.match(editor, /Precision\.lineFromInput/);
assert.match(editor, /Precision\.rectangleFromInput/);
assert.match(editor, /Precision\.circleFromInput/);
assert.match(editor, /Precision\.arcFromSweep/);
assert.match(editor, /Handles\.resize/);
assert.match(editor, /S\.resolvePoint/);
assert.match(editor, /S\.resolveArcEndpoint/);
assert.match(editor, /forcedAxis:/);
assert.match(editor, /axisLock:\s*c\.tool === "line"/);
assert.match(editor, /G\.translateObject/);
assert.match(editor, /root\.EditorStage5/);
assert.match(editor, /r:\s*"rectangle"/);
assert.match(editor, /o:\s*"circle"/);
assert.match(editor, /a:\s*"arc"/);

assert.match(geometry, /function rectangle\(/);
assert.match(geometry, /function circle\(/);
assert.match(geometry, /function arc\(/);
assert.match(snapping, /const DEFAULT_SNAP_PX = 22/);
assert.match(snapping, /const JOIN_SNAP_PX = 26/);
assert.match(snapping, /function objectAnchors/);
assert.match(snapping, /function preferredAnchor/);
assert.match(snapping, /function resolvePoint/);
assert.match(snapping, /function resolveObjectMove/);
assert.match(snapping, /forcedAxis/);
assert.doesNotMatch(snapping, /clientX|clientY|getBoundingClientRect/, "Snapping application policy must stay independent from DOM coordinates");
assert.match(handles, /function handlesFor/);
assert.match(handles, /function resizeRectangle/);
assert.match(handles, /function resizeCircle/);
assert.match(handles, /function resizeArc/);
assert.doesNotMatch(handles, /document\.|querySelector|getBoundingClientRect|clientX|clientY/, "Shape handle transforms must remain independent from DOM coordinates");
assert.match(precision, /function parseLine/);
assert.match(precision, /function parseRectangle/);
assert.match(precision, /function parseCircle/);
assert.match(precision, /function parseArc/);
assert.doesNotMatch(precision, /document\.|querySelector|getBoundingClientRect|clientX|clientY|px\b/i, "Precision input must remain a world-mm application policy, not a screen coordinate feature");
assert.match(magnetic, /function magneticMove/);
assert.match(magnetic, /S\.resolveObjectMove/);
assert.match(magnetic, /function hoverSnap/);
assert.match(magnetic, /stickyTarget/);
assert.doesNotMatch(editor + view + magnetic, /special_shape_geometry_json\s*=/, "Drawing editor must not fabricate manufacturing geometry from visual output");

assert.match(css, /\.ddv3-app/);
assert.match(css, /\.ddv3-inspector/);
assert.match(css, /\.ddv3-toolbar/);
assert.match(css, /\.ddv3-measure/);
assert.match(css, /\.ddv3-handle/);
assert.match(css, /\.ddv3-snap-axis-guide/);
assert.match(css, /\.ddv3-snap-indicator/);
assert.match(precisionCss, /\.ddv3-precision-entry/);
assert.match(magneticCss, /\.ddv3-magnetic-badge/);
assert.match(magneticCss, /has-magnetic-snap/);
assert.doesNotMatch(css + precisionCss + magneticCss, /^body\s*\{/m);
assert.doesNotMatch(css + precisionCss + magneticCss, /^\.form-layout\s*\{/m);

console.log("Door Drawing V3 magnetic connection architecture contract passed");
