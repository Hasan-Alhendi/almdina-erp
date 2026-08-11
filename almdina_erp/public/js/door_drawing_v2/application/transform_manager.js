(() => {
    "use strict";

    const root = window.AlmdinaDoorDrawingV2 = window.AlmdinaDoorDrawingV2 || Object.create(null);
    const precision = root.Precision;
    const geometryEngine = root.Geometry;
    const documents = root.DocumentModel;
    if (!precision || !geometryEngine || !documents) {
        throw new Error("Door Drawing V2 domain must load before TransformManager");
    }

    function clone(value) {
        return value == null ? value : JSON.parse(JSON.stringify(value));
    }

    function point(value, label = "point") {
        return precision.point(value, label);
    }

    function translatedPoint(value, dx, dy) {
        const source = point(value);
        return point({ x: source.x + dx, y: source.y + dy });
    }

    function rotatePoint(value, pivot, angleDeg) {
        const source = point(value);
        const center = point(pivot, "pivot");
        const radians = precision.assertFinite(angleDeg, "angleDeg") * Math.PI / 180;
        const cos = Math.cos(radians);
        const sin = Math.sin(radians);
        const dx = source.x - center.x;
        const dy = source.y - center.y;
        return point({
            x: center.x + dx * cos - dy * sin,
            y: center.y + dx * sin + dy * cos,
        });
    }

    function mapBezierSegments(segments, mapper) {
        return (segments || []).map(segment => ({
            start: mapper(segment.start),
            control1: mapper(segment.control1),
            control2: mapper(segment.control2),
            end: mapper(segment.end),
        }));
    }

    function translateObject(object, dxMm, dyMm) {
        if (!object || object.locked) return clone(object);
        const dx = precision.assertFinite(dxMm, "dxMm");
        const dy = precision.assertFinite(dyMm, "dyMm");
        const next = clone(object);
        const g = next.geometry || {};
        const map = value => translatedPoint(value, dx, dy);
        if (next.type === "point") g.point = map(g.point);
        else if (next.type === "line") { g.start = map(g.start); g.end = map(g.end); }
        else if (next.type === "rectangle") { g.x = precision.serialized(g.x + dx); g.y = precision.serialized(g.y + dy); }
        else if (next.type === "circle" || next.type === "ellipse" || next.type === "arc") g.center = map(g.center);
        else if (next.type === "polyline" || next.type === "polygon") g.points = (g.points || []).map(map);
        else if (next.type === "bezier") g.segments = mapBezierSegments(g.segments, map);
        else if (next.type === "text") g.position = map(g.position);
        else if (next.type === "guide") g.value = precision.serialized(g.value + (g.axis === "x" ? dx : dy));
        next.geometry = g;
        return documents.normalizeObject(next);
    }

    function translateSelection(document, objectIds, dxMm, dyMm) {
        const ids = new Set((Array.isArray(objectIds) ? objectIds : []).map(String));
        let next = documents.parse(document);
        next.objects.forEach(object => {
            if (!ids.has(object.id) || object.locked) return;
            next = documents.replaceObject(next, object.id, translateObject(object, dxMm, dyMm));
        });
        return next;
    }

    function setLineEndpoint(document, objectId, role, nextPointMm, options = {}) {
        const parsed = documents.parse(document);
        const current = parsed.objects.find(object => object.id === String(objectId));
        if (!current || current.type !== "line") throw new TypeError("Selected object must be a line");
        if (current.locked) return parsed;
        const fixedRole = role === "start" ? "end" : "start";
        const targetRole = role === "start" ? "start" : "end";
        const fixed = point(current.geometry[fixedRole], `line.${fixedRole}`);
        let target = point(nextPointMm, `line.${targetRole}`);
        if (options.axisLock === "dominant") {
            const dx = Math.abs(target.x - fixed.x);
            const dy = Math.abs(target.y - fixed.y);
            target = point(dx >= dy
                ? { x: target.x, y: fixed.y }
                : { x: fixed.x, y: target.y });
        }
        if (geometryEngine.distance(fixed, target) <= precision.EPSILON_MM) {
            throw new RangeError("Line endpoint cannot collapse onto the opposite endpoint");
        }
        const replacement = clone(current);
        replacement.geometry[targetRole] = target;
        return documents.replaceObject(parsed, current.id, replacement);
    }

    function setLineLength(document, objectId, lengthMm, options = {}) {
        const parsed = documents.parse(document);
        const current = parsed.objects.find(object => object.id === String(objectId));
        if (!current || current.type !== "line") throw new TypeError("Selected object must be a line");
        const length = precision.assertFinite(lengthMm, "lengthMm");
        if (length <= precision.EPSILON_MM) throw new RangeError("Line length must be greater than zero");
        const anchor = options.anchor === "end" ? "end" : "start";
        const angle = options.angleDeg == null
            ? geometryEngine.lineAngleDeg(current.geometry)
            : geometryEngine.normalizeAngleDeg(options.angleDeg);
        const replacement = clone(current);
        if (anchor === "start") {
            replacement.geometry.end = geometryEngine.pointAt(replacement.geometry.start, length, angle);
        } else {
            replacement.geometry.start = geometryEngine.pointAt(
                replacement.geometry.end,
                length,
                geometryEngine.normalizeAngleDeg(angle + 180)
            );
        }
        return documents.replaceObject(parsed, current.id, replacement);
    }

    function rotateObject(object, angleDeg, pivotMm) {
        if (!object || object.locked) return clone(object);
        const angle = geometryEngine.normalizeAngleDeg(angleDeg);
        const pivot = point(pivotMm, "pivotMm");
        const next = clone(object);
        const g = next.geometry || {};
        const map = value => rotatePoint(value, pivot, angle);
        if (next.type === "point") g.point = map(g.point);
        else if (next.type === "line") { g.start = map(g.start); g.end = map(g.end); }
        else if (next.type === "circle" || next.type === "ellipse") g.center = map(g.center);
        else if (next.type === "arc") {
            g.center = map(g.center);
            g.startAngleDeg = geometryEngine.normalizeAngleDeg(g.startAngleDeg + angle);
            g.endAngleDeg = geometryEngine.normalizeAngleDeg(g.endAngleDeg + angle);
        } else if (next.type === "polyline" || next.type === "polygon") g.points = (g.points || []).map(map);
        else if (next.type === "bezier") g.segments = mapBezierSegments(g.segments, map);
        else if (next.type === "text") {
            g.position = map(g.position);
            g.rotationDeg = geometryEngine.normalizeAngleDeg((Number(g.rotationDeg) || 0) + angle);
        } else if (next.type === "rectangle") {
            const center = { x: Number(g.x) + Number(g.width) / 2, y: Number(g.y) + Number(g.height) / 2 };
            const rotatedCenter = map(center);
            g.x = precision.serialized(rotatedCenter.x - Number(g.width) / 2);
            g.y = precision.serialized(rotatedCenter.y - Number(g.height) / 2);
            g.rotationDeg = geometryEngine.normalizeAngleDeg((Number(g.rotationDeg) || 0) + angle);
        }
        next.geometry = g;
        return documents.normalizeObject(next);
    }

    function rotateSelection(document, objectIds, angleDeg, pivotMm) {
        const ids = new Set((Array.isArray(objectIds) ? objectIds : []).map(String));
        let next = documents.parse(document);
        next.objects.forEach(object => {
            if (!ids.has(object.id) || object.locked) return;
            next = documents.replaceObject(next, object.id, rotateObject(object, angleDeg, pivotMm));
        });
        return next;
    }

    function selectionBounds(document, objectIds) {
        const parsed = documents.parse(document);
        const ids = new Set((Array.isArray(objectIds) ? objectIds : []).map(String));
        const bounds = parsed.objects
            .filter(object => ids.has(object.id) && object.visible !== false)
            .map(object => geometryEngine.bounds(object))
            .filter(Boolean);
        if (!bounds.length) return null;
        const left = Math.min(...bounds.map(item => item.x));
        const bottom = Math.min(...bounds.map(item => item.y));
        const right = Math.max(...bounds.map(item => item.x + item.width));
        const top = Math.max(...bounds.map(item => item.y + item.height));
        return Object.freeze({
            x: precision.serialized(left),
            y: precision.serialized(bottom),
            width: precision.serialized(right - left),
            height: precision.serialized(top - bottom),
            center: point({ x: (left + right) / 2, y: (bottom + top) / 2 }),
        });
    }

    root.TransformManager = Object.freeze({
        translatedPoint,
        rotatePoint,
        translateObject,
        translateSelection,
        setLineEndpoint,
        setLineLength,
        rotateObject,
        rotateSelection,
        selectionBounds,
    });
})();
