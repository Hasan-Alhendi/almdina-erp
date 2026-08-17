(() => {
    "use strict";

    const root = window.AlmdinaDoorDrawingV3 = window.AlmdinaDoorDrawingV3 || Object.create(null);
    const G = root.Geometry;
    if (!G) throw new Error("Door Drawing V3 geometry must load before smart stroke reconstruction");

    const DEFAULTS = Object.freeze({
        resampleSpacingMm: 3.0,
        minSamples: 10,
        maxSamples: 180,
        trendPasses: 3,
        trendRadius: 3,
        cornerWindow: 3,
        cornerAngleDeg: 42,
        cornerMinGapMm: 8,
        minimumStraightLengthMm: 10,
        straightMaxDeviationRatio: 0.055,
        straightRmsRatio: 0.025,
        straightMaxHeadingDeviationDeg: 16,
        straightTotalTurnDeg: 45,
        straightLengthRatio: 1.2,
        deliberateCurveBias: 0.78,
        deliberateCurveEvidenceRatio: 0.01,
        deliberateCurveEvidenceMinMm: 1.2,
        curveAnchorToleranceRatio: 0.012,
        curveAnchorToleranceMinMm: 0.9,
        curveAnchorToleranceMaxMm: 3.5,
        curveHandleScale: 0.29,
        maximumCurveAnchors: 18,
    });

    function point(value) { return G.point(value && value.x, value && value.y); }

    function dedupe(points, minimumMm = G.EPSILON_MM) {
        const input = Array.isArray(points) ? points : [];
        const minimum = Math.max(G.EPSILON_MM, Number(minimumMm) || G.EPSILON_MM);
        const result = [];
        input.forEach(raw => {
            const p = point(raw);
            if (!result.length || G.distance(result[result.length - 1], p) >= minimum) result.push(p);
        });
        return result;
    }

    function polylineLength(points) {
        let total = 0;
        for (let index = 1; index < points.length; index += 1) total += G.distance(points[index - 1], points[index]);
        return total;
    }

    function lerp(a, b, t) {
        return G.point(a.x + (b.x - a.x) * t, a.y + (b.y - a.y) * t);
    }

    function resampleUniform(points, options = {}) {
        const input = dedupe(points);
        if (input.length <= 2) return input;
        const total = polylineLength(input);
        if (total <= G.EPSILON_MM) return [input[0]];
        const spacing = Math.max(0.5, Number(options.resampleSpacingMm) || DEFAULTS.resampleSpacingMm);
        const minSamples = Math.max(3, Math.floor(Number(options.minSamples) || DEFAULTS.minSamples));
        const maxSamples = Math.max(minSamples, Math.floor(Number(options.maxSamples) || DEFAULTS.maxSamples));
        const count = Math.max(minSamples, Math.min(maxSamples, Math.round(total / spacing) + 1));
        const cumulative = [0];
        for (let index = 1; index < input.length; index += 1) cumulative.push(cumulative[index - 1] + G.distance(input[index - 1], input[index]));
        const result = [];
        let segment = 1;
        for (let sample = 0; sample < count; sample += 1) {
            const target = sample === count - 1 ? total : total * sample / (count - 1);
            while (segment < cumulative.length - 1 && cumulative[segment] < target) segment += 1;
            const startIndex = Math.max(0, segment - 1);
            const endIndex = Math.min(input.length - 1, segment);
            const span = cumulative[endIndex] - cumulative[startIndex];
            const ratio = span <= G.EPSILON_MM ? 0 : (target - cumulative[startIndex]) / span;
            result.push(lerp(input[startIndex], input[endIndex], Math.max(0, Math.min(1, ratio))));
        }
        result[0] = input[0];
        result[result.length - 1] = input[input.length - 1];
        return dedupe(result);
    }

    function weightedAverage(points, index, radius) {
        let x = 0, y = 0, weightSum = 0;
        for (let offset = -radius; offset <= radius; offset += 1) {
            const sampleIndex = index + offset;
            if (sampleIndex < 0 || sampleIndex >= points.length) continue;
            const weight = radius + 1 - Math.abs(offset);
            x += points[sampleIndex].x * weight;
            y += points[sampleIndex].y * weight;
            weightSum += weight;
        }
        return weightSum ? G.point(x / weightSum, y / weightSum) : point(points[index]);
    }

    function smoothTrend(points, options = {}) {
        const original = dedupe(points);
        if (original.length <= 2) return original;
        const passes = Math.max(1, Math.min(6, Math.floor(Number(options.trendPasses) || DEFAULTS.trendPasses)));
        const radius = Math.max(1, Math.min(8, Math.floor(Number(options.trendRadius) || DEFAULTS.trendRadius)));
        let current = original.map(point);
        for (let pass = 0; pass < passes; pass += 1) {
            const next = current.map(point);
            for (let index = 1; index < current.length - 1; index += 1) next[index] = weightedAverage(current, index, radius);
            next[0] = original[0];
            next[next.length - 1] = original[original.length - 1];
            current = next;
        }
        return current;
    }

    function angleDeg(a, b) { return Math.atan2(b.y - a.y, b.x - a.x) * 180 / Math.PI; }
    function signedAngleDelta(first, second) {
        let delta = Number(second) - Number(first);
        while (delta <= -180) delta += 360;
        while (delta > 180) delta -= 360;
        return delta;
    }
    function angleDistance(first, second) { return Math.abs(signedAngleDelta(first, second)); }

    function signedDistanceToLine(p, start, end) {
        const dx = end.x - start.x, dy = end.y - start.y;
        const length = Math.hypot(dx, dy);
        if (length <= G.EPSILON_MM) return 0;
        return (dx * (p.y - start.y) - dy * (p.x - start.x)) / length;
    }

    function distanceToSegment(p, start, end) {
        const dx = end.x - start.x, dy = end.y - start.y;
        const length2 = dx * dx + dy * dy;
        if (length2 <= G.EPSILON_MM * G.EPSILON_MM) return G.distance(p, start);
        const t = Math.max(0, Math.min(1, ((p.x - start.x) * dx + (p.y - start.y) * dy) / length2));
        return Math.hypot(p.x - (start.x + dx * t), p.y - (start.y + dy * t));
    }

    function turnAt(points, index, windowSize) {
        const left = Math.max(0, index - windowSize), right = Math.min(points.length - 1, index + windowSize);
        if (left === index || right === index) return 0;
        return angleDistance(angleDeg(points[left], points[index]), angleDeg(points[index], points[right]));
    }

    function detectCorners(points, options = {}) {
        const input = dedupe(points);
        if (input.length < 7) return [];
        const trend = smoothTrend(input, options);
        const windowSize = Math.max(2, Math.min(8, Math.floor(Number(options.cornerWindow) || DEFAULTS.cornerWindow)));
        const threshold = Math.max(20, Number(options.cornerAngleDeg) || DEFAULTS.cornerAngleDeg);
        const minimumGapMm = Math.max(2, Number(options.cornerMinGapMm) || DEFAULTS.cornerMinGapMm);
        const candidates = [];
        for (let index = windowSize; index < trend.length - windowSize; index += 1) {
            const turn = turnAt(trend, index, windowSize);
            if (turn < threshold) continue;
            const leftLength = polylineLength(input.slice(Math.max(0, index - windowSize), index + 1));
            const rightLength = polylineLength(input.slice(index, Math.min(input.length, index + windowSize + 1)));
            if (leftLength < minimumGapMm || rightLength < minimumGapMm) continue;
            candidates.push({ index, turn });
        }
        candidates.sort((a, b) => b.turn - a.turn);
        const chosen = [];
        candidates.forEach(candidate => {
            if (chosen.some(item => Math.abs(item.index - candidate.index) <= windowSize * 2)) return;
            chosen.push(candidate);
        });
        chosen.sort((a, b) => a.index - b.index);
        return chosen;
    }

    function straightEvidence(points, options = {}) {
        const input = dedupe(points);
        if (input.length < 2) return Object.freeze({ eligible: false });
        const start = input[0], end = input[input.length - 1], chord = G.distance(start, end);
        if (chord <= G.EPSILON_MM) return Object.freeze({ eligible: false });
        const trend = smoothTrend(input, { ...options, trendPasses: Math.max(2, Math.floor((Number(options.trendPasses) || DEFAULTS.trendPasses) - 1)), trendRadius: Math.max(2, Math.floor((Number(options.trendRadius) || DEFAULTS.trendRadius) - 1)) });
        const distances = input.slice(1, -1).map(p => signedDistanceToLine(p, start, end));
        const absolute = distances.map(Math.abs);
        const maxDeviation = absolute.length ? Math.max(...absolute) : 0;
        const rms = absolute.length ? Math.sqrt(absolute.reduce((sum, value) => sum + value * value, 0) / absolute.length) : 0;
        const noiseFloor = Math.max(0.35, chord * 0.0025);
        const significant = distances.filter(value => Math.abs(value) >= noiseFloor);
        const positive = significant.filter(value => value > 0).length;
        const negative = significant.filter(value => value < 0).length;
        const curveBias = significant.length ? Math.max(positive, negative) / significant.length : 0;
        const chordHeading = angleDeg(start, end);
        const localHeadings = [];
        for (let index = 1; index < trend.length; index += 1) {
            if (G.distance(trend[index - 1], trend[index]) > G.EPSILON_MM) localHeadings.push(angleDeg(trend[index - 1], trend[index]));
        }
        const maxHeadingDeviation = localHeadings.length ? Math.max(...localHeadings.map(value => angleDistance(chordHeading, value))) : 0;
        let totalTurn = 0;
        for (let index = 1; index < localHeadings.length; index += 1) totalTurn += angleDistance(localHeadings[index - 1], localHeadings[index]);
        const lengthRatio = polylineLength(input) / chord;
        const maxDeviationLimit = Math.max(1.5, Math.min(8, chord * (Number(options.straightMaxDeviationRatio) || DEFAULTS.straightMaxDeviationRatio)));
        const rmsLimit = Math.max(0.8, Math.min(4.2, chord * (Number(options.straightRmsRatio) || DEFAULTS.straightRmsRatio)));
        const curveEvidence = Math.max(Number(options.deliberateCurveEvidenceMinMm) || DEFAULTS.deliberateCurveEvidenceMinMm, chord * (Number(options.deliberateCurveEvidenceRatio) || DEFAULTS.deliberateCurveEvidenceRatio));
        const deliberateCurve = curveBias >= (Number(options.deliberateCurveBias) || DEFAULTS.deliberateCurveBias) && maxDeviation >= curveEvidence;
        const eligible = chord >= (Number(options.minimumStraightLengthMm) || DEFAULTS.minimumStraightLengthMm)
            && maxDeviation <= maxDeviationLimit
            && rms <= rmsLimit
            && maxHeadingDeviation <= (Number(options.straightMaxHeadingDeviationDeg) || DEFAULTS.straightMaxHeadingDeviationDeg)
            && totalTurn <= (Number(options.straightTotalTurnDeg) || DEFAULTS.straightTotalTurnDeg)
            && lengthRatio <= (Number(options.straightLengthRatio) || DEFAULTS.straightLengthRatio)
            && !deliberateCurve;
        return Object.freeze({
            eligible,
            chordMm: G.roundMm(chord),
            maxDeviationMm: G.roundMm(maxDeviation),
            rmsMm: G.roundMm(rms),
            curveBias,
            maxHeadingDeviationDeg: G.roundMm(maxHeadingDeviation),
            totalTurnDeg: G.roundMm(totalTurn),
            lengthRatio,
            deliberateCurve,
        });
    }

    function rdpIndices(points, toleranceMm) {
        const input = dedupe(points);
        if (input.length <= 2) return input.map((_, index) => index);
        const tolerance = Math.max(0.05, Number(toleranceMm) || 0.5);
        const keep = new Set([0, input.length - 1]);
        function visit(startIndex, endIndex) {
            if (endIndex <= startIndex + 1) return;
            let bestIndex = -1, bestDistance = -1;
            for (let index = startIndex + 1; index < endIndex; index += 1) {
                const distance = distanceToSegment(input[index], input[startIndex], input[endIndex]);
                if (distance > bestDistance) { bestDistance = distance; bestIndex = index; }
            }
            if (bestIndex >= 0 && bestDistance > tolerance) {
                keep.add(bestIndex);
                visit(startIndex, bestIndex);
                visit(bestIndex, endIndex);
            }
        }
        visit(0, input.length - 1);
        return [...keep].sort((a, b) => a - b);
    }

    function maxDeviationIndex(points) {
        if (points.length <= 2) return -1;
        const start = points[0], end = points[points.length - 1];
        let bestIndex = -1, bestDistance = -1;
        for (let index = 1; index < points.length - 1; index += 1) {
            const distance = distanceToSegment(points[index], start, end);
            if (distance > bestDistance) { bestDistance = distance; bestIndex = index; }
        }
        return bestIndex;
    }

    function unitVector(a, b) {
        const dx = b.x - a.x, dy = b.y - a.y, length = Math.hypot(dx, dy);
        if (length <= G.EPSILON_MM) return { x: 1, y: 0 };
        return { x: dx / length, y: dy / length };
    }

    function buildCurveSpan(points, options = {}) {
        const input = dedupe(points);
        const trend = smoothTrend(input, { ...options, trendPasses: Math.max(3, Number(options.trendPasses) || DEFAULTS.trendPasses), trendRadius: Math.max(2, Number(options.trendRadius) || DEFAULTS.trendRadius) });
        const length = polylineLength(trend);
        let tolerance = Math.max(
            Number(options.curveAnchorToleranceMinMm) || DEFAULTS.curveAnchorToleranceMinMm,
            Math.min(
                Number(options.curveAnchorToleranceMaxMm) || DEFAULTS.curveAnchorToleranceMaxMm,
                length * (Number(options.curveAnchorToleranceRatio) || DEFAULTS.curveAnchorToleranceRatio)
            )
        );
        let indices = rdpIndices(trend, tolerance);
        if (indices.length <= 2 && trend.length > 2) {
            const middle = maxDeviationIndex(trend);
            if (middle > 0) indices = [0, middle, trend.length - 1];
        }
        const maximumAnchors = Math.max(4, Math.floor(Number(options.maximumCurveAnchors) || DEFAULTS.maximumCurveAnchors));
        let attempts = 0;
        while (indices.length > maximumAnchors && attempts < 5) {
            tolerance *= 1.35;
            indices = rdpIndices(trend, tolerance);
            attempts += 1;
        }
        if (indices.length <= 2 && trend.length > 2) {
            const middle = Math.floor((trend.length - 1) / 2);
            indices = [0, middle, trend.length - 1];
        }
        const anchors = indices.map(index => trend[index]);
        anchors[0] = input[0];
        anchors[anchors.length - 1] = input[input.length - 1];
        const tangents = anchors.map((anchor, index) => {
            if (anchors.length === 1) return { x: 1, y: 0 };
            if (index === 0) return unitVector(anchor, anchors[1]);
            if (index === anchors.length - 1) return unitVector(anchors[index - 1], anchor);
            return unitVector(anchors[index - 1], anchors[index + 1]);
        });
        const handleScale = Math.max(0.12, Math.min(0.34, Number(options.curveHandleScale) || DEFAULTS.curveHandleScale));
        const segments = [];
        for (let index = 0; index < anchors.length - 1; index += 1) {
            const start = anchors[index], end = anchors[index + 1], distance = G.distance(start, end);
            const handle = distance * handleScale;
            const c1 = G.point(start.x + tangents[index].x * handle, start.y + tangents[index].y * handle);
            const c2 = G.point(end.x - tangents[index + 1].x * handle, end.y - tangents[index + 1].y * handle);
            segments.push(Object.freeze({ curved: true, c1, c2 }));
        }
        return Object.freeze({ anchors: Object.freeze(anchors), segments: Object.freeze(segments), toleranceMm: G.roundMm(tolerance) });
    }

    function buildStraightSpan(points) {
        const input = dedupe(points);
        return Object.freeze({ anchors: Object.freeze([input[0], input[input.length - 1]]), segments: Object.freeze([Object.freeze({ curved: false, c1: null, c2: null })]) });
    }

    function vectorFrom(anchor, control) {
        if (!anchor || !control) return null;
        const x = G.roundMm(control.x - anchor.x), y = G.roundMm(control.y - anchor.y);
        return Math.hypot(x, y) <= G.EPSILON_MM ? null : Object.freeze({ x, y });
    }

    function appendSpan(target, span, explicitCornerAtStart = false) {
        if (!span || !span.anchors || span.anchors.length < 2) return;
        if (!target.points.length) {
            target.points.push(span.anchors[0]);
            target.nodes.push({ type: "corner", in: null, out: null, explicitCorner: false });
        }
        const startOffset = target.points.length - 1;
        if (explicitCornerAtStart && target.nodes[startOffset]) target.nodes[startOffset].explicitCorner = true;
        for (let index = 1; index < span.anchors.length; index += 1) {
            target.points.push(span.anchors[index]);
            target.nodes.push({ type: "corner", in: null, out: null, explicitCorner: false });
        }
        span.segments.forEach((segment, localIndex) => {
            const globalIndex = startOffset + localIndex;
            if (!segment.curved) return;
            target.nodes[globalIndex].out = vectorFrom(target.points[globalIndex], segment.c1);
            target.nodes[globalIndex + 1].in = vectorFrom(target.points[globalIndex + 1], segment.c2);
            target.curveSegmentCount += 1;
        });
        if (span.segments.some(segment => !segment.curved)) target.straightSegmentCount += span.segments.filter(segment => !segment.curved).length;
    }

    function finalizeNodeTypes(points, nodes) {
        return nodes.map((node, index) => {
            const incoming = node.in, outgoing = node.out;
            let type = "corner";
            if (!node.explicitCorner && incoming && outgoing && index > 0 && index < points.length - 1) {
                const inAbs = G.point(points[index].x + incoming.x, points[index].y + incoming.y);
                const outAbs = G.point(points[index].x + outgoing.x, points[index].y + outgoing.y);
                const incomingHeading = angleDeg(inAbs, points[index]);
                const outgoingHeading = angleDeg(points[index], outAbs);
                if (angleDistance(incomingHeading, outgoingHeading) <= 15) type = "smooth";
            }
            return Object.freeze({ type, in: incoming || null, out: outgoing || null });
        });
    }

    function sameRawGeometry(raw, points, nodes) {
        if (raw.length !== points.length) return false;
        const samePoints = raw.every((p, index) => G.distance(p, points[index]) <= G.EPSILON_MM);
        const hasHandles = nodes.some(node => node.in || node.out);
        return samePoints && !hasHandles;
    }

    function reconstruct(points, options = {}) {
        const raw = dedupe(points);
        if (raw.length < 2) return Object.freeze({ points: Object.freeze(raw), nodes: Object.freeze(raw.map(() => Object.freeze({ type: "corner", in: null, out: null }))), changed: false, cornerCount: 0, straightSegmentCount: 0, curveSegmentCount: 0 });
        const sampled = resampleUniform(raw, options);
        if (sampled.length < 2) return Object.freeze({ points: Object.freeze(raw), nodes: Object.freeze(raw.map(() => Object.freeze({ type: "corner", in: null, out: null }))), changed: false, cornerCount: 0, straightSegmentCount: 0, curveSegmentCount: 0 });
        const corners = detectCorners(sampled, options);
        const boundaries = [0, ...corners.map(item => item.index), sampled.length - 1]
            .filter((value, index, list) => index === 0 || value !== list[index - 1]);
        const target = { points: [], nodes: [], straightSegmentCount: 0, curveSegmentCount: 0 };
        const spans = [];
        for (let index = 1; index < boundaries.length; index += 1) {
            const start = boundaries[index - 1], end = boundaries[index];
            if (end <= start) continue;
            const spanPoints = sampled.slice(start, end + 1);
            const evidence = straightEvidence(spanPoints, options);
            const span = evidence.eligible ? buildStraightSpan(spanPoints) : buildCurveSpan(spanPoints, options);
            appendSpan(target, span, index > 1);
            spans.push(Object.freeze({ startIndex: start, endIndex: end, kind: evidence.eligible ? "line" : "curve", evidence }));
        }
        if (target.points.length < 2) {
            target.points = raw.slice();
            target.nodes = raw.map(() => ({ type: "corner", in: null, out: null, explicitCorner: false }));
        }
        target.points[0] = raw[0];
        target.points[target.points.length - 1] = raw[raw.length - 1];
        const finalNodes = finalizeNodeTypes(target.points, target.nodes);
        return Object.freeze({
            points: Object.freeze(target.points.map(point)),
            nodes: Object.freeze(finalNodes),
            changed: !sameRawGeometry(raw, target.points, finalNodes),
            cornerCount: corners.length,
            straightSegmentCount: target.straightSegmentCount,
            curveSegmentCount: target.curveSegmentCount,
            spans: Object.freeze(spans),
        });
    }

    root.SmartStrokeReconstructionDomain = Object.freeze({
        DEFAULTS,
        dedupe,
        polylineLength,
        resampleUniform,
        smoothTrend,
        detectCorners,
        straightEvidence,
        rdpIndices,
        buildCurveSpan,
        buildStraightSpan,
        reconstruct,
    });
})();
