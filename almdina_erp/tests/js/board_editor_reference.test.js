"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const root = path.resolve(__dirname, "../..");

function loadContext(files, extras) {
    const context = Object.assign({
        console,
        __: (message) => message,
        frappe: { utils: { escape_html: (value) => String(value == null ? "" : value) }, boot: { lang: "en" } },
        document: { createElementNS() { return { setAttribute() {}, appendChild() {} }; } },
    }, extras || {});
    context.window = context;
    context.globalThis = context;
    vm.createContext(context);
    files.forEach((relative) => {
        vm.runInContext(fs.readFileSync(path.join(root, relative), "utf8"), context, { filename: relative });
    });
    return context;
}

function load(files, extras) {
    return loadContext(files, extras).AlmdinaBoardEditor;
}

const editor = load([
    "public/js/board_editor/history.js",
    "public/js/board_editor/drawing_space.js",
    "public/js/board_editor/drawing_model.js",
    "public/js/board_editor/drawing_reference.js",
    "public/js/board_editor/drawing_snap.js",
    "public/js/board_editor/session_document.js",
]);
const Reference = editor.DrawingReference;
const Model = editor.DrawingModel;
const Snap = editor.DrawingSnap;
const Space = editor.DrawingSpace;

function session(piece) {
    const drawing = Model.createSession();
    drawing.activate({ pieceInstanceId: piece || "piece:special", widthMm: 600, lengthMm: 2100 });
    drawing.markReady();
    return drawing;
}

function image(overrides) {
    return Object.assign({
        x_mm: 0,
        y_mm: 0,
        width_mm: 400,
        height_mm: 600,
        rotation_deg: 0,
    }, overrides || {});
}

const placed = Reference.initialPlacement(600, 2100, 400, 200);
assert.equal(placed.opacity, 0.5);
assert.ok(Math.abs((placed.width_mm / placed.height_mm) - 2) < 0.001);

const scaled = Reference.applyCalibration(image(), { x: 0, y: 0 }, { x: 200, y: 0 }, 350);
assert.equal(scaled.ok, true);
assert.equal(scaled.width_mm, 700);
assert.equal(scaled.height_mm, 1050);
assert.equal(scaled.x_mm, 0);
assert.equal(scaled.y_mm, 0);
assert.equal(scaled.calibration.known_distance_mm, 350);
assert.equal(scaled.calibration.end_mm.x_mm, 350);
assert.equal(Math.hypot(scaled.calibration.end_mm.x_mm - scaled.calibration.start_mm.x_mm, scaled.calibration.end_mm.y_mm - scaled.calibration.start_mm.y_mm), 350);

const rotated = Reference.applyCalibration(image({ rotation_deg: 90 }), { x: 0, y: 0 }, { x: 0, y: 200 }, 350);
assert.equal(rotated.ok, true);
assert.equal(rotated.x_mm, 0);
assert.equal(rotated.y_mm, 0);
assert.equal(rotated.width_mm, 700);
assert.equal(rotated.height_mm, 1050);
assert.equal(rotated.calibration.end_mm.y_mm, 350);

const frame = Space.pieceFrame({
    placement_cm: { x: 10, y: 4 },
    rotation_deg: 90,
    flip_h: true,
    flip_v: true,
    sheet_no: 1,
    pivot_mm: { x: 50, y: 50 },
}, { 1: { origin_x_mm: 20, origin_y_mm: 30 } }, { widthMm: 700, lengthMm: 1050 });
const startWorld = Space.doorToWorld(frame, rotated.calibration.start_mm.x_mm, rotated.calibration.start_mm.y_mm);
const endWorld = Space.doorToWorld(frame, rotated.calibration.end_mm.x_mm, rotated.calibration.end_mm.y_mm);
assert.ok(Math.abs(Math.hypot(endWorld.x - startWorld.x, endWorld.y - startWorld.y) - 350) < 0.05);

assert.equal(Reference.applyCalibration(image(), { x: 1, y: 1 }, { x: 1, y: 1 }, 350).code, "invalid_calibration");
assert.equal(Reference.applyCalibration(image(), { x: 0, y: 0 }, { x: 200, y: 0 }, 0).code, "invalid_calibration");
assert.equal(Reference.applyCalibration(image(), { x: 0, y: 0 }, { x: 200, y: 0 }, -4).code, "invalid_calibration");
assert.equal(Reference.applyCalibration(image(), { x: 0, y: 0 }, { x: 200, y: 0 }, "abc").code, "invalid_calibration");
assert.equal(Reference.applyCalibration(image(), { x: -30, y: 0 }, { x: 200, y: 0 }, 350).code, "calibration_outside");
assert.equal(Reference.applyCalibration(image(), { x: 0, y: 0 }, { x: 200, y: 0 }, 100000000).code, "unbounded");

