"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

const root = path.resolve(__dirname, "../..");
function read(relative) {
    return fs.readFileSync(path.join(root, relative), "utf8");
}

global.window = {};
require(path.join(root, "public/js/door_drawing_v4/reference/domain.js"));

const domain = global.window.AlmdinaDoorDrawingReference.Domain;
assert.ok(domain, "reference-image domain must register independently");
assert.equal(domain.VERSION, 1);
assert.equal(domain.validateFile({ name: "door.jpg", type: "image/jpeg", size: 1200 }).ok, true);
assert.equal(domain.validateFile({ name: "door.png", type: "image/png", size: 1200 }).ok, true);
assert.equal(domain.validateFile({ name: "door.pdf", type: "application/pdf", size: 1200 }).ok, false);
assert.equal(domain.validateFile({ name: "door.exe", type: "application/octet-stream", size: 1200 }).ok, false);
assert.equal(domain.validateFile({ name: "door.jpg", type: "image/jpeg", size: domain.MAX_SOURCE_BYTES + 1 }).code, "file-too-large");

const metadata = domain.buildMetadata({
    source: domain.SOURCES.SCANNER,
    originalName: "scan.jpg",
    originalMime: "image/jpeg",
    sourceWidthPx: 2480,
    sourceHeightPx: 3508,
    crop: { x: 40, y: 50, width: 2000, height: 3000 },
    outputWidthPx: 2000,
    outputHeightPx: 3000,
    outputMime: "image/jpeg",
    scanner: { provider: "local-wia-bridge", device: "Office Scanner", dpi: 300 },
});
assert.equal(metadata.source, "scanner");
assert.equal(metadata.scanner.dpi, 300);
assert.equal(metadata.crop.width, 2000);
assert.equal(domain.active({ special_shape_documentation_mode: "Image", special_shape_reference_image: "/private/files/door.jpg" }), true);
assert.equal(domain.active({ special_shape_documentation_mode: "Drawing", special_shape_reference_image: "/private/files/door.jpg" }), false);

const scanner = read("public/js/door_drawing_v4/reference/scanner_bridge.js");
assert.ok(scanner.includes("http://127.0.0.1:17654"), "scanner bridge must default to loopback only");
assert.ok(scanner.includes('"/health"'), "scanner bridge must expose a health handshake");
assert.ok(scanner.includes('"/scan"'), "scanner bridge must expose a scan command");
assert.ok(scanner.includes("deviceCount"), "browser adapter must expose detected scanner count");
assert.ok(scanner.includes("ready:"), "browser adapter must expose readiness separately from bridge reachability");
assert.ok(scanner.includes("X-Almdina-Scanner-Bridge"), "scanner bridge calls must carry the dedicated request header");
assert.ok(!scanner.includes("0.0.0.0"), "browser adapter must not target a network-wide scanner listener");

const cropper = read("public/js/door_drawing_v4/reference/cropper.js");
assert.ok(cropper.includes("pointerdown"));
assert.ok(cropper.includes("pointermove"));
assert.ok(cropper.includes("MAX_OUTPUT_EDGE_PX = 3200"));
assert.ok(cropper.includes("imageSmoothingQuality = \"high\""));

const page = read("almdina_erp/page/door_drawing/door_drawing.js");
const order = [
    "/reference/domain.js",
    "/reference/device_source.js",
    "/reference/scanner_bridge.js",
    "/reference/cropper.js",
    "/reference/reference_view.js",
    "/workspace/api.js",
    "/workspace/reference_controller.js",
    "/workspace/session_controller.js",
];
let previous = -1;
for (const token of order) {
    const index = page.indexOf(token);
    assert.ok(index > previous, `${token} must load in dependency order`);
    previous = index;
}

const session = read("public/js/door_drawing_v4/workspace/session_controller.js");
assert.ok(session.includes('activeContent = "image"'));
assert.ok(session.includes('activeContent = "drawing"'));
assert.ok(session.includes("سيتم مسح هندسة الرسم الحالية"), "switching to image mode must warn before discarding manual geometry");
assert.ok(session.includes("referenceController.scanFromScanner()"));
assert.ok(session.includes("referenceController.uploadFromDevice()"));

const referenceController = read("public/js/door_drawing_v4/workspace/reference_controller.js");
assert.ok(referenceController.includes("health.deviceCount < 1"), "workspace must distinguish a reachable bridge from an available scanner");
assert.ok(referenceController.includes("Windows لا يرى أي Scanner عبر WIA"), "operator must receive an actionable Arabic scanner-driver message");

const backend = read("almdina_erp/services/special_shape_workspace_service.py");
assert.ok(backend.includes('is_private=1'), "reference images must be stored as private Frappe files");
assert.ok(backend.includes('piece.special_shape_drawing_json = ""'), "image mode must clear stale manual drawing data");
assert.ok(backend.includes('piece.special_shape_geometry_json = ""'), "image mode must clear stale exact manufacturing geometry");
assert.ok(backend.includes('piece.special_shape_documentation_mode = "Image"'));

const bridge = read("../tools/scanner_bridge/windows/AlmdinaScannerBridge.ps1");
assert.ok(bridge.includes('http://127.0.0.1:'));
assert.ok(bridge.includes("WIA.CommonDialog"));
assert.ok(bridge.includes("WIA.DeviceManager"), "local bridge must detect WIA scanners before acquisition");
assert.ok(bridge.includes("Get-WiaScannerCount"));
assert.ok(bridge.includes("device_count = $scannerCount"));
assert.ok(bridge.includes("ready = ($scannerCount -gt 0)"));
assert.ok(bridge.includes("ShowAcquireImage"));
assert.ok(bridge.includes("AllowedOrigins"));
assert.ok(!bridge.includes('http://+:'));

const installer = read("../tools/scanner_bridge/windows/install.ps1");
const uninstaller = read("../tools/scanner_bridge/windows/uninstall.ps1");
for (const script of [installer, uninstaller]) {
    assert.ok(script.includes("config.json"));
    assert.ok(script.includes("$config.port"), "install and uninstall must derive URL reservation from the configured port");
    assert.ok(script.includes('http://127.0.0.1:$port/'));
}
assert.ok(installer.includes("$health.device_count"), "installer must report whether Windows sees a WIA scanner");

console.log("Door Drawing V4 reference image and scanner tests passed");
