"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const root = path.resolve(__dirname, "../..");

function load(...relativePaths) {
    const context = {
        frappe: { utils: { escape_html: (value) => String(value) } },
        __: (message) => message,
        console,
    };
    context.window = context;
    context.globalThis = context;
    vm.createContext(context);
    relativePaths.forEach((relativePath) => {
        vm.runInContext(
            fs.readFileSync(path.join(root, relativePath), "utf8"),
            context,
            { filename: relativePath }
        );
    });
    return context.window.AlmdinaBoardEditor;
}

const { CanvasRenderer } = load("public/js/board_editor/canvas_renderer.js");
const css = fs.readFileSync(path.join(root, "public/css/board_editor.css"), "utf8");
const controller = fs.readFileSync(path.join(root, "public/js/board_editor/controller.js"), "utf8");
const rendererSrc = fs.readFileSync(path.join(root, "public/js/board_editor/canvas_renderer.js"), "utf8");
const page = fs.readFileSync(path.join(root, "almdina_erp/page/board_editor/board_editor.js"), "utf8");

assert.equal(CanvasRenderer.OPENING_SCALE_FACTOR, 0.7);
assert.match(css, /grid-template-columns:\s*224px/);
assert.match(css, /\.abe-canvas-stage[\s\S]*direction:\s*ltr/);
assert.match(rendererSrc, /viewBox="0 0 \$\{contentW\} \$\{contentH\}"/);
assert.doesNotMatch(rendererSrc, /viewBox="\$\{metrics\.minX \* scale\}/);

function assertAnchorStable(camera, focal, factor) {
    const before = CanvasRenderer.cameraPointToWorld(
        camera.scrollX,
        camera.scrollY,
        focal.x,
        focal.y,
        camera.scale,
        camera
    );
    const next = CanvasRenderer.zoomAroundFocal(camera, focal, factor);
    const after = CanvasRenderer.cameraPointToWorld(
        next.scrollX,
        next.scrollY,
        focal.x,
        focal.y,
        next.scale,
        next
    );
    assert.ok(Math.abs(before.x - after.x) < 1e-9, `x ${before.x} -> ${after.x}`);
    assert.ok(Math.abs(before.y - after.y) < 1e-9, `y ${before.y} -> ${after.y}`);
    const screen = CanvasRenderer.worldToScreen(before.x, before.y, next);
    assert.ok(Math.abs(screen.x - focal.x) < 1e-9, `screen x ${screen.x} vs ${focal.x}`);
    assert.ok(Math.abs(screen.y - focal.y) < 1e-9, `screen y ${screen.y} vs ${focal.y}`);
    return next;
}

// Reproduce the reported piece-under-pointer case across a zoom ladder.
{
    let camera = {
        scale: 0.28,
        scrollX: 140,
        scrollY: 90,
        padX: 48,
        padY: 36,
        minX: -80,
        minY: -40,
    };
    const focal = { x: 260, y: 190 };
    const held = CanvasRenderer.cameraPointToWorld(
        camera.scrollX,
        camera.scrollY,
        focal.x,
        focal.y,
        camera.scale,
        camera
    );
    const ladder = [1.25, 1.2, 1.15, 1 / 1.15, 1 / 1.2, 1 / 1.25];
    ladder.forEach((factor) => {
        camera = assertAnchorStable(camera, focal, factor);
    });
    const finalWorld = CanvasRenderer.cameraPointToWorld(
        camera.scrollX,
        camera.scrollY,
        focal.x,
        focal.y,
        camera.scale,
        camera
    );
    assert.ok(Math.abs(held.x - finalWorld.x) < 1e-9);
    assert.ok(Math.abs(held.y - finalWorld.y) < 1e-9);
}

// Origin camera, negative world min, moved boards, edge zoom.
[
    { scale: 0.4, scrollX: 0, scrollY: 0, padX: 16, padY: 16, minX: 0, minY: 0 },
    { scale: 0.35, scrollX: 220, scrollY: 0, padX: 20, padY: 18, minX: 0, minY: 0 },
    { scale: 0.35, scrollX: 0, scrollY: 180, padX: 20, padY: 18, minX: 0, minY: 0 },
    { scale: 0.42, scrollX: 160, scrollY: 110, padX: 30, padY: 24, minX: -120, minY: -60 },
    { scale: 0.5, scrollX: 90, scrollY: 70, padX: 16, padY: 16, minX: 80, minY: 40 },
    { scale: 0.55, scrollX: 6, scrollY: 4, padX: 16, padY: 16, minX: -30, minY: 10 },
].forEach((camera) => {
    assertAnchorStable(camera, { x: 40, y: 30 }, 1.3);
    assertAnchorStable(camera, { x: 40, y: 30 }, 0.75);
});

// Empty-space / piece-like focal points with rapid in/out.
{
    let camera = {
        scale: 0.32,
        scrollX: 300,
        scrollY: 240,
        padX: 22,
        padY: 22,
        minX: -50,
        minY: 20,
    };
    const foci = [
        { x: 120, y: 80 },
        { x: 10, y: 12 },
        { x: 500, y: 360 },
    ];
    foci.forEach((focal) => {
        camera = assertAnchorStable(camera, focal, 1.4);
        camera = assertAnchorStable(camera, focal, 0.7);
        camera = assertAnchorStable(camera, focal, 1.1);
    });
}

assert.equal(CanvasRenderer.columnCount(1220, 1100), 2);
assert.match(controller, /metrics\.minX/);
assert.match(controller, /lastCanvasPointerClient/);
assert.match(page, /canvas_renderer\.js\?v=29/);
assert.match(page, /board_editor\.css\?v=28/);

console.log("board_editor_camera_density.test.js: ok");
