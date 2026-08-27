const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

global.window = global;
const root = path.resolve(__dirname, "../../public/js/special_shape_documentation");
require(path.join(root, "domain/reference_crop.js"));
require(path.join(root, "domain/document.js"));
require(path.join(root, "application/history.js"));
require(path.join(root, "application/templates.js"));
require(path.join(root, "application/smart_pen.js"));
require(path.join(root, "application/element_transform.js"));
require(path.join(root, "application/element_clipboard.js"));
require(path.join(root, "application/keyboard_shortcuts.js"));
require(path.join(root, "infrastructure/scanner_bridge.js"));
require(path.join(root, "presentation/canvas_viewport.js"));

const api = global.AlmdinaSpecialShapeDocumentation;

const runtimeFiles = [
    "presentation/workspace_controller.js", "presentation/workspace_shell.js", "presentation/canvas_renderer.js", "presentation/canvas_viewport.js",
    "infrastructure/scanner_bridge.js", "infrastructure/workspace_api.js", "application/element_transform.js",
    "application/element_clipboard.js", "application/keyboard_shortcuts.js", "application/smart_pen.js", "application/templates.js", "application/history.js", "domain/document.js", "domain/reference_crop.js",
];
const parallelSandbox = { console, setTimeout, clearTimeout, AbortController, fetch, File, Blob, Response };
parallelSandbox.window = parallelSandbox;
vm.createContext(parallelSandbox);
runtimeFiles.forEach(relative => vm.runInContext(fs.readFileSync(path.join(root, relative), "utf8"), parallelSandbox, { filename: relative }));
const parallelApi = parallelSandbox.AlmdinaSpecialShapeDocumentation;
const parallelDocument = parallelApi.Document.create({ width_cm: 80, length_cm: 210 });
assert.ok(parallelApi.Templates.apply(parallelDocument, "top-arch").elements.length, "runtime modules must resolve dependencies after parallel, order-independent loading");
assert.equal(parallelApi.History.create(parallelDocument).state().dirty, false);

const piece = { width_cm: 80, length_cm: 210 };
const initial = api.Document.create(piece);
assert.equal(initial.schema, "almdina.special-shape-documentation");
assert.deepEqual(initial.canvas, { widthMm: 800, heightMm: 2100 });
assert.equal(api.Document.hasContent(initial), false);

for (const definition of api.Templates.DEFINITIONS) {
    const applied = api.Templates.apply(initial, definition.id);
    assert.ok(applied.elements.length, `${definition.id} must produce editable elements`);
    assert.equal(applied.templateId, definition.id);
}

const jitteredLine = Array.from({ length: 31 }, (_, index) => ({ xMm: 50 + index * 8, yMm: 100 + (index % 3 - 1) * 1.6 }));
const cleanedLine = api.SmartPen.clean(jitteredLine, { toleranceMm: 5 });
assert.equal(cleanedLine.kind, "straight");
assert.equal(cleanedLine.points.length, 2, "a nearly straight stroke should collapse to one clean segment");
assert.equal(cleanedLine.points[0].yMm, cleanedLine.points[1].yMm, "a nearly horizontal stroke should snap as one line");

const center = { xMm: 240, yMm: 220 }, radius = 120;
const sampledArc = Array.from({ length: 81 }, (_, index) => {
    const angle = Math.PI - index * Math.PI / 80;
    return { xMm: center.xMm + Math.cos(angle) * radius, yMm: center.yMm - Math.sin(angle) * radius + (index % 2 ? 0.45 : -0.45) };
});
const cleanedArc = api.SmartPen.clean(sampledArc, { toleranceMm: 5 });
assert.equal(cleanedArc.kind, "curve");
assert.ok(cleanedArc.points.length >= 20, "an arc must retain enough samples to render smoothly rather than as a polygon");
const radialError = Math.max(...cleanedArc.points.map(point => Math.abs(Math.hypot(point.xMm - center.xMm, point.yMm - center.yMm) - radius)));
assert.ok(radialError < 2, `arc cleanup must preserve curvature; radial error was ${radialError}`);

