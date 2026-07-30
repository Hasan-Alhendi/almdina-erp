"use strict";

const assert = require("node:assert/strict");
const path = require("node:path");

global.window = {};

require(path.resolve(
    __dirname,
    "../../public/js/door_cutting_order_sketch_engine.js"
));
require(path.resolve(
    __dirname,
    "../../public/js/door_cutting_order_sketch_viewport.js"
));

const viewport = global.window.AlmdinaSketchViewport;

assert.equal(Object.isFrozen(viewport), true, "The viewport API should be immutable");
assert.equal(viewport.MIN_ZOOM, 1);
assert.equal(viewport.MAX_ZOOM, 4);
assert.equal(viewport.ZOOM_STEP, 1.25);

const initial = viewport.createState();
assert.deepEqual(initial, {
    zoom: 1,
    viewBox: { x: 0, y: 0, width: 1000, height: 650 },
});
assert.deepEqual(
    viewport.createState({ canvas: { width: 800, height: 500 }, minZoom: 1 }),
    { zoom: 1, viewBox: { x: 0, y: 0, width: 800, height: 500 } }
);

assert.deepEqual(viewport.clampPoint({ x: -20, y: 900 }), { x: 0, y: 650 });
assert.deepEqual(
    viewport.clampPoint({ x: 900, y: 600 }, {
        canvas: { width: 700, height: 400 },
    }),
    { x: 700, y: 400 }
);

assert.deepEqual(
    viewport.mapClientPoint(
        { x: 500, y: 325 },
        { left: 0, top: 0, width: 1000, height: 650 },
        initial.viewBox
    ),
    { x: 500, y: 325 }
);
assert.deepEqual(
    viewport.mapClientPoint(
        { x: 500, y: 325 },
        { left: 0, top: 0, width: 1000, height: 650 },
        { x: 250, y: 162.5, width: 500, height: 325 }
    ),
    { x: 500, y: 325 },
    "Fallback pointer mapping should respect the active zoomed viewBox"
);
assert.deepEqual(
    viewport.mapClientPoint(
        { x: -500, y: 2000 },
        { left: 0, top: 0, width: 1000, height: 650 },
        initial.viewBox
    ),
    { x: 0, y: 650 },
    "Pointer mapping must stay inside the drawing paper"
);
assert.deepEqual(
    viewport.mapClientPoint(
        { x: 400, y: 250 },
        { left: 0, top: 0, width: 800, height: 500 },
        { x: 200, y: 125, width: 400, height: 250 },
        { canvas: { width: 800, height: 500 } }
    ),
    { x: 400, y: 250 },
    "Viewport calculations should support a future non-default canvas size"
);

const stateBeforeZoom = JSON.stringify(initial);
const zoomed = viewport.zoomState(initial, 2, { x: 500, y: 325 });
assert.equal(JSON.stringify(initial), stateBeforeZoom, "Zoom must not mutate its input");
assert.deepEqual(zoomed, {
    zoom: 2,
    viewBox: { x: 250, y: 162.5, width: 500, height: 325 },
});
assert.deepEqual(
    viewport.zoomState(zoomed, 10, { x: 500, y: 325 }),
    {
        zoom: 4,
        viewBox: { x: 375, y: 243.75, width: 250, height: 162.5 },
    },
    "Zoom should stop at the configured maximum"
);
assert.deepEqual(
    viewport.zoomState(zoomed, 0, { x: 500, y: 325 }),
    initial,
    "Zoom should stop at the configured minimum"
);
assert.deepEqual(
    viewport.zoomState(
        viewport.createState({ canvas: { width: 800, height: 500 } }),
        2,
        { x: 400, y: 250 },
        { canvas: { width: 800, height: 500 } }
    ),
    {
        zoom: 2,
        viewBox: { x: 200, y: 125, width: 400, height: 250 },
    }
);
assert.deepEqual(viewport.resetState(), initial);

assert.deepEqual(viewport.zoomControls(1), {
    percentage: 100,
    canZoomIn: true,
    canZoomOut: false,
});
assert.deepEqual(viewport.zoomControls(4), {
    percentage: 400,
    canZoomIn: false,
    canZoomOut: true,
});

const sourceViewBox = { x: 250, y: 162.5, width: 500, height: 325 };
const pan = viewport.beginPan({ x: 100, y: 100 }, sourceViewBox);
sourceViewBox.x = 999;
assert.deepEqual(pan, {
    clientX: 100,
    clientY: 100,
    viewBox: { x: 250, y: 162.5, width: 500, height: 325 },
});
assert.deepEqual(
    viewport.panState(
        pan,
        { x: 150, y: 130 },
        { width: 1000, height: 650 }
    ),
    { x: 225, y: 147.5, width: 500, height: 325 },
    "Dragging right and down should move the viewed paper left and up"
);
assert.deepEqual(
    viewport.panState(
        pan,
        { x: -10000, y: -10000 },
        { width: 1000, height: 650 }
    ),
    { x: 500, y: 325, width: 500, height: 325 },
    "Panning should remain within the drawing paper"
);
assert.equal(viewport.panState(null, { x: 1, y: 1 }, { width: 10, height: 10 }), null);

console.log("Pure special-shape viewport, zoom, and pan checks passed");