const drawing = session();
assert.equal(drawing.placePoint(10, 10), true);
assert.equal(drawing.placePoint(110, 10), true);
const before = JSON.stringify(drawing.current().document.paths);
const id = drawing.addReference(Object.assign({ file_id: "FILE-PRIVATE-1" }, image({ x_mm: 12, y_mm: 18, opacity: 0.5 })));
assert.equal(typeof id, "string");
drawing.updateReference(id, scaled);
assert.equal(JSON.stringify(drawing.current().document.paths), before);
assert.equal(drawing.current().document.references[0].calibration.known_distance_mm, 350);
drawing.updateReference(id, { width_mm: 500 });
assert.equal(drawing.current().document.references[0].calibration, null);
assert.equal(drawing.current().document.references[0].height_mm, 1050);

const aspect = Reference.resizeReference(image(), "se", 2, 2);
assert.equal(aspect.width_mm, 800);
assert.equal(aspect.height_mm, 1200);
assert.equal(aspect.x_mm, 0);
assert.equal(aspect.y_mm, 0);

drawing.updateReference(id, { locked: true, hidden: true, opacity: 0.25 });
const locked = drawing.current().document.references[0];
assert.equal(locked.locked, true);
assert.equal(locked.hidden, true);
assert.equal(locked.opacity, 0.25);
assert.equal(drawing.deleteReference(id), true);
assert.equal(drawing.current().document.references.length, 0);
assert.equal(drawing.current().document.paths.length, 1);
assert.equal(drawing.undo(), true);
assert.equal(drawing.current().document.references[0].file_id, "FILE-PRIVATE-1");
assert.equal(drawing.redo(), true);
assert.equal(drawing.current().document.references.length, 0);
assert.equal(drawing.undo(), true);

const second = drawing.addReference(Object.assign({ file_id: "FILE-PRIVATE-2" }, image()));
assert.notEqual(second, id);
assert.equal(drawing.current().document.references.length, 2);
assert.equal(drawing.current().document.paths.length, 1);

drawing.activate({ pieceInstanceId: "piece:other", widthMm: 600, lengthMm: 2100 });
drawing.markReady();
assert.equal(drawing.current().document.references.length, 0);
drawing.activate({ pieceInstanceId: "piece:special", widthMm: 600, lengthMm: 2100 });
assert.equal(drawing.current().document.references.length, 2);

const onlyImage = session("piece:image");
assert.equal(onlyImage.addReference(Object.assign({ file_id: "FILE-PRIVATE-3" }, image())), "r1");
assert.equal(onlyImage.current().document.paths.length, 0);
assert.equal(onlyImage.documentDirty(), true);

const index = Snap.buildIndex({
    paths: [],
    shapes: [],
    references: [Object.assign({ id: "r1", file_id: "FILE-PRIVATE-1" }, image())],
});
assert.equal(index.endpoints.length, 0);
assert.equal(index.lines.length, 0);
const missed = Snap.resolve({
    index,
    pointer: { x: 0, y: 0 },
    settings: Snap.defaultSettings(),
    scale: 1,
});
assert.equal(missed.snap, null);
assert.equal(missed.point.x, 0);
assert.equal(missed.point.y, 0);

const renderer = fs.readFileSync(path.join(root, "public/js/board_editor/canvas_renderer.js"), "utf8");
const controller = fs.readFileSync(path.join(root, "public/js/board_editor/controller.js"), "utf8");
const snapGeometry = fs.readFileSync(path.join(root, "public/js/board_editor/snap_geometry.js"), "utf8");
const sessionSource = fs.readFileSync(path.join(root, "public/js/board_editor/session_document.js"), "utf8");
assert.match(renderer, /data-abe-reference-image="\$\{esc\(reference\.id\)\}"[^>]*pointer-events="none"/);
assert.match(controller, /drawingTool === "select" && reference\.locked !== true/);
assert.match(controller, /function uploadReferenceFiles/);
assert.doesNotMatch(controller, /raster|traceBitmap|potrace/i);
assert.match(snapGeometry, /SNAP_ENTER_PX = 8/);
assert.doesNotMatch(snapGeometry, /reference_image|drawing_reference/);
assert.doesNotMatch(sessionSource, /references|drawing_json/);
assert.match(fs.readFileSync(path.join(root, "translations/ar.csv"), "utf8"), /Upload reference image,رفع صورة مرجعية/);
assert.match(fs.readFileSync(path.join(root, "almdina_erp/page/board_editor/board_editor.js"), "utf8"), /drawing_reference\.js\?v=1/);