const closedLoop = Array.from({ length: 65 }, (_, index) => {
    const angle = index * Math.PI * 2 / 64;
    return { xMm: 200 + Math.cos(angle) * 100, yMm: 200 + Math.sin(angle) * 100 };
});
const cleanedLoop = api.SmartPen.clean(closedLoop, { toleranceMm: 5, joinToleranceMm: 20 });
assert.equal(cleanedLoop.suggestClose, true, "near endpoints must offer closure");
assert.deepEqual(api.SmartPen.close(cleanedLoop.points).at(-1), cleanedLoop.points[0]);

let template = api.Templates.apply(initial, "top-arch");
const element = template.elements[0];
const moved = api.ElementTransform.translate(element, 20, 30, template.canvas);
assert.equal(moved.points[0].xMm, element.points[0].xMm + 20);
assert.equal(moved.points[0].yMm, element.points[0].yMm + 30);
const resized = api.ElementTransform.resize(element, "resize-end", { xMm: 760, yMm: 2000 }, template.canvas);
assert.ok(api.ElementTransform.bounds(resized).maxX > api.ElementTransform.bounds(element).maxX);
const movedOutsideDoor = api.ElementTransform.translate(element, -1000, -1000, template.canvas);
assert.ok(api.ElementTransform.bounds(movedOutsideDoor).minX < 0, "the free workspace must not clamp moved elements to the door width");
assert.ok(api.ElementTransform.bounds(movedOutsideDoor).minY < 0, "the free workspace must not clamp moved elements to the door height");
const resizedOutsideDoor = api.ElementTransform.resize(element, "resize-end", { xMm: 1200, yMm: 2600 }, template.canvas);
assert.ok(api.ElementTransform.bounds(resizedOutsideDoor).maxX > template.canvas.widthMm, "free resize must extend beyond the nominal door frame");
assert.ok(api.ElementTransform.bounds(resizedOutsideDoor).maxY > template.canvas.heightMm, "free resize must extend beyond the nominal door frame");

const initialViewport = api.CanvasViewport.initial(
    { width: 900, height: 620 },
    { widthMm: 400, heightMm: 2100 },
);
assert.equal(initialViewport.scale, 1, "a 40 cm door must open at a comfortable 100% scale without manual zoom");
const anchor = { x: 450, y: 250 };
const worldBeforeZoom = api.CanvasViewport.toWorld(initialViewport, anchor);
const zoomedViewport = api.CanvasViewport.zoomAt(initialViewport, 2, anchor);
const worldAfterZoom = api.CanvasViewport.toWorld(zoomedViewport, anchor);
assert.deepEqual(worldAfterZoom, worldBeforeZoom, "zoom must stay centered under the pointer");
const freePoint = api.CanvasViewport.toWorld({ scale: 1, x: 300, y: 180 }, { x: 0, y: 0 });
assert.deepEqual(freePoint, { xMm: -300, yMm: -180 }, "the canvas coordinate system must remain free outside the nominal door frame");

const shortcuts = api.KeyboardShortcuts;
assert.equal(shortcuts.resolve({ code: "KeyV", key: "ر" }), "select", "V must select even while the Arabic keyboard layout is active");
assert.equal(shortcuts.resolve({ code: "KeyP", key: "ح" }), "pen", "P must select the pen even while the Arabic keyboard layout is active");
assert.equal(shortcuts.resolve({ code: "KeyL", key: "م" }), "line", "L must select the line tool with a non-English key value");
assert.equal(shortcuts.resolve({ code: "KeyR", key: "ق" }), "rect", "R must select the rectangle tool with a non-English key value");
assert.equal(shortcuts.resolve({ code: "KeyC", key: "ؤ", ctrlKey: true }), "copy");
assert.equal(shortcuts.resolve({ code: "KeyV", key: "ر", ctrlKey: true }), "paste");
assert.equal(shortcuts.resolve({ code: "KeyZ", key: "ئ", ctrlKey: true }), "undo");
assert.equal(shortcuts.resolve({ code: "KeyY", key: "غ", ctrlKey: true }), "redo");
assert.equal(shortcuts.resolve({ code: "KeyZ", key: "ئ", ctrlKey: true, shiftKey: true }), "redo");

