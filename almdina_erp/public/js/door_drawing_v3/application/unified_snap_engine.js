(() => {
    "use strict";

    const root = window.AlmdinaDoorDrawingV3 = window.AlmdinaDoorDrawingV3 || Object.create(null);
    const Base = root.Snapping;
    const G = root.Geometry;
    if (!Base || !G || typeof Base.collectSegments !== "function") {
        throw new Error("Door Drawing V3 smart guides must load before unified snap engine");
    }

    const MOVE_JOIN_CAPTURE_PX = 20;
    const MOVE_SURFACE_CAPTURE_PX = 12;
    const MIDPOINT_CAPTURE_PX = 10;
    const MOVE_ALIGNMENT_CAPTURE_PX = 8;
    const RELEASE_FACTOR = 1.6;

    const INTENT_RANK = Object.freeze({
        joint: 1000,
        midpoint: 820,
        surface: 700,
        alignment: 500,
        fallback: 100,
    });

    function featureIdentity(feature) {
        if (!feature) return "";
        return `${String(feature.objectId || "")}::${String(feature.role || "")}::${String(feature.kind || "")}`;
    }

    function sameFeature(a, b) {
        return Boolean(a && b && featureIdentity(a) === featureIdentity(b));
    }

    function midpoint(start, end) {
        return G.point((start.x + end.x) / 2, (start.y + end.y) / 2);
    }

    function midpointFeature(segment) {
        return Object.freeze({
            objectId: String(segment.objectId),
            role: `midpoint:${segment.role}`,
            point: midpoint(segment.start, segment.end),
            priority: Number(segment.priority) || 0,
            kind: "midpoint",
            segmentRole: segment.role,
        });
    }

    function featuresForObject(object) {
        if (!object) return Object.freeze([]);
        const anchors = typeof Base.anchorsForObject === "function"
            ? Base.anchorsForObject(object)
            : Base.objectAnchors(object);
        const segments = Base.collectSegments({ objects: [object] }, {});
        const features = [];
        for (const anchor of anchors || []) {
            if (!Base.isJoint(anchor)) continue;
            features.push(Object.freeze({ ...anchor, kind: "joint" }));
        }
        for (const segment of segments) features.push(midpointFeature(segment));
        return Object.freeze(features);
    }

    function collectTargetFeatures(document, options = {}) {
        const excluded = new Set(
            (Array.isArray(options.excludeIds) ? options.excludeIds : [options.excludeId])
                .filter(Boolean)
                .map(String)
        );
        const features = [];
        for (const object of (document && document.objects) || []) {
            if (excluded.has(String(object.id))) continue;
            features.push(...featuresForObject(object));
        }
        return Object.freeze(features);
    }

    function scoreCandidate(candidate) {
        if (!candidate) return -Infinity;
        const rank = INTENT_RANK[candidate.kind] || INTENT_RANK.fallback;
        const priority = Number(candidate.target && candidate.target.priority) || 0;
        const distance = Math.max(0, Number(candidate.distanceMm) || 0);
        return rank * 100000 + priority * 100 - distance;
    }

    function chooseBest(candidates) {
        let best = null;
        let bestScore = -Infinity;
        for (const candidate of candidates || []) {
            if (!candidate) continue;
            const score = scoreCandidate(candidate);
            if (score > bestScore) {
                best = candidate;
                bestScore = score;
            }
        }
        return best;
    }

    function nearestFeature(source, targets, toleranceMm, kind) {
        let best = null;
        for (const target of targets || []) {
            if (kind && target.kind !== kind) continue;
            const distanceMm = G.distance(source.point, target.point);
            if (distanceMm > toleranceMm) continue;
            const candidate = { source, target, distanceMm, kind: target.kind };
            if (!best || scoreCandidate(candidate) > scoreCandidate(best)) best = candidate;
        }
        return best;
    }

    function segmentByIdentity(document, identity, excludeId = null) {
        if (!identity) return null;
        return Base.collectSegments(document, { excludeId }).find(segment => (
            String(segment.objectId) === String(identity.objectId)
            && String(segment.role) === String(identity.segmentRole || identity.role)
        )) || null;
    }

    function nearestSurfaceForSource(document, source, toleranceMm, options = {}) {
        let best = null;
        for (const segment of Base.collectSegments(document, options)) {
            const projection = Base.projectSegment(source.point, segment.start, segment.end);
            if (!projection || projection.distanceMm > toleranceMm) continue;
            const target = Object.freeze({
                objectId: String(segment.objectId),
                role: String(segment.role),
                segmentRole: String(segment.role),
                point: projection.point,
                priority: Number(segment.priority) || 0,
                kind: "surface",
                t: projection.t,
            });
            const candidate = { source, target, distanceMm: projection.distanceMm, kind: "surface" };
            if (!best || scoreCandidate(candidate) > scoreCandidate(best)) best = candidate;
        }
        return best;
    }

    function stickyCandidate(document, movedObject, options, tolerances) {
        if (!options.stickySource || !options.stickyTarget || !options.stickyKind) return null;
        const source = featuresForObject(movedObject).find(feature => sameFeature(feature, options.stickySource));
        if (!source) return null;
        const releaseJoinMm = tolerances.joinMm * RELEASE_FACTOR;
        const releaseSurfaceMm = Math.max(tolerances.surfaceMm, tolerances.joinMm) * RELEASE_FACTOR;

        if (options.stickyKind === "joint" || options.stickyKind === "midpoint") {
            const target = collectTargetFeatures(document, { excludeId: movedObject.id }).find(feature => sameFeature(feature, options.stickyTarget));
            if (!target || target.kind !== options.stickyKind) return null;
            const distanceMm = G.distance(source.point, target.point);
            if (distanceMm > releaseJoinMm) return null;
            return { source, target, distanceMm, kind: target.kind, sticky: true };
        }

        if (options.stickyKind === "surface") {
            const segment = segmentByIdentity(document, options.stickyTarget, movedObject.id);
            if (!segment) return null;
            const projection = Base.projectSegment(source.point, segment.start, segment.end);
            if (!projection || projection.distanceMm > releaseSurfaceMm) return null;
            const target = Object.freeze({
                objectId: String(segment.objectId),
                role: String(segment.role),
                segmentRole: String(segment.role),
                point: projection.point,
                priority: Number(segment.priority) || 0,
                kind: "surface",
                t: projection.t,
            });
            return { source, target, distanceMm: projection.distanceMm, kind: "surface", sticky: true };
        }
        return null;
    }

    function alignmentCandidate(document, movedObject, toleranceMm) {
        const sources = featuresForObject(movedObject).filter(feature => feature.kind === "joint" || feature.kind === "midpoint");
        const targets = collectTargetFeatures(document, { excludeId: movedObject.id });
        let bestX = null;
        let bestY = null;

        for (const source of sources) {
            for (const target of targets) {
                const dx = Math.abs(target.point.x - source.point.x);
                const dy = Math.abs(target.point.y - source.point.y);
                if (dx <= toleranceMm) {
                    const candidate = { source, target, distanceMm: dx, correctionX: target.point.x - source.point.x };
                    if (!bestX || dx < bestX.distanceMm - G.EPSILON_MM) bestX = candidate;
                }
                if (dy <= toleranceMm) {
                    const candidate = { source, target, distanceMm: dy, correctionY: target.point.y - source.point.y };
                    if (!bestY || dy < bestY.distanceMm - G.EPSILON_MM) bestY = candidate;
                }
            }
        }

        if (!bestX && !bestY) return null;
        const correctionX = bestX ? bestX.correctionX : 0;
        const correctionY = bestY ? bestY.correctionY : 0;
        const source = bestX && bestY
            ? (bestX.distanceMm <= bestY.distanceMm ? bestX.source : bestY.source)
            : (bestX ? bestX.source : bestY.source);
        const target = bestX && bestY
            ? (bestX.distanceMm <= bestY.distanceMm ? bestX.target : bestY.target)
            : (bestX ? bestX.target : bestY.target);
        const point = G.point(source.point.x + correctionX, source.point.y + correctionY);
        const guideType = bestX && bestY ? "xy-alignment" : bestX ? "vertical-alignment" : "horizontal-alignment";
        return {
            source,
            target,
            distanceMm: Math.min(bestX ? bestX.distanceMm : Infinity, bestY ? bestY.distanceMm : Infinity),
            correctionX,
            correctionY,
            point,
            kind: "alignment",
            guideType,
            bestX,
            bestY,
        };
    }

    function pointGuide(kind, point, target, extra = {}) {
        if (kind === "joint") {
            return Object.freeze({ type: "endpoint", point, targetPoint: target && target.point ? target.point : point, ...extra });
        }
        if (kind === "midpoint") {
            return Object.freeze({ type: "midpoint", point, targetPoint: target && target.point ? target.point : point, ...extra });
        }
        if (kind === "surface") {
            return Object.freeze({ type: "surface", point, targetPoint: null, ...extra });
        }
        return null;
    }

    function moveResult(object, rawObject, candidate, tolerances) {
        if (!candidate) {
            return Object.freeze({
                object: rawObject,
                point: null,
                rawPoint: null,
                snapped: false,
                target: null,
                source: null,
                distanceMm: null,
                toleranceMm: G.roundMm(tolerances.joinMm),
                releaseToleranceMm: G.roundMm(tolerances.joinMm * RELEASE_FACTOR),
                axis: null,
                anchor: null,
                kind: "move",
                sticky: false,
                smartGuide: null,
            });
        }

        let correctionX = candidate.correctionX;
        let correctionY = candidate.correctionY;
        if (!Number.isFinite(correctionX)) correctionX = candidate.target.point.x - candidate.source.point.x;
        if (!Number.isFinite(correctionY)) correctionY = candidate.target.point.y - candidate.source.point.y;
        const corrected = G.translateObject(rawObject, correctionX, correctionY);
        const point = candidate.kind === "alignment"
            ? candidate.point
            : G.point(candidate.source.point.x + correctionX, candidate.source.point.y + correctionY);
        let smartGuide = pointGuide(candidate.kind, point, candidate.target, {
            objectId: String(candidate.target && candidate.target.objectId || ""),
            role: String(candidate.target && candidate.target.role || ""),
        });
        if (candidate.kind === "alignment") {
            smartGuide = Object.freeze({
                type: candidate.guideType,
                point,
                targetPoint: candidate.target.point,
                xAnchor: candidate.bestX ? candidate.bestX.target : null,
                yAnchor: candidate.bestY ? candidate.bestY.target : null,
            });
        }
        return Object.freeze({
            object: corrected,
            point,
            rawPoint: candidate.source.point,
            snapped: true,
            target: candidate.target,
            source: candidate.source,
            distanceMm: G.roundMm(candidate.distanceMm),
            toleranceMm: G.roundMm(tolerances.joinMm),
            releaseToleranceMm: G.roundMm(tolerances.joinMm * RELEASE_FACTOR),
            axis: null,
            anchor: candidate.source.point,
            kind: candidate.kind,
            sticky: Boolean(candidate.sticky),
            smartGuide,
        });
    }

    function resolveObjectMove(document, object, deltaX, deltaY, options = {}) {
        const dx = G.number(deltaX);
        const dy = G.number(deltaY);
        const rawObject = G.translateObject(object, dx, dy);
        const scale = options.viewportScale;
        const tolerances = Object.freeze({
            joinMm: Base.worldTolerance(scale, options.moveJoinSnapPx || MOVE_JOIN_CAPTURE_PX),
            surfaceMm: Base.worldTolerance(scale, options.moveSurfaceSnapPx || MOVE_SURFACE_CAPTURE_PX),
            midpointMm: Base.worldTolerance(scale, options.midpointSnapPx || MIDPOINT_CAPTURE_PX),
            alignmentMm: Base.worldTolerance(scale, options.moveAlignSnapPx || MOVE_ALIGNMENT_CAPTURE_PX),
        });

        const sticky = stickyCandidate(document, rawObject, options, tolerances);
        if (sticky) return moveResult(object, rawObject, sticky, tolerances);

        const sources = featuresForObject(rawObject);
        const targets = collectTargetFeatures(document, { excludeId: object && object.id });
        const candidates = [];

        for (const source of sources) {
            if (source.kind !== "joint") continue;
            candidates.push(nearestFeature(source, targets, tolerances.joinMm, "joint"));
            candidates.push(nearestFeature(source, targets, tolerances.midpointMm, "midpoint"));
            candidates.push(nearestSurfaceForSource(document, source, tolerances.surfaceMm, { excludeId: object && object.id }));
        }
        for (const source of sources) {
            if (source.kind !== "midpoint") continue;
            candidates.push(nearestFeature(source, targets, tolerances.midpointMm, "midpoint"));
        }

        const bestGeometric = chooseBest(candidates);
        if (bestGeometric) return moveResult(object, rawObject, bestGeometric, tolerances);

        const alignment = alignmentCandidate(document, rawObject, tolerances.alignmentMm);
        if (alignment) return moveResult(object, rawObject, alignment, tolerances);

        return moveResult(object, rawObject, null, tolerances);
    }

    function resolvePoint(document, candidate, options = {}) {
        const raw = G.point(candidate && candidate.x, candidate && candidate.y);
        const reference = options.anchor ? G.point(options.anchor.x, options.anchor.y) : null;
        const forcedAxis = options.forcedAxis === "horizontal" || options.forcedAxis === "vertical" ? options.forcedAxis : null;
        const useAxisLock = Boolean(reference && (forcedAxis || (options.axisLock && options.shiftKey)));
        let probe = raw;
        let axis = null;
        if (useAxisLock) {
            const locked = Base.axisLock(reference, raw, forcedAxis);
            probe = locked.point;
            axis = locked.axis;
        }

        const joinMm = Base.worldTolerance(options.viewportScale, options.joinSnapPx || Base.JOIN_SNAP_PX);
        const midpointMm = Base.worldTolerance(options.viewportScale, options.midpointSnapPx || MIDPOINT_CAPTURE_PX);
        const surfaceMm = Base.worldTolerance(options.viewportScale, options.surfaceSnapPx || MOVE_SURFACE_CAPTURE_PX);
        const targets = collectTargetFeatures(document, options);
        const source = Object.freeze({ objectId: "candidate", role: "candidate", point: probe, priority: 0, kind: "joint" });
        const candidates = [
            nearestFeature(source, targets, joinMm, "joint"),
            nearestFeature(source, targets, midpointMm, "midpoint"),
            nearestSurfaceForSource(document, source, surfaceMm, options),
        ];
        const best = chooseBest(candidates);
        if (best) {
            let point = best.target.point;
            if (useAxisLock && axis === "horizontal") point = G.point(best.target.point.x, reference.y);
            if (useAxisLock && axis === "vertical") point = G.point(reference.x, best.target.point.y);
            return Object.freeze({
                point,
                rawPoint: raw,
                snapped: true,
                target: best.target,
                distanceMm: G.roundMm(best.distanceMm),
                toleranceMm: G.roundMm(joinMm),
                joinToleranceMm: G.roundMm(joinMm),
                axis,
                anchor: reference,
                kind: best.kind,
                smartGuide: pointGuide(best.kind, point, best.target, {
                    objectId: String(best.target.objectId || ""),
                    role: String(best.target.role || ""),
                }),
            });
        }

        return Base.resolvePoint(document, raw, options);
    }

    root.Snapping = Object.freeze({
        ...Base,
        MOVE_JOIN_CAPTURE_PX,
        MOVE_SURFACE_CAPTURE_PX,
        MIDPOINT_CAPTURE_PX,
        MOVE_ALIGNMENT_CAPTURE_PX,
        UNIFIED_RELEASE_FACTOR: RELEASE_FACTOR,
        INTENT_RANK,
        featuresForObject,
        collectTargetFeatures,
        resolvePoint,
        resolveObjectMove,
    });

    root.UnifiedSnapEngine = Object.freeze({
        MOVE_JOIN_CAPTURE_PX,
        MOVE_SURFACE_CAPTURE_PX,
        MIDPOINT_CAPTURE_PX,
        MOVE_ALIGNMENT_CAPTURE_PX,
        RELEASE_FACTOR,
        INTENT_RANK,
        featuresForObject,
        collectTargetFeatures,
        resolvePoint,
        resolveObjectMove,
    });
})();
