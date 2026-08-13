(() => {
    "use strict";

    const root = window.AlmdinaDoorDrawingV3 = window.AlmdinaDoorDrawingV3 || Object.create(null);
    const G = root.Geometry;
    const S = root.Snapping;
    const Selection = root.VectorSelectionGeometry;
    if (!G || !S || !Selection || typeof S.featuresForObject !== "function" || typeof S.collectSegments !== "function" || typeof S.projectSegment !== "function") {
        throw new Error("Door Drawing V3 unified snapping and smart guides must load before snap candidate engine");
    }

    const POINT_CAPTURE_PX = 10;
    const SEGMENT_CAPTURE_PX = 9;
    const COLLINEAR_CAPTURE_PX = 7;
    const COLLINEAR_EXTENSION_PX = 72;
    const COLLINEAR_ANGLE_TOLERANCE_DEG = 1.5;
    const RELEASE_FACTOR = 1.6;
    const RANK = Object.freeze({
        endpoint: 1000,
        midpoint: 900,
        segment: 860,
        center: 760,
        collinear: 720,
    });

    function centerFeature(object) {
        const box = Selection.boundsOfObject(object);
        if (!box) return null;
        return Object.freeze({
            objectId: String(object.id),
            role: "center",
            point: G.point(box.cx, box.cy),
            priority: 20,
            kind: "center",
        });
    }

    function featuresForObject(object) {
        const features = [...(S.featuresForObject(object) || [])];
        const center = centerFeature(object);
        if (center) features.push(center);
        return Object.freeze(features);
    }

    function featuresForObjects(objects) {
        const out = [];
        for (const object of objects || []) out.push(...featuresForObject(object));
        return Object.freeze(out);
    }

    function movedObjects(objects, dx, dy) {
        return (objects || []).map(object => G.translateObject(object, dx, dy));
    }

    function movedFeatures(objects, dx, dy) {
        return featuresForObjects(movedObjects(objects, dx, dy));
    }

    function targetFeatures(document, excludedIds = []) {
        const excluded = new Set((excludedIds || []).filter(Boolean).map(String));
        return featuresForObjects(((document && document.objects) || []).filter(object => !excluded.has(String(object.id))));
    }

    function segmentsForObjects(objects) {
        return Object.freeze(S.collectSegments({ objects: objects || [] }, {}).filter(segment => !segment.curved));
    }

    function targetSegments(document, excludedIds = []) {
        return Object.freeze(S.collectSegments(document, { excludeIds: excludedIds || [] }).filter(segment => !segment.curved));
    }

    function pairKind(source, target) {
        if (!source || !target) return null;
        if (source.kind === "joint" && target.kind === "joint") return "endpoint";
        if (source.kind === "joint" && target.kind === "midpoint") return "midpoint";
        if (source.kind === "midpoint" && target.kind === "midpoint") return "midpoint";
        if (source.kind === "center" && target.kind === "center") return "center";
        return null;
    }

    function identity(kind, source, target) {
        return Object.freeze({
            kind: String(kind || ""),
            sourceObjectId: String(source && source.objectId || ""),
            sourceRole: String(source && source.role || ""),
            targetObjectId: String(target && target.objectId || ""),
            targetRole: String(target && target.role || ""),
        });
    }

    function sameIdentity(feature, objectId, role) {
        return Boolean(feature
            && String(feature.objectId) === String(objectId || "")
            && String(feature.role) === String(role || ""));
    }

    function score(candidate) {
        if (!candidate) return -Infinity;
        const rank = Number(RANK[candidate.kind]) || 0;
        const sourcePriority = Number(candidate.source && candidate.source.priority) || 0;
        const targetPriority = Number(candidate.target && candidate.target.priority) || 0;
        return rank * 1000000 + (sourcePriority + targetPriority) * 1000 - Math.max(0, Number(candidate.distanceMm) || 0);
    }

    function compatibleWithAxis(correctionX, correctionY, lockedAxis) {
        const epsilon = Number(S.AXIS_EPSILON_MM) || Math.max(G.EPSILON_MM, 0.01);
        if (lockedAxis === "x") return Math.abs(correctionY) <= epsilon;
        if (lockedAxis === "y") return Math.abs(correctionX) <= epsilon;
        return true;
    }

    function pointCandidate(source, target, toleranceMm, lockedAxis, sticky = false) {
        const kind = pairKind(source, target);
        if (!kind) return null;
        const correctionX = target.point.x - source.point.x;
        const correctionY = target.point.y - source.point.y;
        if (!compatibleWithAxis(correctionX, correctionY, lockedAxis)) return null;
        const distanceMm = G.distance(source.point, target.point);
        if (distanceMm > toleranceMm) return null;
        return Object.freeze({
            kind,
            source,
            target,
            correctionX,
            correctionY,
            distanceMm,
            sticky: Boolean(sticky),
            claimedAxes: Object.freeze(["x", "y"]),
            identity: identity(kind, source, target),
        });
    }

    function segmentDescriptor(segment, point = null, kind = "segment") {
        const targetPoint = point || G.point(
            (segment.start.x + segment.end.x) / 2,
            (segment.start.y + segment.end.y) / 2
        );
        return Object.freeze({
            objectId: String(segment.objectId),
            role: String(segment.role),
            point: targetPoint,
            priority: Number(segment.priority) || 0,
            kind,
            start: G.point(segment.start.x, segment.start.y),
            end: G.point(segment.end.x, segment.end.y),
        });
    }

    function segmentClaimedAxes(segment) {
        const dx = segment.end.x - segment.start.x;
        const dy = segment.end.y - segment.start.y;
        const epsilon = Math.max(G.EPSILON_MM, 0.01);
        if (Math.abs(dy) <= epsilon) return Object.freeze(["y"]);
        if (Math.abs(dx) <= epsilon) return Object.freeze(["x"]);
        return Object.freeze(["x", "y"]);
    }

    function surfaceCandidate(source, segment, toleranceMm, lockedAxis, sticky = false) {
        if (!source || source.kind !== "joint" || !segment || segment.curved) return null;
        const projection = S.projectSegment(source.point, segment.start, segment.end);
        if (!projection || projection.distanceMm > toleranceMm) return null;
        const target = segmentDescriptor(segment, projection.point, "surface");
        const correctionX = target.point.x - source.point.x;
        const correctionY = target.point.y - source.point.y;
        if (!compatibleWithAxis(correctionX, correctionY, lockedAxis)) return null;
        return Object.freeze({
            kind: "segment",
            source,
            target,
            correctionX,
            correctionY,
            distanceMm: projection.distanceMm,
            sticky: Boolean(sticky),
            claimedAxes: segmentClaimedAxes(segment),
            identity: identity("segment", source, target),
            targetSegment: target,
        });
    }

    function angleDistance180(a, b) {
        const delta = Math.abs((((Number(a) || 0) - (Number(b) || 0)) % 180 + 180) % 180);
        return Math.min(delta, 180 - delta);
    }

    function segmentAngle(segment) {
        return G.angleDeg(segment.start, segment.end);
    }

    function projectInfinite(point, start, end) {
        const p = G.point(point.x, point.y);
        const a = G.point(start.x, start.y);
        const b = G.point(end.x, end.y);
        const dx = b.x - a.x;
        const dy = b.y - a.y;
        const length2 = dx * dx + dy * dy;
        if (length2 <= G.EPSILON_MM * G.EPSILON_MM) return null;
        const t = ((p.x - a.x) * dx + (p.y - a.y) * dy) / length2;
        const projected = G.point(a.x + dx * t, a.y + dy * t);
        return Object.freeze({ point: projected, distanceMm: G.distance(p, projected), t });
    }

    function scalarAlong(point, origin, ux, uy) {
        return (point.x - origin.x) * ux + (point.y - origin.y) * uy;
    }

    function longitudinalGap(sourceSegment, targetSegment) {
        const dx = targetSegment.end.x - targetSegment.start.x;
        const dy = targetSegment.end.y - targetSegment.start.y;
        const length = Math.hypot(dx, dy);
        if (length <= G.EPSILON_MM) return Infinity;
        const ux = dx / length;
        const uy = dy / length;
        const origin = targetSegment.start;
        const sourceValues = [
            scalarAlong(sourceSegment.start, origin, ux, uy),
            scalarAlong(sourceSegment.end, origin, ux, uy),
        ];
        const targetValues = [0, length];
        const sourceMin = Math.min(...sourceValues);
        const sourceMax = Math.max(...sourceValues);
        const targetMin = Math.min(...targetValues);
        const targetMax = Math.max(...targetValues);
        if (sourceMax < targetMin) return targetMin - sourceMax;
        if (targetMax < sourceMin) return sourceMin - targetMax;
        return 0;
    }

    function collinearCandidate(sourceSegment, targetSegment, toleranceMm, lockedAxis, sticky = false, extensionToleranceMm = Infinity) {
        if (!sourceSegment || !targetSegment || sourceSegment.curved || targetSegment.curved) return null;
        if (angleDistance180(segmentAngle(sourceSegment), segmentAngle(targetSegment)) > COLLINEAR_ANGLE_TOLERANCE_DEG) return null;
        const alongGapMm = longitudinalGap(sourceSegment, targetSegment);
        if (alongGapMm > Math.max(0, Number(extensionToleranceMm) || 0)) return null;
        const sourceMid = G.point(
            (sourceSegment.start.x + sourceSegment.end.x) / 2,
            (sourceSegment.start.y + sourceSegment.end.y) / 2
        );
        const projection = projectInfinite(sourceMid, targetSegment.start, targetSegment.end);
        if (!projection || projection.distanceMm > toleranceMm) return null;
        const correctionX = projection.point.x - sourceMid.x;
        const correctionY = projection.point.y - sourceMid.y;
        if (!compatibleWithAxis(correctionX, correctionY, lockedAxis)) return null;
        const source = segmentDescriptor(sourceSegment, sourceMid, "source-segment");
        const target = segmentDescriptor(targetSegment, projection.point, "target-segment");
        return Object.freeze({
            kind: "collinear",
            source,
            target,
            correctionX,
            correctionY,
            distanceMm: projection.distanceMm,
            longitudinalGapMm: G.roundMm(alongGapMm),
            sticky: Boolean(sticky),
            claimedAxes: segmentClaimedAxes(targetSegment),
            identity: identity("collinear", source, target),
            targetSegment: target,
        });
    }

    function bestPointCandidate(sources, targets, toleranceMm, lockedAxis, allowSameObject = false) {
        let best = null;
        for (const source of sources || []) {
            for (const target of targets || []) {
                if (!allowSameObject && String(source.objectId) === String(target.objectId)) continue;
                const next = pointCandidate(source, target, toleranceMm, lockedAxis, false);
                if (!next) continue;
                if (!best || score(next) > score(best)) best = next;
            }
        }
        return best;
    }

    function bestSurfaceCandidate(sources, segments, toleranceMm, lockedAxis, allowSameObject = false) {
        let best = null;
        for (const source of sources || []) {
            if (source.kind !== "joint") continue;
            for (const segment of segments || []) {
                if (!allowSameObject && String(source.objectId) === String(segment.objectId)) continue;
                const next = surfaceCandidate(source, segment, toleranceMm, lockedAxis, false);
                if (!next) continue;
                if (!best || score(next) > score(best)) best = next;
            }
        }
        return best;
    }

    function bestCollinearCandidate(sources, targets, toleranceMm, lockedAxis, allowSameObject = false, extensionToleranceMm = Infinity) {
        let best = null;
        for (const source of sources || []) {
            for (const target of targets || []) {
                if (!allowSameObject && String(source.objectId) === String(target.objectId)) continue;
                const next = collinearCandidate(source, target, toleranceMm, lockedAxis, false, extensionToleranceMm);
                if (!next) continue;
                if (!best || score(next) > score(best)) best = next;
            }
        }
        return best;
    }

    function segmentByIdentity(segments, objectId, role) {
        return (segments || []).find(segment => (
            String(segment.objectId) === String(objectId || "")
            && String(segment.role) === String(role || "")
        )) || null;
    }

    function stickyCandidate(sources, sourceSegments, targets, segments, previous, tolerances, lockedAxis) {
        if (!previous) return null;
        if (previous.kind === "segment") {
            const source = (sources || []).find(feature => sameIdentity(feature, previous.sourceObjectId, previous.sourceRole));
            const segment = segmentByIdentity(segments, previous.targetObjectId, previous.targetRole);
            return source && segment ? surfaceCandidate(source, segment, tolerances.segmentMm * RELEASE_FACTOR, lockedAxis, true) : null;
        }
        if (previous.kind === "collinear") {
            const source = segmentByIdentity(sourceSegments, previous.sourceObjectId, previous.sourceRole);
            const target = segmentByIdentity(segments, previous.targetObjectId, previous.targetRole);
            return source && target ? collinearCandidate(
                source,
                target,
                tolerances.collinearMm * RELEASE_FACTOR,
                lockedAxis,
                true,
                tolerances.collinearExtensionMm * RELEASE_FACTOR
            ) : null;
        }
        const source = (sources || []).find(feature => sameIdentity(feature, previous.sourceObjectId, previous.sourceRole));
        const target = (targets || []).find(feature => sameIdentity(feature, previous.targetObjectId, previous.targetRole));
        if (!source || !target || pairKind(source, target) !== previous.kind) return null;
        return pointCandidate(source, target, tolerances.pointMm * RELEASE_FACTOR, lockedAxis, true);
    }

    function pointGuide(best) {
        return Object.freeze({
            type: "geometry-point",
            kind: best.kind,
            point: best.target.point,
            sourcePoint: best.source.point,
            targetPoint: best.target.point,
            sourceId: String(best.source.objectId),
            sourceRole: String(best.source.role),
            targetId: String(best.target.objectId),
            targetRole: String(best.target.role),
            sticky: Boolean(best.sticky),
        });
    }

    function segmentGuide(best) {
        const target = best.targetSegment || best.target;
        return Object.freeze({
            type: best.kind === "collinear" ? "geometry-line" : "geometry-segment",
            kind: best.kind,
            point: best.target.point,
            sourcePoint: best.source.point,
            targetPoint: best.target.point,
            targetSegment: Object.freeze({ start: target.start, end: target.end }),
            sourceId: String(best.source.objectId),
            sourceRole: String(best.source.role),
            targetId: String(best.target.objectId),
            targetRole: String(best.target.role),
            sticky: Boolean(best.sticky),
        });
    }

    function guideFor(best) {
        if (!best) return null;
        return best.kind === "segment" || best.kind === "collinear" ? segmentGuide(best) : pointGuide(best);
    }

    function resolve(document, sourceObjects, requestedDx, requestedDy, options = {}) {
        let dx = G.number(requestedDx);
        let dy = G.number(requestedDy);
        const lockedAxis = options.lockedAxis === "x" || options.lockedAxis === "y" ? options.lockedAxis : null;
        if (lockedAxis === "x") dy = 0;
        if (lockedAxis === "y") dx = 0;

        const includeSourceTargets = Boolean(options.includeSourceTargets);
        const excludedIds = includeSourceTargets ? [] : (sourceObjects || []).map(object => String(object.id));
        const moved = movedObjects(sourceObjects || [], dx, dy);
        const sources = featuresForObjects(moved);
        const sourceSegments = segmentsForObjects(moved);
        const targets = targetFeatures(document, excludedIds);
        const segments = targetSegments(document, excludedIds);
        const tolerances = Object.freeze({
            pointMm: S.worldTolerance(options.viewportScale, options.pointSnapPx || POINT_CAPTURE_PX),
            segmentMm: S.worldTolerance(options.viewportScale, options.segmentSnapPx || SEGMENT_CAPTURE_PX),
            collinearMm: S.worldTolerance(options.viewportScale, options.collinearSnapPx || COLLINEAR_CAPTURE_PX),
            collinearExtensionMm: S.worldTolerance(options.viewportScale, options.collinearExtensionPx || COLLINEAR_EXTENSION_PX),
        });

        let best = stickyCandidate(sources, sourceSegments, targets, segments, options.stickyCandidate, tolerances, lockedAxis);
        if (!best) {
            const candidates = [
                bestPointCandidate(sources, targets, tolerances.pointMm, lockedAxis, includeSourceTargets),
                bestSurfaceCandidate(sources, segments, tolerances.segmentMm, lockedAxis, includeSourceTargets),
                bestCollinearCandidate(
                    sourceSegments,
                    segments,
                    tolerances.collinearMm,
                    lockedAxis,
                    includeSourceTargets,
                    tolerances.collinearExtensionMm
                ),
            ].filter(Boolean);
            best = candidates.sort((a, b) => score(b) - score(a))[0] || null;
        }

        if (!best) {
            return Object.freeze({
                dx: G.roundMm(dx),
                dy: G.roundMm(dy),
                snapped: false,
                candidate: null,
                guide: null,
                stickyCandidate: null,
                claimedAxes: Object.freeze([]),
                toleranceMm: G.roundMm(tolerances.pointMm),
                releaseToleranceMm: G.roundMm(tolerances.pointMm * RELEASE_FACTOR),
            });
        }

        dx += best.correctionX;
        dy += best.correctionY;
        return Object.freeze({
            dx: G.roundMm(dx),
            dy: G.roundMm(dy),
            snapped: true,
            candidate: best,
            guide: guideFor(best),
            stickyCandidate: best.identity,
            claimedAxes: best.claimedAxes || Object.freeze(["x", "y"]),
            toleranceMm: G.roundMm(tolerances.pointMm),
            releaseToleranceMm: G.roundMm(tolerances.pointMm * RELEASE_FACTOR),
        });
    }

    root.SnapCandidateEngine = Object.freeze({
        POINT_CAPTURE_PX,
        SEGMENT_CAPTURE_PX,
        COLLINEAR_CAPTURE_PX,
        COLLINEAR_EXTENSION_PX,
        COLLINEAR_ANGLE_TOLERANCE_DEG,
        RELEASE_FACTOR,
        RANK,
        centerFeature,
        featuresForObject,
        featuresForObjects,
        movedFeatures,
        targetFeatures,
        segmentsForObjects,
        targetSegments,
        pairKind,
        score,
        projectInfinite,
        longitudinalGap,
        surfaceCandidate,
        collinearCandidate,
        resolve,
    });
})();
