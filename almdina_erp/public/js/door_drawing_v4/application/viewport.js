(() => {
    "use strict";

    const root = window.AlmdinaDoorDrawingV4 = window.AlmdinaDoorDrawingV4 || Object.create(null);

    const MIN_SCALE_PX_PER_MM = 0.05;
    const MAX_SCALE_PX_PER_MM = 20;
    const DEFAULT_PADDING_PX = 48;
    const DEFAULT_GRID_TARGET_PX = 48;

    function finite(value, fallback = 0) {
        const number = Number(value);
        return Number.isFinite(number) ? number : fallback;
    }

    function clamp(value, min, max) {
        return Math.min(max, Math.max(min, value));
    }

    function freeze(camera) {
        return Object.freeze({
            viewportWidthPx: Math.max(0, finite(camera.viewportWidthPx)),
            viewportHeightPx: Math.max(0, finite(camera.viewportHeightPx)),
            scalePxPerMm: clamp(finite(camera.scalePxPerMm, 1), MIN_SCALE_PX_PER_MM, MAX_SCALE_PX_PER_MM),
            offsetXPx: finite(camera.offsetXPx),
            offsetYPx: finite(camera.offsetYPx),
        });
    }

    function create(options = {}) {
        return freeze({
            viewportWidthPx: options.viewportWidthPx,
            viewportHeightPx: options.viewportHeightPx,
            scalePxPerMm: options.scalePxPerMm || 1,
            offsetXPx: options.offsetXPx,
            offsetYPx: options.offsetYPx,
        });
    }

    function resize(camera, widthPx, heightPx) {
        return freeze({ ...camera, viewportWidthPx: widthPx, viewportHeightPx: heightPx });
    }

    function worldToScreen(camera, point) {
        return Object.freeze({
            x: camera.offsetXPx + Number(point.xMm) * camera.scalePxPerMm,
            y: camera.offsetYPx + Number(point.yMm) * camera.scalePxPerMm,
        });
    }

    function screenToWorld(camera, point) {
        return Object.freeze({
            xMm: (Number(point.x) - camera.offsetXPx) / camera.scalePxPerMm,
            yMm: (Number(point.y) - camera.offsetYPx) / camera.scalePxPerMm,
        });
    }

    function panBy(camera, deltaXPx, deltaYPx) {
        return freeze({
            ...camera,
            offsetXPx: camera.offsetXPx + finite(deltaXPx),
            offsetYPx: camera.offsetYPx + finite(deltaYPx),
        });
    }

    function zoomAt(camera, screenPoint, factor) {
        const zoomFactor = clamp(finite(factor, 1), 0.1, 10);
        const worldBefore = screenToWorld(camera, screenPoint);
        const nextScale = clamp(
            camera.scalePxPerMm * zoomFactor,
            MIN_SCALE_PX_PER_MM,
            MAX_SCALE_PX_PER_MM
        );
        return freeze({
            ...camera,
            scalePxPerMm: nextScale,
            offsetXPx: Number(screenPoint.x) - worldBefore.xMm * nextScale,
            offsetYPx: Number(screenPoint.y) - worldBefore.yMm * nextScale,
        });
    }

    function fitBlank(camera, blank, options = {}) {
        const paddingPx = Math.max(0, finite(options.paddingPx, DEFAULT_PADDING_PX));
        const blankWidthMm = Math.max(0, finite(blank && blank.widthMm));
        const blankHeightMm = Math.max(0, finite(blank && blank.heightMm));
        if (!blankWidthMm || !blankHeightMm || !camera.viewportWidthPx || !camera.viewportHeightPx) return camera;

        const availableWidthPx = Math.max(1, camera.viewportWidthPx - paddingPx * 2);
        const availableHeightPx = Math.max(1, camera.viewportHeightPx - paddingPx * 2);
        const scalePxPerMm = clamp(
            Math.min(availableWidthPx / blankWidthMm, availableHeightPx / blankHeightMm),
            MIN_SCALE_PX_PER_MM,
            MAX_SCALE_PX_PER_MM
        );
        const contentWidthPx = blankWidthMm * scalePxPerMm;
        const contentHeightPx = blankHeightMm * scalePxPerMm;
        return freeze({
            ...camera,
            scalePxPerMm,
            offsetXPx: (camera.viewportWidthPx - contentWidthPx) / 2,
            offsetYPx: (camera.viewportHeightPx - contentHeightPx) / 2,
        });
    }

    function screenToleranceToMm(camera, tolerancePx) {
        return Math.max(0, finite(tolerancePx)) / camera.scalePxPerMm;
    }

    function gridStepMm(camera, targetPx = DEFAULT_GRID_TARGET_PX) {
        const preferredPx = Math.max(8, finite(targetPx, DEFAULT_GRID_TARGET_PX));
        const rawMm = preferredPx / camera.scalePxPerMm;
        const magnitude = Math.pow(10, Math.floor(Math.log10(Math.max(rawMm, 0.0001))));
        for (const factor of [1, 2, 5]) {
            const candidate = factor * magnitude;
            if (candidate * camera.scalePxPerMm >= 28) return candidate;
        }
        return 10 * magnitude;
    }

    function zoomPercent(camera, baselinePxPerMm = 1) {
        return Math.round((camera.scalePxPerMm / Math.max(MIN_SCALE_PX_PER_MM, finite(baselinePxPerMm, 1))) * 100);
    }

    root.Viewport = Object.freeze({
        MIN_SCALE_PX_PER_MM,
        MAX_SCALE_PX_PER_MM,
        DEFAULT_PADDING_PX,
        DEFAULT_GRID_TARGET_PX,
        create,
        resize,
        worldToScreen,
        screenToWorld,
        panBy,
        zoomAt,
        fitBlank,
        screenToleranceToMm,
        gridStepMm,
        zoomPercent,
    });
})();