"use strict";

const assert = require("node:assert/strict");
const path = require("node:path");

global.window = {};

const publicJs = path.resolve(__dirname, "../../public/js");
require(path.join(publicJs, "door_drawing_v2/domain/precision_policy.js"));
require(path.join(publicJs, "door_drawing_v2/presentation/viewport_model.js"));

const viewport = window.AlmdinaDoorDrawingV2.ViewportModel;

let state = viewport.createFree({
    viewportWidthPx: 1200,
    viewportHeightPx: 800,
    referenceWidthMm: 1200,
    referenceHeightMm: 900,
});
assert.equal(state.mode, "free");

[
    { x: 0, y: 0 },
    { x: -850.125, y: 420.5 },
    { x: 3000, y: -1400 },
].forEach(point => {
    const screen = viewport.worldToScreen(state, point);
    const roundtrip = viewport.screenToWorld(state, screen);
    assert.deepEqual(roundtrip, point, `Free viewport roundtrip must preserve ${JSON.stringify(point)} mm`);
});

const anchor = { x: 913, y: 267 };
const beforeZoom = viewport.screenToWorld(state, anchor);
state = viewport.zoomBy(state, 1.8, anchor);
assert.deepEqual(viewport.screenToWorld(state, anchor), beforeZoom, "Zoom around pointer must preserve the world-mm point under the pointer");

const beforePanWorld = viewport.screenToWorld(state, { x: 600, y: 400 });
const panned = viewport.panByScreen(state, 137, -81);
const afterPanWorld = viewport.screenToWorld(panned, { x: 737, y: 319 });
assert.deepEqual(afterPanWorld, beforePanWorld, "Pan must move the view, not the underlying geometry");

const centerBeforeResize = viewport.screenToWorld(panned, {
    x: panned.viewportWidthPx / 2,
    y: panned.viewportHeightPx / 2,
});
const resized = viewport.resizeViewport(panned, 1600, 950);
const centerAfterResize = viewport.screenToWorld(resized, { x: 800, y: 475 });
assert.deepEqual(centerAfterResize, centerBeforeResize, "Resizing the editor must preserve the world point at viewport center");

console.log("Door Drawing V2 free viewport tests passed");
