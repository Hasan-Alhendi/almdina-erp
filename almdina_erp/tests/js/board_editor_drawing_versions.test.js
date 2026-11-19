"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const root = path.resolve(__dirname, "../..");

function load(files) {
    const context = { console, __: (message) => message };
    context.window = context;
    context.globalThis = context;
    vm.createContext(context);
    files.forEach((relative) => {
        vm.runInContext(fs.readFileSync(path.join(root, relative), "utf8"), context, { filename: relative });
    });
    return context.AlmdinaBoardEditor;
}

const editor = load([
    "public/js/board_editor/drawing_space.js",
    "public/js/board_editor/drawing_model.js",
]);
const session = editor.DrawingModel.createSession();
const saved = { "piece:hidden": 3, "piece:a": 1 };
session.captureSeenVersions(saved);
saved["piece:hidden"] = 9;
saved["piece:new"] = 1;

const seen = JSON.parse(session.seenVersionPayload());
assert.equal(seen["piece:hidden"], 3);
assert.equal(seen["piece:a"], 1);
assert.equal(Object.prototype.hasOwnProperty.call(seen, "piece:new"), false);

session.activate({ pieceInstanceId: "piece:a", widthMm: 600, lengthMm: 2100 });
session.markReady();
const ticket = session.beginLoad();
assert.equal(session.applyLoaded(ticket.pieceInstanceId, ticket.token, {
    ok: true,
    drawing_version: 7,
    drawing: session.current().document,
}), true);
assert.equal(session.current().drawingVersion, 7);
assert.equal(JSON.parse(session.seenVersionPayload())["piece:a"], 1);
assert.equal(session.placePoint(0, 0), true);
assert.equal(session.placePoint(40, 0), true);
assert.equal(session.undo(), true);
assert.equal(session.redo(), true);
assert.equal(session.documentDirty(), true);
const localCanonical = session.documentCanonical();

session.applyLoaded("piece:a", session.current().loadToken, {
    ok: true,
    drawing_version: 8,
    drawing: session.current().document,
});
assert.equal(JSON.parse(session.seenVersionPayload())["piece:a"], 1);
assert.equal(session.documentCanonical(), localCanonical);
assert.equal(session.undo(), true);
assert.equal(session.current().future.length > 0, true);

assert.equal(session.applySave("piece:a", { ok: true, drawing_version: 2 }), true);
const afterSave = JSON.parse(session.seenVersionPayload());
assert.equal(afterSave["piece:a"], 2);
assert.equal(afterSave["piece:hidden"], 3);
assert.equal(session.documentDirty(), false);

assert.equal(session.applySave("piece:a", { ok: false, code: "version_conflict" }), false);
assert.equal(JSON.parse(session.seenVersionPayload())["piece:a"], 2);
assert.equal(session.current().document.piece_instance_id, "piece:a");

const controller = fs.readFileSync(path.join(root, "public/js/board_editor/controller.js"), "utf8");
const copy = controller.slice(
    controller.indexOf("async function createPlanCopy"),
    controller.indexOf("function onShellGeometryChange")
);
assert.match(copy, /drawingVersionPayload\(\)/);
assert.match(
    controller.slice(controller.indexOf("function drawingVersionPayload"), controller.indexOf("function revealCutProblem")),
    /seenVersionPayload/
);
assert.doesNotMatch(copy, /drawingSession\.reset\(/);
assert.doesNotMatch(copy, /captureSeenVersions/);
assert.match(copy, /drawing_versions_missing/);
assert.match(copy, /drawing_versions_invalid/);
assert.match(controller, /captureSeenVersions\(\(payload && payload\.saved_drawings\)/);
assert.doesNotMatch(
    controller.slice(controller.indexOf("function drawingVersionPayload"), controller.indexOf("function revealCutProblem")),
    /loadedRecords/
);

const catalog = fs.readFileSync(path.join(root, "translations/ar.csv"), "utf8");
assert.match(
    catalog,
    /Drawings for this cutting plan were changed in another window\. Refresh the plan before copying it\.,تم تعديل رسومات هذه الخطة في نافذة أخرى\. يرجى تحديث الخطة قبل نسخها\./
);
