(() => {
    "use strict";

    const root = window.AlmdinaDoorDrawingV3 = window.AlmdinaDoorDrawingV3 || Object.create(null);
    const G = root.Geometry;
    const D = root.DocumentModel;
    if (!G || !D) throw new Error("Door Drawing V3 domain must load before snapping");

    const DEFAULT_SNAP_PX = 14;
    const AXIS_EPSILON_MM = 0.01;

    function freezeAnchor(objectId, role, point, priority = 0) {
        return Object.freeze({
            objectId: String(objectId || ""),
            role: String(role || "point"),
            point: G.point(point && point.x, point && point.y),
            priority: Number(priority) || 0,
        });
    }

    function objectAnchors(object) {
        if (!object || !object.geometry) return Object.freeze([]);
        const g = object.geometry;
        const anchors = [];

        if (object.type === "line") {
            anchors.push(freezeAnchor(object.id, "start", g.start, 50));
            anchors.push(freezeAnchor(object.id, "end", g.end, 50));
        } else if (object.type === "rectangle") {
            const x = g.origin.x;
            const y = g.origin.y;
            const right = x + g.widthMm;
            const top = y + g.heightMm;
            anchors.push(freezeAnchor(object.id, "bottom-left", G.point(x, y), 40));
            anchors.push(freezeAnchor(object.id, "bottom-right", G.point(right, y), 40));
            anchors.push(freezeAnchor(object.id, "top-right", G.point(right, top), 40));
            anchors.push(freezeAnchor(object.id, "top-left", G.point(x, top), 40));
        } else if (object.type === "circle") {
            const c = g.center;
            const r = g.radiusMm;
            anchors.push(freezeAnchor(object.id, "east", G.point(c.x + r, c.y), 30));
            anchors.push(freezeAnchor(object.id, "north", G.point(c.x, c.y + r), 30));
            anchors.push(freezeAnchor(object.id, "west", G.point(c.x - r, c.y), 30));
            anchors.push(freezeAnchor(object.id, "south", G.point(c.x, c.y - r), 30));
            anchors.push(freezeAnchor(object.id, "center", c, 10));
        } else if (object.type === "arc") {
            anchors.push(freezeAnchor(object.id, "start", G.arcStart(object), 50));
            anchors.push(freezeAnchor(object.id, "end", G.arcEnd(object), 50));
            anchors.push(freezeAnchor(object.id, "center", g.center, 10));
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
            snapped = nearestAnchor(point, anchors, toleranceMm, compatible);
        } else {
            snapped = nearestAnchor(point, anchors, toleranceMm);
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
            axis,
            anchor: reference,
        });
    }

    function resolveArcEndpoint(document, candidate, center, radiusMm, options = {}) {
        const raw = G.point(candidate && candidate.x, candidate && candidate.y);
        const c = G.point(center && center.x, center && center.y);
        const radius = Math.max(G.EPSILON_MM, G.number(radiusMm));
        const toleranceMm = worldTolerance(options.viewportScale, options.snapPx);
        const anchors = options.anchors || collectAnchors(document, options);
        const nearest = nearestAnchor(raw, anchors, toleranceMm, target => (
            Math.abs(G.distance(c, target.point) - radius) <= AXIS_EPSILON_MM
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
        });
    }

    root.Snapping = Object.freeze({
        DEFAULT_SNAP_PX,
        AXIS_EPSILON_MM,
        objectAnchors,
        collectAnchors,
        worldTolerance,
        nearestAnchor,
        axisLock,
        resolvePoint,
        resolveArcEndpoint,
    });
})();
