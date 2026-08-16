"use strict";

const assert = require("node:assert/strict");
const path = require("node:path");

global.window = { devicePixelRatio: 2 };
const load = file => require(path.resolve(__dirname, `../../public/js/door_drawing_v4/${file}`));
load("domain/geometry.js");
load("domain/document.js");
load("domain/dimension.js");
load("application/viewport.js");
load("presentation/canvas_renderer.js");

const V4 = global.window.AlmdinaDoorDrawingV4;
const V = V4.Viewport;

let camera = V.create({ viewportWidthPx: 1000, viewportHeightPx: 800, scalePxPerMm: 1 });
camera = V.fitBlank(camera, { widthMm: 1000, heightMm: 2000 }, { paddingPx: 40 });
assert.equal(camera.scalePxPerMm, 0.36, "fit must use the limiting viewport dimension");

const world = { xMm: 275.5, yMm: 618.25 };
const screen = V.worldToScreen(camera, world);
const roundTrip = V.screenToWorld(camera, screen);
assert.ok(Math.abs(roundTrip.xMm - world.xMm) < 1e-9);
assert.ok(Math.abs(roundTrip.yMm - world.yMm) < 1e-9);

const pointer = { x: 427, y: 312 };
const worldUnderPointer = V.screenToWorld(camera, pointer);
const zoomed = V.zoomAt(camera, pointer, 1.75);
const worldAfterZoom = V.screenToWorld(zoomed, pointer);
assert.ok(Math.abs(worldAfterZoom.xMm - worldUnderPointer.xMm) < 1e-9, "zoom must preserve X under cursor");
assert.ok(Math.abs(worldAfterZoom.yMm - worldUnderPointer.yMm) < 1e-9, "zoom must preserve Y under cursor");

const panned = V.panBy(zoomed, 25, -18);
assert.equal(panned.offsetXPx, zoomed.offsetXPx + 25);
assert.equal(panned.offsetYPx, zoomed.offsetYPx - 18);

const lowZoom = V.create({ scalePxPerMm: 0.5 });
const highZoom = V.create({ scalePxPerMm: 2 });
assert.equal(V.screenToleranceToMm(lowZoom, 10), 20);
assert.equal(V.screenToleranceToMm(highZoom, 10), 5);
assert.equal(V.screenToleranceToMm(lowZoom, 10) * lowZoom.scalePxPerMm, 10, "snap tolerance must remain 10 screen pixels at low zoom");
assert.equal(V.screenToleranceToMm(highZoom, 10) * highZoom.scalePxPerMm, 10, "snap tolerance must remain 10 screen pixels at high zoom");

const canvas = { width: 0, height: 0, style: {} };
const resized = V4.CanvasRenderer.resizeCanvas(canvas, 640, 360, 2);
assert.equal(canvas.width, 1280, "backing canvas width must honor devicePixelRatio");
assert.equal(canvas.height, 720, "backing canvas height must honor devicePixelRatio");
assert.equal(canvas.style.width, "640px");
assert.equal(canvas.style.height, "360px");
assert.equal(resized.dpr, 2);

console.log("Door Drawing V4 viewport and high-DPI tests passed");
