"use strict";

const assert = require("node:assert/strict");
const path = require("node:path");

global.window = {};

require(path.resolve(
    __dirname,
    "../../public/js/door_drawing_v2/domain/precision_policy.js"
));
require(path.resolve(
    __dirname,
    "../../public/js/door_drawing_v2/presentation/viewport_model.js"
));

const viewport = window.AlmdinaDoorDrawingV2.ViewportModel;

let state = viewport.create({
    viewportWidthPx: 1200,
    viewportHeightPx: 800,
    worldWidthMm: 800,
    worldHeightMm: 2100,
    paddingPx: 64,
});

assert.equal(viewport.zoomPercent(state), 100, "fit state must be the 100% reference zoom");

const origin = viewport.worldToScreen(state, { x: 0, y: 0 });
const topLeft = viewport.worldToScreen(state, { x: 0, y: 2100 });
assert.ok(origin.y > topLeft.y, "CAD +Y must project upward while screen +Y points down");

const sourcePoint = { x: 214, y: 1337.5 };
const screenPoint = viewport.worldToScreen(state, sourcePoint);
const roundTrip = viewport.screenToWorld(state, screenPoint);
assert.equal(roundTrip.x, 214);
assert.equal(roundTrip.y, 1337.5);

const cursor = { x: 777, y: 286 };
const beforeZoom = viewport.screenToWorld(state, cursor);
state = viewport.zoomAt(state, state.scale * 2, cursor);
const afterZoom = viewport.screenToWorld(state, cursor);
assert.equal(afterZoom.x, beforeZoom.x, "zoom-at-pointer must preserve the world X below the cursor");
assert.equal(afterZoom.y, beforeZoom.y, "zoom-at-pointer must preserve the world Y below the cursor");
assert.equal(viewport.zoomPercent(state), 200);

const beforePan = viewport.worldToScreen(state, { x: 400, y: 1000 });
state = viewport.panByScreen(state, 37, -22);
const afterPan = viewport.worldToScreen(state, { x: 400, y: 1000 });
assert.equal(Math.round(afterPan.x - beforePan.x), 37);
assert.equal(Math.round(afterPan.y - beforePan.y), -22);

const centerWorldBeforeResize = viewport.screenToWorld(state, {
    x: state.viewportWidthPx / 2,
    y: state.viewportHeightPx / 2,
});
state = viewport.resizeViewport(state, 1600, 900);
const centerWorldAfterResize = viewport.screenToWorld(state, {
    x: state.viewportWidthPx / 2,
    y: state.viewportHeightPx / 2,
});
assert.equal(centerWorldAfterResize.x, centerWorldBeforeResize.x);
assert.equal(centerWorldAfterResize.y, centerWorldBeforeResize.y);

const matrix = viewport.matrix(state);
assert.equal(matrix.a, state.scale);
assert.equal(matrix.d, -state.scale, "world-to-screen matrix must invert only the Y axis");

console.log("Door Drawing V2 viewport transformation tests passed");
