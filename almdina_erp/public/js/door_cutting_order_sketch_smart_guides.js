(() => {
    "use strict";

    const renderer = window.AlmdinaSketchRenderer;
    const engine = window.AlmdinaSketchEngine;
    if (!renderer || !engine) {
        console.error("Sketch renderer and engine must load before smart guides");
        return;
    }

    const GUIDE_COLOR = "#2490ef";
    const DEFAULT_VERTEX_SNAP_THRESHOLD = 14;

    function clonePoints(points) {
        return engine.sanitizePoints(points).map(point => [point[0], point[1]]);
    }

    function samePoint(first, second, epsilon = 0.001) {
        return Boolean(first && second)
            && Math.abs(Number(first[0]) - Number(second[0])) <= epsilon
            && Math.abs(Number(first[1]) - Number(second[1])) <= epsilon;
    }

    function uniqueClosedPoints(points) {
        const source = clonePoints(points);
        if (source.length > 2 && samePoint(source[0], source[source.length - 1])) {
            return source.slice(0, -1);
        }
        return source;
    }

    function constrainVertexPoint(rawPoint, originalPoint, shiftKey) {
        const raw = [Number(rawPoint[0]), Number(rawPoint[1])];
        const original = [Number(originalPoint[0]), Number(originalPoint[1])];
        if (!shiftKey || !raw.every(Number.isFinite) || !original.every(Number.isFinite)) {
            return raw;
        }
        const dx = raw[0] - original[0];
        const dy = raw[1] - original[1];
        return Math.abs(dx) >= Math.abs(dy)
            ? [raw[0], original[1]]
            : [original[0], raw[1]];
    }

    function nearestCandidate(value, candidates, threshold) {
        let best = null;
        let bestDistance = Number(threshold);
        (candidates || []).forEach(candidate => {
            const numeric = Number(candidate);
            if (!Number.isFinite(numeric)) return;
            const distance = Math.abs(numeric - Number(value));
            if (distance <= bestDistance) {
                best = numeric;
                bestDistance = distance;
            }
        });
        return best;
    }

    function snapTemplateVertex(points, index, rawPoint, options = {}) {
        const source = uniqueClosedPoints(points);
        const pointIndex = Math.max(0, Math.min(source.length - 1, Number(index) || 0));
        const original = source[pointIndex] || [Number(rawPoint[0]), Number(rawPoint[1])];
        const constrained = constrainVertexPoint(rawPoint, options.originalPoint || original, options.shiftKey);
        const width = Number(options.width) > 0 ? Number(options.width) : engine.DEFAULT_CANVAS.width;
        const height = Number(options.height) > 0 ? Number(options.height) : engine.DEFAULT_CANVAS.height;
        const threshold = Math.max(3, Number(options.threshold) || DEFAULT_VERTEX_SNAP_THRESHOLD);
        const otherPoints = source.filter((_, pointIndexValue) => pointIndexValue !== pointIndex);
        const external = engine.sanitizePoints(options.externalAnchors);
        const xCandidates = [0, width / 2, width];
        const yCandidates = [0, height / 2, height];
        [...otherPoints, ...external].forEach(point => {
            xCandidates.push(point[0]);
            yCandidates.push(point[1]);
        });

        const snappedX = nearestCandidate(constrained[0], xCandidates, threshold);
        const snappedY = nearestCandidate(constrained[1], yCandidates, threshold);
        const point = [
            snappedX === null ? constrained[0] : snappedX,
            snappedY === null ? constrained[1] : snappedY,
        ];
        return {
            point,
            guides: {
                x: snappedX,
                y: snappedY,
            },
        };
    }

    function applyClosedVertex(points, index, point) {
        const source = clonePoints(points);
        if (!source.length) return source;
        const closed = source.length > 2 && samePoint(source[0], source[source.length - 1]);
        const uniqueCount = closed ? source.length - 1 : source.length;
        const safeIndex = Math.max(0, Math.min(uniqueCount - 1, Number(index) || 0));
        source[safeIndex] = [Number(point[0]), Number(point[1])];
        if (closed && safeIndex === 0) {
            source[source.length - 1] = source[0].slice();
        }
        return source;
    }

    function inferredAxis(state) {
        const draft = state && state.draft;
        if (!draft || !["line", "dimension"].includes(draft.type)) return "";
        const x1 = Number(draft.x1);
        const y1 = Number(draft.y1);
        const x2 = Number(draft.x2);
        const y2 = Number(draft.y2);
        if (![x1, y1, x2, y2].every(Number.isFinite)) return "";
        if (Math.abs(y1 - y2) <= 0.001 && Math.abs(x1 - x2) > 0.001) return "horizontal";
        if (Math.abs(x1 - x2) <= 0.001 && Math.abs(y1 - y2) > 0.001) return "vertical";
        return "";
    }

    function guideMarkup(state, options = {}) {
        const axis = inferredAxis(state);
        if (!axis) return "";
        const width = Number(options.width) > 0 ? Number(options.width) : engine.DEFAULT_CANVAS.width;
        const height = Number(options.height) > 0 ? Number(options.height) : engine.DEFAULT_CANVAS.height;
        const draft = state.draft;
        if (axis === "horizontal") {
            const y = Number(draft.y1);
            return `<g class="dco-smart-axis-guide" pointer-events="none">
                <line x1="0" y1="${y}" x2="${width}" y2="${y}" stroke="${GUIDE_COLOR}" stroke-width="1.5" stroke-dasharray="7 7" opacity=".72" vector-effect="non-scaling-stroke"/>
                <rect x="${Math.max(8, Math.min(width - 80, Number(draft.x2) + 12))}" y="${Math.max(8, y - 28)}" width="64" height="20" rx="7" fill="${GUIDE_COLOR}" opacity=".92"/>
                <text x="${Math.max(40, Math.min(width - 48, Number(draft.x2) + 44))}" y="${Math.max(22, y - 14)}" text-anchor="middle" font-family="Tahoma,Arial" font-size="11" font-weight="700" fill="#fff">أفقي</text>
            </g>`;
        }
        const x = Number(draft.x1);
        return `<g class="dco-smart-axis-guide" pointer-events="none">
            <line x1="${x}" y1="0" x2="${x}" y2="${height}" stroke="${GUIDE_COLOR}" stroke-width="1.5" stroke-dasharray="7 7" opacity=".72" vector-effect="non-scaling-stroke"/>
            <rect x="${Math.max(8, Math.min(width - 72, x + 12))}" y="${Math.max(8, Math.min(height - 28, Number(draft.y2) + 12))}" width="56" height="20" rx="7" fill="${GUIDE_COLOR}" opacity=".92"/>
            <text x="${Math.max(36, Math.min(width - 44, x + 40))}" y="${Math.max(22, Math.min(height - 14, Number(draft.y2) + 26))}" text-anchor="middle" font-family="Tahoma,Arial" font-size="11" font-weight="700" fill="#fff">عمودي</text>
        </g>`;
    }

    function injectBeforeCursor(markup, guides) {
        if (!guides) return markup;
        const marker = '<g class="dco-sketch-cursor-preview"';
        const index = String(markup || "").indexOf(marker);
        if (index < 0) return `${markup || ""}${guides}`;
        return `${markup.slice(0, index)}${guides}${markup.slice(index)}`;
    }

    const baseCanvasView = renderer.canvasView;
    window.AlmdinaSketchRenderer = Object.freeze({
        ...renderer,
        canvasView(state, options = {}) {
            const result = baseCanvasView(state, options);
            return {
                ...result,
                markup: injectBeforeCursor(result.markup, guideMarkup(state, options)),
            };
        },
        smartGuideMarkup: guideMarkup,
        inferredAxis,
    });

    window.AlmdinaSketchSmartGuides = Object.freeze({
        GUIDE_COLOR,
        DEFAULT_VERTEX_SNAP_THRESHOLD,
        samePoint,
        uniqueClosedPoints,
        constrainVertexPoint,
        nearestCandidate,
        snapTemplateVertex,
        applyClosedVertex,
    });
})();