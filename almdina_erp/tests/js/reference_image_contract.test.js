"use strict";

const assert = require("node:assert/strict");
const path = require("node:path");

global.window = {};

require(path.resolve(
    __dirname,
    "../../public/js/door_cutting_order_reference_image_contract.js"
));

const contract = window.AlmdinaReferenceImageContract;
assert.ok(Object.isFrozen(contract), "Reference image contract should be immutable");
assert.equal(contract.safeFileUrl("javascript:alert(1)"), "");
assert.equal(contract.safeFileUrl("https://evil.example/image.jpg"), "");
assert.equal(contract.safeFileUrl("/private/files/door.jpg"), "/private/files/door.jpg");
assert.equal(contract.clampOpacity(0), contract.MIN_OPACITY);
assert.equal(contract.clampOpacity(2), contract.MAX_OPACITY);

const row = {
    idx: 3,
    piece_type: "Special",
    width_cm: 77,
    length_cm: 120,
    special_shape_drawing_json: JSON.stringify({
        version: 1,
        canvas: { width: 1000, height: 650 },
        elements: [{ id: "line-1", type: "line", x1: 1, y1: 2, x2: 3, y2: 4 }],
        meta: { purpose: "operator_documentation_only" },
    }),
};

contract.writeToRow(row, {
    file_url: "/private/files/reference.jpg",
    file_name: "reference.jpg",
    source: "scanner",
    opacity: 0.4,
    visible: true,
});
let parsed = JSON.parse(row.special_shape_drawing_json);
assert.equal(parsed.elements.length, 1, "Adding a reference must preserve drawing elements");
assert.equal(parsed.reference_image.source, "scanner");
assert.equal(parsed.reference_image.opacity, 0.4);
assert.equal(contract.fromRow(row).file_url, "/private/files/reference.jpg");
assert.equal(contract.hasDrawingElements(row), true);

contract.writeToRow(row, null);
parsed = JSON.parse(row.special_shape_drawing_json);
assert.equal(parsed.elements.length, 1, "Removing a reference must preserve the sketch");
assert.equal(Object.prototype.hasOwnProperty.call(parsed, "reference_image"), false);

const emptyRow = {
    idx: 4,
    width_cm: 55,
    length_cm: 70,
    special_shape_drawing_json: "",
};
contract.writeToRow(emptyRow, {
    file_url: "/files/ref.png",
    file_name: "ref.png",
    source: "file",
});
assert.equal(contract.hasDrawingElements(emptyRow), false);
assert.equal(contract.fromRow(emptyRow).source, "file");
contract.writeToRow(emptyRow, null);
assert.equal(
    emptyRow.special_shape_drawing_json,
    "",
    "Removing a reference-only payload should clean up empty JSON"
);

console.log("Reference image contract validation and persistence tests passed");
