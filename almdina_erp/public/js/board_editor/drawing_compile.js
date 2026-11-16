(function () {
    "use strict";

    const MAX_VERTICES = 64;
    const CHORD_ERROR_MM = 0.05;
    const STORAGE_EPSILON_CM = 0.001;
    const MIN_SAMPLE_MM = 0.02;
    const MAX_BEZIER_DEPTH = 16;
    const LONG_CHORD_TOLERANCE_MM = 0.042;
    const SHORT_CHORD_TOLERANCE_MM = 0.022;
    const MESSAGES = {
        path_open: "The cut outline is not closed. Close the path, then validate it again.",
        self_intersection: "The cut outline crosses itself. Move the nodes so the edges no longer cross.",
        outside_blank: "The cut outline extends outside the door blank. Move the whole path inside the blank.",
        bounds_not_touched: "The cut outline must touch all four edges of the door blank. Move it; it will not be scaled automatically.",
        multiple_outers: "This door already has a cut outline. Clear the extra one before copying the plan.",
        invalid_area: "The cut outline does not enclose a usable area. Redraw a closed shape with area.",
        holes_unsupported: "Internal cutouts are not supported by the manufacturing geometry. Clear that role.",
        zero_edge: "The cut outline has a zero-length edge. Remove the duplicate node.",
        curve_unrepresentable: "This curve cannot be represented within 0.05 mm and the 64-corner manufacturing limit. Simplify it.",
        non_finite: "The cut outline contains a value that is not a number. Edit the path and validate again.",
        invalid_document: "The drawing could not be read. Reload the piece and try again.",
    };

    function compile(document, blankWidthMm, blankLengthMm) {
        const width = Number(blankWidthMm);
        const length = Number(blankLengthMm);
        if (!document || !Array.isArray(document.paths) || !Number.isFinite(width) || !Number.isFinite(length) || width <= 0 || length <= 0) {
            return rejected("invalid_document", "");
        }
        const outers = document.paths.filter((path) => path && path.role === "manufacturing_outer");
        const holes = document.paths.filter((path) => path && path.role === "manufacturing_hole");
        if (holes.length) return rejected("holes_unsupported", holes[0].id);
        if (!outers.length) return { status: "absent", code: "", pathId: "", geometry: null, messageKey: "" };
        if (outers.length > 1) return rejected("multiple_outers", outers[1].id);
        const path = outers[0];
        if (path.closed !== true) return rejected("path_open", path.id);
        const flat = flattenPath(path);
        if (flat && flat.status === "rejected") return flat;
        const checked = polygon(flat, width, length, path.id);
        if (checked.status !== "ready") return checked;
        const result = {
            status: "ready",
            code: "",
            pathId: String(path.id || ""),
            messageKey: "The cut outline is valid for manufacturing.",
            geometry: {
                version: 1,
                kind: "polygon",
                units: "cm",
                template: "drawing",
                blank_width_cm: roundCm(width / 10),
                blank_length_cm: roundCm(length / 10),
                points: checked.points,
                exact: true,
            },
        };
        if (!checked.spansBlank) result.geometry.reservation = "blank";
        return result;
    }

    function rejected(code, pathId) {
        return {
            status: "rejected",
            code,
            pathId: String(pathId || ""),
            geometry: null,
            messageKey: MESSAGES[code] || MESSAGES.invalid_document,
        };
    }

    function flattenPath(path) {
        const nodes = {};
        (path.nodes || []).forEach((node) => { nodes[node.id] = node; });
        const samples = [];
        const segments = path.segments || [];
        for (let index = 0; index < segments.length; index += 1) {
            const segment = segments[index];
            const start = nodes[segment.from_node];
            const end = nodes[segment.to_node];
            if (!start || !end) return rejected("invalid_document", path.id);
            const startPoint = [Number(start.x_mm), Number(start.y_mm)];
            const endPoint = [Number(end.x_mm), Number(end.y_mm)];
            let piece = null;
            if (segment.kind === "line") {
                if (distance(startPoint, endPoint) < MIN_SAMPLE_MM) return rejected("zero_edge", path.id);
                piece = [startPoint, endPoint];
            } else if (segment.kind === "arc") {
                piece = flattenArc(startPoint, endPoint, segment);
            } else if (segment.kind === "bezier" && segment.controls && segment.controls.length === 2) {
                piece = flattenBezier(
                    startPoint,
                    [Number(segment.controls[0].x_mm), Number(segment.controls[0].y_mm)],
                    [Number(segment.controls[1].x_mm), Number(segment.controls[1].y_mm)],
                    endPoint
                );
            }
            if (!piece) return rejected("curve_unrepresentable", path.id);
            const copy = samples.length && distance(samples[samples.length - 1], piece[0]) <= MIN_SAMPLE_MM ? piece.slice(1) : piece;
            copy.forEach((point) => samples.push(point));
        }
        if (samples.length >= 2 && distance(samples[0], samples[samples.length - 1]) <= MIN_SAMPLE_MM) samples.pop();
        return samples;
    }

    function flattenArc(start, end, segment) {
        const radius = Number(segment.radius_mm);
        const frame = arcFrame(start, end, radius, segment.large_arc === true, segment.sweep_clockwise === true);
        if (!frame) return null;
        const step = arcStep(radius);
        const count = Math.max(1, Math.ceil(Math.abs(frame.delta) / Math.max(step, 1e-6)));
        if (count > MAX_VERTICES) return null;
        const fractions = { 0: true, 1: true };
        for (let index = 1; index < count; index += 1) fractions[index / count] = true;
        axisAngles(frame.theta, frame.delta).forEach((angle) => {
            const fraction = Math.abs(frame.delta) > 1e-12 ? (angle - frame.theta) / frame.delta : 0;
            if (fraction > 0 && fraction < 1) fractions[fraction] = true;
        });
        const ordered = Object.keys(fractions).map(Number).sort((a, b) => a - b);
        const points = ordered.map((fraction) => {
            const angle = frame.theta + frame.delta * fraction;
            return [frame.cx + radius * Math.cos(angle), frame.cy + radius * Math.sin(angle)];
        });
        points[0] = start;
        points[points.length - 1] = end;
        return points;
    }

    function arcFrame(start, end, radius, large, sweep) {
        const dx = (start[0] - end[0]) / 2;
        const dy = (start[1] - end[1]) / 2;
        const chord2 = dx * dx + dy * dy;
        if (chord2 <= 1e-12 || radius * radius < chord2 - 1e-9) return null;
        const factor = Math.sqrt(Math.max(0, (radius * radius) / chord2 - 1));
        const sign = large === sweep ? -1 : 1;
        const cx = (start[0] + end[0]) / 2 + sign * factor * dy;
        const cy = (start[1] + end[1]) / 2 + sign * factor * -dx;
        const theta = Math.atan2(start[1] - cy, start[0] - cx);
        const theta2 = Math.atan2(end[1] - cy, end[0] - cx);
        let delta = theta2 - theta;
        if (sweep && delta < 0) delta += Math.PI * 2;
        if (!sweep && delta > 0) delta -= Math.PI * 2;
        return { cx, cy, theta, delta };
    }

    function arcStep(radius) {
        const ratio = Math.max(-1, Math.min(1, 1 - CHORD_ERROR_MM / Math.max(radius, CHORD_ERROR_MM)));
        return 2 * Math.acos(ratio);
    }

    function axisAngles(theta, delta) {
        const end = theta + delta;
        const low = delta >= 0 ? theta : end;
        const high = delta >= 0 ? end : theta;
        const found = [];
        let candidate = Math.floor(low / (Math.PI / 2)) * (Math.PI / 2);
        while (candidate <= high + 1e-9) {
            if (candidate > low + 1e-9) found.push(candidate);
            candidate += Math.PI / 2;
        }
        return found;
    }

    function flattenBezier(p0, c1, c2, p1) {
        return adaptiveBezier(p0, c1, c2, p1, 0, MAX_VERTICES);
    }

    function adaptiveBezier(p0, c1, c2, p1, depth, budget) {
        if (![p0, c1, c2, p1].every((point) => Number.isFinite(point[0]) && Number.isFinite(point[1]))) return null;
        if (controlsWithinChord(p0, c1, c2, p1)) {
            return budget < 2 ? null : [p0, p1];
        }
        if (depth >= MAX_BEZIER_DEPTH || budget <= 2) return null;
        const parts = splitBezier(p0, c1, c2, p1);
        const left = adaptiveBezier(parts[0][0], parts[0][1], parts[0][2], parts[0][3], depth + 1, budget);
        if (!left) return null;
        const right = adaptiveBezier(
            parts[1][0], parts[1][1], parts[1][2], parts[1][3],
            depth + 1,
            budget - left.length + 1
        );
        if (!right) return null;
        return left.slice(0, -1).concat(right);
    }

    function splitBezier(p0, c1, c2, p1) {
        function mid(a, b) {
            return [(a[0] + b[0]) * 0.5, (a[1] + b[1]) * 0.5];
        }
        const a = mid(p0, c1);
        const b = mid(c1, c2);
        const c = mid(c2, p1);
        const d = mid(a, b);
        const e = mid(b, c);
        const f = mid(d, e);
        return [[p0, a, d, f], [f, e, c, p1]];
    }

    function controlsWithinChord(p0, c1, c2, p1) {
        const bound = chordDeviationBound(p0, c1, c2, p1);
        if (bound <= SHORT_CHORD_TOLERANCE_MM) return true;
        return bound <= LONG_CHORD_TOLERANCE_MM && distance(p0, p1) >= MIN_SAMPLE_MM;
    }

    function chordDeviationBound(p0, c1, c2, p1) {
        const dx = p1[0] - p0[0];
        const dy = p1[1] - p0[1];
        const length2 = dx * dx + dy * dy;
        if (length2 <= 1e-18) return Math.max(distance(c1, p0), distance(c2, p0));
        const length = Math.sqrt(length2);
        const along = (point) => ((point[0] - p0[0]) * dx + (point[1] - p0[1]) * dy) / length;
        const height = (point) => Math.abs((point[0] - p0[0]) * dy - (point[1] - p0[1]) * dx) / length;
        const span1 = along(c1);
        const span2 = along(c2);
        if (span1 >= 0 && span1 <= length && span2 >= 0 && span2 <= length) {
            return (4 / 9) * (height(c1) + height(c2));
        }
        return Math.max(distanceToSegment(c1, p0, p1), distanceToSegment(c2, p0, p1));
    }

    function distanceToSegment(point, start, end) {
        const dx = end[0] - start[0];
        const dy = end[1] - start[1];
        const length2 = dx * dx + dy * dy;
        if (length2 <= 1e-18) return distance(point, start);
        const ratio = ((point[0] - start[0]) * dx + (point[1] - start[1]) * dy) / length2;
        if (ratio <= 0) return distance(point, start);
        if (ratio >= 1) return distance(point, end);
        return Math.hypot(point[0] - (start[0] + ratio * dx), point[1] - (start[1] + ratio * dy));
    }

    function polygon(points, widthMm, lengthMm, pathId) {
        const kept = [];
        for (let index = 0; index < points.length; index += 1) {
            const point = points[index];
            if (!Number.isFinite(point[0]) || !Number.isFinite(point[1])) return rejected("non_finite", pathId);
            if (kept.length && distance(kept[kept.length - 1], point) < MIN_SAMPLE_MM) continue;
            kept.push(point);
        }
        if (kept.length >= 2 && distance(kept[0], kept[kept.length - 1]) < MIN_SAMPLE_MM) kept.pop();
        const compact = [];
        for (let index = 0; index < kept.length; index += 1) {
            const point = [roundCm(kept[index][0] / 10), roundCm(kept[index][1] / 10)];
            if (compact.length && compact[compact.length - 1][0] === point[0] && compact[compact.length - 1][1] === point[1]) {
                return rejected("zero_edge", pathId);
            }
            compact.push(point);
        }
        if (compact.length > MAX_VERTICES) return rejected("curve_unrepresentable", pathId);
        if (compact.length < 3) return rejected("invalid_area", pathId);
        const widthCm = roundCm(widthMm / 10);
        const lengthCm = roundCm(lengthMm / 10);
        if (compact.some((point) => point[0] < -STORAGE_EPSILON_CM || point[1] < -STORAGE_EPSILON_CM || point[0] > widthCm + STORAGE_EPSILON_CM || point[1] > lengthCm + STORAGE_EPSILON_CM)) {
            return rejected("outside_blank", pathId);
        }
        const xs = compact.map((point) => point[0]);
        const ys = compact.map((point) => point[1]);
        const spansBlank = Math.abs(Math.min.apply(null, xs)) <= STORAGE_EPSILON_CM
            && Math.abs(Math.max.apply(null, xs) - widthCm) <= STORAGE_EPSILON_CM
            && Math.abs(Math.min.apply(null, ys)) <= STORAGE_EPSILON_CM
            && Math.abs(Math.max.apply(null, ys) - lengthCm) <= STORAGE_EPSILON_CM;
        if (edgesCross(compact)) return rejected("self_intersection", pathId);
        if (Math.abs(area(compact)) <= STORAGE_EPSILON_CM) return rejected("invalid_area", pathId);
        return { status: "ready", points: compact, spansBlank };
    }

    function edgesCross(points) {
        const count = points.length;
        for (let index = 0; index < count; index += 1) {
            for (let other = index + 1; other < count; other += 1) {
                if (other === (index + 1) % count || (other + 1) % count === index) continue;
                if (properCross(points[index], points[(index + 1) % count], points[other], points[(other + 1) % count])) return true;
            }
        }
        return false;
    }

    function properCross(a, b, c, d) {
        return turn(a, b, c) * turn(a, b, d) < 0 && turn(c, d, a) * turn(c, d, b) < 0;
    }

    function turn(a, b, c) {
        return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0]);
    }

    function area(points) {
        let total = 0;
        points.forEach((point, index) => {
            const next = points[(index + 1) % points.length];
            total += point[0] * next[1] - next[0] * point[1];
        });
        return total / 2;
    }

    function distance(a, b) {
        return Math.hypot(b[0] - a[0], b[1] - a[1]);
    }

    function roundCm(value) {
        // Same half-even rule as Python round(value, 3). Half-up would store a
        // different centimetre point and let the preview accept another outline.
        const sign = value < 0 ? -1 : 1;
        const scaled = Math.abs(value) * 1000;
        const base = Math.floor(scaled);
        const fraction = scaled - base;
        let rounded = base;
        if (fraction > 0.5) rounded = base + 1;
        else if (fraction === 0.5) rounded = base % 2 === 0 ? base : base + 1;
        return (sign * rounded) / 1000;
    }

    window.AlmdinaBoardEditor = window.AlmdinaBoardEditor || {};
    window.AlmdinaBoardEditor.DrawingCompile = Object.freeze({
        MAX_VERTICES,
        CHORD_ERROR_MM,
        compile,
        messages: MESSAGES,
    });
})();