const hud = loadContext(["public/js/board_editor/canvas_renderer.js"]).AlmdinaBoardEditor.CanvasRenderer.computePolylineHudPosition({
    startX: 100,
    startY: 80,
    endX: 300,
    endY: 80,
    width: 120,
    height: 32,
    gap: 24,
});
assert.equal(hud.left, 124);
assert.equal(hud.top, 24);
const hudFurther = loadContext(["public/js/board_editor/canvas_renderer.js"]).AlmdinaBoardEditor.CanvasRenderer.computePolylineHudPosition({
    startX: 100,
    startY: 80,
    endX: 500,
    endY: 80,
    width: 120,
    height: 32,
    gap: 24,
});
assert.equal(hudFurther.left, hud.left);
assert.equal(hudFurther.top, hud.top);

const uploadStart = controller.indexOf("function uploadReferenceFiles");
const uploadSource = controller.slice(uploadStart, controller.indexOf("function referenceErrorKey"));
const fetchSource = controller.slice(controller.indexOf("function ensureReferenceMedia"), controller.indexOf("function readReferenceFile"));
assert.match(controller, /function drawingServerIdentity\(\) \{[\s\S]*activeOrderName[\s\S]*loadedPlanName/);
assert.match(uploadSource, /drawingServerIdentity\(\)/);
assert.match(fetchSource, /drawingServerIdentity\(\)/);
assert.match(uploadSource, /drawingSession\.isCurrent\(pieceId, token\)/);
assert.doesNotMatch(uploadSource, /view\.orderName|target\.planName/);
assert.doesNotMatch(fetchSource, /view\.orderName|target\.planName/);
assert.match(fs.readFileSync(path.join(root, "almdina_erp/page/board_editor/board_editor.js"), "utf8"), /controller\.js\?v=50/);

const calls = [];
const apiHost = loadContext(["public/js/board_editor/api.js"], {
    frappe: {
        call(spec) {
            calls.push(spec);
            const message = spec.method.endsWith("upload_board_editor_reference_image")
                ? { ok: true, file_id: "FILE-PRIVATE-1", width_px: 40, height_px: 20, content_base64: "UE5H" }
                : { ok: true, file_id: spec.args.file_id, content_type: "image/png", content_base64: "UE5H" };
            spec.callback({ message });
        },
        utils: { escape_html: (value) => String(value == null ? "" : value) },
        boot: { lang: "en" },
    },
});
const Api = apiHost.AlmdinaBoardEditor.Api;
const identity = { orderName: "DCO-0001", planName: "PLAN-0007", pieceInstanceId: "piece:special" };
const uploadResult = Api.uploadReferenceImage(Object.assign({ fileName: "door.png", contentBase64: "abc" }, identity));
const readResult = Api.getReferenceImage(Object.assign({ fileId: "FILE-PRIVATE-1" }, identity));
assert.equal(calls.length, 2);
assert.equal(typeof uploadResult.then, "function");
assert.equal(typeof readResult.then, "function");
calls.forEach((spec) => {
    assert.equal(spec.args.order_name, "DCO-0001");
    assert.equal(spec.args.plan_name, "PLAN-0007");
    assert.equal(spec.args.piece_instance_id, "piece:special");
    assert.equal(Object.prototype.hasOwnProperty.call(spec.args, "file_url"), false);
});
assert.equal(calls[0].args.file_name, "door.png");
assert.equal(calls[0].args.content_base64, "abc");
assert.equal(calls[1].args.file_id, "FILE-PRIVATE-1");
Api.uploadReferenceImage({ orderName: "", planName: "PLAN-0007", pieceInstanceId: "piece:special", contentBase64: "abc" });
assert.equal(calls[2].args.order_name, "");

const live = session("piece:live");
live.placePoint(10, 20);
live.placePoint(80, 20);
const pathsBefore = JSON.stringify(live.current().document.paths);
const uploadToken = live.current().loadToken;
assert.equal(live.isCurrent("piece:live", uploadToken), true);
live.activate({ pieceInstanceId: "piece:other", widthMm: 600, lengthMm: 2100 });
live.markReady();
assert.equal(live.isCurrent("piece:live", uploadToken), false);
assert.equal(live.current().document.paths.length, 0);
live.activate({ pieceInstanceId: "piece:live", widthMm: 600, lengthMm: 2100 });
assert.equal(live.isCurrent("piece:live", uploadToken), true);
assert.equal(JSON.stringify(live.current().document.paths), pathsBefore);
const added = live.addReference(Object.assign({ file_id: "FILE-PRIVATE-1" }, image()));
assert.equal(live.current().document.references.length, 1);
assert.equal(live.current().document.references[0].file_id, "FILE-PRIVATE-1");
assert.equal(JSON.stringify(live.current().document.paths), pathsBefore);
assert.equal(live.documentDirty(), true);
assert.equal(added, live.current().document.references[0].id);

const board = load([
    "public/js/board_editor/history.js",
    "public/js/board_editor/session_document.js",
    "public/js/board_editor/store.js",
]);
const layoutStore = board.createStore({ projection: { pieces: [] }, order_name: "DCO-0001", plan_name: "PLAN-0007" });
layoutStore.attachSession({ pieces: { special: { piece_key: "special" } }, boards: {} }, board.History.create({ pieces: {}, boards: {} }));
const distribution = JSON.stringify(layoutStore.snapshot().session);
assert.equal(layoutStore.snapshot().orderName, undefined);
assert.equal(layoutStore.snapshot().drawingTarget, null);
live.updateReference(added, { x_mm: 30 });
assert.equal(JSON.stringify(layoutStore.snapshot().session), distribution);
assert.equal(layoutStore.snapshot().canUndo, false);
assert.equal(layoutStore.snapshot().distributionDirty, false);

const dom = loadContext([
    "public/js/board_editor/editor_mode.js",
    "public/js/board_editor/canvas_renderer.js",
], {
    frappe: { utils: { escape_html: (value) => String(value == null ? "" : value) }, boot: { lang: "en" } },
    document: null,
});
const helperSource = fs.readFileSync(path.join(root, "tests/js/board_editor_polyline_input.test.js"), "utf8");
vm.runInContext(
    `${helperSource.slice(helperSource.indexOf("const VOID"), helperSource.indexOf("function loadEditor"))}\nthis.MiniElement = MiniElement;\nthis.emit = emit;\n`,
    dom
);
dom.document = {
    createElementNS(_ns, tag) { return new dom.MiniElement(tag, {}, dom.document); },
};
const host = new dom.MiniElement("section", { class: "abe-canvas-host" }, dom.document);
const uploads = [];
const view = {
    editorMode: "drawing",
    canSaveLayout: true,
    drawingTarget: { status: "special", canEdit: true, label: "Special door", widthCm: 60, lengthCm: 210 },
    drawingView: {
        tool: "select",
        ready: true,
        referenceMenuOpen: true,
        paths: [{ id: "p1", closed: false, points: [{ id: "n1", x: 10, y: 20 }, { id: "n2", x: 80, y: 20 }], markup: "M10 20 L80 20" }],
        shapes: [],
        references: [{
            id: "r1",
            hidden: false,
            locked: false,
            selected: true,
            interactive: true,
            opacity: 0.5,
            widthMm: 400,
            heightMm: 600,
            href: "data:image/png;base64,UE5H",
            world: { origin: { x: 0, y: 0 }, xAxis: { x: 400, y: 0 }, yAxis: { x: 0, y: 600 } },
        }],
        referenceForm: { x_mm: 0, y_mm: 0, width_mm: 400, height_mm: 600, rotation_deg: 0, opacity: 0.5, aspectLocked: true },
    },
    viewport: { scale: 1, opened: true, userAdjusted: true },
    session: { pieces: {}, boards: {} },
    selectedPieceKeys: [],
    projection: { pieces: [], sheets: [], elements: [] },
};
dom.AlmdinaBoardEditor.CanvasRenderer.render(host, view, {
    uploadReferenceFiles(files) { uploads.push(Array.prototype.slice.call(files)); },
});
assert.equal(host.querySelectorAll("[data-abe-reference-image]").length, 1);
assert.equal(host.querySelector("[data-abe-reference-image]").getAttribute("pointer-events"), "none");
assert.equal(host.querySelector("[data-abe-reference-form]") != null, true);
assert.match(host.querySelector("[data-abe-drawing-path]").getAttribute("d"), /M10 20 L80 20/);
const file = { name: "door.png" };
const input = host.querySelector("[data-abe-reference-file]");
input.files = [file];
dom.emit(input, "change");
const stage = host.querySelector("[data-abe-stage]");
dom.emit(stage, "drop", { dataTransfer: { files: [file], types: ["Files"] } });
assert.equal(uploads.length, 2);
assert.equal(uploads[0][0].name, "door.png");
assert.equal(uploads[1][0].name, "door.png");

console.log("board editor reference tests ok");
