(() => {
    "use strict";

    const root = window.AlmdinaDoorDrawingV3 = window.AlmdinaDoorDrawingV3 || Object.create(null);
    const BaseG = root.Geometry;
    const BaseD = root.DocumentModel;
    if (!BaseG || !BaseD) throw new Error("Door Drawing V3 base domain must load before smart path domain");

    const PATH_TYPE = "path";

    function normalizePoints(points) {
        const out = [];
        for (const raw of Array.isArray(points) ? points : []) {
            const p = BaseG.point(raw && raw.x, raw && raw.y);
            if (!out.length || BaseG.distance(out[out.length - 1], p) >= BaseG.EPSILON_MM) out.push(p);
        }
        return out;
    }

    function path(id, points, closed = false, style = {}) {
        const safePoints = normalizePoints(points);
        const isClosed = Boolean(closed);
        const minimum = isClosed ? 3 : 2;
        if (safePoints.length < minimum) throw new Error(isClosed ? "A closed path needs at least three nodes" : "An open path needs at least two nodes");
        const styleObject = BaseG.styleObject
            ? BaseG.styleObject(style)
            : Object.freeze({ stroke: String(style.stroke || "#1e1e1e"), strokeWidthMm: Math.max(0.05, BaseG.roundMm(style.strokeWidthMm || 0.35)) });
        return Object.freeze({
            id: String(id || `path-${Date.now()}`),
            type: PATH_TYPE,
            geometry: Object.freeze({ points: Object.freeze(safePoints.map(p => BaseG.point(p.x, p.y))), closed: isClosed }),
            style: styleObject,
        });
    }

    function pathSegments(object) {
        if (!object || object.type !== PATH_TYPE) return Object.freeze([]);
        const points = object.geometry.points || [];
        const segments = [];
        for (let index = 0; index < points.length - 1; index += 1) segments.push(Object.freeze({ index, start: points[index], end: points[index + 1] }));
        if (object.geometry.closed && points.length > 2) segments.push(Object.freeze({ index: points.length - 1, start: points[points.length - 1], end: points[0] }));
        return Object.freeze(segments);
    }

    function pathLength(object) {
        return BaseG.roundMm(pathSegments(object).reduce((sum, segment) => sum + BaseG.distance(segment.start, segment.end), 0));
    }

    function setPathPoint(object, index, nextPoint) {
        if (!object || object.type !== PATH_TYPE) throw new Error("Expected a path object");
        const points = object.geometry.points.map((p, current) => current === Number(index) ? BaseG.point(nextPoint.x, nextPoint.y) : p);
        return path(object.id, points, object.geometry.closed, object.style);
    }

    function insertPathPoint(object, segmentIndex, nextPoint) {
        if (!object || object.type !== PATH_TYPE) throw new Error("Expected a path object");
        const points = object.geometry.points.slice();
        const index = Math.max(0, Math.min(points.length - 1, Number(segmentIndex) || 0));
        points.splice(index + 1, 0, BaseG.point(nextPoint.x, nextPoint.y));
        return path(object.id, points, object.geometry.closed, object.style);
    }

    function removePathPoint(object, index) {
        if (!object || object.type !== PATH_TYPE) throw new Error("Expected a path object");
        const minimum = object.geometry.closed ? 3 : 2;
        if (object.geometry.points.length <= minimum) return object;
        const points = object.geometry.points.filter((_, current) => current !== Number(index));
        return path(object.id, points, object.geometry.closed, object.style);
    }

    function nearestPointOnSegment(candidate, start, end) {
        const p = BaseG.point(candidate && candidate.x, candidate && candidate.y);
        const a = BaseG.point(start && start.x, start && start.y);
        const b = BaseG.point(end && end.x, end && end.y);
        const dx = b.x - a.x;
        const dy = b.y - a.y;
        const length2 = dx * dx + dy * dy;
        if (length2 <= BaseG.EPSILON_MM * BaseG.EPSILON_MM) return Object.freeze({ point: a, t: 0, distanceMm: BaseG.distance(p, a) });
        const t = Math.max(0, Math.min(1, ((p.x - a.x) * dx + (p.y - a.y) * dy) / length2));
        const projected = BaseG.point(a.x + dx * t, a.y + dy * t);
        return Object.freeze({ point: projected, t, distanceMm: BaseG.roundMm(BaseG.distance(p, projected)) });
    }

    function nearestPathSegment(object, candidate) {
        let best = null;
        for (const segment of pathSegments(object)) {
            const projection = nearestPointOnSegment(candidate, segment.start, segment.end);
            if (!best || projection.distanceMm < best.distanceMm) best = Object.freeze({ ...projection, segmentIndex: segment.index });
        }
        return best;
    }

    const Geometry = Object.freeze({
        ...BaseG,
        PATH_TYPE,
        path,
        pathSegments,
        pathLength,
        setPathPoint,
        insertPathPoint,
        removePathPoint,
        nearestPointOnSegment,
        nearestPathSegment,
        translateObject(object, dxMm, dyMm) {
            if (object && object.type === PATH_TYPE) {
                const dx = BaseG.number(dxMm), dy = BaseG.number(dyMm);
                return path(object.id, object.geometry.points.map(p => BaseG.point(p.x + dx, p.y + dy)), object.geometry.closed, object.style);
            }
            return BaseG.translateObject(object, dxMm, dyMm);
        },
        cloneObject(object, id = object && object.id) {
            if (object && object.type === PATH_TYPE) return path(id, object.geometry.points, object.geometry.closed, object.style);
            return BaseG.cloneObject(object, id);
        },
    });

    const SUPPORTED_TYPES = Object.freeze([...BaseD.SUPPORTED_TYPES.filter(type => type !== PATH_TYPE), PATH_TYPE]);
    function cloneObject(object) { return Geometry.cloneObject(object); }
    function freezeDocument(document) {
        return Object.freeze({
            schema: BaseD.SCHEMA,
            version: BaseD.VERSION,
            units: BaseD.UNITS,
            blank: Object.freeze({ widthMm: Geometry.roundMm(document.blank && document.blank.widthMm), heightMm: Geometry.roundMm(document.blank && document.blank.heightMm) }),
            objects: Object.freeze((document.objects || []).map(cloneObject)),
        });
    }
    function create(options = {}) {
        return freezeDocument({
            blank: { widthMm: Math.max(0, Geometry.number(options.widthMm)), heightMm: Math.max(0, Geometry.number(options.heightMm)) },
            objects: Array.isArray(options.objects) ? options.objects : [],
        });
    }
    function normalizeObject(item) {
        if (!item || !SUPPORTED_TYPES.includes(item.type) || !item.geometry) return null;
        if (item.type === PATH_TYPE) return Geometry.path(item.id, item.geometry.points, item.geometry.closed, item.style || {});
        const temp = BaseD.normalize({ schema: BaseD.SCHEMA, version: BaseD.VERSION, units: BaseD.UNITS, blank: { widthMm: 1, heightMm: 1 }, objects: [item] });
        return temp.objects[0] || null;
    }
    function normalize(raw, fallback = {}) {
        if (!raw || typeof raw !== "object") return create(fallback);
        if (raw.schema !== BaseD.SCHEMA || Number(raw.version) !== BaseD.VERSION || raw.units !== BaseD.UNITS) return create(fallback);
        const objects = [];
        for (const item of Array.isArray(raw.objects) ? raw.objects : []) {
            try { const object = normalizeObject(item); if (object) objects.push(object); } catch (error) { /* skip corrupt object */ }
        }
        return create({ widthMm: raw.blank && raw.blank.widthMm, heightMm: raw.blank && raw.blank.heightMm, objects });
    }
    function objectById(document, id) { return (document && document.objects || []).find(object => String(object.id) === String(id || "")) || null; }
    function addObject(document, object) {
        if (objectById(document, object && object.id)) throw new Error("Duplicate drawing object id");
        return freezeDocument({ ...document, objects: [...document.objects, cloneObject(object)] });
    }
    function replaceObject(document, object) {
        let found = false;
        const objects = document.objects.map(item => {
            if (String(item.id) !== String(object.id)) return item;
            found = true;
            return cloneObject(object);
        });
        if (!found) throw new Error("Drawing object not found");
        return freezeDocument({ ...document, objects });
    }
    function removeObject(document, id) { return freezeDocument({ ...document, objects: document.objects.filter(object => String(object.id) !== String(id)) }); }
    function serialize(document) { return JSON.stringify(document); }

    root.Geometry = Geometry;
    root.DocumentModel = Object.freeze({ ...BaseD, SUPPORTED_TYPES, create, normalize, objectById, addObject, replaceObject, removeObject, serialize });
    root.SmartPathDomain = Object.freeze({ PATH_TYPE });
})();
