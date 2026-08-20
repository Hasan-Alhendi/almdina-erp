"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

const root = path.resolve(__dirname, "../..");
global.window = { AlmdinaDoorDrawingReference: Object.create(null) };
require(path.join(root, "public/js/door_drawing_v4/reference/domain.js"));
require(path.join(root, "public/js/door_drawing_v4/reference/scanner_bridge.js"));

const reference = global.window.AlmdinaDoorDrawingReference;
const domain = reference.Domain;
const scanner = reference.ScannerBridge;
assert.ok(domain, "reference image domain must register");
assert.ok(scanner, "scanner bridge provider must register");
assert.equal(scanner.DEFAULT_BASE_URL, "http://127.0.0.1:17654");
assert.equal(scanner.MAX_SCAN_BYTES, domain.MAX_SOURCE_BYTES);
assert.equal(domain.validateFile({ name: "door.jpg", type: "image/jpeg", size: 1000 }).ok, true);
assert.equal(domain.validateFile({ name: "door.pdf", type: "application/pdf", size: 1000 }).ok, false);
assert.equal(domain.validateFile({ name: "huge.png", type: "image/png", size: domain.MAX_SOURCE_BYTES + 1 }).code, "file-too-large");
assert.equal(domain.validateDecodedDimensions(6000, 6000).ok, true);
assert.equal(domain.validateDecodedDimensions(10000, 6000).code, "image-too-large-to-decode", "compressed files must not expand into unsafe canvases");

const metadata = domain.buildMetadata({
    source: domain.SOURCES.UPLOAD,
    originalName: "customer-plan.png",
    originalMime: "image/png",
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
assert.equal(metadata.original_mime, "image/png");
assert.equal(metadata.output.mime, "image/jpeg", "cropped references normalize to compressed JPEG output");
assert.deepEqual(metadata.crop, { x: 100, y: 200, width: 1800, height: 1200 });

const scannerMetadata = domain.buildMetadata({
    source: domain.SOURCES.SCANNER,
    originalName: "scanner.jpg",
    originalMime: "image/jpeg",
    sourceWidthPx: 2480,
    sourceHeightPx: 3508,
    crop: { x: 0, y: 0, width: 2480, height: 3508 },
    outputWidthPx: 2262,
    outputHeightPx: 3200,
    outputMime: "image/jpeg",
    scanner: { provider: "local-wia-bridge", device: "WIA Scanner", dpi: 300 },
});
assert.equal(scannerMetadata.source, "scanner");
assert.equal(scannerMetadata.scanner.provider, "local-wia-bridge");
assert.equal(scannerMetadata.scanner.dpi, 300);

const cropper = fs.readFileSync(path.join(root, "public/js/door_drawing_v4/reference/cropper.js"), "utf8");
assert.match(cropper, /MAX_OUTPUT_EDGE_PX = 3200/);
assert.match(cropper, /MAX_OUTPUT_BYTES = 6 \* 1024 \* 1024/);
assert.match(cropper, /OUTPUT_MIME = "image\/jpeg"/);
assert.match(cropper, /validateDecodedDimensions/);
assert.match(cropper, /encodeBounded/);
assert.match(cropper, /pointerdown/);
assert.match(cropper, /data-rotate-left/);
assert.match(cropper, /data-rotate-right/);
assert.match(cropper, /imageSmoothingQuality = "high"/);

const scannerSource = fs.readFileSync(path.join(root, "public/js/door_drawing_v4/reference/scanner_bridge.js"), "utf8");
assert.match(scannerSource, /credentials: "omit"/);
assert.match(scannerSource, /X-Almdina-Scanner-Bridge/);
assert.match(scannerSource, /MAX_SCAN_BYTES = 16 \* 1024 \* 1024/);
assert.match(scannerSource, /\/health/);
assert.match(scannerSource, /\/scan/);

const referenceController = fs.readFileSync(path.join(root, "public/js/door_drawing_v4/reference/reference_controller.js"), "utf8");
assert.match(referenceController, /saveReferenceImage/);
assert.match(referenceController, /removeReferenceImage/);
assert.match(referenceController, /scannerBridge\.scan/);
assert.match(referenceController, /source: domain\.SOURCES\.SCANNER/);
assert.match(referenceController, /processFile\(context, captured\.file/);
assert.match(referenceController, /لن يتم حذف الرسم الهندسي/);

const workspace = fs.readFileSync(path.join(root, "public/js/door_drawing_v4/professional/workspace_controller.js"), "utf8");
assert.match(workspace, /loadReferenceImage/);
assert.match(workspace, /referenceController\.open/);
assert.doesNotMatch(referenceController, /special_shape_geometry_json/);
assert.doesNotMatch(referenceController, /special_shape_drawing_json/);

console.log("Professional reference image upload, crop, and scanner architecture passed");
