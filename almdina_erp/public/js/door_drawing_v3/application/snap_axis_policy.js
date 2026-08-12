(() => {
    "use strict";

    const root = window.AlmdinaDoorDrawingV3 = window.AlmdinaDoorDrawingV3 || Object.create(null);
    const Base = root.Snapping;
    const G = root.Geometry;
    if (!Base || !G || !Base.UnifiedSnapEngine && !root.UnifiedSnapEngine) {
        throw new Error("Door Drawing V3 unified snap engine must load before axis snap policy");
    }

    const DISABLE_GEOMETRIC_SNAP_PX = 0.000001;

    function axisCompatible(point, axis, reference) {
        if (!point || !reference || !axis) return true;
        if (axis === "vertical") return Math.abs(point.x - reference.x) <= Base.AXIS_EPSILON_MM;
        if (axis === "horizontal") return Math.abs(point.y - reference.y) <= Base.AXIS_EPSILON_MM;
        return true;
    }

    function score(kind, priority, distanceMm) {
        const rank = Base.INTENT_RANK && Base.INTENT_RANK[kind] || 0;
        return rank * 100000 + (Number(priority) || 0) * 100 - (Number(distanceMm) || 0);
    }

    function nearestCompatibleFeature(source, targets, toleranceMm, kind, axis, reference) {
        let best = null;
        for (const target of targets || []) {
            if (target.kind !== kind || !axisCompatible(target.point, axis, reference)) continue;
            const distanceMm = G.distance(source.point, target.point);
            if (distanceMm > toleranceMm) continue;
            const candidate = { target, distanceMm, kind };
            if (!best || score(kind, target.priority, distanceMm) > score(best.kind, best.target.priority, best.distanceMm)) best = candidate;
        }
        return best;
    }

    function nearestCompatibleSurface(document, source, toleranceMm, options, axis, reference) {
        let best = null;
        for (const segment of Base.collectSegments(document, options)) {
            const projection = Base.projectSegment(source.point, segment.start, segment.end);
            if (!projection || projection.distanceMm > toleranceMm) continue;
            if (!axisCompatible(projection.point, axis, reference)) continue;
            const target = Object.freeze({
                objectId: String(segment.objectId),
                role: String(segment.role),
                segmentRole: String(segment.role),
                point: projection.point,
                priority: Number(segment.priority) || 0,
                kind: "surface",
                t: projection.t,
            });
            const candidate = { target, distanceMm: projection.distanceMm, kind: "surface" };
            if (!best || score("surface", target.priority, candidate.distanceMm) > score(best.kind, best.target.priority, best.distanceMm)) best = candidate;
        }
        return best;
    }

    function bestCandidate(candidates) {
        let best = null;
        for (const candidate of candidates || []) {
            if (!candidate) continue;
            if (!best || score(candidate.kind, candidate.target.priority, candidate.distanceMm) > score(best.kind, best.target.priority, best.distanceMm)) best = candidate;
        }
        return best;
    }

    function pointGuide(kind, point, target) {
        if (kind === "joint") return Object.freeze({ type: "endpoint", point, targetPoint: target.point });
        if (kind === "midpoint") return Object.freeze({ type: "midpoint", point, targetPoint: target.point });
        if (kind === "surface") return Object.freeze({ type: "surface", point, targetPoint: null, objectId: target.objectId, role: target.role });
        return null;
    }

    function resolvePoint(document, candidate, options = {}) {
        const raw = G.point(candidate && candidate.x, candidate && candidate.y);
        const reference = options.anchor ? G.point(options.anchor.x, options.anchor.y) : null;
        const forcedAxis = options.forcedAxis === "horizontal" || options.forcedAxis === "vertical" ? options.forcedAxis : null;
        const useAxisLock = Boolean(reference && (forcedAxis || (options.axisLock && options.shiftKey)));
        if (!useAxisLock) return Base.resolvePoint(document, raw, options);

        const locked = Base.axisLock(reference, raw, forcedAxis);
        const probe = locked.point;
        const axis = locked.axis;
        const joinMm = Base.worldTolerance(options.viewportScale, options.joinSnapPx || Base.JOIN_SNAP_PX);
        const midpointMm = Base.worldTolerance(options.viewportScale, options.midpointSnapPx || Base.MIDPOINT_CAPTURE_PX);
        const surfaceMm = Base.worldTolerance(options.viewportScale, options.surfaceSnapPx || Base.MOVE_SURFACE_CAPTURE_PX);
        const targets = Base.collectTargetFeatures(document, options);
        const source = Object.freeze({ objectId: "candidate", role: "candidate", point: probe, priority: 0, kind: "joint" });
        const best = bestCandidate([
            nearestCompatibleFeature(source, targets, joinMm, "joint", axis, reference),
            nearestCompatibleFeature(source, targets, midpointMm, "midpoint", axis, reference),
            nearestCompatibleSurface(document, source, surfaceMm, options, axis, reference),
        ]);

        if (best) {
            return Object.freeze({
                point: best.target.point,
                rawPoint: raw,
                snapped: true,
                target: best.target,
                distanceMm: G.roundMm(best.distanceMm),
                toleranceMm: G.roundMm(joinMm),
                joinToleranceMm: G.roundMm(joinMm),
                axis,
                anchor: reference,
                kind: best.kind,
                smartGuide: pointGuide(best.kind, best.target.point, best.target),
            });
        }

        // Let the underlying smart-guide layer still provide remote alignment
        // and equal-length intents, while disabling only geometric capture that
        // was already evaluated with the stricter axis compatibility rule above.
        return Base.resolvePoint(document, raw, {
            ...options,
            joinSnapPx: DISABLE_GEOMETRIC_SNAP_PX,
            midpointSnapPx: DISABLE_GEOMETRIC_SNAP_PX,
            surfaceSnapPx: DISABLE_GEOMETRIC_SNAP_PX,
        });
    }

    root.Snapping = Object.freeze({ ...Base, resolvePoint, axisCompatible });
    root.SnapAxisPolicy = Object.freeze({ axisCompatible, resolvePoint });
})();
