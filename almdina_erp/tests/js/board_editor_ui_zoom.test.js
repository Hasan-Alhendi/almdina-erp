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
        getComputedStyle: () => ({
            getPropertyValue: (name) => (name === "--abe-ui-zoom" ? "0.9" : ""),
        }),
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
const page = fs.readFileSync(path.join(root, "almdina_erp/page/board_editor/board_editor.js"), "utf8");
const controller = fs.readFileSync(path.join(root, "public/js/board_editor/controller.js"), "utf8");
const contextActions = fs.readFileSync(
    path.join(root, "public/js/door_cutting_order/cutting_plan/door_cutting_order_plan_context_actions_ux.js"),
    "utf8"
);

assert.equal(CanvasRenderer.UI_ZOOM, 0.9);
assert.match(css, /--abe-ui-zoom:\s*0\.9/);
assert.match(css, /\.abe-page[\s\S]*zoom:\s*var\(--abe-ui-zoom\)/);
assert.match(css, /width:\s*calc\(100% \/ var\(--abe-ui-zoom\)\)/);
assert.match(page, /board_editor\.css\?v=29/);
assert.match(page, /canvas_renderer\.js\?v=31/);
assert.match(page, /controller\.js\?v=28/);
assert.match(controller, /clientPointToLocal/);
assert.match(contextActions, /target="_blank"/);
assert.match(contextActions, /boardEditorAppPath/);
assert.doesNotMatch(contextActions, /frappe\.set_route\("board-editor"/);

function fakeStage(layoutW, layoutH, cssZoom) {
    return {
        clientWidth: layoutW,
        clientHeight: layoutH,
        getBoundingClientRect() {
            return {
                left: 40,
                top: 60,
                width: layoutW * cssZoom,
                height: layoutH * cssZoom,
                right: 40 + layoutW * cssZoom,
                bottom: 60 + layoutH * cssZoom,
            };
        },
        closest: () => ({
            /* marker for declaredUiZoom */
        }),
    };
}

{
    const stage = fakeStage(900, 600, 0.9);
    assert.ok(Math.abs(CanvasRenderer.elementCssZoom(stage) - 0.9) < 1e-9);
    const local = CanvasRenderer.clientPointToLocal(stage, 40 + 90, 60 + 45);
    // 90 visual px → 100 layout px under 0.9 zoom.
    assert.ok(Math.abs(local.x - 100) < 1e-9, `x ${local.x}`);
    assert.ok(Math.abs(local.y - 50) < 1e-9, `y ${local.y}`);
    const delta = CanvasRenderer.clientDeltaToLocal(stage, 90, 0);
    assert.ok(Math.abs(delta.x - 100) < 1e-9);
}

// Zoom-around-pointer remains stable when focal is expressed in layout units
// under a 0.9 CSS zoom (the conversion controller must apply).
{
    const viewSize = { width: 900, height: 600 };
    const worldSize = { width: 3000, height: 2000 };
    const camera = {
        scale: 0.4,
        scrollX: 200,
        scrollY: 80,
        padX: 16,
        padY: 16,
        trailX: 16,
        trailY: 16,
        minX: 0,
        minY: 0,
    };
    const visualFocal = { x: 90, y: 45 };
    const layoutFocal = {
        x: visualFocal.x / 0.9,
        y: visualFocal.y / 0.9,
    };
    const world = CanvasRenderer.cameraPointToWorld(
        camera.scrollX,
        camera.scrollY,
        layoutFocal.x,
        layoutFocal.y,
        camera.scale,
        camera
    );
    const next = CanvasRenderer.zoomAroundFocal(
        camera,
        layoutFocal,
        1.2,
        viewSize,
        worldSize
    );
    const sized = CanvasRenderer.contentSizeForCamera(next, viewSize, worldSize);
    const applied = {
        ...next,
        scrollX: Math.min(Math.max(0, next.scrollX), sized.maxScrollX),
        scrollY: Math.min(Math.max(0, next.scrollY), sized.maxScrollY),
    };
    const screen = CanvasRenderer.worldToScreen(world.x, world.y, applied);
    const drift = Math.hypot(screen.x - layoutFocal.x, screen.y - layoutFocal.y);
    assert.ok(drift <= 1e-6, `layout-focal drift ${drift}`);
}

console.log("board_editor_ui_zoom.test.js: ok");
