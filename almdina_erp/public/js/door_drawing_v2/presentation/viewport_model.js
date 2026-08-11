(() => {
    "use strict";

    const root = window.AlmdinaDoorDrawingV2 = window.AlmdinaDoorDrawingV2 || Object.create(null);
    const precision = root.Precision;
    if (!precision) throw new Error("Door Drawing V2 Precision must load before ViewportModel");

    const DEFAULT_PADDING_PX = 72;
    const DEFAULT_MIN_SCALE = 0.02;
    const DEFAULT_MAX_SCALE = 64;
    const DEFAULT_FREE_REFERENCE_WIDTH_MM = 1200;
    const DEFAULT_FREE_REFERENCE_HEIGHT_MM = 900;

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

    function sharedOptions(options = {}) {
        const viewportWidthPx = positive(options.viewportWidthPx, "viewportWidthPx");
        const viewportHeightPx = positive(options.viewportHeightPx, "viewportHeightPx");
        const paddingPx = clamp(
            finite(options.paddingPx == null ? DEFAULT_PADDING_PX : options.paddingPx, "paddingPx"),
            0,
            Math.min(viewportWidthPx, viewportHeightPx) * 0.45
        );
        const minScale = positive(options.minScale == null ? DEFAULT_MIN_SCALE : options.minScale, "minScale");
        const maxScale = positive(options.maxScale == null ? DEFAULT_MAX_SCALE : options.maxScale, "maxScale");
        if (minScale > maxScale) throw new RangeError("minScale cannot exceed maxScale");
        return { viewportWidthPx, viewportHeightPx, paddingPx, minScale, maxScale };
    }

    function normalizedOptions(options = {}) {
        return {
            ...sharedOptions(options),
            worldWidthMm: positive(options.worldWidthMm, "worldWidthMm"),
            worldHeightMm: positive(options.worldHeightMm, "worldHeightMm"),
        };
    }

    function fitScaleForSpan(options, widthMm, heightMm) {
        const availableWidth = Math.max(1, options.viewportWidthPx - options.paddingPx * 2);
        const availableHeight = Math.max(1, options.viewportHeightPx - options.paddingPx * 2);
        return clamp(
            Math.min(availableWidth / widthMm, availableHeight / heightMm),
            options.minScale,
            options.maxScale
        );
    }

    function fitScale(options) {
        return fitScaleForSpan(options, options.worldWidthMm, options.worldHeightMm);
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
            mode: "bounded",
            ...normalized,
            scale,
            fitScale: fittedScale,
            panX,
            panY,
        });
    }

    function createFree(options = {}) {
        const shared = sharedOptions(options);
        const referenceWidthMm = positive(
            options.referenceWidthMm == null ? DEFAULT_FREE_REFERENCE_WIDTH_MM : options.referenceWidthMm,
            "referenceWidthMm"
        );
        const referenceHeightMm = positive(
            options.referenceHeightMm == null ? DEFAULT_FREE_REFERENCE_HEIGHT_MM : options.referenceHeightMm,
            "referenceHeightMm"
        );
        const fittedScale = fitScaleForSpan(shared, referenceWidthMm, referenceHeightMm);
        const requestedScale = options.scale == null ? fittedScale : finite(options.scale, "scale");
        const scale = clamp(requestedScale, shared.minScale, shared.maxScale);
        return Object.freeze({
            mode: "free",
            ...shared,
            referenceWidthMm,
            referenceHeightMm,
            scale,
            fitScale: fittedScale,
            originX: options.originX == null ? shared.viewportWidthPx / 2 : finite(options.originX, "originX"),
            originY: options.originY == null ? shared.viewportHeightPx / 2 : finite(options.originY, "originY"),
        });
    }

    function isFree(state) {
        return Boolean(state && state.mode === "free");
    }

    function worldToScreen(state, point) {
        const x = finite(point && point.x, "point.x");
        const y = finite(point && point.y, "point.y");
        if (isFree(state)) {
            return Object.freeze({
                x: state.originX + x * state.scale,
                y: state.originY - y * state.scale,
            });
        }
        return Object.freeze({
            x: state.panX + x * state.scale,
            y: state.panY + (state.worldHeightMm - y) * state.scale,
        });
    }

    function screenToWorld(state, point) {
        const x = finite(point && point.x, "point.x");
        const y = finite(point && point.y, "point.y");
        if (isFree(state)) {
            return Object.freeze({
                x: precision.serialized((x - state.originX) / state.scale),
                y: precision.serialized((state.originY - y) / state.scale),
            });
        }
        return Object.freeze({
            x: precision.serialized((x - state.panX) / state.scale),
            y: precision.serialized(state.worldHeightMm - (y - state.panY) / state.scale),
        });
    }

    function zoomAt(state, nextScale, screenPoint) {
        const anchor = {
            x: finite(screenPoint && screenPoint.x, "screenPoint.x"),
            y: finite(screenPoint && screenPoint.y, "screenPoint.y"),
        };
        const worldAnchor = screenToWorld(state, anchor);
        const scale = clamp(finite(nextScale, "nextScale"), state.minScale, state.maxScale);
        if (isFree(state)) {
            return createFree({
                ...state,
                scale,
                originX: anchor.x - worldAnchor.x * scale,
                originY: anchor.y + worldAnchor.y * scale,
            });
        }
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
        const dx = finite(deltaX, "deltaX");
        const dy = finite(deltaY, "deltaY");
        if (isFree(state)) {
            return createFree({
                ...state,
                scale: state.scale,
                originX: state.originX + dx,
                originY: state.originY + dy,
            });
        }
        return create({
            ...state,
            scale: state.scale,
            panX: state.panX + dx,
            panY: state.panY + dy,
        });
    }

    function fit(state) {
        if (isFree(state)) {
            return createFree({
                ...state,
                scale: state.fitScale,
                originX: state.viewportWidthPx / 2,
                originY: state.viewportHeightPx / 2,
            });
        }
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
        const center = { x: viewportWidthPx / 2, y: viewportHeightPx / 2 };
        if (isFree(state)) {
            return createFree({
                ...state,
                viewportWidthPx,
                viewportHeightPx,
                scale: state.scale,
                originX: center.x - previousCenter.x * state.scale,
                originY: center.y + previousCenter.y * state.scale,
            });
        }
        const next = create({
            ...state,
            viewportWidthPx,
            viewportHeightPx,
            scale: state.scale,
            panX: 0,
            panY: 0,
        });
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
            left: Math.min(topLeft.x, bottomRight.x),
            right: Math.max(topLeft.x, bottomRight.x),
            top: Math.max(topLeft.y, bottomRight.y),
            bottom: Math.min(topLeft.y, bottomRight.y),
        });
    }

    function zoomPercent(state) {
        return Math.round((state.scale / state.fitScale) * 100);
    }

    function matrix(state) {
        if (isFree(state)) {
            return Object.freeze({
                a: state.scale,
                b: 0,
                c: 0,
                d: -state.scale,
                e: state.originX,
                f: state.originY,
            });
        }
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
        DEFAULT_FREE_REFERENCE_WIDTH_MM,
        DEFAULT_FREE_REFERENCE_HEIGHT_MM,
        create,
        createFree,
        isFree,
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
