(() => {
    "use strict";

    const root = window.AlmdinaDoorDrawingV3 = window.AlmdinaDoorDrawingV3 || Object.create(null);
    const Base = root.SmartStrokeIntelligence;
    const G = root.Geometry;
    const F = root.SmartFreehandPolicy;
    if (!Base || !G || !F) throw new Error("Door Drawing V3 stroke intelligence must load before fidelity guard");

    const PRIMITIVE_CONFIDENCE = Object.freeze({
        line: 0.9,
        rectangle: 0.9,
        circle: 0.92,
        arc: 0.94,
    });

    function windowTurn(points, index, radius = 2) {
        const left = Math.max(0, index - radius);
        const right = Math.min(points.length - 1, index + radius);
        if (left === index || right === index) return 0;
        const incoming = G.angleDeg(points[left], points[index]);
        const outgoing = G.angleDeg(points[index], points[right]);
        return Math.abs(G.normalizeAngle(outgoing - incoming));
    }

    function strongestCorner(points, options = {}) {
        const input = F.dedupe(points);
        if (input.length < 7) return null;
        const thresholdDeg = Math.max(25, Number(options.cornerThresholdDeg) || 48);
        let best = null;
        for (let index = 2; index <= input.length - 3; index += 1) {
            const turnDeg = windowTurn(input, index, 2);
            if (turnDeg < thresholdDeg) continue;
            if (!best || turnDeg > best.turnDeg) best = { index, turnDeg };
        }
        return best ? Object.freeze(best) : null;
    }

    function lineDescriptor(points, startIndex, endIndex, options = {}) {
        const range = points.slice(startIndex, endIndex + 1);
        if (range.length < 3) return null;
        const quality = F.lineQuality(range);
        const straightToleranceMm = Math.max(G.EPSILON_MM, Number(options.straightToleranceMm) || F.DEFAULTS.straightToleranceMm);
        const straightRatio = Number(options.straightRatio) || F.DEFAULTS.straightRatio;
        const lengthMm = G.distance(range[0], range[range.length - 1]);
        const minimumSegmentMm = Math.max(G.EPSILON_MM, Number(options.minimumSegmentMm) || 12);
        if (!quality.eligible || quality.maxDeviationMm > straightToleranceMm || quality.ratio > straightRatio || lengthMm < minimumSegmentMm) return null;
        return Object.freeze({
            type: "line",
            startIndex,
            endIndex,
            start: range[0],
            end: range[range.length - 1],
            lengthMm: G.roundMm(lengthMm),
        });
    }

    // Kept as an explicit helper for future assisted commands, but deliberately not
    // applied automatically by the freehand pen. A hand-drawn L/S/flower must not be
    // silently rebuilt from straight/arc primitives.
    function sharpLineCorner(points, options = {}) {
        if (options.closed) return null;
        const input = F.dedupe(points);
        const corner = strongestCorner(input, options);
        if (!corner) return null;
        const first = lineDescriptor(input, 0, corner.index, options);
        const second = lineDescriptor(input, corner.index, input.length - 1, options);
        if (!first || !second) return null;
        return Object.freeze({
            type: "compound",
            segments: Object.freeze([first, second]),
            closed: false,
            confidence: Math.min(0.99, 0.82 + corner.turnDeg / 900),
            cornerIndex: corner.index,
            cornerTurnDeg: G.roundMm(corner.turnDeg),
        });
    }

    function faithfulPoints(points, closed = false) {
        let output = F.dedupe(points);
        if (closed && output.length > 2 && G.distance(output[0], output[output.length - 1]) <= G.EPSILON_MM) {
            output = output.slice(0, -1);
        }
        return output.map(point => G.point(point.x, point.y));
    }

    function faithfulPath(points, options = {}) {
        const raw = F.dedupe(points);
        const closed = Boolean(options.closed);
        return Object.freeze({
            type: "path",
            points: Object.freeze(faithfulPoints(raw, closed)),
            closed,
            confidence: 1,
            rawPoints: Object.freeze(raw.map(point => G.point(point.x, point.y))),
            fidelity: true,
        });
    }

    function primitiveIsUnambiguous(result, points, options = {}) {
        if (!result || !Object.prototype.hasOwnProperty.call(PRIMITIVE_CONFIDENCE, result.type)) return false;
        const confidence = Number(result.confidence) || 0;
        if (confidence + 1e-9 < PRIMITIVE_CONFIDENCE[result.type]) return false;

        if (result.type === "line") {
            const quality = F.lineQuality(F.dedupe(points));
            if (!quality.eligible) return false;
            const tolerance = Math.max(G.EPSILON_MM, Number(options.straightToleranceMm) || F.DEFAULTS.straightToleranceMm);
            const ratioLimit = Math.max(1.005, Math.min(1.025, Number(options.straightRatio) || F.DEFAULTS.straightRatio));
            return quality.maxDeviationMm <= tolerance * 0.5 && quality.ratio <= ratioLimit;
        }
        return true;
    }

    // Preview fidelity matters as much as saved geometry. SmartPen uses this method
    // for its live stroke, so return the real sampled point rather than a lagging
    // low-pass approximation. Sampling already removes sub-pixel jitter.
    function pushStabilized(state, rawPoint) {
        const raw = G.point(rawPoint && rawPoint.x, rawPoint && rawPoint.y);
        if (state) state.point = raw;
        return raw;
    }

    function stabilizeSeries(points) {
        return faithfulPoints(points, false);
    }

    function interpret(points, options = {}) {
        const raw = F.dedupe(points);
        if (raw.length < 2) return Object.freeze({ type: "none", points: raw, confidence: 0 });

        // Whole-stroke recognition only. This keeps useful intelligence for an
        // unmistakable line/circle/arc/rectangle without segmenting an arbitrary
        // freehand sketch into primitives or changing its silhouette.
        const recognized = F.recognize(raw, options);
        if (primitiveIsUnambiguous(recognized, raw, options)) return recognized;
        return faithfulPath(raw, options);
    }

    root.SmartStrokeIntelligence = Object.freeze({
        ...Base,
        pushStabilized,
        stabilizeSeries,
        windowTurn,
        strongestCorner,
        sharpLineCorner,
        faithfulPoints,
        faithfulPath,
        primitiveIsUnambiguous,
        interpret,
    });
    root.SmartStrokeCornerGuard = Object.freeze({
        PRIMITIVE_CONFIDENCE,
        windowTurn,
        strongestCorner,
        sharpLineCorner,
        faithfulPoints,
        faithfulPath,
        primitiveIsUnambiguous,
    });
})();
