(() => {
    "use strict";

    const sketchEngine = window.AlmdinaSketchEngine;
    if (!sketchEngine) {
        console.error("AlmdinaSketchEngine must load before sketch interaction");
        return;
    }

    const DRAWING_TOOLS = Object.freeze([
        "pen",
        "line",
        "rectangle",
        "ellipse",
        "dimension",
    ]);

    function clone(value) {
        return value == null ? value : JSON.parse(JSON.stringify(value));
    }

    function pointOf(value) {
        const x = Number(value && value.x);
        const y = Number(value && value.y);
        return Number.isFinite(x) && Number.isFinite(y) ? { x, y } : null;
    }

    function beginDraft(options = {}) {
        const tool = String(options.tool || "");
        let start = pointOf(options.point);
        if (!DRAWING_TOOLS.includes(tool) || !start) {
            return { draft: null, start, snapPoint: null };
        }

        let snapPoint = null;
        if (["pen", "line", "dimension"].includes(tool)) {
            const anchor = sketchEngine.nearestAnchor(
                [start.x, start.y],
                options.elements,
                options.snapRadius
            );
            if (anchor) {
                start = { x: anchor[0], y: anchor[1] };
                snapPoint = { ...start };
            }
        }

        const common = {
            id: String(options.id || ""),
            type: tool,
            color: options.color || "#172033",
        };
        let draft = null;
        if (tool === "pen") {
            draft = { ...common, points: [[start.x, start.y]] };
        } else if (tool === "line" || tool === "dimension") {
            draft = {
                ...common,
                x1: start.x,
                y1: start.y,
                x2: start.x,
                y2: start.y,
            };
        } else if (tool === "rectangle") {
            draft = {
                ...common,
                x: start.x,
                y: start.y,
                width: 0,
                height: 0,
            };
        } else if (tool === "ellipse") {
            draft = {
                ...common,
                cx: start.x,
                cy: start.y,
                rx: 0,
                ry: 0,
            };
        }
        return { draft, start, snapPoint };
    }

    function appendPenPoints(draft, points, minimumDistance = 1.25) {
        if (!draft || draft.type !== "pen") return clone(draft);
        const result = clone(draft);
        const safeDistance = Math.max(0, Number(minimumDistance) || 0);
        sketchEngine.sanitizePoints(points).forEach(point => {
            const previous = result.points[result.points.length - 1];
            if (
                !previous
                || sketchEngine.pointDistance(previous, point) >= safeDistance
            ) {
                result.points.push(point);
            }
        });
        return result;
    }

    function penSnapPoint(draft, elements, radius = sketchEngine.DEFAULT_SNAP_RADIUS) {
        const points = sketchEngine.sanitizePoints(draft && draft.points);
        if (!points.length) return null;
        const last = points[points.length - 1];
        const closeStart = points.length > 8
            && sketchEngine.polylineLength(points) >= 70
            && sketchEngine.pointDistance(last, points[0]) <= Number(radius) * 1.35
            ? points[0]
            : null;
        const anchor = closeStart || sketchEngine.nearestAnchor(last, elements, radius);
        return anchor ? { x: anchor[0], y: anchor[1] } : null;
    }

    function updateDraft(options = {}) {
        if (!options.draft) return { draft: null, snapPoint: null };
        const start = pointOf(options.start);
        const point = pointOf(options.point);
        let draft = clone(options.draft);

        if (draft.type === "pen") {
            draft = appendPenPoints(draft, options.penPoints, 1.25);
            if (options.finalPenPoint) {
                draft = appendPenPoints(draft, [options.finalPenPoint], 0.35);
            }
            return {
                draft,
                snapPoint: penSnapPoint(
                    draft,
                    options.elements,
                    options.snapRadius
                ),
            };
        }
        if (!start || !point) return { draft, snapPoint: null };

        if (draft.type === "line" || draft.type === "dimension") {
            const aligned = sketchEngine.snapLineEnd(
                start,
                point,
                Boolean(options.forceAngle)
            );
            const anchor = sketchEngine.nearestAnchor(
                [aligned.x, aligned.y],
                options.elements,
                options.snapRadius
            );
            const endpoint = anchor
                ? { x: anchor[0], y: anchor[1] }
                : aligned;
            draft.x2 = endpoint.x;
            draft.y2 = endpoint.y;
            return {
                draft,
                snapPoint: anchor ? endpoint : null,
            };
        }
        if (draft.type === "rectangle") {
            draft.x = Math.min(start.x, point.x);
            draft.y = Math.min(start.y, point.y);
            draft.width = Math.abs(point.x - start.x);
            draft.height = Math.abs(point.y - start.y);
        } else if (draft.type === "ellipse") {
            draft.cx = (start.x + point.x) / 2;
            draft.cy = (start.y + point.y) / 2;
            draft.rx = Math.abs(point.x - start.x) / 2;
            draft.ry = Math.abs(point.y - start.y) / 2;
        }
        return { draft, snapPoint: null };
    }

    function tooSmall(element) {
        if (!element) return true;
        if (element.type === "rectangle") {
            const width = Number(element.width);
            const height = Number(element.height);
            return (
                !Number.isFinite(width)
                || !Number.isFinite(height)
                || width < 4
                || height < 4
            );
        }
        if (element.type === "ellipse") {
            const rx = Number(element.rx);
            const ry = Number(element.ry);
            return (
                !Number.isFinite(rx)
                || !Number.isFinite(ry)
                || rx < 2
                || ry < 2
            );
        }
        const length = Math.hypot(
            Number(element.x2) - Number(element.x1),
            Number(element.y2) - Number(element.y1)
        );
        return !Number.isFinite(length) || length < 4;
    }

    function finalizeDraft(options = {}) {
        if (options.cancelled || !options.draft) {
            return {
                accepted: false,
                element: null,
                needsText: false,
                reason: options.cancelled ? "cancelled" : "missing",
            };
        }
        const element = clone(options.draft);
        if (element.type === "pen") {
            element.points = sketchEngine.snapPenEndpoints(
                sketchEngine.normalizePenStroke(element.points),
                options.elements,
                options.snapRadius
            );
            return {
                accepted: element.points.length >= 2,
                element,
                needsText: false,
                reason: element.points.length >= 2 ? "" : "too-small",
            };
        }
        if (!DRAWING_TOOLS.includes(element.type) || tooSmall(element)) {
            return {
                accepted: false,
                element,
                needsText: false,
                reason: "too-small",
            };
        }
        return {
            accepted: true,
            element,
            needsText: element.type === "dimension",
            reason: "",
        };
    }

    window.AlmdinaSketchInteraction = Object.freeze({
        DRAWING_TOOLS,
        beginDraft,
        appendPenPoints,
        penSnapPoint,
        updateDraft,
        tooSmall,
        finalizeDraft,
    });
})();
