(() => {
    "use strict";

    const root = window.AlmdinaDoorDrawingV2 = window.AlmdinaDoorDrawingV2 || Object.create(null);
    const precision = root.Precision;
    if (!precision) throw new Error("Door Drawing V2 Precision must load before ViewportModel");

    const DEFAULT_PADDING_PX = 72;
    const DEFAULT_MIN_SCALE = 0.02;
    const DEFAULT_MAX_SCALE = 64;

    function finite(value, label) {
        const number = Number(value);
        if (!Number.isFinite(number)) throw new TypeError(`${label} must be finite`);
        return number;
    }

    function positive(value, label) {
        const number = finite(value, label);
        if (number <= 0) throw new RangeError(`${label} must be greater than zero`);
        return number;
    }

    function clamp(value, minimum, maximum) {
        return Math.max(minimum, Math.min(maximum, value));
    }

    function normalizedOptions(options = {}) {
        const viewportWidthPx = positive(options.viewportWidthPx, "viewportWidthPx");
        const viewportHeightPx = positive(options.viewportHeightPx, "viewportHeightPx");
        const worldWidthMm = positive(options.worldWidthMm, "worldWidthMm");
        const worldHeightMm = positive(options.worldHeightMm, "worldHeightMm");
        const paddingPx = clamp(
            finite(options.paddingPx == null ? DEFAULT_PADDING_PX : options.paddingPx, "paddingPx"),
            0,
            Math.min(viewportWidthPx, viewportHeightPx) * 0.45
        );
        const minScale = positive(options.minScale == null ? DEFAULT_MIN_SCALE : options.minScale, "minScale");
        const maxScale = positive(options.maxScale == null ? DEFAULT_MAX_SCALE : options.maxScale, "maxScale");
        if (minScale > maxScale) throw new RangeError("minScale cannot exceed maxScale");
        return {
            viewportWidthPx,
            viewportHeightPx,
            worldWidthMm,
            worldHeightMm,
            paddingPx,
            minScale,
            maxScale,
        };
    }

    function fitScale(options) {
        const availableWidth = Math.max(1, options.viewportWidthPx - options.paddingPx * 2);
        const availableHeight = Math.max(1, options.viewportHeightPx - options.paddingPx * 2);
        return clamp(
            Math.min(availableWidth / options.worldWidthMm, availableHeight / options.worldHeightMm),
            options.minScale,
            options.maxScale
        );
    }

    function create(options = {}) {
        const normalized = normalizedOptions(options);
        const fittedScale = fitScale(normalized);
        const requestedScale = options.scale == null ? fittedScale : finite(options.scale, "scale");
        const scale = clamp(requestedScale, normalized.minScale, normalized.maxScale);
        const drawnWidthPx = normalized.worldWidthMm * scale;
        const drawnHeightPx = normalized.worldHeightMm * scale;
        const panX = options.panX == null
            ? (normalized.viewportWidthPx - drawnWidthPx) / 2
            : finite(options.panX, "panX");
        const panY = options.panY == null
            ? (normalized.viewportHeightPx - drawnHeightPx) / 2
            : finite(options.panY, "panY");
        return Object.freeze({
            ...normalized,
            scale,
            fitScale: fittedScale,
            panX,
            panY,
        });
    }

    function worldToScreen(state, point) {
        const x = finite(point && point.x, "point.x");
        const y = finite(point && point.y, "point.y");
        return Object.freeze({
            x: state.panX + x * state.scale,
            y: state.panY + (state.worldHeightMm - y) * state.scale,
        });
    }

    function screenToWorld(state, point) {
        const x = finite(point && point.x, "point.x");
        const y = finite(point && point.y, "point.y");
        return Object.freeze({
            x: precision.serialized((x - state.panX) / state.scale),
            y: precision.serialized(
                state.worldHeightMm - (y - state.panY) / state.scale
            ),
        });
    }

    function zoomAt(state, nextScale, screenPoint) {
        const anchor = {
            x: finite(screenPoint && screenPoint.x, "screenPoint.x"),
            y: finite(screenPoint && screenPoint.y, "screenPoint.y"),
        };
        const worldAnchor = screenToWorld(state, anchor);
        const scale = clamp(finite(nextScale, "nextScale"), state.minScale, state.maxScale);
        return create({
            ...state,
            scale,
            panX: anchor.x - worldAnchor.x * scale,
            panY: anchor.y - (state.worldHeightMm - worldAnchor.y) * scale,
        });
    }

    function zoomBy(state, factor, screenPoint = null) {
        const multiplier = positive(factor, "factor");
        const anchor = screenPoint || {
            x: state.viewportWidthPx / 2,
            y: state.viewportHeightPx / 2,
        };
        return zoomAt(state, state.scale * multiplier, anchor);
    }

    function panByScreen(state, deltaX, deltaY) {
        return create({
            ...state,
            scale: state.scale,
            panX: state.panX + finite(deltaX, "deltaX"),
            panY: state.panY + finite(deltaY, "deltaY"),
        });
    }

    function fit(state) {
        return create({
            ...state,
            scale: state.fitScale,
            panX: undefined,
            panY: undefined,
        });
    }

    function resizeViewport(state, viewportWidthPx, viewportHeightPx) {
        const previousCenter = screenToWorld(state, {
            x: state.viewportWidthPx / 2,
            y: state.viewportHeightPx / 2,
        });
        const next = create({
            ...state,
            viewportWidthPx,
            viewportHeightPx,
            scale: state.scale,
            panX: 0,
            panY: 0,
        });
        const center = {
            x: next.viewportWidthPx / 2,
            y: next.viewportHeightPx / 2,
        };
        return create({
            ...next,
            scale: next.scale,
            panX: center.x - previousCenter.x * next.scale,
            panY: center.y - (next.worldHeightMm - previousCenter.y) * next.scale,
        });
    }

    function visibleWorldRect(state) {
        const topLeft = screenToWorld(state, { x: 0, y: 0 });
        const bottomRight = screenToWorld(state, {
            x: state.viewportWidthPx,
            y: state.viewportHeightPx,
        });
        return Object.freeze({
            left: topLeft.x,
            right: bottomRight.x,
            top: topLeft.y,
            bottom: bottomRight.y,
        });
    }

    function zoomPercent(state) {
        return Math.round((state.scale / state.fitScale) * 100);
    }

    function matrix(state) {
        return Object.freeze({
            a: state.scale,
            b: 0,
            c: 0,
            d: -state.scale,
            e: state.panX,
            f: state.panY + state.worldHeightMm * state.scale,
        });
    }

    root.ViewportModel = Object.freeze({
        DEFAULT_PADDING_PX,
        DEFAULT_MIN_SCALE,
        DEFAULT_MAX_SCALE,
        create,
        fit,
        worldToScreen,
        screenToWorld,
        zoomAt,
        zoomBy,
        panByScreen,
        resizeViewport,
        visibleWorldRect,
        zoomPercent,
        matrix,
    });
})();
