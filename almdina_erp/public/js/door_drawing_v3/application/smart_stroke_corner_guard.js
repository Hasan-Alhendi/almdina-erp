(() => {
    "use strict";

    const root = window.AlmdinaDoorDrawingV3 = window.AlmdinaDoorDrawingV3 || Object.create(null);
    const Base = root.SmartStrokeIntelligence;
    const G = root.Geometry;
    const F = root.SmartFreehandPolicy;
    if (!Base || !G || !F) throw new Error("Door Drawing V3 stroke intelligence must load before corner guard");

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

    function interpret(points, options = {}) {
        const deliberateCorner = sharpLineCorner(points, options);
        return deliberateCorner || Base.interpret(points, options);
    }

    root.SmartStrokeIntelligence = Object.freeze({
        ...Base,
        windowTurn,
        strongestCorner,
        sharpLineCorner,
        interpret,
    });
    root.SmartStrokeCornerGuard = Object.freeze({ windowTurn, strongestCorner, sharpLineCorner });
})();
