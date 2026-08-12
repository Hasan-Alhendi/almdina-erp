(() => {
    "use strict";

    const root = window.AlmdinaDoorDrawingV3 = window.AlmdinaDoorDrawingV3 || Object.create(null);
    const G = root.Geometry;
    if (!G) throw new Error("Door Drawing V3 geometry must load before intelligent freehand policy");

    const DEFAULTS = Object.freeze({
        minSampleMm: 0.8,
        simplifyToleranceMm: 1.2,
        straightToleranceMm: 1.6,
        straightRatio: 1.035,
        circleResidualRatio: 0.035,
        arcResidualRatio: 0.03,
        minimumArcSweepDeg: 20,
        maximumArcSweepDeg: 335,
        pathSmoothingPasses: 1,
        collinearAngleToleranceDeg: 7,
        orthogonalAngleToleranceDeg: 8,
    });

    function p(value) { return G.point(value && value.x, value && value.y); }
    function dedupe(points, minimumMm = G.EPSILON_MM) {
        const result = [];
        for (const raw of Array.isArray(points) ? points : []) {
            const point = p(raw);
            if (!result.length || G.distance(result[result.length - 1], point) >= minimumMm) result.push(point);
        }
        return result;
    }

    function appendSample(points, point, minSampleMm = DEFAULTS.minSampleMm) {
        const result = Array.isArray(points) ? points.slice() : [];
        const next = p(point);
        if (!result.length || G.distance(result[result.length - 1], next) >= Math.max(G.EPSILON_MM, Number(minSampleMm) || 0)) result.push(next);
        return result;
    }

    function polylineLength(points) {
        let total = 0;
        for (let index = 1; index < points.length; index += 1) total += G.distance(points[index - 1], points[index]);
        return total;
    }

    function distanceToSegment(point, start, end) {
        const px = point.x, py = point.y, ax = start.x, ay = start.y, bx = end.x, by = end.y;
        const dx = bx - ax, dy = by - ay;
        const length2 = dx * dx + dy * dy;
        if (length2 <= G.EPSILON_MM * G.EPSILON_MM) return G.distance(point, start);
        const t = Math.max(0, Math.min(1, ((px - ax) * dx + (py - ay) * dy) / length2));
        return Math.hypot(px - (ax + dx * t), py - (ay + dy * t));
    }

    function smooth(points, passes = 2) {
        let current = dedupe(points);
        const count = Math.max(0, Math.min(4, Number(passes) || 0));
        for (let pass = 0; pass < count && current.length > 2; pass += 1) {
            const next = [current[0]];
            for (let index = 1; index < current.length - 1; index += 1) {
                const a = current[index - 1], b = current[index], c = current[index + 1];
                next.push(G.point(a.x * 0.2 + b.x * 0.6 + c.x * 0.2, a.y * 0.2 + b.y * 0.6 + c.y * 0.2));
            }
            next.push(current[current.length - 1]);
            current = next;
        }
        return current;
    }

    function simplifyRdp(points, toleranceMm = DEFAULTS.simplifyToleranceMm) {
        const input = dedupe(points);
        if (input.length <= 2) return input;
        const tolerance = Math.max(G.EPSILON_MM, Number(toleranceMm) || DEFAULTS.simplifyToleranceMm);
        let maxDistance = -1;
        let splitIndex = -1;
        const start = input[0], end = input[input.length - 1];
        for (let index = 1; index < input.length - 1; index += 1) {
            const distance = distanceToSegment(input[index], start, end);
            if (distance > maxDistance) { maxDistance = distance; splitIndex = index; }
        }
        if (maxDistance <= tolerance || splitIndex < 0) return [start, end];
        const left = simplifyRdp(input.slice(0, splitIndex + 1), tolerance);
        const right = simplifyRdp(input.slice(splitIndex), tolerance);
        return [...left.slice(0, -1), ...right];
    }

    function lineQuality(points) {
        const input = dedupe(points);
        if (input.length < 2) return Object.freeze({ eligible: false, maxDeviationMm: Infinity, ratio: Infinity, chordMm: 0 });
        const start = input[0], end = input[input.length - 1];
        const chordMm = G.distance(start, end);
        if (chordMm < G.EPSILON_MM) return Object.freeze({ eligible: false, maxDeviationMm: Infinity, ratio: Infinity, chordMm });
        let maxDeviationMm = 0;
        for (const point of input) maxDeviationMm = Math.max(maxDeviationMm, distanceToSegment(point, start, end));
        const ratio = polylineLength(input) / chordMm;
        return Object.freeze({ eligible: true, maxDeviationMm, ratio, chordMm });
    }

    function circumcircle(a, b, c) {
        const ax = a.x, ay = a.y, bx = b.x, by = b.y, cx = c.x, cy = c.y;
        const d = 2 * (ax * (by - cy) + bx * (cy - ay) + cx * (ay - by));
        if (Math.abs(d) <= G.EPSILON_MM) return null;
        const a2 = ax * ax + ay * ay, b2 = bx * bx + by * by, c2 = cx * cx + cy * cy;
        const ux = (a2 * (by - cy) + b2 * (cy - ay) + c2 * (ay - by)) / d;
        const uy = (a2 * (cx - bx) + b2 * (ax - cx) + c2 * (bx - ax)) / d;
        const center = G.point(ux, uy);
        const radiusMm = G.distance(center, a);
        return radiusMm >= G.EPSILON_MM ? Object.freeze({ center, radiusMm: G.roundMm(radiusMm) }) : null;
    }

    function determinant3(matrix) {
        return matrix[0][0] * (matrix[1][1] * matrix[2][2] - matrix[1][2] * matrix[2][1])
            - matrix[0][1] * (matrix[1][0] * matrix[2][2] - matrix[1][2] * matrix[2][0])
            + matrix[0][2] * (matrix[1][0] * matrix[2][1] - matrix[1][1] * matrix[2][0]);
    }

    function solve3(matrix, vector) {
        const det = determinant3(matrix);
        if (Math.abs(det) <= 1e-9) return null;
        const replace = column => matrix.map((row, rowIndex) => row.map((value, colIndex) => colIndex === column ? vector[rowIndex] : value));
        return [determinant3(replace(0)) / det, determinant3(replace(1)) / det, determinant3(replace(2)) / det];
    }

    function leastSquaresCircle(points) {
        const input = dedupe(points);
        if (input.length < 5) return null;
        let sx = 0, sy = 0, sxx = 0, syy = 0, sxy = 0, sz = 0, sxz = 0, syz = 0;
        for (const point of input) {
            const x = point.x, y = point.y, z = x * x + y * y;
            sx += x; sy += y; sxx += x * x; syy += y * y; sxy += x * y; sz += z; sxz += x * z; syz += y * z;
        }
        const solution = solve3(
            [[sxx, sxy, sx], [sxy, syy, sy], [sx, sy, input.length]],
            [-sxz, -syz, -sz]
        );
        if (!solution) return null;
        const [d, e, f] = solution;
        const cx = -d / 2, cy = -e / 2;
        const radius2 = cx * cx + cy * cy - f;
        if (!Number.isFinite(radius2) || radius2 <= G.EPSILON_MM * G.EPSILON_MM) return null;
        const center = G.point(cx, cy);
        return Object.freeze({ center, radiusMm: G.roundMm(Math.sqrt(radius2)) });
    }

    function radialResidual(points, circle) {
        if (!circle || !points.length) return Infinity;
        let sum = 0;
        for (const point of points) {
            const delta = G.distance(circle.center, point) - circle.radiusMm;
            sum += delta * delta;
        }
        return Math.sqrt(sum / points.length);
    }

    function fittedCircle(points, closed = false) {
        const input = dedupe(points);
        if (input.length < 5) return null;
        let circle = leastSquaresCircle(input);
        if (!circle) {
            const first = input[0];
            const a = first;
            const b = input[Math.floor((input.length - 1) / 3)];
            const c = input[Math.floor((input.length - 1) * 2 / 3)];
            circle = circumcircle(a, b, c);
            if (!circle && !closed) circle = circumcircle(first, input[Math.floor(input.length / 2)], input[input.length - 1]);
        }
        if (!circle) return null;
        return Object.freeze({ ...circle, residualMm: G.roundMm(radialResidual(input, circle)) });
    }

    function unwrapSweep(points, center) {
        if (points.length < 2) return Object.freeze({ sweepDeg: 0, consistency: 0 });
        let sweep = 0;
        let positive = 0;
        let negative = 0;
        let previous = G.angleDeg(center, points[0]);
        for (let index = 1; index < points.length; index += 1) {
            const angle = G.angleDeg(center, points[index]);
            const delta = G.normalizeAngle(angle - previous);
            sweep += delta;
            if (delta > 0.05) positive += 1;
            if (delta < -0.05) negative += 1;
            previous = angle;
        }
        const directional = positive + negative;
        const consistency = directional ? Math.max(positive, negative) / directional : 0;
        return Object.freeze({ sweepDeg: G.roundMm(sweep), consistency });
    }

    function directionDifference(firstAngle, secondAngle) {
        return Math.abs(G.normalizeAngle(Number(secondAngle) - Number(firstAngle)));
    }

    function pruneCollinear(points, closed = false, toleranceDeg = DEFAULTS.collinearAngleToleranceDeg) {
        const input = dedupe(points);
        if (input.length <= (closed ? 3 : 2)) return input;
        const tolerance = Math.max(0, Number(toleranceDeg) || 0);
        const output = [];
        for (let index = 0; index < input.length; index += 1) {
            if (!closed && (index === 0 || index === input.length - 1)) { output.push(input[index]); continue; }
            const previous = input[(index - 1 + input.length) % input.length];
            const current = input[index];
            const next = input[(index + 1) % input.length];
            const firstAngle = G.angleDeg(previous, current);
            const secondAngle = G.angleDeg(current, next);
            if (directionDifference(firstAngle, secondAngle) <= tolerance) continue;
            output.push(current);
        }
        if (output.length < (closed ? 3 : 2)) return input;
        return output;
    }

    function axisKind(start, end, toleranceDeg = DEFAULTS.orthogonalAngleToleranceDeg) {
        if (G.distance(start, end) < G.EPSILON_MM) return null;
        const angle = G.positiveAngle(G.angleDeg(start, end));
        const horizontalError = Math.min(Math.abs(angle), Math.abs(angle - 180), Math.abs(angle - 360));
        const verticalError = Math.min(Math.abs(angle - 90), Math.abs(angle - 270));
        const tolerance = Math.max(0, Number(toleranceDeg) || 0);
        if (horizontalError <= tolerance) return "horizontal";
        if (verticalError <= tolerance) return "vertical";
        return null;
    }

    function orthogonalize(points, closed = false, toleranceDeg = DEFAULTS.orthogonalAngleToleranceDeg, preserveEndpoints = true) {
        const input = dedupe(points);
        if (input.length < 2) return input;
        const output = input.map(point => ({ x: point.x, y: point.y }));
        const segmentCount = closed ? input.length : input.length - 1;
        for (let index = 0; index < segmentCount; index += 1) {
            const nextIndex = (index + 1) % input.length;
            const axis = axisKind(input[index], input[nextIndex], toleranceDeg);
            if (!axis) continue;
            if (axis === "horizontal") {
                let y = (input[index].y + input[nextIndex].y) / 2;
                if (!closed && preserveEndpoints && index === 0) y = input[0].y;
                if (!closed && preserveEndpoints && nextIndex === input.length - 1) y = input[input.length - 1].y;
                output[index].y = y;
                output[nextIndex].y = y;
            } else {
                let x = (input[index].x + input[nextIndex].x) / 2;
                if (!closed && preserveEndpoints && index === 0) x = input[0].x;
                if (!closed && preserveEndpoints && nextIndex === input.length - 1) x = input[input.length - 1].x;
                output[index].x = x;
                output[nextIndex].x = x;
            }
        }
        return output.map(point => G.point(point.x, point.y));
    }

    function cleanPath(points, options = {}) {
        const raw = dedupe(points);
        if (raw.length < 2) return raw;
        const closed = Boolean(options.closed);
        let source = smooth(raw, options.pathSmoothingPasses == null ? DEFAULTS.pathSmoothingPasses : options.pathSmoothingPasses);
        if (closed && source.length > 3 && G.distance(source[0], source[source.length - 1]) < G.EPSILON_MM) source = source.slice(0, -1);
        let cleaned = simplifyRdp(source, Math.max(G.EPSILON_MM, Number(options.simplifyToleranceMm) || DEFAULTS.simplifyToleranceMm));
        if (!closed) {
            cleaned[0] = raw[0];
            cleaned[cleaned.length - 1] = raw[raw.length - 1];
        }
        cleaned = pruneCollinear(cleaned, closed, options.collinearAngleToleranceDeg == null ? DEFAULTS.collinearAngleToleranceDeg : options.collinearAngleToleranceDeg);
        if (options.orthogonalize !== false) {
            cleaned = orthogonalize(cleaned, closed, options.orthogonalAngleToleranceDeg == null ? DEFAULTS.orthogonalAngleToleranceDeg : options.orthogonalAngleToleranceDeg, options.preserveEndpoints !== false);
        }
        cleaned = pruneCollinear(cleaned, closed, options.collinearAngleToleranceDeg == null ? DEFAULTS.collinearAngleToleranceDeg : options.collinearAngleToleranceDeg);
        return cleaned.map(p);
    }

    function rectangleFromPath(points, options = {}) {
        const input = dedupe(points);
        if (input.length !== 4) return null;
        const toleranceDeg = options.orthogonalAngleToleranceDeg == null ? DEFAULTS.orthogonalAngleToleranceDeg : options.orthogonalAngleToleranceDeg;
        const axes = [];
        for (let index = 0; index < input.length; index += 1) {
            const axis = axisKind(input[index], input[(index + 1) % input.length], toleranceDeg);
            if (!axis) return null;
            axes.push(axis);
        }
        for (let index = 0; index < axes.length; index += 1) if (axes[index] === axes[(index + 1) % axes.length]) return null;
        const xs = input.map(point => point.x), ys = input.map(point => point.y);
        const minX = Math.min(...xs), maxX = Math.max(...xs), minY = Math.min(...ys), maxY = Math.max(...ys);
        const widthMm = maxX - minX, heightMm = maxY - minY;
        if (widthMm < G.EPSILON_MM || heightMm < G.EPSILON_MM) return null;
        return Object.freeze({ origin: G.point(minX, minY), widthMm: G.roundMm(widthMm), heightMm: G.roundMm(heightMm) });
    }

    function recognize(points, options = {}) {
        const raw = dedupe(points);
        if (raw.length < 2) return Object.freeze({ type: "none", points: raw, confidence: 0 });
        const simplifyToleranceMm = Math.max(G.EPSILON_MM, Number(options.simplifyToleranceMm) || DEFAULTS.simplifyToleranceMm);
        const straightToleranceMm = Math.max(G.EPSILON_MM, Number(options.straightToleranceMm) || DEFAULTS.straightToleranceMm);
        const straightRatio = Number(options.straightRatio) || DEFAULTS.straightRatio;
        const circleResidualRatio = Number(options.circleResidualRatio) || DEFAULTS.circleResidualRatio;
        const arcResidualRatio = Number(options.arcResidualRatio) || DEFAULTS.arcResidualRatio;
        const closed = Boolean(options.closed);
        const prepared = smooth(raw, options.smoothingPasses == null ? 2 : options.smoothingPasses);
        const quality = lineQuality(prepared);
        if (!closed && quality.eligible && quality.maxDeviationMm <= straightToleranceMm && quality.ratio <= straightRatio) {
            return Object.freeze({ type: "line", start: raw[0], end: raw[raw.length - 1], confidence: Math.max(0, 1 - quality.maxDeviationMm / Math.max(straightToleranceMm, G.EPSILON_MM)), rawPoints: raw });
        }

        const circle = fittedCircle(prepared, closed);
        if (circle) {
            const residualLimit = Math.max(straightToleranceMm, circle.radiusMm * (closed ? circleResidualRatio : arcResidualRatio));
            const sweep = unwrapSweep(prepared, circle.center);
            if (closed && circle.residualMm <= residualLimit && Math.abs(sweep.sweepDeg) >= 280 && sweep.consistency >= 0.8) {
                return Object.freeze({ type: "circle", center: circle.center, radiusMm: circle.radiusMm, confidence: Math.max(0, 1 - circle.residualMm / residualLimit), rawPoints: raw });
            }
            const absSweep = Math.abs(sweep.sweepDeg);
            const minimumArcSweepDeg = Number(options.minimumArcSweepDeg) || DEFAULTS.minimumArcSweepDeg;
            const maximumArcSweepDeg = Number(options.maximumArcSweepDeg) || DEFAULTS.maximumArcSweepDeg;
            if (!closed && circle.residualMm <= residualLimit && absSweep >= minimumArcSweepDeg && absSweep <= maximumArcSweepDeg && sweep.consistency >= 0.86) {
                return Object.freeze({
                    type: "arc",
                    center: circle.center,
                    radiusMm: circle.radiusMm,
                    startAngleDeg: G.angleDeg(circle.center, raw[0]),
                    sweepAngleDeg: sweep.sweepDeg,
                    confidence: Math.max(0, 1 - circle.residualMm / residualLimit),
                    rawPoints: raw,
                });
            }
        }

        const cleaned = cleanPath(raw, { ...options, closed, simplifyToleranceMm });
        if (closed) {
            const rectangle = rectangleFromPath(cleaned, options);
            if (rectangle) return Object.freeze({ type: "rectangle", ...rectangle, confidence: 0.9, rawPoints: raw });
        }
        if (cleaned.length < 2) return Object.freeze({ type: "none", points: cleaned, confidence: 0 });
        return Object.freeze({ type: "path", points: cleaned, closed, confidence: 1, rawPoints: raw });
    }

    root.SmartFreehandPolicy = Object.freeze({
        DEFAULTS,
        dedupe,
        appendSample,
        polylineLength,
        distanceToSegment,
        smooth,
        simplifyRdp,
        lineQuality,
        circumcircle,
        leastSquaresCircle,
        radialResidual,
        fittedCircle,
        unwrapSweep,
        directionDifference,
        pruneCollinear,
        axisKind,
        orthogonalize,
        cleanPath,
        rectangleFromPath,
        recognize,
    });
})();
