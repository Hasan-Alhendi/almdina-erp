(() => {
    "use strict";

    // Drawing snap is door-local and screen-thresholded. It does not share
    // candidates or hysteresis with the board-move magnet in snap_geometry.js.
    const SNAP_PX = 8;
    const HOLD_PX = 12;
    const SWITCH_PX = 4;
    const PRIORITY = Object.freeze({
        endpoint: 1,
        intersection: 2,
        midpoint: 3,
        alignment: 4,
        grid: 5,
    });
    const GRID_STEPS = Object.freeze([1, 5, 10, 25, 50]);
    const LABEL_KEYS = Object.freeze({
        endpoint: "Endpoint",
        midpoint: "Midpoint",
        intersection: "Intersection",
        alignment: "Alignment",
        grid: "Grid",
        horizontal: "Horizontal",
        vertical: "Vertical",
    });

    function num(value) {
        const number = Number(value);
        return Number.isFinite(number) ? number : 0;
    }

    function quantize(value) {
        const number = Number(value);
        if (!Number.isFinite(number) || Math.abs(number) > 100000) return null;
        const quantized = Math.round((number + Number.EPSILON) * 1000) / 1000;
        return quantized === 0 ? 0 : quantized;
    }

    function point(x, y) {
        const qx = quantize(x);
        const qy = quantize(y);
        if (qx == null || qy == null) return null;
        return { x: qx, y: qy };
    }

    function hypot(a, b) {
        return Math.hypot(b.x - a.x, b.y - a.y);
    }

    function same(a, b) {
        const left = point(a && a.x, a && a.y);
        const right = point(b && b.x, b && b.y);
        return Boolean(left && right && left.x === right.x && left.y === right.y);
    }

    function thresholdMm(scale) {
        const pixels = Math.max(0.0001, num(scale) || 1);
        return SNAP_PX / pixels;
    }

    function distancePx(a, b, scale) {
        return hypot(a, b) * Math.max(0.0001, num(scale) || 1);
    }

    function defaultSettings() {
        return {
            enabled: true,
            endpoint: true,
            midpoint: true,
            intersection: true,
            alignment: true,
            grid: false,
            spacing: 10,
        };
    }

    function normalizeSettings(settings) {
        const source = settings || {};
        const spacing = GRID_STEPS.indexOf(Number(source.spacing)) >= 0 ? Number(source.spacing) : 10;
        return {
            enabled: source.enabled !== false,
            endpoint: source.endpoint !== false,
            midpoint: source.midpoint !== false,
            intersection: source.intersection !== false,
            alignment: source.alignment !== false,
            grid: source.grid === true,
            spacing,
        };
    }

    function snapAngle(anchor, target) {
        const Space = window.AlmdinaBoardEditor && window.AlmdinaBoardEditor.DrawingSpace;
        const angle = Math.atan2(target.y - anchor.y, target.x - anchor.x) * 180 / Math.PI;
        if (Space && Space.snapAngleDeg) return Space.snapAngleDeg(angle, true);
        let wrapped = angle % 360;
        if (wrapped < 0) wrapped += 360;
        const stepped = Math.round(wrapped / 15) * 15;
        return stepped === 360 ? 0 : stepped;
    }

    function rayPoint(anchor, length, angleDeg) {
        const Space = window.AlmdinaBoardEditor && window.AlmdinaBoardEditor.DrawingSpace;
        if (Space && Space.polarPoint) return Space.polarPoint(anchor, length, angleDeg);
        const rad = num(angleDeg) * Math.PI / 180;
        return {
            x: num(anchor.x) + num(length) * Math.cos(rad),
            y: num(anchor.y) + num(length) * Math.sin(rad),
        };
    }

    function projectOnRay(anchor, angleDeg, target) {
        const rad = num(angleDeg) * Math.PI / 180;
        const dx = Math.cos(rad);
        const dy = Math.sin(rad);
        const along = ((target.x - anchor.x) * dx) + ((target.y - anchor.y) * dy);
        if (!(along > 0.05)) return null;
        return point(anchor.x + (dx * along), anchor.y + (dy * along));
    }

    function perpToRay(anchor, angleDeg, target) {
        const projected = projectOnRay(anchor, angleDeg, target);
        if (!projected) return Infinity;
        return hypot(target, projected);
    }

    function arcCenter(start, end, radius, largeArc, sweepClockwise) {
        const chord = hypot(start, end);
        const absRadius = Math.abs(num(radius));
        if (!(chord > 0) || absRadius + 1e-6 < chord / 2) return null;
        const radiusMm = Math.max(absRadius, chord / 2);
        const mx = (start.x + end.x) / 2;
        const my = (start.y + end.y) / 2;
        const dx = (start.x - end.x) / 2;
        const dy = (start.y - end.y) / 2;
        const denom = (radiusMm * radiusMm * dy * dy) + (radiusMm * radiusMm * dx * dx);
        const numer = (radiusMm * radiusMm * radiusMm * radiusMm) - (radiusMm * radiusMm * dy * dy) - (radiusMm * radiusMm * dx * dx);
        if (!(denom > 0) || numer < -1e-6) return null;
        let factor = Math.sqrt(Math.max(0, numer / denom));
        if (Boolean(largeArc) === Boolean(sweepClockwise)) factor = -factor;
        return point(mx + (factor * dy), my - (factor * dx));
    }

    function signedSweep(center, start, end, sweepClockwise, largeArc) {
        const startAngle = Math.atan2(start.y - center.y, start.x - center.x);
        const endAngle = Math.atan2(end.y - center.y, end.x - center.x);
        let delta = endAngle - startAngle;
        while (delta <= -Math.PI) delta += Math.PI * 2;
        while (delta > Math.PI) delta -= Math.PI * 2;
        const shortIsClockwise = delta >= 0;
        let sweep = delta;
        if (Boolean(sweepClockwise) !== shortIsClockwise) {
            sweep = delta > 0 ? delta - (Math.PI * 2) : delta + (Math.PI * 2);
        }
        if (largeArc && Math.abs(sweep) < Math.PI - 1e-4) {
            sweep = sweep > 0 ? sweep - (Math.PI * 2) : sweep + (Math.PI * 2);
        }
        if (!largeArc && Math.abs(sweep) > Math.PI + 1e-4) {
            sweep = sweep > 0 ? sweep - (Math.PI * 2) : sweep + (Math.PI * 2);
        }
        void startAngle;
        return sweep;
    }

    function arcPoint(center, radius, angle) {
        return point(center.x + (radius * Math.cos(angle)), center.y + (radius * Math.sin(angle)));
    }

    function angleOnSweep(center, target, startAngle, sweep) {
        const angle = Math.atan2(target.y - center.y, target.x - center.x);
        let delta = angle - startAngle;
        if (sweep >= 0) {
            while (delta < -1e-6) delta += Math.PI * 2;
            while (delta > Math.PI * 2 + 1e-6) delta -= Math.PI * 2;
            return delta <= sweep + 1e-4;
        }
        while (delta > 1e-6) delta -= Math.PI * 2;
        while (delta < -Math.PI * 2 - 1e-6) delta += Math.PI * 2;
        return delta >= sweep - 1e-4;
    }

    function bezierAt(segment, t) {
        const u = 1 - t;
        return {
            x: (u * u * u * segment.a.x) + (3 * u * u * t * segment.c1.x) + (3 * u * t * t * segment.c2.x) + (t * t * t * segment.b.x),
            y: (u * u * u * segment.a.y) + (3 * u * u * t * segment.c1.y) + (3 * u * t * t * segment.c2.y) + (t * t * t * segment.b.y),
        };
    }

    function bezierLengthPoint(segment) {
        const steps = 32;
        const samples = [];
        for (let index = 0; index <= steps; index += 1) samples.push(bezierAt(segment, index / steps));
        let total = 0;
        const lengths = [];
        for (let index = 1; index < samples.length; index += 1) {
            const length = hypot(samples[index - 1], samples[index]);
            lengths.push(length);
            total += length;
        }
        if (!(total > 0)) return point(segment.a.x, segment.a.y);
        let walked = 0;
        const half = total / 2;
        for (let index = 0; index < lengths.length; index += 1) {
            if (walked + lengths[index] >= half) {
                const ratio = lengths[index] ? (half - walked) / lengths[index] : 0;
                const from = samples[index];
                const to = samples[index + 1];
                return point(from.x + ((to.x - from.x) * ratio), from.y + ((to.y - from.y) * ratio));
            }
            walked += lengths[index];
        }
        return point(segment.b.x, segment.b.y);
    }

    function lineHit(a, b, c, d) {
        const rx = b.x - a.x;
        const ry = b.y - a.y;
        const sx = d.x - c.x;
        const sy = d.y - c.y;
        const denom = (rx * sy) - (ry * sx);
        if (Math.abs(denom) < 1e-8) return null;
        const qpx = c.x - a.x;
        const qpy = c.y - a.y;
        const t = ((qpx * sy) - (qpy * sx)) / denom;
        const u = ((qpx * ry) - (qpy * rx)) / denom;
        if (t < -1e-6 || t > 1 + 1e-6 || u < -1e-6 || u > 1 + 1e-6) return null;
        return point(a.x + (t * rx), a.y + (t * ry));
    }

    function lineCircleHits(a, b, center, radius) {
        const dx = b.x - a.x;
        const dy = b.y - a.y;
        const fx = a.x - center.x;
        const fy = a.y - center.y;
        const aa = (dx * dx) + (dy * dy);
        if (!(aa > 0)) return [];
        const bb = 2 * ((fx * dx) + (fy * dy));
        const cc = (fx * fx) + (fy * fy) - (radius * radius);
        const disc = (bb * bb) - (4 * aa * cc);
        if (disc < -1e-6) return [];
        const roots = disc <= 1e-6
            ? [-bb / (2 * aa)]
            : [(-bb - Math.sqrt(disc)) / (2 * aa), (-bb + Math.sqrt(disc)) / (2 * aa)];
        const hits = [];
        roots.forEach((t) => {
            if (t < -1e-6 || t > 1 + 1e-6) return;
            const hit = point(a.x + (t * dx), a.y + (t * dy));
            if (hit) hits.push(hit);
        });
        return hits;
    }

    function nearBox(segment, pointer, limit) {
        const xs = [segment.a.x, segment.b.x];
        const ys = [segment.a.y, segment.b.y];
        if (segment.c1) {
            xs.push(segment.c1.x, segment.c2.x);
            ys.push(segment.c1.y, segment.c2.y);
        }
        if (segment.center) {
            xs.push(segment.center.x - segment.radius, segment.center.x + segment.radius);
            ys.push(segment.center.y - segment.radius, segment.center.y + segment.radius);
        }
        const minX = Math.min.apply(null, xs) - limit;
        const maxX = Math.max.apply(null, xs) + limit;
        const minY = Math.min.apply(null, ys) - limit;
        const maxY = Math.max.apply(null, ys) + limit;
        return pointer.x >= minX && pointer.x <= maxX && pointer.y >= minY && pointer.y <= maxY;
    }

    function excludedNode(segment, exclude) {
        if (!exclude || !exclude.nodeId) return false;
        return segment.pathId === exclude.pathId && (segment.nodeIds || []).indexOf(exclude.nodeId) >= 0;
    }

    function pushEndpoint(index, raw, meta) {
        const next = point(raw.x, raw.y);
        if (!next) return;
        index.endpoints.push(Object.assign({ point: next, align: false }, meta));
    }

    function pushLine(index, a, b, meta) {
        const start = point(a.x, a.y);
        const end = point(b.x, b.y);
        if (!start || !end || same(start, end)) return;
        index.lines.push(Object.assign({ kind: "line", a: start, b: end }, meta));
    }

    function shapeSpace() {
        return window.AlmdinaBoardEditor && window.AlmdinaBoardEditor.DrawingSpace;
    }

    function addPolygon(index, points, closed, meta) {
        points.forEach((vertex, vertexIndex) => {
            pushEndpoint(index, vertex, {
                type: "endpoint",
                sourceId: `${meta.sourceId}:v${vertexIndex}`,
                pathId: meta.pathId || null,
                nodeId: meta.nodeId || null,
                align: true,
                closes: false,
            });
        });
        for (let vertexIndex = 0; vertexIndex < points.length - (closed ? 0 : 1); vertexIndex += 1) {
            const endIndex = (vertexIndex + 1) % points.length;
            if (!closed && endIndex === 0) break;
            pushLine(index, points[vertexIndex], points[endIndex], {
                sourceId: `${meta.sourceId}:e${vertexIndex}`,
                pathId: meta.pathId || null,
                nodeIds: [],
            });
        }
    }

    function addCircle(index, center, radius, sourceId) {
        const origin = point(center.x, center.y);
        if (!origin || !(radius > 0)) return;
        index.circles.push({ center: origin, radius, sourceId });
        [[radius, 0], [0, radius], [-radius, 0], [0, -radius]].forEach((offset, offsetIndex) => {
            pushEndpoint(index, { x: origin.x + offset[0], y: origin.y + offset[1] }, {
                type: "endpoint",
                sourceId: `${sourceId}:cardinal${offsetIndex}`,
                align: true,
                closes: false,
            });
        });
    }

    function addArc(index, center, radius, start, end, sweepClockwise, largeArc, sourceId, pathId) {
        const origin = point(center.x, center.y);
        const a = point(start.x, start.y);
        const b = point(end.x, end.y);
        if (!origin || !a || !b || !(radius > 0)) return;
        const startAngle = Math.atan2(a.y - origin.y, a.x - origin.x);
        const sweep = signedSweep(origin, a, b, sweepClockwise, largeArc);
        index.arcs.push({
            a,
            b,
            center: origin,
            radius,
            startAngle,
            sweep,
            sourceId,
            pathId: pathId || null,
            nodeIds: [],
        });
        pushEndpoint(index, a, { type: "endpoint", sourceId: `${sourceId}:start`, pathId, align: true, closes: false });
        pushEndpoint(index, b, { type: "endpoint", sourceId: `${sourceId}:end`, pathId, align: true, closes: false });
    }

    function buildIndex(document) {
        const index = { endpoints: [], lines: [], arcs: [], circles: [], beziers: [] };
        const source = document || {};
        (source.paths || []).forEach((path) => {
            const nodes = {};
            (path.nodes || []).forEach((node) => {
                nodes[node.id] = node;
            });
            const alignAll = (path.nodes || []).length <= 16 || path.closed === true && (path.nodes || []).length <= 32;
            (path.nodes || []).forEach((node, nodeIndex) => {
                const terminal = nodeIndex === 0 || nodeIndex === path.nodes.length - 1;
                pushEndpoint(index, { x: node.x_mm, y: node.y_mm }, {
                    type: "endpoint",
                    sourceId: `${path.id}:${node.id}`,
                    pathId: path.id,
                    nodeId: node.id,
                    align: alignAll || terminal || path.closed === true,
                    closes: path.closed !== true && nodeIndex === 0 && path.segments && path.segments.length > 0,
                });
            });
            (path.segments || []).forEach((segment) => {
                const from = nodes[segment.from_node];
                const to = nodes[segment.to_node];
                if (!from || !to) return;
                const meta = {
                    sourceId: `${path.id}:${segment.id}`,
                    pathId: path.id,
                    nodeIds: [segment.from_node, segment.to_node],
                };
                if (segment.kind === "line") {
                    pushLine(index, { x: from.x_mm, y: from.y_mm }, { x: to.x_mm, y: to.y_mm }, meta);
                } else if (segment.kind === "bezier" && segment.controls && segment.controls.length === 2) {
                    const a = point(from.x_mm, from.y_mm);
                    const b = point(to.x_mm, to.y_mm);
                    const c1 = point(segment.controls[0].x_mm, segment.controls[0].y_mm);
                    const c2 = point(segment.controls[1].x_mm, segment.controls[1].y_mm);
                    if (a && b && c1 && c2) index.beziers.push(Object.assign({ kind: "bezier", a, b, c1, c2 }, meta));
                } else if (segment.kind === "arc") {
                    const start = { x: from.x_mm, y: from.y_mm };
                    const end = { x: to.x_mm, y: to.y_mm };
                    const center = arcCenter(start, end, segment.radius_mm, segment.large_arc === true, segment.sweep_clockwise === true);
                    if (center) {
                        addArc(
                            index,
                            center,
                            segment.radius_mm,
                            start,
                            end,
                            segment.sweep_clockwise === true,
                            segment.large_arc === true,
                            meta.sourceId,
                            path.id
                        );
                        index.arcs[index.arcs.length - 1].nodeIds = meta.nodeIds;
                    }
                }
            });
        });
        const Space = shapeSpace();
        (source.shapes || []).forEach((shape) => {
            if (!shape || shape.exploded || !Space || !Space.normalizeShape) return;
            const built = Space.normalizeShape(shape.kind, shape.params);
            if (!built || !built.ok || !built.figure) return;
            const figure = built.figure;
            const sourceId = shape.id;
            if (shape.kind === "circle") {
                addCircle(index, { x: shape.params.cx_mm, y: shape.params.cy_mm }, shape.params.radius_mm, sourceId);
                return;
            }
            if (shape.kind === "ellipse") {
                const rotation = num(shape.params.rotation_deg) * Math.PI / 180;
                const cos = Math.cos(rotation);
                const sin = Math.sin(rotation);
                [[shape.params.rx_mm, 0], [0, shape.params.ry_mm], [-shape.params.rx_mm, 0], [0, -shape.params.ry_mm]].forEach((offset, offsetIndex) => {
                    pushEndpoint(index, {
                        x: shape.params.cx_mm + (offset[0] * cos) - (offset[1] * sin),
                        y: shape.params.cy_mm + (offset[0] * sin) + (offset[1] * cos),
                    }, {
                        type: "endpoint",
                        sourceId: `${sourceId}:extent${offsetIndex}`,
                        align: true,
                        closes: false,
                    });
                });
                return;
            }
            if (shape.kind === "arc") {
                const start = figure.points[0];
                const end = figure.points[figure.points.length - 1];
                addArc(
                    index,
                    { x: shape.params.cx_mm, y: shape.params.cy_mm },
                    shape.params.radius_mm,
                    start,
                    end,
                    shape.params.sweep_angle_deg > 0,
                    Math.abs(shape.params.sweep_angle_deg) > 180,
                    sourceId,
                    null
                );
                return;
            }
            if (figure.points && figure.points.length >= 2) {
                addPolygon(index, figure.points, figure.closed !== false, { sourceId });
            }
        });
        return index;
    }

    function candidate(type, raw, scale, pointer, extra) {
        const next = point(raw.x, raw.y);
        if (!next) return null;
        const distance = distancePx(pointer, next, scale);
        return Object.assign({
            type,
            point: next,
            distancePx: distance,
            priority: PRIORITY[type] || 9,
            sourceId: "",
            labelKey: LABEL_KEYS[type] || "Endpoint",
            guide: null,
            closes: false,
        }, extra || {}, { point: next, distancePx: distance });
    }

    function blocked(hit, blockPoints) {
        return (blockPoints || []).some((entry) => same(entry, hit));
    }

    function collect(spec) {
        const index = spec.index || { endpoints: [], lines: [], arcs: [], circles: [], beziers: [] };
        const settings = normalizeSettings(spec.settings);
        const pointer = spec.pointer;
        const scale = Math.max(0.0001, num(spec.scale) || 1);
        const limit = thresholdMm(scale);
        const found = [];
        const exclude = spec.exclude || null;
        if (settings.endpoint) {
            index.endpoints.forEach((entry) => {
                if (exclude && entry.nodeId && entry.pathId === exclude.pathId && entry.nodeId === exclude.nodeId) return;
                if (hypot(pointer, entry.point) > limit) return;
                found.push(candidate("endpoint", entry.point, scale, pointer, {
                    sourceId: entry.sourceId,
                    closes: entry.closes === true && exclude && entry.pathId === exclude.pathId,
                    labelKey: "Endpoint",
                }));
            });
        }
        const lines = index.lines.filter((segment) => nearBox(segment, pointer, limit)).slice(0, 48);
        const arcs = index.arcs.filter((segment) => nearBox(segment, pointer, limit)).slice(0, 24);
        const beziers = index.beziers.filter((segment) => nearBox(segment, pointer, limit)).slice(0, 24);
        if (settings.midpoint) {
            lines.forEach((segment) => {
                found.push(candidate("midpoint", {
                    x: (segment.a.x + segment.b.x) / 2,
                    y: (segment.a.y + segment.b.y) / 2,
                }, scale, pointer, { sourceId: segment.sourceId, labelKey: "Midpoint" }));
            });
            arcs.forEach((segment) => {
                const mid = arcPoint(segment.center, segment.radius, segment.startAngle + (segment.sweep / 2));
                if (mid) found.push(candidate("midpoint", mid, scale, pointer, { sourceId: segment.sourceId, labelKey: "Midpoint" }));
            });
            beziers.forEach((segment) => {
                const mid = bezierLengthPoint(segment);
                if (mid) found.push(candidate("midpoint", mid, scale, pointer, { sourceId: segment.sourceId, labelKey: "Midpoint" }));
            });
        }
        if (settings.intersection) {
            for (let left = 0; left < lines.length; left += 1) {
                for (let right = left + 1; right < lines.length; right += 1) {
                    if (excludedNode(lines[left], exclude) && excludedNode(lines[right], exclude)) continue;
                    const hit = lineHit(lines[left].a, lines[left].b, lines[right].a, lines[right].b);
                    if (!hit || hypot(pointer, hit) > limit) continue;
                    found.push(candidate("intersection", hit, scale, pointer, {
                        sourceId: `${lines[left].sourceId}+${lines[right].sourceId}`,
                        labelKey: "Intersection",
                    }));
                }
                index.circles.forEach((circle) => {
                    if (hypot(pointer, circle.center) > circle.radius + limit) return;
                    lineCircleHits(lines[left].a, lines[left].b, circle.center, circle.radius).forEach((hit) => {
                        if (hypot(pointer, hit) > limit) return;
                        found.push(candidate("intersection", hit, scale, pointer, {
                            sourceId: `${lines[left].sourceId}+${circle.sourceId}`,
                            labelKey: "Intersection",
                        }));
                    });
                });
                arcs.forEach((arc) => {
                    lineCircleHits(lines[left].a, lines[left].b, arc.center, arc.radius).forEach((hit) => {
                        if (!angleOnSweep(arc.center, hit, arc.startAngle, arc.sweep)) return;
                        if (hypot(pointer, hit) > limit) return;
                        found.push(candidate("intersection", hit, scale, pointer, {
                            sourceId: `${lines[left].sourceId}+${arc.sourceId}`,
                            labelKey: "Intersection",
                        }));
                    });
                });
            }
        }
        if (settings.alignment && spec.anchor) {
            const axis = spec.anchor;
            if (Math.abs(pointer.y - axis.y) <= limit && Math.abs(pointer.y - axis.y) > 0.05) {
                found.push(candidate("alignment", { x: pointer.x, y: axis.y }, scale, pointer, {
                    sourceId: `h:${axis.x}:${axis.y}`,
                    labelKey: "Horizontal",
                    guide: { x1: axis.x, y1: axis.y, x2: pointer.x, y2: axis.y },
                }));
            }
            if (Math.abs(pointer.x - axis.x) <= limit && Math.abs(pointer.x - axis.x) > 0.05) {
                found.push(candidate("alignment", { x: axis.x, y: pointer.y }, scale, pointer, {
                    sourceId: `v:${axis.x}:${axis.y}`,
                    labelKey: "Vertical",
                    guide: { x1: axis.x, y1: axis.y, x2: axis.x, y2: pointer.y },
                }));
            }
        }
        if (settings.grid) {
            const spacing = settings.spacing;
            const hit = point(
                Math.round(pointer.x / spacing) * spacing,
                Math.round(pointer.y / spacing) * spacing
            );
            if (hit && hypot(pointer, hit) <= limit) {
                found.push(candidate("grid", hit, scale, pointer, { sourceId: `grid:${spacing}`, labelKey: "Grid" }));
            }
        }
        return found.filter((entry) => entry && entry.distancePx <= SNAP_PX + 0.01 && !blocked(entry.point, spec.blockPoints));
    }

    function better(current, next) {
        if (!current) return next;
        if (next.distancePx + 0.01 < current.distancePx - SWITCH_PX) return next;
        if (current.distancePx + 0.01 < next.distancePx - SWITCH_PX) return current;
        if (next.closes && !current.closes && Math.abs(next.distancePx - current.distancePx) <= SWITCH_PX) return next;
        if (current.closes && !next.closes && Math.abs(next.distancePx - current.distancePx) <= SWITCH_PX) return current;
        if (next.priority !== current.priority) return next.priority < current.priority ? next : current;
        return next.distancePx < current.distancePx ? next : current;
    }

    function heldStill(hold, pointer, scale) {
        if (!hold || !hold.point) return false;
        return distancePx(pointer, hold.point, scale) <= HOLD_PX;
    }

    function choose(found, hold, pointer, scale) {
        let best = null;
        found.forEach((entry) => {
            best = better(best, entry);
        });
        if (hold && hold.point && heldStill(hold, pointer, scale)) {
            const heldDistance = distancePx(pointer, hold.point, scale);
            const held = Object.assign({}, hold, { distancePx: heldDistance });
            if (!best) return heldDistance <= HOLD_PX ? held : null;
            if (same(best.point, hold.point)) return Object.assign({}, best, { distancePx: heldDistance });
            if (heldDistance - best.distancePx < SWITCH_PX) return held;
        }
        return best;
    }

    function applyShift(anchor, pointer, snap) {
        const length = hypot(anchor, pointer);
        if (!(length > 0)) return { point: { x: anchor.x, y: anchor.y }, snap: null };
        const angle = snapAngle(anchor, pointer);
        const constrained = point(rayPoint(anchor, length, angle).x, rayPoint(anchor, length, angle).y);
        if (!snap) return { point: constrained || pointer, snap: null, angle };
        if (perpToRay(anchor, angle, snap.point) > 0.5) return { point: constrained || pointer, snap: null, angle };
        const projected = projectOnRay(anchor, angle, snap.point);
        if (!projected) return { point: constrained || pointer, snap: null, angle };
        return {
            point: projected,
            angle,
            snap: Object.assign({}, snap, { point: projected, shifted: true }),
        };
    }

    function resolve(spec) {
        const input = spec || {};
        const pointer = input.pointer || { x: 0, y: 0 };
        const settings = normalizeSettings(input.settings);
        if (!settings.enabled || input.alt === true) {
            return { point: { x: num(pointer.x), y: num(pointer.y) }, snap: null };
        }
        const scale = Math.max(0.0001, num(input.scale) || 1);
        const found = collect(input);
        let snap = choose(found, input.hold, pointer, scale);
        if (snap && snap.distancePx > SNAP_PX && !(input.hold && same(input.hold.point, snap.point))) snap = null;
        if (input.shift && input.anchor) return applyShift(input.anchor, pointer, snap);
        if (!snap) return { point: { x: num(pointer.x), y: num(pointer.y) }, snap: null };
        return { point: snap.point, snap };
    }

    window.AlmdinaBoardEditor = window.AlmdinaBoardEditor || {};
    window.AlmdinaBoardEditor.DrawingSnap = Object.freeze({
        SNAP_PX,
        HOLD_PX,
        SWITCH_PX,
        PRIORITY,
        GRID_STEPS,
        defaultSettings,
        normalizeSettings,
        thresholdMm,
        buildIndex,
        resolve,
        bezierLengthPoint,
        arcCenter,
    });
})();
