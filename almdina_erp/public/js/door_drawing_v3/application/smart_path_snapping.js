(() => {
    "use strict";

    const root = window.AlmdinaDoorDrawingV3 = window.AlmdinaDoorDrawingV3 || Object.create(null);
    const Base = root.Snapping;
    const G = root.Geometry;
    const D = root.DocumentModel;
    if (!Base || !G || !D || !G.path) throw new Error("Door Drawing V3 smart path domain and snapping must load first");

    function pathAnchors(object) {
        if (!object || object.type !== G.PATH_TYPE) return Object.freeze([]);
        return Object.freeze(object.geometry.points.map((point, index) => Object.freeze({
            objectId: String(object.id),
            role: `node-${index}`,
            point: G.point(point.x, point.y),
            priority: 120,
            kind: "joint",
            nodeIndex: index,
        })));
    }

    function anchorsForObject(object) {
        return object && object.type === G.PATH_TYPE ? pathAnchors(object) : Base.objectAnchors(object);
    }

    function collectAnchors(document, options = {}) {
        const excluded = new Set((Array.isArray(options.excludeIds) ? options.excludeIds : [options.excludeId]).filter(Boolean).map(String));
        const anchors = [];
        for (const object of (document && document.objects) || []) {
            if (excluded.has(String(object.id))) continue;
            anchors.push(...anchorsForObject(object));
        }
        return Object.freeze(anchors);
    }

    function sameAnchor(anchor, identity) {
        return Boolean(anchor && identity && String(anchor.objectId) === String(identity.objectId) && String(anchor.role) === String(identity.role));
    }

    function resolvePoint(document, candidate, options = {}) {
        const raw = G.point(candidate && candidate.x, candidate && candidate.y);
        const toleranceMm = Base.worldTolerance(options.viewportScale, options.snapPx || Base.DEFAULT_SNAP_PX);
        const joinToleranceMm = Base.worldTolerance(options.viewportScale, options.joinSnapPx || Base.JOIN_SNAP_PX);
        const anchors = options.anchors || collectAnchors(document, options);
        const reference = options.anchor ? G.point(options.anchor.x, options.anchor.y) : null;
        const forcedAxis = options.forcedAxis === "horizontal" || options.forcedAxis === "vertical" ? options.forcedAxis : null;
        const useAxisLock = Boolean(reference && (forcedAxis || (options.axisLock && options.shiftKey)));
        let point = raw;
        let axis = null;
        let snapped = null;

        if (useAxisLock) {
            const locked = Base.axisLock(reference, raw, forcedAxis);
            point = locked.point;
            axis = locked.axis;
            const compatible = target => axis === "horizontal"
                ? Math.abs(target.point.y - reference.y) <= Base.AXIS_EPSILON_MM
                : Math.abs(target.point.x - reference.x) <= Base.AXIS_EPSILON_MM;
            snapped = Base.preferredAnchor(point, anchors, {
                toleranceMm,
                joinToleranceMm,
                predicate: compatible,
                stickyTarget: options.stickyTarget,
            });
        } else {
            snapped = Base.preferredAnchor(point, anchors, {
                toleranceMm,
                joinToleranceMm,
                stickyTarget: options.stickyTarget,
            });
        }

        if (snapped) {
            point = useAxisLock && axis === "horizontal"
                ? G.point(snapped.target.point.x, reference.y)
                : useAxisLock && axis === "vertical"
                    ? G.point(reference.x, snapped.target.point.y)
                    : snapped.target.point;
        }

        return Object.freeze({
            point,
            rawPoint: raw,
            snapped: Boolean(snapped),
            target: snapped ? snapped.target : null,
            distanceMm: snapped ? G.roundMm(snapped.distanceMm) : null,
            toleranceMm: G.roundMm(toleranceMm),
            joinToleranceMm: G.roundMm(joinToleranceMm),
            axis,
            anchor: reference,
            kind: snapped ? "joint" : "reference",
        });
    }

    function resolveObjectMove(document, object, deltaX, deltaY, options = {}) {
        const dx = G.number(deltaX);
        const dy = G.number(deltaY);
        const moved = G.translateObject(object, dx, dy);
        const sourceAnchors = anchorsForObject(moved).filter(Base.isJoint);
        const targetAnchors = collectAnchors(document, { excludeId: object && object.id }).filter(Base.isJoint);
        const toleranceMm = Base.worldTolerance(options.viewportScale, options.moveJoinSnapPx || Base.MOVE_JOIN_SNAP_PX);
        const releaseToleranceMm = toleranceMm * Base.MOVE_SNAP_RELEASE_FACTOR;
        let best = null;

        if (options.stickySource && options.stickyTarget) {
            const source = sourceAnchors.find(anchor => sameAnchor(anchor, options.stickySource));
            const target = targetAnchors.find(anchor => sameAnchor(anchor, options.stickyTarget));
            if (source && target) {
                const distanceMm = G.distance(source.point, target.point);
                if (distanceMm <= releaseToleranceMm) best = { source, target, distanceMm, sticky: true };
            }
        }

        if (!best) {
            for (const source of sourceAnchors) {
                const candidate = Base.nearestAnchor(source.point, targetAnchors, toleranceMm);
                if (!candidate) continue;
                if (!best || candidate.distanceMm < best.distanceMm - G.EPSILON_MM || (Math.abs(candidate.distanceMm - best.distanceMm) <= G.EPSILON_MM && candidate.target.priority > best.target.priority)) {
                    best = { source, target: candidate.target, distanceMm: candidate.distanceMm, sticky: false };
                }
            }
        }

        if (!best) {
            return Object.freeze({ object: moved, point: null, rawPoint: null, snapped: false, target: null, source: null, distanceMm: null, toleranceMm: G.roundMm(toleranceMm), releaseToleranceMm: G.roundMm(releaseToleranceMm), axis: null, anchor: null, kind: "move", sticky: false });
        }

        const correctionX = best.target.point.x - best.source.point.x;
        const correctionY = best.target.point.y - best.source.point.y;
        const corrected = G.translateObject(object, dx + correctionX, dy + correctionY);
        return Object.freeze({
            object: corrected,
            point: best.target.point,
            rawPoint: best.source.point,
            snapped: true,
            target: best.target,
            source: best.source,
            distanceMm: G.roundMm(best.distanceMm),
            toleranceMm: G.roundMm(toleranceMm),
            releaseToleranceMm: G.roundMm(releaseToleranceMm),
            axis: null,
            anchor: best.source.point,
            kind: "joint",
            sticky: Boolean(best.sticky),
        });
    }

    function resolveArcEndpoint(document, candidate, center, radiusMm, options = {}) {
        const raw = G.point(candidate && candidate.x, candidate && candidate.y);
        const c = G.point(center && center.x, center && center.y);
        const radius = Math.max(G.EPSILON_MM, G.number(radiusMm));
        const toleranceMm = Base.worldTolerance(options.viewportScale, options.joinSnapPx || Base.JOIN_SNAP_PX);
        const anchors = options.anchors || collectAnchors(document, options);
        const nearest = Base.nearestAnchor(raw, anchors, toleranceMm, target => Base.isJoint(target) && Math.abs(G.distance(c, target.point) - radius) <= Base.AXIS_EPSILON_MM);
        const point = nearest ? nearest.target.point : G.pointAt(c, radius, G.angleDeg(c, raw));
        return Object.freeze({ point, rawPoint: raw, snapped: Boolean(nearest), target: nearest ? nearest.target : null, distanceMm: nearest ? G.roundMm(nearest.distanceMm) : null, toleranceMm: G.roundMm(toleranceMm), axis: null, anchor: c, kind: nearest ? "joint" : "arc" });
    }

    root.Snapping = Object.freeze({ ...Base, pathAnchors, anchorsForObject, collectAnchors, resolvePoint, resolveObjectMove, resolveArcEndpoint });
    root.SmartPathSnapping = Object.freeze({ pathAnchors, anchorsForObject, collectAnchors });
})();
