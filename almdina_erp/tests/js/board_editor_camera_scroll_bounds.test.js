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
const page = fs.readFileSync(path.join(root, "almdina_erp/page/board_editor/board_editor.js"), "utf8");

assert.match(page, /canvas_renderer\.js\?v=30/);
assert.match(page, /controller\.js\?v=27/);
assert.match(page, /store\.js\?v=20/);

function pointerDrift(camera, focal, world) {
    const screen = CanvasRenderer.worldToScreen(world.x, world.y, camera);
    return Math.hypot(screen.x - focal.x, screen.y - focal.y);
}

function assertZoomKeepsPointer(camera, focal, factor, viewSize, worldSize, label) {
    const world = CanvasRenderer.cameraPointToWorld(
        camera.scrollX,
        camera.scrollY,
        focal.x,
        focal.y,
        camera.scale,
        camera
    );
    const next = CanvasRenderer.zoomAroundFocal(camera, focal, factor, viewSize, worldSize);
    const sized = CanvasRenderer.contentSizeForCamera(next, viewSize, worldSize);
    assert.ok(
        next.scrollX <= sized.maxScrollX + 1e-9,
        `${label}: scrollX ${next.scrollX} exceeds max ${sized.maxScrollX}`
    );
    assert.ok(
        next.scrollY <= sized.maxScrollY + 1e-9,
        `${label}: scrollY ${next.scrollY} exceeds max ${sized.maxScrollY}`
    );
    // Browser can only apply scroll within [0, maxScroll]; use applied scroll for drift.
    const applied = {
        ...next,
        scrollX: Math.min(Math.max(0, next.scrollX), sized.maxScrollX),
        scrollY: Math.min(Math.max(0, next.scrollY), sized.maxScrollY),
        trailX: sized.trailX,
        trailY: sized.trailY,
    };
    const drift = pointerDrift(applied, focal, world);
    assert.ok(drift <= 1 + 1e-9, `${label}: drift ${drift}px`);
    return applied;
}

// Regression: requiredScrollX 311.6 > previous maxScrollX 302 → 9.6px drift without trail.
{
    const viewSize = { width: 900, height: 600 };
    const worldSize = { width: 3000, height: 2000 };
    const camera = {
        scale: 0.4,
        scrollX: 332,
        scrollY: 0,
        padX: 16,
        padY: 16,
        trailX: 16,
        trailY: 16,
        minX: 0,
        minY: 0,
    };
    const before = CanvasRenderer.contentSizeForCamera(camera, viewSize, worldSize);
    assert.equal(before.maxScrollX, 332);
    const focal = { x: 500, y: 200 };
    const world = CanvasRenderer.cameraPointToWorld(
        camera.scrollX,
        camera.scrollY,
        focal.x,
        focal.y,
        camera.scale,
        camera
    );
    const naiveScrollX = camera.padX - camera.minX * 0.39 + world.x * 0.39 - focal.x;
    assert.ok(Math.abs(naiveScrollX - 311.6) < 1e-9, `expected 311.6 got ${naiveScrollX}`);
    const naiveMax = Math.max(
        0,
        Math.max(viewSize.width, Math.ceil(worldSize.width * 0.39 + 16 + 16)) - viewSize.width
    );
    assert.equal(naiveMax, 302);
    assert.ok(Math.abs(naiveScrollX - naiveMax - 9.6) < 1e-9);

    const next = assertZoomKeepsPointer(camera, focal, 0.39 / 0.4, viewSize, worldSize, "9.6px case");
    assert.ok(next.trailX > 16, `trail must expand, got ${next.trailX}`);
    const sized = CanvasRenderer.contentSizeForCamera(next, viewSize, worldSize);
    assert.ok(sized.maxScrollX + 1e-9 >= next.scrollX);
    assert.ok(pointerDrift(next, focal, world) <= 1e-9);
}

// Edges, max scroll, negative scroll absorption, negative world mins.
[
    {
        label: "left-edge zoom-in",
        camera: { scale: 0.35, scrollX: 0, scrollY: 0, padX: 16, padY: 16, minX: 0, minY: 0 },
        focal: { x: 12, y: 40 },
        factor: 1.25,
    },
    {
        label: "right-edge zoom-out past max",
        camera: {
            scale: 0.4,
            scrollX: 332,
            scrollY: 80,
            padX: 16,
            padY: 16,
            trailX: 16,
            trailY: 16,
            minX: 0,
            minY: 0,
        },
        focal: { x: 880, y: 40 },
        factor: 0.9,
    },
    {
        label: "bottom-edge",
        camera: {
            scale: 0.42,
            scrollX: 100,
            scrollY: 400,
            padX: 20,
            padY: 20,
            trailX: 16,
            trailY: 16,
            minX: -50,
            minY: -30,
        },
        focal: { x: 200, y: 580 },
        factor: 0.85,
    },
    {
        label: "negative-scroll demand",
        camera: {
            scale: 0.5,
            scrollX: 0,
            scrollY: 0,
            padX: 16,
            padY: 16,
            minX: -120,
            minY: -80,
        },
        focal: { x: 40, y: 30 },
        factor: 1.4,
    },
].forEach((row) => {
    const viewSize = { width: 900, height: 600 };
    const worldSize = { width: 3000, height: 2200 };
    assertZoomKeepsPointer(row.camera, row.focal, row.factor, viewSize, worldSize, row.label);
});

