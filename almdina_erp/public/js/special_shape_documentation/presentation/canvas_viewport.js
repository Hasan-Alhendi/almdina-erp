(() => {
    "use strict";

    const root = window.AlmdinaSpecialShapeDocumentation = window.AlmdinaSpecialShapeDocumentation || Object.create(null);
    const MIN_SCALE = 0.1;
    const MAX_SCALE = 4;
    const DEFAULT_SCALE = 1;
    const SIDE_PADDING_PX = 80;

    function finite(value, fallback = 0) {
        const resolved = Number(value);
        return Number.isFinite(resolved) ? resolved : fallback;
    }

    function size(value = {}) {
        return {
            width: Math.max(1, finite(value.width, 1)),
            height: Math.max(1, finite(value.height, 1)),
        };
    }

    function clampScale(value) {
        return Math.max(MIN_SCALE, Math.min(MAX_SCALE, finite(value, DEFAULT_SCALE)));
    }

    function initial(rawSize, frame = {}) {
        const nextSize = size(rawSize);
        const frameWidth = Math.max(1, finite(frame.widthMm, 400));
        const availableWidth = Math.max(160, nextSize.width - SIDE_PADDING_PX * 2);
        const scale = clampScale(Math.min(DEFAULT_SCALE, availableWidth / frameWidth));
        const top = Math.round(Math.max(48, Math.min(96, nextSize.height * 0.12)));
        return Object.freeze({
            scale,
            x: (nextSize.width - frameWidth * scale) / 2,
            y: top,
            size: nextSize,
        });
    }

    function toWorld(viewport, point) {
        const scale = clampScale(viewport && viewport.scale);
        return {
            xMm: (finite(point && point.x) - finite(viewport && viewport.x)) / scale,
            yMm: (finite(point && point.y) - finite(viewport && viewport.y)) / scale,
        };
    }

    function toScreen(viewport, point) {
        const scale = clampScale(viewport && viewport.scale);
        return {
            x: finite(viewport && viewport.x) + finite(point && point.xMm) * scale,
            y: finite(viewport && viewport.y) + finite(point && point.yMm) * scale,
        };
    }

    function zoomAt(viewport, nextScale, anchor) {
        const scale = clampScale(nextScale);
        const point = { x: finite(anchor && anchor.x), y: finite(anchor && anchor.y) };
        const world = toWorld(viewport, point);
        return Object.freeze({
            scale,
            x: point.x - world.xMm * scale,
            y: point.y - world.yMm * scale,
            size: size(viewport && viewport.size),
        });
    }

    function pan(viewport, dx, dy) {
        return Object.freeze({
            scale: clampScale(viewport && viewport.scale),
            x: finite(viewport && viewport.x) + finite(dx),
            y: finite(viewport && viewport.y) + finite(dy),
            size: size(viewport && viewport.size),
        });
    }

    function resize(viewport, rawSize) {
        const nextSize = size(rawSize);
        if (!viewport || !viewport.size) return viewport;
        const previousSize = size(viewport.size);
        const previousCenter = { x: previousSize.width / 2, y: previousSize.height / 2 };
        const worldCenter = toWorld(viewport, previousCenter);
        return Object.freeze({
            scale: clampScale(viewport.scale),
            x: nextSize.width / 2 - worldCenter.xMm * viewport.scale,
            y: nextSize.height / 2 - worldCenter.yMm * viewport.scale,
            size: nextSize,
        });
    }

    function fit(rawSize, bounds, paddingPx = 72) {
        const nextSize = size(rawSize);
        const minX = finite(bounds && bounds.minX);
        const minY = finite(bounds && bounds.minY);
        const maxX = finite(bounds && bounds.maxX, minX + 1);
        const maxY = finite(bounds && bounds.maxY, minY + 1);
        const widthMm = Math.max(1, maxX - minX);
        const heightMm = Math.max(1, maxY - minY);
        const padding = Math.max(24, Math.min(finite(paddingPx, 72), Math.min(nextSize.width, nextSize.height) / 3));
        const scale = clampScale(Math.min(
            Math.max(1, nextSize.width - padding * 2) / widthMm,
            Math.max(1, nextSize.height - padding * 2) / heightMm,
        ));
        return Object.freeze({
            scale,
            x: nextSize.width / 2 - (minX + maxX) / 2 * scale,
            y: nextSize.height / 2 - (minY + maxY) / 2 * scale,
            size: nextSize,
        });
    }

    function percentage(viewport) {
        return Math.round(clampScale(viewport && viewport.scale) * 100);
    }

    root.CanvasViewport = Object.freeze({
        MIN_SCALE,
        MAX_SCALE,
        DEFAULT_SCALE,
        initial,
        toWorld,
        toScreen,
        zoomAt,
        pan,
        resize,
        fit,
        percentage,
    });
})();
