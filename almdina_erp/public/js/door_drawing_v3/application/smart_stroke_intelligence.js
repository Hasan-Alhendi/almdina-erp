(() => {
    "use strict";

    const root = window.AlmdinaDoorDrawingV3 = window.AlmdinaDoorDrawingV3 || Object.create(null);
    const G = root.Geometry;
    const F = root.SmartFreehandPolicy;
    if (!G || !F) throw new Error("Door Drawing V3 freehand policy must load before smart stroke intelligence");

    const STABILIZER_PROFILES = Object.freeze({
        mouse: Object.freeze({ responsiveness: 0.34, motionBoost: 0.38 }),
        pen: Object.freeze({ responsiveness: 0.68, motionBoost: 0.24 }),
        touch: Object.freeze({ responsiveness: 0.28, motionBoost: 0.34 }),
    });

    function profile(pointerType) {
        const key = String(pointerType || "mouse").toLowerCase();
        return STABILIZER_PROFILES[key] || STABILIZER_PROFILES.mouse;
    }

    function createStabilizer(pointerType, startPoint, options = {}) {
        const selected = profile(pointerType);
        return {
            pointerType: String(pointerType || "mouse").toLowerCase(),
            point: G.point(startPoint && startPoint.x, startPoint && startPoint.y),
            responsiveness: Math.max(0.05, Math.min(1, Number(options.responsiveness) || selected.responsiveness)),
            motionBoost: Math.max(0, Math.min(1, Number(options.motionBoost) || selected.motionBoost)),
        };
    }

    function pushStabilized(state, rawPoint, options = {}) {
        if (!state) return G.point(rawPoint && rawPoint.x, rawPoint && rawPoint.y);
        const raw = G.point(rawPoint && rawPoint.x, rawPoint && rawPoint.y);
        const previous = state.point || raw;
        const motionScaleMm = Math.max(G.EPSILON_MM, Number(options.motionScaleMm) || 8);
        const movement = G.distance(previous, raw);
        const motionFactor = Math.min(1, movement / motionScaleMm);
        const alpha = Math.max(0.05, Math.min(0.96, state.responsiveness + state.motionBoost * motionFactor));
        state.point = G.point(
            previous.x + (raw.x - previous.x) * alpha,
            previous.y + (raw.y - previous.y) * alpha
        );
        return state.point;
    }

    function stabilizeSeries(points, pointerType = "mouse", options = {}) {
        const input = F.dedupe(points);
        if (!input.length) return [];
        const state = createStabilizer(pointerType, input[0], options);
        const output = [input[0]];
        for (let index = 1; index < input.length; index += 1) {
            output.push(pushStabilized(state, input[index], options));
        }
        output[0] = input[0];
        output[output.length - 1] = input[input.length - 1];
        return F.dedupe(output);
    }

    function midpointByLength(points) {
        if (!Array.isArray(points) || !points.length) return G.point(0, 0);
        if (points.length === 1) return G.point(points[0].x, points[0].y);
        const total = F.polylineLength(points);
        if (total <= G.EPSILON_MM) return G.point(points[Math.floor(points.length / 2)].x, points[Math.floor(points.length / 2)].y);
        const target = total / 2;
        let travelled = 0;
        for (let index = 1; index < points.length; index += 1) {
            const segment = G.distance(points[index - 1], points[index]);
            if (travelled + segment >= target && segment > G.EPSILON_MM) {
                const ratio = (target - travelled) / segment;
                return G.point(
                    points[index - 1].x + (points[index].x - points[index - 1].x) * ratio,
                    points[index - 1].y + (points[index].y - points[index - 1].y) * ratio
                );
            }
            travelled += segment;
        }
        return G.point(points[points.length - 1].x, points[points.length - 1].y);
    }

    function endpointSweep(center, start, end, referenceSweep) {
        const startAngle = G.angleDeg(center, start);
        const endAngle = G.angleDeg(center, end);
        const positive = G.positiveAngle(endAngle - startAngle);
        let sweep = Number(referenceSweep) < 0 ? (positive === 0 ? -359.999 : positive - 360) : (positive === 0 ? 359.999 : positive);
        if (Math.abs(sweep) > G.MAX_ARC_SWEEP_DEG) sweep = Math.sign(sweep || 1) * G.MAX_ARC_SWEEP_DEG;
        return G.roundMm(sweep);
    }

    function arcThroughEndpoints(points, options = {}) {
        const input = F.dedupe(points);
        if (input.length < 5) return null;
        const start = input[0];
        const end = input[input.length - 1];
        if (G.distance(start, end) < G.EPSILON_MM) return null;
        const mid = midpointByLength(input);
        const circle = F.circumcircle(start, mid, end);
        if (!circle) return null;
        const residualMm = F.radialResidual(input, circle);
        const straightToleranceMm = Math.max(G.EPSILON_MM, Number(options.straightToleranceMm) || F.DEFAULTS.straightToleranceMm);
        const residualRatio = Number(options.arcResidualRatio) || F.DEFAULTS.arcResidualRatio;
        const residualLimit = Math.max(straightToleranceMm, circle.radiusMm * residualRatio);
        if (residualMm > residualLimit) return null;
        const sweepInfo = F.unwrapSweep(input, circle.center);
        const absSweep = Math.abs(sweepInfo.sweepDeg);
        const minimumArcSweepDeg = Number(options.minimumArcSweepDeg) || F.DEFAULTS.minimumArcSweepDeg;
        const maximumArcSweepDeg = Number(options.maximumArcSweepDeg) || F.DEFAULTS.maximumArcSweepDeg;
        if (absSweep < minimumArcSweepDeg || absSweep > maximumArcSweepDeg || sweepInfo.consistency < 0.82) return null;
        const sweepAngleDeg = endpointSweep(circle.center, start, end, sweepInfo.sweepDeg);
        if (Math.abs(sweepAngleDeg) < minimumArcSweepDeg) return null;
        return Object.freeze({
            type: "arc",
            center: circle.center,
            radiusMm: circle.radiusMm,
            startAngleDeg: G.angleDeg(circle.center, start),
            sweepAngleDeg,
            start,
            end,
            residualMm: G.roundMm(residualMm),
        });
    }

    function lineRun(points, startIndex, options = {}) {
        const input = points || [];
        const minimumSegmentMm = Math.max(G.EPSILON_MM, Number(options.minimumSegmentMm) || 12);
        const straightToleranceMm = Math.max(G.EPSILON_MM, Number(options.straightToleranceMm) || F.DEFAULTS.straightToleranceMm);
        const straightRatio = Number(options.straightRatio) || F.DEFAULTS.straightRatio;
        let best = null;
        let invalid = 0;
        for (let endIndex = startIndex + 2; endIndex < input.length; endIndex += 1) {
            const range = input.slice(startIndex, endIndex + 1);
            const quality = F.lineQuality(range);
            const lengthMm = G.distance(range[0], range[range.length - 1]);
            if (quality.eligible && quality.maxDeviationMm <= straightToleranceMm && quality.ratio <= straightRatio && lengthMm >= minimumSegmentMm) {
                best = { type: "line", startIndex, endIndex, start: range[0], end: range[range.length - 1], lengthMm };
                invalid = 0;
            } else if (best) {
                invalid += 1;
                if (invalid >= 3) break;
            }
        }
        return best;
    }

    function arcRun(points, startIndex, options = {}) {
        const input = points || [];
        const minimumSegmentMm = Math.max(G.EPSILON_MM, Number(options.minimumSegmentMm) || 12);
        let best = null;
        let invalid = 0;
        for (let endIndex = startIndex + 4; endIndex < input.length; endIndex += 1) {
            const range = input.slice(startIndex, endIndex + 1);
            const arc = arcThroughEndpoints(range, options);
            const lengthMm = F.polylineLength(range);
            if (arc && lengthMm >= minimumSegmentMm) {
                best = { ...arc, startIndex, endIndex, lengthMm };
                invalid = 0;
            } else if (best) {
                invalid += 1;
                if (invalid >= 4) break;
            }
        }
        return best;
    }

    function bestRun(points, startIndex, options = {}) {
        const line = lineRun(points, startIndex, options);
        const arc = arcRun(points, startIndex, options);
        if (!line) return arc;
        if (!arc) return line;
        if (arc.endIndex >= line.endIndex + 2) return arc;
        if (line.endIndex >= arc.endIndex) return line;
        return arc.lengthMm > line.lengthMm * 1.12 ? arc : line;
    }

    function nextRunStart(points, fromIndex, options = {}) {
        for (let index = fromIndex; index < points.length - 2; index += 1) {
            if (bestRun(points, index, options)) return index;
        }
        return -1;
    }

    function pathDescriptor(points, startIndex, endIndex, options = {}) {
        const range = points.slice(startIndex, endIndex + 1);
        if (range.length < 2) return null;
        const cleaned = F.cleanPath(range, {
            ...options,
            closed: false,
            preserveEndpoints: true,
            orthogonalize: true,
        });
        if (cleaned.length < 2) return null;
        return Object.freeze({ type: "path", points: cleaned, closed: false, startIndex, endIndex, start: cleaned[0], end: cleaned[cleaned.length - 1] });
    }

    function mergeAdjacentPaths(segments) {
        const output = [];
        for (const segment of segments) {
            const previous = output[output.length - 1];
            if (previous && previous.type === "path" && segment.type === "path") {
                output[output.length - 1] = Object.freeze({
                    type: "path",
                    points: F.dedupe([...previous.points, ...segment.points]),
                    closed: false,
                    startIndex: previous.startIndex,
                    endIndex: segment.endIndex,
                    start: previous.start,
                    end: segment.end,
                });
            } else output.push(segment);
        }
        return output;
    }

    function recognizeMixed(points, options = {}) {
        const input = F.dedupe(points);
        if (input.length < 5 || options.closed) return null;
        const minimumSegmentMm = Math.max(G.EPSILON_MM, Number(options.minimumSegmentMm) || 12);
        const segments = [];
        let index = 0;
        while (index < input.length - 1) {
            const run = bestRun(input, index, { ...options, minimumSegmentMm });
            if (run) {
                segments.push(Object.freeze(run));
                index = run.endIndex;
                continue;
            }
            const next = nextRunStart(input, index + 1, { ...options, minimumSegmentMm });
            const endIndex = next > index ? next : input.length - 1;
            const path = pathDescriptor(input, index, endIndex, options);
            if (path) segments.push(path);
            index = endIndex;
            if (next < 0) break;
        }
        const merged = mergeAdjacentPaths(segments);
        if (merged.length < 2) return null;
        const intelligentCount = merged.filter(segment => segment.type === "line" || segment.type === "arc").length;
        if (!intelligentCount) return null;
        return Object.freeze({ type: "compound", segments: Object.freeze(merged), closed: false, confidence: 0.88 });
    }

    function interpret(points, options = {}) {
        const raw = F.dedupe(points);
        const whole = F.recognize(raw, options);
        if (whole.type !== "path") return whole;
        const mixed = recognizeMixed(raw, options);
        return mixed || whole;
    }

    root.SmartStrokeIntelligence = Object.freeze({
        STABILIZER_PROFILES,
        profile,
        createStabilizer,
        pushStabilized,
        stabilizeSeries,
        midpointByLength,
        endpointSweep,
        arcThroughEndpoints,
        lineRun,
        arcRun,
        bestRun,
        recognizeMixed,
        interpret,
    });
})();