const clipboard = api.ElementClipboard.create(api.Document, api.ElementTransform);
assert.equal(clipboard.copy(element), true);
const firstPaste = clipboard.paste(24);
assert.notEqual(firstPaste.id, element.id);
assert.equal(api.ElementTransform.bounds(firstPaste).minX, api.ElementTransform.bounds(element).minX + 24);
const secondPaste = clipboard.paste(24);
assert.equal(api.ElementTransform.bounds(secondPaste).minX, api.ElementTransform.bounds(firstPaste).minX + 24, "repeated paste must offset each duplicate visibly");

const history = api.History.create(initial);
history.commit(template);
assert.equal(history.state().dirty, true);
assert.equal(history.state().canUndo, true);
history.undo();
assert.equal(history.get().elements.length, 0);
history.redo();
assert.ok(history.get().elements.length);
history.markSaved();
assert.equal(history.state().dirty, false);
const submittedSnapshot = history.get();
history.commit(api.Document.setNotes(history.get(), "تعديل أثناء الحفظ"));
history.markSaved(submittedSnapshot);
assert.equal(history.state().dirty, true, "an edit made while a save is pending must remain unsaved after the older request completes");

const image = api.Document.setReference(initial, { fileUrl: "/private/files/reference.jpg", opacity: 0.72, rotationDeg: 0, locked: true });
assert.equal(api.Document.hasContent(image), true);
assert.equal(api.Document.fromStored(api.Document.toStored(image), piece).reference.fileUrl, "/private/files/reference.jpg");
assert.deepEqual(image.reference.crop, { x: 0, y: 0, width: 1, height: 1 });

const crop = api.ReferenceCrop;
assert.deepEqual(crop.normalize({ x: -1, y: 0.9, width: 2, height: 0.5 }), { x: 0, y: 0.9, width: 1, height: 0.1 });
assert.deepEqual(crop.transform({ x: 0.2, y: 0.2, width: 0.5, height: 0.5 }, "move", { x: 0.6, y: -0.4 }), { x: 0.5, y: 0, width: 0.5, height: 0.5 });
assert.deepEqual(crop.transform({ x: 0.2, y: 0.2, width: 0.5, height: 0.5 }, "nw", { x: 0.1, y: 0.1 }), { x: 0.3, y: 0.3, width: 0.4, height: 0.4 });
const croppedImage = api.Document.setReference(image, {
    ...image.reference,
    crop: { x: 0.2, y: 0.1, width: 0.5, height: 0.6 },
    imageSize: { widthPx: 2480, heightPx: 3508 },
});
const storedCrop = api.Document.fromStored(api.Document.toStored(croppedImage), piece).reference;
assert.deepEqual(storedCrop.crop, { x: 0.2, y: 0.1, width: 0.5, height: 0.6 });
assert.deepEqual(storedCrop.imageSize, { widthPx: 2480, heightPx: 3508 });

const pixels = new Uint8ClampedArray(100 * 100 * 4);
for (let index = 0; index < pixels.length; index += 4) { pixels[index] = 250; pixels[index + 1] = 250; pixels[index + 2] = 250; pixels[index + 3] = 255; }
for (let y = 30; y < 70; y += 1) for (let x = 25; x < 75; x += 1) { const offset = (y * 100 + x) * 4; pixels[offset] = 35; pixels[offset + 1] = 35; pixels[offset + 2] = 35; }
const detectedCrop = crop.detectContentBounds({ width: 100, height: 100, data: pixels });
assert.ok(detectedCrop.x < 0.25 && detectedCrop.x > 0.15);
assert.ok(detectedCrop.y < 0.3 && detectedCrop.y > 0.2);
assert.ok(detectedCrop.width > 0.5 && detectedCrop.width < 0.65);
assert.ok(detectedCrop.height > 0.4 && detectedCrop.height < 0.55);