// Trail must shrink back toward SCENE_PAD when unused after zoom-in.
{
    const viewSize = { width: 900, height: 600 };
    const worldSize = { width: 3000, height: 2000 };
    let camera = {
        scale: 0.4,
        scrollX: 332,
        scrollY: 0,
        padX: 16,
        padY: 16,
        trailX: 16,
        trailY: 16,
        minX: 0,
        minY: 0,
    };
    const focal = { x: 500, y: 200 };
    camera = assertZoomKeepsPointer(camera, focal, 0.39 / 0.4, viewSize, worldSize, "expand");
    assert.ok(camera.trailX > CanvasRenderer.SCENE_PAD_PX);
    camera = assertZoomKeepsPointer(camera, focal, 0.4 / 0.39, viewSize, worldSize, "shrink-back");
    // After returning near original scale with attainable scroll, trail should not keep growing.
    camera = assertZoomKeepsPointer(camera, focal, 1.2, viewSize, worldSize, "zoom-in");
    const sized = CanvasRenderer.contentSizeForCamera(camera, viewSize, worldSize);
    assert.ok(
        sized.trailX <= camera.trailX + 1e-9,
        `trail should not accumulate unboundedly (${sized.trailX})`
    );
}

// World-min change must keep an unmoved world point fixed on screen.
{
    const viewSize = { width: 900, height: 600 };
    const worldSize = { width: 3200, height: 2100 };
    const camera = {
        scale: 0.4,
        scrollX: 120,
        scrollY: 80,
        padX: 24,
        padY: 18,
        trailX: 16,
        trailY: 16,
        minX: 0,
        minY: 0,
    };
    const world = { x: 400, y: 250 };
    const before = CanvasRenderer.worldToScreen(world.x, world.y, camera);
    const fixed = CanvasRenderer.reconcileCameraWorldOrigin(
        camera,
        -150,
        -40,
        viewSize,
        worldSize
    );
    assert.ok(fixed);
    assert.equal(fixed.minX, -150);
    assert.equal(fixed.minY, -40);
    const after = CanvasRenderer.worldToScreen(world.x, world.y, fixed);
    assert.ok(Math.abs(after.x - before.x) < 1e-9, `x ${before.x} -> ${after.x}`);
    assert.ok(Math.abs(after.y - before.y) < 1e-9, `y ${before.y} -> ${after.y}`);
}

// DOM scrollport model: content sized so assigned scrollLeft is not browser-clamped.
{
    function fakeStage(clientWidth, clientHeight) {
        let scrollLeft = 0;
        let scrollTop = 0;
        let scrollWidth = clientWidth;
        let scrollHeight = clientHeight;
        return {
            clientWidth,
            clientHeight,
            get scrollWidth() { return scrollWidth; },
            get scrollHeight() { return scrollHeight; },
            get scrollLeft() { return scrollLeft; },
            set scrollLeft(value) {
                const max = Math.max(0, scrollWidth - clientWidth);
                scrollLeft = Math.min(Math.max(0, Number(value) || 0), max);
            },
            get scrollTop() { return scrollTop; },
            set scrollTop(value) {
                const max = Math.max(0, scrollHeight - clientHeight);
                scrollTop = Math.min(Math.max(0, Number(value) || 0), max);
            },
            setContent(width, height) {
                scrollWidth = width;
                scrollHeight = height;
                // Re-clamp like a browser after layout.
                this.scrollLeft = scrollLeft;
                this.scrollTop = scrollTop;
            },
        };
    }

    const viewSize = { width: 900, height: 600 };
    const worldSize = { width: 3000, height: 2000 };
    const camera = {
        scale: 0.4,
        scrollX: 332,
        scrollY: 40,
        padX: 16,
        padY: 16,
        trailX: 16,
        trailY: 16,
        minX: 0,
        minY: 0,
    };
    const focal = { x: 500, y: 200 };
    const world = CanvasRenderer.cameraPointToWorld(
        camera.scrollX,
        camera.scrollY,
        focal.x,
        focal.y,
        camera.scale,
        camera
    );
    const next = CanvasRenderer.zoomAroundFocal(
        camera,
        focal,
        0.39 / 0.4,
        viewSize,
        worldSize
    );
    const stage = fakeStage(viewSize.width, viewSize.height);
    stage.setContent(next.contentW, next.contentH);
    stage.scrollLeft = next.scrollX;
    stage.scrollTop = next.scrollY;
    assert.ok(Math.abs(stage.scrollLeft - next.scrollX) < 1e-9, `applied ${stage.scrollLeft} vs ${next.scrollX}`);
    const appliedCamera = { ...next, scrollX: stage.scrollLeft, scrollY: stage.scrollTop };
    assert.ok(pointerDrift(appliedCamera, focal, world) <= 1e-6);
}

console.log("board_editor_camera_scroll_bounds.test.js: ok");
