(() => {
    "use strict";

    const root = window.AlmdinaDoorDrawingV3 = window.AlmdinaDoorDrawingV3 || Object.create(null);
    const G = root.Geometry;
    const D = root.DocumentModel;
    if (!G || !D) throw new Error("Door Drawing V3 domain must load before snapping");

    const DEFAULT_SNAP_PX = 22;
    const JOIN_SNAP_PX = 26;
    const MOVE_JOIN_SNAP_PX = 46;
    const SNAP_RELEASE_FACTOR = 1.55;
    const MOVE_SNAP_RELEASE_FACTOR = 1.8;
    const AXIS_EPSILON_MM = 0.01;

    function freezeAnchor(objectId, role, point, priority = 0, kind = "reference") {
        return Object.freeze({
            objectId: String(objectId || ""),
            role: String(role || "point"),
            point: G.point(point && point.x, point && point.y),
            priority: Number(priority) || 0,
            kind: String(kind || "reference"),
        });
    }

    function objectAnchors(object) {
        if (!object || !object.geometry) return Object.freeze([]);
        const g = object.geometry;
        const anchors = [];

        if (object.type === "line") {
            anchors.push(freezeAnchor(object.id, "start", g.start, 100, "joint"));
            anchors.push(freezeAnchor(object.id, "end", g.end, 100, "joint"));
        } else if (object.type === "rectangle") {
            const x = g.origin.x;
            const y = g.origin.y;
            const right = x + g.widthMm;
            const top = y + g.heightMm;
            anchors.push(freezeAnchor(object.id, "bottom-left", G.point(x, y), 90, "joint"));
            anchors.push(freezeAnchor(object.id, "bottom-right", G.point(right, y), 90, "joint"));
            anchors.push(freezeAnchor(object.id, "top-right", G.point(right, top), 90, "joint"));
            anchors.push(freezeAnchor(object.id, "top-left", G.point(x, top), 90, "joint"));
        } else if (object.type === "circle") {
            const c = g.center;
            const r = g.radiusMm;
            anchors.push(freezeAnchor(object.id, "east", G.point(c.x + r, c.y), 70, "joint"));
            anchors.push(freezeAnchor(object.id, "north", G.point(c.x, c.y + r), 70, "joint"));
            anchors.push(freezeAnchor(object.id, "west", G.point(c.x - r, c.y), 70, "joint"));
            anchors.push(freezeAnchor(object.id, "south", G.point(c.x, c.y - r), 70, "joint"));
            anchors.push(freezeAnchor(object.id, "center", c, 10, "reference"));
        } else if (object.type === "arc") {
            anchors.push(freezeAnchor(object.id, "start", G.arcStart(object), 100, "joint"));
            anchors.push(freezeAnchor(object.id, "end", G.arcEnd(object), 100, "joint"));
            anchors.push(freezeAnchor(object.id, "center", g.center, 10, "reference"));
        }

        return Object.freeze(anchors);
    }

    function collectAnchors(document, options = {}) {
        const excluded = new Set(
            (Array.isArray(options.excludeIds) ? options.excludeIds : [options.excludeId])
                .filter(Boolean)
                .map(String)
        );
        const anchors = [];
        for (const object of (document && document.objects) || []) {
            if (excluded.has(String(object.id))) continue;
            anchors.push(...objectAnchors(object));
        }
        return Object.freeze(anchors);
    }

    function worldTolerance(viewportScale, snapPx = DEFAULT_SNAP_PX) {
        const scale = Math.max(0.000001, Math.abs(G.number(viewportScale, 1)));
        return Math.max(0, G.number(snapPx, DEFAULT_SNAP_PX)) / scale;
    }

    function nearestAnchor(candidate, anchors, toleranceMm, predicate = null) {
        const point = G.point(candidate && candidate.x, candidate && candidate.y);
        const tolerance = Math.max(0, G.number(toleranceMm));
        let best = null;
        for (const anchor of anchors || []) {
            if (predicate && !predicate(anchor)) continue;
            const distanceMm = G.distance(point, anchor.point);
            if (distanceMm > tolerance) continue;
            if (
                !best
                || distanceMm < best.distanceMm - G.EPSILON_MM
                || (Math.abs(distanceMm - best.distanceMm) <= G.EPSILON_MM && anchor.priority > best.target.priority)
            ) {
                best = { target: anchor, distanceMm };
            }
        }
        return best;
    }

    function isJoint(anchor) {
        return Boolean(anchor && anchor.kind === "joint");
    }

    function sameAnchor(anchor, identity) {
        return Boolean(anchor && identity
            && String(anchor.objectId) === String(identity.objectId)
            && String(anchor.role) === String(identity.role));
    }

    function stickyAnchor(candidate, anchors, target, toleranceMm, predicate = null) {
        if (!target) return null;
        const found = (anchors || []).find(anchor => sameAnchor(anchor, target));
        if (!found || (predicate && !predicate(found))) return null;
        const distanceMm = G.distance(candidate, found.point);
        return distanceMm <= toleranceMm * SNAP_RELEASE_FACTOR
            ? { target: found, distanceMm }
            : null;
    }

    function preferredAnchor(candidate, anchors, options = {}) {
        const normalToleranceMm = Math.max(0, G.number(options.toleranceMm));
        const joinToleranceMm = Math.max(normalToleranceMm, G.number(options.joinToleranceMm, normalToleranceMm));
        const predicate = options.predicate || null;
        const sticky = stickyAnchor(candidate, anchors, options.stickyTarget, joinToleranceMm, predicate);
        if (sticky) return sticky;
        const joint = nearestAnchor(candidate, anchors, joinToleranceMm, anchor => (
            isJoint(anchor) && (!predicate || predicate(anchor))
        ));
        if (joint) return joint;
        return nearestAnchor(candidate, anchors, normalToleranceMm, predicate);
    }

    function axisLock(anchor, candidate, forcedAxis = null) {
        const start = G.point(anchor && anchor.x, anchor && anchor.y);
        const raw = G.point(candidate && candidate.x, candidate && candidate.y);
        const dx = raw.x - start.x;
        const dy = raw.y - start.y;
        const axis = forcedAxis === "horizontal" || forcedAxis === "vertical"
            ? forcedAxis
            : (Math.abs(dx) >= Math.abs(dy) ? "horizontal" : "vertical");
        return Object.freeze({
            axis,
            anchor: start,
            point: axis === "horizontal" ? G.point(raw.x, start.y) : G.point(start.x, raw.y),
        });
    }

    function resolvePoint(document, candidate, options = {}) {
        const raw = G.point(candidate && candidate.x, candidate && candidate.y);
        const toleranceMm = worldTolerance(options.viewportScale, options.snapPx);
        const joinToleranceMm = worldTolerance(options.viewportScale, options.joinSnapPx || JOIN_SNAP_PX);
        const anchors = options.anchors || collectAnchors(document, options);
        const reference = options.anchor ? G.point(options.anchor.x, options.anchor.y) : null;
        const forcedAxis = options.forcedAxis === "horizontal" || options.forcedAxis === "vertical"
            ? options.forcedAxis
            : null;
        const useAxisLock = Boolean(reference && (forcedAxis || (options.axisLock && options.shiftKey)));
        let point = raw;
        let axis = null;
        let snapped = null;

        if (useAxisLock) {
            const locked = axisLock(reference, raw, forcedAxis);
            point = locked.point;
            axis = locked.axis;
            const compatible = target => axis === "horizontal"
                ? Math.abs(target.point.y - reference.y) <= AXIS_EPSILON_MM
                : Math.abs(target.point.x - reference.x) <= AXIS_EPSILON_MM;
            snapped = preferredAnchor(point, anchors, {
                toleranceMm,
                joinToleranceMm,
                predicate: compatible,
                stickyTarget: options.stickyTarget,
            });
        } else {
            snapped = preferredAnchor(point, anchors, {
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
            kind: snapped && isJoint(snapped.target) ? "joint" : "reference",
        });
    }

    function resolveObjectMove(document, object, deltaX, deltaY, options = {}) {
        const dx = G.number(deltaX);
        const dy = G.number(deltaY);
        const moved = G.translateObject(object, dx, dy);
        const sourceAnchors = objectAnchors(moved).filter(isJoint);
        const targetAnchors = collectAnchors(document, { excludeId: object && object.id }).filter(isJoint);
        const toleranceMm = worldTolerance(options.viewportScale, options.moveJoinSnapPx || MOVE_JOIN_SNAP_PX);
        const releaseToleranceMm = toleranceMm * MOVE_SNAP_RELEASE_FACTOR;
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
                const candidate = nearestAnchor(source.point, targetAnchors, toleranceMm);
                if (!candidate) continue;
                if (
                    !best
                    || candidate.distanceMm < best.distanceMm - G.EPSILON_MM
                    || (Math.abs(candidate.distanceMm - best.distanceMm) <= G.EPSILON_MM && candidate.target.priority > best.target.priority)
                ) {
                    best = { source, target: candidate.target, distanceMm: candidate.distanceMm, sticky: false };
                }
            }
        }

        if (!best) {
            return Object.freeze({
                object: moved,
                point: null,
                rawPoint: null,
                snapped: false,
                target: null,
                source: null,
                distanceMm: null,
                toleranceMm: G.roundMm(toleranceMm),
                releaseToleranceMm: G.roundMm(releaseToleranceMm),
                axis: null,
                anchor: null,
                kind: "move",
                sticky: false,
            });
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
        const toleranceMm = worldTolerance(options.viewportScale, options.joinSnapPx || JOIN_SNAP_PX);
        const anchors = options.anchors || collectAnchors(document, options);
        const nearest = nearestAnchor(raw, anchors, toleranceMm, target => (
            isJoint(target) && Math.abs(G.distance(c, target.point) - radius) <= AXIS_EPSILON_MM
        ));
        const point = nearest
            ? nearest.target.point
            : G.pointAt(c, radius, G.angleDeg(c, raw));
        return Object.freeze({
            point,
            rawPoint: raw,
            snapped: Boolean(nearest),
            target: nearest ? nearest.target : null,
            distanceMm: nearest ? G.roundMm(nearest.distanceMm) : null,
            toleranceMm: G.roundMm(toleranceMm),
            axis: null,
            anchor: c,
            kind: nearest ? "joint" : "arc",
        });
    }

    root.Snapping = Object.freeze({
        DEFAULT_SNAP_PX,
        JOIN_SNAP_PX,
        MOVE_JOIN_SNAP_PX,
        SNAP_RELEASE_FACTOR,
        MOVE_SNAP_RELEASE_FACTOR,
        AXIS_EPSILON_MM,
        objectAnchors,
        collectAnchors,
        worldTolerance,
        nearestAnchor,
        isJoint,
        preferredAnchor,
        axisLock,
        resolvePoint,
        resolveObjectMove,
        resolveArcEndpoint,
    });
})();
