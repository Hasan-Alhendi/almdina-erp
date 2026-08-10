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
    "../../public/js/door_cutting_order_sketch_template_catalog.js"
));

const catalog = window.AlmdinaSketchTemplateCatalog;
const engine = window.AlmdinaSketchEngine;

assert.ok(Object.isFrozen(catalog));
assert.ok(Object.isFrozen(engine));
assert.ok(catalog.all().length >= 14, "The factory should expose a useful starter template library");
assert.ok(catalog.common().length >= 8, "Common shapes should be visible without expanding the palette");
assert.equal(catalog.resolveKey("single-slope"), "single-slope-left");
assert.equal(catalog.resolveKey("lshape"), "l-bottom-left");

for (const item of catalog.all()) {
    const points = catalog.points(item.key);
    assert.ok(points.length >= 4, `${item.key} should provide a drawable contour`);
    assert.deepEqual(
        points[0],
        points[points.length - 1],
        `${item.key} should be closed so it is immediately useful as a door outline`
    );
    for (const point of points) {
        assert.ok(point[0] >= 0 && point[0] <= catalog.CANVAS.width, `${item.key} X should stay inside canvas`);
        assert.ok(point[1] >= 0 && point[1] <= catalog.CANVAS.height, `${item.key} Y should stay inside canvas`);
    }
}

assert.ok(engine.templatePoints("u-bottom").length >= 8);
assert.ok(engine.templatePoints("step-right").length >= 8);
assert.ok(engine.templatePoints("crown").length >= 9);
assert.deepEqual(
    engine.templatePoints("single-slope"),
    catalog.points("single-slope-left"),
    "Legacy template keys must keep working after the smart catalog is installed"
);

console.log("Smart sketch template catalog and compatibility aliases passed");