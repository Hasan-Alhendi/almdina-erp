"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

const modelSource = fs.readFileSync(
    path.resolve(__dirname, "../../public/js/door_cutting_order_exact_shape_chain_model.js"),
    "utf8"
);

for (const marker of [
    'const TEMPLATE = "exact-line-chain"',
    "geometry.create(",
    "geometry.validate(candidate",
    "geometry.serialize(analysis.geometry)",
    "lines.length < 3",
]) {
    assert.ok(modelSource.includes(marker), `Geometry promotion should include ${marker}`);
}

console.log("Exact shape geometry promotion contract passed");
