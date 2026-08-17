"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

const root = path.resolve(__dirname, "../..");
global.window = { AlmdinaDoorDrawingReference: Object.create(null) };
require(path.join(root, "public/js/door_drawing_v4/reference/domain.js"));

const domain = global.window.AlmdinaDoorDrawingReference.Domain;
assert.ok(domain, "reference image domain must register");
assert.equal(domain.validateFile({ name: "door.jpg", type: "image/jpeg", size: 1000 }).ok, true);
assert.equal(domain.validateFile({ name: "door.pdf", type: "application/pdf", size: 1000 }).ok, false);
assert.equal(domain.validateFile({ name: "huge.png", type: "image/png", size: domain.MAX_SOURCE_BYTES + 1 }).code, "file-too-large");

const metadata = domain.buildMetadata({
    source: domain.SOURCES.UPLOAD,
    originalName: "customer-plan.jpg",
    originalMime: "image/jpeg",
    sourceWidthPx: 2400,
    sourceHeightPx: 3200,
    rotationDeg: 90,
    crop: { x: 100, y: 200, width: 1800, height: 1200 },
    outputWidthPx: 1800,
    outputHeightPx: 1200,
    outputMime: "image/jpeg",
});
assert.equal(metadata.source, "upload");
assert.equal(metadata.rotation_deg, 90);
assert.deepEqual(metadata.crop, { x: 100, y: 200, width: 1800, height: 1200 });

const cropper = fs.readFileSync(path.join(root, "public/js/door_drawing_v4/reference/cropper.js"), "utf8");
assert.match(cropper, /MAX_OUTPUT_EDGE_PX = 3200/);
assert.match(cropper, /pointerdown/);
assert.match(cropper, /data-rotate-left/);
assert.match(cropper, /data-rotate-right/);
assert.match(cropper, /imageSmoothingQuality = "high"/);

const referenceController = fs.readFileSync(path.join(root, "public/js/door_drawing_v4/reference/reference_controller.js"), "utf8");
assert.match(referenceController, /saveReferenceImage/);
assert.match(referenceController, /removeReferenceImage/);
assert.match(referenceController, /لن يتم حذف الرسم الهندسي/);

const workspace = fs.readFileSync(path.join(root, "public/js/door_drawing_v4/professional/workspace_controller.js"), "utf8");
assert.match(workspace, /loadReferenceImage/);
assert.match(workspace, /referenceController\.open/);
assert.doesNotMatch(referenceController, /special_shape_geometry_json/);
assert.doesNotMatch(referenceController, /special_shape_drawing_json/);

console.log("Professional reference image upload/crop architecture passed");
