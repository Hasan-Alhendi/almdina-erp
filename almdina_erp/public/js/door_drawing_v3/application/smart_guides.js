(() => {
    "use strict";

    const root = window.AlmdinaDoorDrawingV3 = window.AlmdinaDoorDrawingV3 || Object.create(null);
    const Base = root.Snapping;
    const G = root.Geometry;
    if (!Base || !G) throw new Error("Door Drawing V3 snapping and geometry must load before smart guides");

    const SURFACE_SNAP_PX = 14;
    const ALIGN_SNAP_PX = 9;
    const EQUAL_LENGTH_SNAP_PX = 10;
    const PARALLEL_TOLERANCE_DEG = 2;

    function clamp01(value) { return Math.max(0, Math.min(1, Number(value) || 0)); }
    function angleDistance180(a, b) {
        const delta = Math.abs((((Number(a) || 0) - (Number(b) || 0)) % 180 + 180) % 180);
        return Math.min(delta, 180 - delta);
    }

    function projectSegment(point, start, end) {
        const p = G.point(point && point.x, point && point.y);
        const a = G.point(start && start.x, start && start.y);
        const b = G.point(end && end.x, end && end.y);
        const dx = b.x - a.x, dy = b.y - a.y;
        const len2 = dx * dx + dy * dy;
        if (len2 <= G.EPSILON_MM * G.EPSILON_MM) return null;
        const t = clamp01(((p.x - a.x) * dx + (p.y - a.y) * dy) / len2);
        const projected = G.point(a.x + dx * t, a.y + dy * t);
        return Object.freeze({ point: projected, distanceMm: G.distance(p, projected), t, start: a, end: b });
    }

    function lineSegmentsForObject(object) {
        if (!object || !object.geometry) return [];
        const g = object.geometry;
        if (object.type === "line") return [{ objectId: object.id, role: "segment", start: g.start, end: g.end, priority: 100, curved: false }];
        if (object.type === "rectangle") {
            const bl = g.origin;
            const br = G.point(g.origin.x + g.widthMm, g.origin.y);
            const tr = G.point(g.origin.x + g.widthMm, g.origin.y + g.heightMm);
            const tl = G.point(g.origin.x, g.origin.y + g.heightMm);
            return [
                { objectId: object.id, role: "bottom", start: bl, end: br, priority: 90, curved: false },
                { objectId: object.id, role: "right", start: br, end: tr, priority: 90, curved: false },
                { objectId: object.id, role: "top", start: tr, end: tl, priority: 90, curved: false },
                { objectId: object.id, role: "left", start: tl, end: bl, priority: 90, curved: false },
            ];
        }
        if (G.PATH_TYPE && object.type === G.PATH_TYPE && typeof G.pathSegments === "function") {
            return G.pathSegments(object).map(segment => ({
                objectId: object.id,
                role: `segment-${segment.index}`,
                start: segment.start,
                end: segment.end,
                c1: segment.c1 || null,
                c2: segment.c2 || null,
                curved: Boolean(segment.curved),
                priority: 110,
            }));
        }
        return [];
    }

    function collectSegments(document, options = {}) {
        const excluded = new Set((Array.isArray(options.excludeIds) ? options.excludeIds : [options.excludeId]).filter(Boolean).map(String));
        const segments = [];
        for (const object of (document && document.objects) || []) {
            if (excluded.has(String(object.id))) continue;
            segments.push(...lineSegmentsForObject(object));
        }
        return segments;
    }

    function nearestSurface(document, candidate, toleranceMm, options = {}) {
        let best = null;
        for (const segment of collectSegments(document, options)) {
            if (segment.curved) continue;
            const projection = projectSegment(candidate, segment.start, segment.end);
            if (!projection || projection.distanceMm > toleranceMm) continue;
            const endpointEpsilon = 0.02;
            if (projection.t <= endpointEpsilon || projection.t >= 1 - endpointEpsilon) continue;
            if (!best || projection.distanceMm < best.distanceMm - G.EPSILON_MM || (Math.abs(projection.distanceMm - best.distanceMm) <= G.EPSILON_MM && segment.priority > best.segment.priority)) {
                best = { segment, ...projection };
            }
        }
        return best;
    }

    function anchorAlignment(document, point, toleranceMm, options = {}) {
        const anchors = Base.collectAnchors(document, options);
        let bestX = null, bestY = null;
        for (const anchor of anchors) {
            const dx = Math.abs(anchor.point.x - point.x);
            const dy = Math.abs(anchor.point.y - point.y);
            if (dx <= toleranceMm && (!bestX || dx < bestX.distanceMm - G.EPSILON_MM || (Math.abs(dx - bestX.distanceMm) <= G.EPSILON_MM && anchor.priority > bestX.anchor.priority))) bestX = { anchor, distanceMm: dx };
            if (dy <= toleranceMm && (!bestY || dy < bestY.distanceMm - G.EPSILON_MM || (Math.abs(dy - bestY.distanceMm) <= G.EPSILON_MM && anchor.priority > bestY.anchor.priority))) bestY = { anchor, distanceMm: dy };
        }
        return { bestX, bestY };
    }

    function equalLengthCandidate(document, start, candidate, toleranceMm, options = {}) {
        if (!start) return null;
        const a = G.point(start.x, start.y), p = G.point(candidate.x, candidate.y);
        const requestedLength = G.distance(a, p);
        if (requestedLength <= G.EPSILON_MM) return null;
        const requestedAngle = G.angleDeg(a, p);
        let best = null;
        for (const segment of collectSegments(document, options)) {
            if (segment.curved) continue;
            const length = G.distance(segment.start, segment.end);
            if (length <= G.EPSILON_MM) continue;
            const segmentAngle = G.angleDeg(segment.start, segment.end);
            if (angleDistance180(requestedAngle, segmentAngle) > PARALLEL_TOLERANCE_DEG) continue;
            const deltaLength = Math.abs(length - requestedLength);
            if (deltaLength > toleranceMm) continue;
            if (!best || deltaLength < best.deltaLength - G.EPSILON_MM) best = { segment, length, deltaLength };
        }
        if (!best) return null;
        const exact = G.pointAt(a, best.length, requestedAngle);
        return { point: exact, segment: best.segment, distanceMm: best.deltaLength, lengthMm: best.length };
    }

    function smartGuide(type, point, targetPoint, extra = {}) {
        return Object.freeze({ type, point: G.point(point.x, point.y), targetPoint: targetPoint ? G.point(targetPoint.x, targetPoint.y) : null, ...extra });
    }

    function resolvePoint(document, candidate, options = {}) {
        const raw = G.point(candidate && candidate.x, candidate && candidate.y);
        const base = Base.resolvePoint(document, raw, options);
        if (base.snapped) return base;

        const scale = options.viewportScale;
        const surfaceToleranceMm = Base.worldTolerance(scale, options.surfaceSnapPx || SURFACE_SNAP_PX);
        const alignToleranceMm = Base.worldTolerance(scale, options.alignSnapPx || ALIGN_SNAP_PX);
        const equalToleranceMm = Base.worldTolerance(scale, options.equalLengthSnapPx || EQUAL_LENGTH_SNAP_PX);
        const reference = options.anchor ? G.point(options.anchor.x, options.anchor.y) : null;
        const axis = base.axis;
        let point = base.point;

        if (!reference) {
            const surface = nearestSurface(document, raw, surfaceToleranceMm, options);
            if (surface) {
                const target = Object.freeze({ objectId: String(surface.segment.objectId), role: surface.segment.role, point: surface.point, priority: surface.segment.priority, kind: "surface" });
                return Object.freeze({ ...base, point: surface.point, snapped: true, target, distanceMm: G.roundMm(surface.distanceMm), kind: "surface", smartGuide: smartGuide("surface", surface.point, null, { objectId: String(surface.segment.objectId), role: surface.segment.role }) });
            }
        }

        if (reference && axis === "vertical") {
            const { bestY } = anchorAlignment(document, point, alignToleranceMm, options);
            if (bestY) {
                const aligned = G.point(reference.x, bestY.anchor.point.y);
                return Object.freeze({ ...base, point: aligned, snapped: true, target: bestY.anchor, distanceMm: G.roundMm(bestY.distanceMm), kind: "alignment", smartGuide: smartGuide("horizontal-alignment", aligned, bestY.anchor.point, { axis: "horizontal" }) });
            }
        }
        if (reference && axis === "horizontal") {
            const { bestX } = anchorAlignment(document, point, alignToleranceMm, options);
            if (bestX) {
                const aligned = G.point(bestX.anchor.point.x, reference.y);
                return Object.freeze({ ...base, point: aligned, snapped: true, target: bestX.anchor, distanceMm: G.roundMm(bestX.distanceMm), kind: "alignment", smartGuide: smartGuide("vertical-alignment", aligned, bestX.anchor.point, { axis: "vertical" }) });
            }
        }

        if (!axis) {
            const { bestX, bestY } = anchorAlignment(document, point, alignToleranceMm, options);
            if (bestX || bestY) {
                const aligned = G.point(bestX ? bestX.anchor.point.x : point.x, bestY ? bestY.anchor.point.y : point.y);
                const target = bestX && bestY ? (bestX.distanceMm <= bestY.distanceMm ? bestX.anchor : bestY.anchor) : (bestX ? bestX.anchor : bestY.anchor);
                const guideType = bestX && bestY ? "xy-alignment" : bestX ? "vertical-alignment" : "horizontal-alignment";
                return Object.freeze({ ...base, point: aligned, snapped: true, target, distanceMm: G.roundMm(Math.min(bestX ? bestX.distanceMm : Infinity, bestY ? bestY.distanceMm : Infinity)), kind: "alignment", smartGuide: smartGuide(guideType, aligned, target.point, { xAnchor: bestX ? bestX.anchor : null, yAnchor: bestY ? bestY.anchor : null }) });
            }
        }

        if (reference) {
            const equal = equalLengthCandidate(document, reference, point, equalToleranceMm, options);
            if (equal) {
                let exact = equal.point;
                if (axis === "vertical") exact = G.point(reference.x, reference.y + Math.sign(point.y - reference.y || 1) * equal.lengthMm);
                if (axis === "horizontal") exact = G.point(reference.x + Math.sign(point.x - reference.x || 1) * equal.lengthMm, reference.y);
                const target = Object.freeze({ objectId: String(equal.segment.objectId), role: equal.segment.role, point: equal.segment.end, priority: equal.segment.priority, kind: "equal-length" });
                return Object.freeze({ ...base, point: exact, snapped: true, target, distanceMm: G.roundMm(equal.distanceMm), kind: "equal-length", smartGuide: smartGuide("equal-length", exact, equal.segment.end, { lengthMm: equal.lengthMm, objectId: String(equal.segment.objectId), role: equal.segment.role }) });
            }
        }

        return base;
    }

    root.Snapping = Object.freeze({ ...Base, SURFACE_SNAP_PX, ALIGN_SNAP_PX, EQUAL_LENGTH_SNAP_PX, PARALLEL_TOLERANCE_DEG, projectSegment, collectSegments, nearestSurface, anchorAlignment, equalLengthCandidate, resolvePoint });
    root.SmartGuides = Object.freeze({ SURFACE_SNAP_PX, ALIGN_SNAP_PX, EQUAL_LENGTH_SNAP_PX, projectSegment, collectSegments, nearestSurface, anchorAlignment, equalLengthCandidate });
})();
