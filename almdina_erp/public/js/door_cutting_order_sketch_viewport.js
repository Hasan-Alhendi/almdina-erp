(() => {
    "use strict";

    const sketchEngine = window.AlmdinaSketchEngine;
    if (!sketchEngine) {
        console.error("AlmdinaSketchEngine must load before sketch viewport");
        return;
    }

    const MIN_ZOOM = 1;
    const MAX_ZOOM = 4;
    const ZOOM_STEP = 1.25;

    function canvasOf(options = {}) {
        const source = options.canvas || sketchEngine.DEFAULT_CANVAS;
        const width = Number(source.width);
        const height = Number(source.height);
        return {
            width: Number.isFinite(width) && width > 0
                ? width
                : sketchEngine.DEFAULT_CANVAS.width,
            height: Number.isFinite(height) && height > 0
                ? height
                : sketchEngine.DEFAULT_CANVAS.height,
        };
    }

    function zoomLimits(options = {}) {
        const minimum = Number(options.minZoom);
        const maximum = Number(options.maxZoom);
        const minZoom = Number.isFinite(minimum) && minimum > 0
            ? minimum
            : MIN_ZOOM;
        const maxZoom = Number.isFinite(maximum) && maximum >= minZoom
            ? maximum
            : Math.max(minZoom, MAX_ZOOM);
        return { minZoom, maxZoom };
    }

    function clampPoint(point, options = {}) {
        const canvas = canvasOf(options);
        const x = Number(point && point.x);
        const y = Number(point && point.y);
        return {
            x: Math.max(0, Math.min(canvas.width, Number.isFinite(x) ? x : 0)),
            y: Math.max(0, Math.min(canvas.height, Number.isFinite(y) ? y : 0)),
        };
    }

    function createState(options = {}) {
        const canvas = canvasOf(options);
        const { minZoom } = zoomLimits(options);
        return {
            zoom: minZoom,
            viewBox: {
                x: 0,
                y: 0,
                width: canvas.width,
                height: canvas.height,
            },
        };
    }

    function mapClientPoint(clientPoint, bounds, viewBox, options = {}) {
        const canvas = canvasOf(options);
        const { maxZoom } = zoomLimits(options);
        const activeView = sketchEngine.clampViewBox(
            viewBox || createState({ ...options, canvas }).viewBox,
            { width: canvas.width, height: canvas.height, maxZoom }
        );
        const left = Number(bounds && bounds.left) || 0;
        const top = Number(bounds && bounds.top) || 0;
        const width = Math.max(1, Number(bounds && bounds.width) || 0);
        const height = Math.max(1, Number(bounds && bounds.height) || 0);
        return clampPoint({
            x: activeView.x
                + (Number(clientPoint && clientPoint.x) - left) * activeView.width / width,
            y: activeView.y
                + (Number(clientPoint && clientPoint.y) - top) * activeView.height / height,
        }, { canvas });
    }

    function zoomState(state, requestedZoom, anchor, options = {}) {
        const canvas = canvasOf(options);
        const { minZoom, maxZoom } = zoomLimits(options);
        const current = sketchEngine.clampViewBox(
            state && state.viewBox || createState({ ...options, canvas }).viewBox,
            { width: canvas.width, height: canvas.height, maxZoom }
        );
        const requested = Number(requestedZoom);
        const nextZoom = Math.max(
            minZoom,
            Math.min(maxZoom, Number.isFinite(requested) ? requested : minZoom)
        );
        const focus = clampPoint(anchor || {
            x: current.x + current.width / 2,
            y: current.y + current.height / 2,
        }, { canvas });
        const ratioX = current.width ? (focus.x - current.x) / current.width : 0.5;
        const ratioY = current.height ? (focus.y - current.y) / current.height : 0.5;
        const width = canvas.width / nextZoom;
        const height = canvas.height / nextZoom;
        return {
            zoom: nextZoom,
            viewBox: sketchEngine.clampViewBox({
                x: focus.x - width * ratioX,
                y: focus.y - height * ratioY,
                width,
                height,
            }, { width: canvas.width, height: canvas.height, maxZoom }),
        };
    }

    function resetState(options = {}) {
        return createState(options);
    }

    function zoomControls(zoom, options = {}) {
        const { minZoom, maxZoom } = zoomLimits(options);
        const current = Math.max(
            minZoom,
            Math.min(maxZoom, Number(zoom) || minZoom)
        );
        return {
            percentage: Math.round(current * 100),
            canZoomIn: current < maxZoom - 0.001,
            canZoomOut: current > minZoom + 0.001,
        };
    }

    function beginPan(clientPoint, viewBox) {
        return {
            clientX: Number(clientPoint && clientPoint.x) || 0,
            clientY: Number(clientPoint && clientPoint.y) || 0,
            viewBox: {
                x: Number(viewBox && viewBox.x) || 0,
                y: Number(viewBox && viewBox.y) || 0,
                width: Number(viewBox && viewBox.width) || 0,
                height: Number(viewBox && viewBox.height) || 0,
            },
        };
    }

    function panState(pan, clientPoint, bounds, options = {}) {
        if (!pan || !pan.viewBox) return null;
        const canvas = canvasOf(options);
        const { maxZoom } = zoomLimits(options);
        const width = Math.max(1, Number(bounds && bounds.width) || 0);
        const height = Math.max(1, Number(bounds && bounds.height) || 0);
        const dx = (Number(clientPoint && clientPoint.x) - Number(pan.clientX))
            * Number(pan.viewBox.width) / width;
        const dy = (Number(clientPoint && clientPoint.y) - Number(pan.clientY))
            * Number(pan.viewBox.height) / height;
        return sketchEngine.clampViewBox({
            ...pan.viewBox,
            x: Number(pan.viewBox.x) - dx,
            y: Number(pan.viewBox.y) - dy,
        }, {
            width: canvas.width,
            height: canvas.height,
            maxZoom,
        });
    }

    window.AlmdinaSketchViewport = Object.freeze({
        MIN_ZOOM,
        MAX_ZOOM,
        ZOOM_STEP,
        clampPoint,
        createState,
        mapClientPoint,
        zoomState,
        resetState,
        zoomControls,
        beginPan,
        panState,
    });
})();