async function verifyScannerBridge() {
    const calls = [];
    const health = await api.ScannerBridge.health({
        timeoutMs: 250,
        fetchImpl: async (url, options) => {
            calls.push({ url, options });
            return new Response(JSON.stringify({ ok: true, service: "almadina-scanner-bridge", version: "1.0.0" }), { status: 200, headers: { "content-type": "application/json" } });
        },
    });
    assert.equal(health.ok, true);
    assert.equal(calls[0].url, "http://127.0.0.1:17831/health");
    assert.equal(calls[0].options.credentials, "omit");
    assert.equal(api.ScannerBridge.INSTALLER_URL, "https://github.com/Hasan-Alhendi/almdina-erp/releases/download/scanner-bridge-latest/AlmdinaScannerBridgeSetup.exe");

    const scanned = await api.ScannerBridge.scan({
        fetchImpl: async () => new Response(new Blob(["jpeg-data"], { type: "image/jpeg" }), { status: 200, headers: { "content-type": "image/jpeg" } }),
    });
    assert.equal(scanned.type, "image/jpeg");
    assert.match(scanned.name, /^scan-.*\.jpg$/);

    const cancelled = await api.ScannerBridge.scan({ fetchImpl: async () => new Response(null, { status: 204 }) });
    assert.equal(cancelled, null, "cancelling the Windows scanner dialog must be a no-op");
    await assert.rejects(
        () => api.ScannerBridge.scan({ fetchImpl: async () => new Response(null, { status: 409 }) }),
        error => error.code === api.ScannerBridge.ERROR_CODES.BUSY,
    );
    await assert.rejects(
        () => api.ScannerBridge.scan({ fetchImpl: async () => new Response(null, { status: 413 }) }),
        error => error.code === api.ScannerBridge.ERROR_CODES.IMAGE_TOO_LARGE,
    );
    await assert.rejects(
        () => api.ScannerBridge.scan({ fetchImpl: async () => new Response(
            JSON.stringify({ ok: false, code: "invalid_scanner_image", message: "Scanner did not return a valid JPEG image." }),
            { status: 500, headers: { "content-type": "application/json" } },
        ) }),
        error => error.code === api.ScannerBridge.ERROR_CODES.INVALID_IMAGE && error.bridgeCode === "invalid_scanner_image",
        "the browser must preserve the bridge error instead of collapsing every HTTP 500 into scan-failed",
    );
    await assert.rejects(
        () => api.ScannerBridge.scan({ fetchImpl: async () => new Response(
            JSON.stringify({ ok: false, code: "scanner_unavailable", message: "Windows cannot find a compatible scanner." }),
            { status: 503, headers: { "content-type": "application/json" } },
        ) }),
        error => error.code === api.ScannerBridge.ERROR_CODES.NO_SCANNER && error.bridgeCode === "scanner_unavailable",
    );
    await assert.rejects(
        () => api.ScannerBridge.health({ timeoutMs: 250, fetchImpl: async () => { throw new Error("offline"); } }),
        error => error.code === api.ScannerBridge.ERROR_CODES.UNAVAILABLE,
    );
    await assert.rejects(
        () => api.ScannerBridge.health({ baseUrl: "http://scanner.example.com:17831", fetchImpl: async () => { throw new Error("must not run"); } }),
        error => error.code === api.ScannerBridge.ERROR_CODES.INVALID_RESPONSE,
        "the browser adapter must never send scanner requests outside IPv4 loopback",
    );
}

verifyScannerBridge()
    .then(() => console.log("Special-shape documentation domain, scanner, smooth smart pen, transforms, and history passed"))
    .catch(error => { console.error(error); process.exitCode = 1; });
