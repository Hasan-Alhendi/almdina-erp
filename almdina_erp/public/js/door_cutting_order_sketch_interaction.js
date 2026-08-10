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
    const SMART_ENDPOINT_SNAP_RADIUS = 24;
    const SOFT_AXIS_SNAP_DEGREES = 7;
    const FORCED_AXIS_ANCHOR_TOLERANCE = 4;

    function clone(value) {
        return value == null ? value : JSON.parse(JSON.stringify(value));
    }

    function pointOf(value) {
        const x = Number(value && value.x);
        const y = Number(value && value.y);
        return Number.isFinite(x) && Number.isFinite(y) ? { x, y } : null;
    }

    function effectiveSnapRadius(radius) {
        const requested = Number(radius);
        return Math.max(
            SMART_ENDPOINT_SNAP_RADIUS,
            Number.isFinite(requested) && requested > 0 ? requested : 0
        );
    }

    function nearestAnchor(point, elements, radius) {
        const anchor = sketchEngine.nearestAnchor(
            [Number(point.x), Number(point.y)],
            elements,
            effectiveSnapRadius(radius)
        );
        return anchor ? { x: anchor[0], y: anchor[1] } : null;
    }

    function axisConstrain(start, end) {
        const dx = Number(end.x) - Number(start.x);
        const dy = Number(end.y) - Number(start.y);
        if (Math.abs(dx) >= Math.abs(dy)) {
            return {
                point: { x: Number(end.x), y: Number(start.y) },
                axis: "horizontal",
            };
        }
        return {
            point: { x: Number(start.x), y: Number(end.y) },
            axis: "vertical",
        };
    }

    function softAxisSnap(start, end) {
        const dx = Number(end.x) - Number(start.x);
        const dy = Number(end.y) - Number(start.y);
        const length = Math.hypot(dx, dy);
        if (length < 0.001) return { point: { ...end }, axis: "" };

        const angle = Math.atan2(dy, dx);
        const interval = Math.PI / 2;
        const snappedAngle = Math.round(angle / interval) * interval;
        const difference = Math.abs(Math.atan2(
            Math.sin(angle - snappedAngle),
            Math.cos(angle - snappedAngle)
        ));
        if (difference > SOFT_AXIS_SNAP_DEGREES * Math.PI / 180) {
            return { point: { ...end }, axis: "" };
        }

        const horizontal = Math.abs(Math.cos(snappedAngle)) >= Math.abs(Math.sin(snappedAngle));
        return horizontal
            ? {
                point: { x: Number(end.x), y: Number(start.y) },
                axis: "horizontal",
            }
            : {
                point: { x: Number(start.x), y: Number(end.y) },
                axis: "vertical",
            };
    }

    function anchorPreservesForcedAxis(start, anchor, axis) {
        if (axis === "horizontal") {
            return Math.abs(Number(anchor.y) - Number(start.y)) <= FORCED_AXIS_ANCHOR_TOLERANCE;
        }
        if (axis === "vertical") {
            return Math.abs(Number(anchor.x) - Number(start.x)) <= FORCED_AXIS_ANCHOR_TOLERANCE;
        }
        return true;
    }

    function projectAnchorToAxis(start, anchor, axis) {
        if (axis === "horizontal") return { x: Number(anchor.x), y: Number(start.y) };
        if (axis === "vertical") return { x: Number(start.x), y: Number(anchor.y) };
        return { x: Number(anchor.x), y: Number(anchor.y) };
    }

    function resolveLineEndpoint(start, point, elements, forceAxis, radius) {
        const alignment = forceAxis
            ? axisConstrain(start, point)
            : softAxisSnap(start, point);
        const anchor = nearestAnchor(alignment.point, elements, radius);
        if (!anchor) {
            return {
                endpoint: alignment.point,
                snapPoint: null,
                axis: alignment.axis,
            };
        }

        if (forceAxis && !anchorPreservesForcedAxis(start, anchor, alignment.axis)) {
            return {
                endpoint: alignment.point,
                snapPoint: null,
                axis: alignment.axis,
            };
        }

        const endpoint = forceAxis
            ? projectAnchorToAxis(start, anchor, alignment.axis)
            : anchor;
        return {
            endpoint,
            snapPoint: endpoint,
            axis: alignment.axis,
        };
    }

    function beginDraft(options = {}) {
        const tool = String(options.tool || "");
        let start = pointOf(options.point);
        if (!DRAWING_TOOLS.includes(tool) || !start) {
            return { draft: null, start, snapPoint: null };
        }

        let snapPoint = null;
        if (["pen", "line", "dimension"].includes(tool)) {
            const anchor = nearestAnchor(start, options.elements, options.snapRadius);
            if (anchor) {
                start = anchor;
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
        const smartRadius = effectiveSnapRadius(radius);
        const last = points[points.length - 1];
        const closeStart = points.length > 8
            && sketchEngine.polylineLength(points) >= 70
            && sketchEngine.pointDistance(last, points[0]) <= smartRadius * 1.35
            ? points[0]
            : null;
        const anchor = closeStart || sketchEngine.nearestAnchor(last, elements, smartRadius);
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
            const resolved = resolveLineEndpoint(
                start,
                point,
                options.elements,
                Boolean(options.forceAngle),
                options.snapRadius
            );
            draft.x2 = resolved.endpoint.x;
            draft.y2 = resolved.endpoint.y;
            return {
                draft,
                snapPoint: resolved.snapPoint,
                axis: resolved.axis,
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
                effectiveSnapRadius(options.snapRadius)
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
        SMART_ENDPOINT_SNAP_RADIUS,
        SOFT_AXIS_SNAP_DEGREES,
        effectiveSnapRadius,
        axisConstrain,
        softAxisSnap,
        resolveLineEndpoint,
        beginDraft,
        appendPenPoints,
        penSnapPoint,
        updateDraft,
        tooSmall,
        finalizeDraft,
    });
})();
