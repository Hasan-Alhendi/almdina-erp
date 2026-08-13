(() => {
    "use strict";

    const root = window.AlmdinaDoorDrawingV3 = window.AlmdinaDoorDrawingV3 || Object.create(null);
    const G = root.Geometry;
    const S = root.Snapping;
    const Selection = root.VectorSelectionGeometry;
    if (!G || !S || !Selection || typeof S.featuresForObject !== "function") {
        throw new Error("Door Drawing V3 unified snapping must load before snap candidate engine");
    }

    const POINT_CAPTURE_PX = 10;
    const RELEASE_FACTOR = 1.6;
    const RANK = Object.freeze({
        endpoint: 1000,
        midpoint: 820,
        center: 760,
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

    function movedFeatures(objects, dx, dy) {
        return featuresForObjects((objects || []).map(object => G.translateObject(object, dx, dy)));
    }

    function targetFeatures(document, excludedIds = []) {
        const excluded = new Set((excludedIds || []).filter(Boolean).map(String));
        return featuresForObjects(((document && document.objects) || []).filter(object => !excluded.has(String(object.id))));
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

    function candidate(source, target, toleranceMm, lockedAxis, sticky = false) {
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
            identity: identity(kind, source, target),
        });
    }

    function stickyCandidate(sources, targets, previous, releaseToleranceMm, lockedAxis) {
        if (!previous) return null;
        const source = (sources || []).find(feature => sameIdentity(feature, previous.sourceObjectId, previous.sourceRole));
        const target = (targets || []).find(feature => sameIdentity(feature, previous.targetObjectId, previous.targetRole));
        if (!source || !target || pairKind(source, target) !== previous.kind) return null;
        return candidate(source, target, releaseToleranceMm, lockedAxis, true);
    }

    function bestCandidate(sources, targets, toleranceMm, lockedAxis, allowSameObject = false) {
        let best = null;
        for (const source of sources || []) {
            for (const target of targets || []) {
                if (!allowSameObject && String(source.objectId) === String(target.objectId)) continue;
                const next = candidate(source, target, toleranceMm, lockedAxis, false);
                if (!next) continue;
                if (!best || score(next) > score(best)) best = next;
            }
        }
        return best;
    }

    function pointGuide(best) {
        if (!best) return null;
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

    function resolve(document, sourceObjects, requestedDx, requestedDy, options = {}) {
        let dx = G.number(requestedDx);
        let dy = G.number(requestedDy);
        const lockedAxis = options.lockedAxis === "x" || options.lockedAxis === "y" ? options.lockedAxis : null;
        if (lockedAxis === "x") dy = 0;
        if (lockedAxis === "y") dx = 0;

        const includeSourceTargets = Boolean(options.includeSourceTargets);
        const excludedIds = includeSourceTargets
            ? []
            : (sourceObjects || []).map(object => String(object.id));
        const sources = movedFeatures(sourceObjects || [], dx, dy);
        const targets = targetFeatures(document, excludedIds);
        const toleranceMm = S.worldTolerance(options.viewportScale, options.pointSnapPx || POINT_CAPTURE_PX);
        const releaseToleranceMm = toleranceMm * RELEASE_FACTOR;

        let best = stickyCandidate(sources, targets, options.stickyCandidate, releaseToleranceMm, lockedAxis);
        if (!best) best = bestCandidate(sources, targets, toleranceMm, lockedAxis, includeSourceTargets);
        if (!best) {
            return Object.freeze({
                dx: G.roundMm(dx),
                dy: G.roundMm(dy),
                snapped: false,
                candidate: null,
                guide: null,
                stickyCandidate: null,
                toleranceMm: G.roundMm(toleranceMm),
                releaseToleranceMm: G.roundMm(releaseToleranceMm),
            });
        }

        dx += best.correctionX;
        dy += best.correctionY;
        return Object.freeze({
            dx: G.roundMm(dx),
            dy: G.roundMm(dy),
            snapped: true,
            candidate: best,
            guide: pointGuide(best),
            stickyCandidate: best.identity,
            toleranceMm: G.roundMm(toleranceMm),
            releaseToleranceMm: G.roundMm(releaseToleranceMm),
        });
    }

    root.SnapCandidateEngine = Object.freeze({
        POINT_CAPTURE_PX,
        RELEASE_FACTOR,
        RANK,
        centerFeature,
        featuresForObject,
        featuresForObjects,
        movedFeatures,
        targetFeatures,
        pairKind,
        score,
        resolve,
    });
})();
