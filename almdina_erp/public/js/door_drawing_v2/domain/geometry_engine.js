(() => {
    "use strict";

    const root = window.AlmdinaDoorDrawingV2 = window.AlmdinaDoorDrawingV2 || Object.create(null);
    const precision = root.Precision;
    if (!precision) throw new Error("Door Drawing V2 Precision must load before GeometryEngine");

    const OBJECT_TYPES = Object.freeze([
        "point", "line", "rectangle", "arc", "circle", "ellipse",
        "polyline", "polygon", "bezier", "text", "dimension", "guide",
    ]);
    const OBJECT_TYPE_SET = new Set(OBJECT_TYPES);

    function p(value, label = "point") {
        return precision.point(value, label);
    }

    function distance(first, second) {
        const a = p(first, "first");
        const b = p(second, "second");
        return precision.serialized(Math.hypot(b.x - a.x, b.y - a.y));
    }

    function normalizeAngleDeg(value) {
        let angle = precision.assertFinite(value, "angle") % 360;
        if (angle <= -180) angle += 360;
        if (angle > 180) angle -= 360;
        return precision.serialized(angle);
    }

    function lineLength(geometry) {
        return distance(geometry.start, geometry.end);
    }

    function lineAngleDeg(geometry) {
        const start = p(geometry.start, "line.start");
        const end = p(geometry.end, "line.end");
        return normalizeAngleDeg(Math.atan2(end.y - start.y, end.x - start.x) * 180 / Math.PI);
    }

    function pointAt(start, lengthMm, angleDeg) {
        const origin = p(start, "start");
        const length = precision.assertFinite(lengthMm, "lengthMm");
        if (length < 0) throw new RangeError("lengthMm cannot be negative");
        const radians = normalizeAngleDeg(angleDeg) * Math.PI / 180;
        return p({
            x: origin.x + Math.cos(radians) * length,
            y: origin.y + Math.sin(radians) * length,
        });
    }

    function positiveSweep(startAngleDeg, endAngleDeg, clockwise = false) {
        const start = ((precision.assertFinite(startAngleDeg) % 360) + 360) % 360;
        const end = ((precision.assertFinite(endAngleDeg) % 360) + 360) % 360;
        let sweep = clockwise ? start - end : end - start;
        while (sweep < 0) sweep += 360;
        while (sweep >= 360) sweep -= 360;
        return precision.serialized(sweep);
    }

    function arcLength(geometry) {
        const radius = precision.assertFinite(geometry.radius, "arc.radius");
        if (radius <= 0) throw new RangeError("arc.radius must be greater than zero");
        const sweep = positiveSweep(geometry.startAngleDeg, geometry.endAngleDeg, Boolean(geometry.clockwise));
        return precision.serialized(radius * sweep * Math.PI / 180);
    }

    function signedPolygonArea(points) {
        const source = normalizePoints(points, "polygon.points");
        if (source.length < 3) return 0;
        const twiceArea = source.reduce((sum, current, index) => {
            const next = source[(index + 1) % source.length];
            return sum + current.x * next.y - next.x * current.y;
        }, 0);
        return precision.serialized(twiceArea / 2);
    }

    function polygonArea(points) {
        return precision.serialized(Math.abs(signedPolygonArea(points)));
    }

    function normalizePoints(points, label = "points") {
        if (!Array.isArray(points)) throw new TypeError(`${label} must be an array`);
        return points.map((value, index) => p(value, `${label}[${index}]`));
    }

    function polylineLength(points, closed = false) {
        const source = normalizePoints(points, "polyline.points");
        if (source.length < 2) return 0;
        let total = 0;
        for (let index = 1; index < source.length; index += 1) total += distance(source[index - 1], source[index]);
        if (closed && source.length > 2) total += distance(source[source.length - 1], source[0]);
        return precision.serialized(total);
    }

    function cubicBezierPoint(segment, t) {
        const start = p(segment.start, "bezier.start");
        const control1 = p(segment.control1, "bezier.control1");
        const control2 = p(segment.control2, "bezier.control2");
        const end = p(segment.end, "bezier.end");
        const ratio = Math.max(0, Math.min(1, precision.assertFinite(t, "t")));
        const inverse = 1 - ratio;
        return p({
            x: inverse ** 3 * start.x + 3 * inverse ** 2 * ratio * control1.x + 3 * inverse * ratio ** 2 * control2.x + ratio ** 3 * end.x,
            y: inverse ** 3 * start.y + 3 * inverse ** 2 * ratio * control1.y + 3 * inverse * ratio ** 2 * control2.y + ratio ** 3 * end.y,
        });
    }

    function pointToLineDistance(point, start, end) {
        const target = p(point);
        const a = p(start);
        const b = p(end);
        const dx = b.x - a.x;
        const dy = b.y - a.y;
        const lengthSquared = dx * dx + dy * dy;
        if (!lengthSquared) return distance(target, a);
        const ratio = Math.max(0, Math.min(1, ((target.x - a.x) * dx + (target.y - a.y) * dy) / lengthSquared));
        return Math.hypot(target.x - (a.x + ratio * dx), target.y - (a.y + ratio * dy));
    }

    function splitCubic(segment) {
        const a = p(segment.start), b = p(segment.control1), c = p(segment.control2), d = p(segment.end);
        const ab = p({ x:(a.x+b.x)/2, y:(a.y+b.y)/2 });
        const bc = p({ x:(b.x+c.x)/2, y:(b.y+c.y)/2 });
        const cd = p({ x:(c.x+d.x)/2, y:(c.y+d.y)/2 });
        const abc = p({ x:(ab.x+bc.x)/2, y:(ab.y+bc.y)/2 });
        const bcd = p({ x:(bc.x+cd.x)/2, y:(bc.y+cd.y)/2 });
        const midpoint = p({ x:(abc.x+bcd.x)/2, y:(abc.y+bcd.y)/2 });
        return [
            { start:a, control1:ab, control2:abc, end:midpoint },
            { start:midpoint, control1:bcd, control2:cd, end:d },
        ];
    }

    function flattenCubicBezier(segment, toleranceMm = 0.05, maxDepth = 14) {
        const tolerance = Math.max(precision.EPSILON_MM, precision.assertFinite(toleranceMm, "toleranceMm"));
        const result = [p(segment.start, "bezier.start")];
        function visit(current, depth) {
            const flatness = Math.max(
                pointToLineDistance(current.control1, current.start, current.end),
                pointToLineDistance(current.control2, current.start, current.end),
            );
            if (flatness <= tolerance || depth >= maxDepth) {
                result.push(p(current.end));
                return;
            }
            const [left, right] = splitCubic(current);
            visit(left, depth + 1);
            visit(right, depth + 1);
        }
        visit(segment, 0);
        return result;
    }

    function rectanglePoints(geometry) {
        const x = precision.assertFinite(geometry.x, "rectangle.x");
        const y = precision.assertFinite(geometry.y, "rectangle.y");
        const width = precision.assertFinite(geometry.width, "rectangle.width");
        const height = precision.assertFinite(geometry.height, "rectangle.height");
        if (width < 0 || height < 0) throw new RangeError("rectangle dimensions cannot be negative");
        return [p({x,y}), p({x:x+width,y}), p({x:x+width,y:y+height}), p({x,y:y+height})];
    }

    function boundsFromPoints(points) {
        const source = normalizePoints(points, "bounds.points");
        if (!source.length) return null;
        const xs = source.map(item => item.x);
        const ys = source.map(item => item.y);
        const minX = Math.min(...xs), maxX = Math.max(...xs), minY = Math.min(...ys), maxY = Math.max(...ys);
        return Object.freeze({ x:minX, y:minY, width:precision.serialized(maxX-minX), height:precision.serialized(maxY-minY) });
    }

    function bounds(object) {
        if (!object || !OBJECT_TYPE_SET.has(object.type)) return null;
        const geometry = object.geometry || {};
        if (object.type === "point") return boundsFromPoints([geometry.point]);
        if (object.type === "line") return boundsFromPoints([geometry.start, geometry.end]);
        if (object.type === "rectangle") return boundsFromPoints(rectanglePoints(geometry));
        if (object.type === "circle") {
            const center = p(geometry.center); const radius = precision.assertFinite(geometry.radius);
            return Object.freeze({ x:center.x-radius, y:center.y-radius, width:radius*2, height:radius*2 });
        }
        if (object.type === "ellipse") {
            const center = p(geometry.center); const rx = precision.assertFinite(geometry.rx); const ry = precision.assertFinite(geometry.ry);
            return Object.freeze({ x:center.x-rx, y:center.y-ry, width:rx*2, height:ry*2 });
        }
        if (object.type === "polyline" || object.type === "polygon") return boundsFromPoints(geometry.points);
        if (object.type === "bezier") {
            const points = [];
            (geometry.segments || []).forEach(segment => points.push(...flattenCubicBezier(segment, 0.05)));
            return boundsFromPoints(points);
        }
        if (object.type === "text") return boundsFromPoints([geometry.position]);
        if (object.type === "guide") {
            const value = precision.assertFinite(geometry.value);
            return geometry.axis === "x" ? Object.freeze({x:value,y:0,width:0,height:0}) : Object.freeze({x:0,y:value,width:0,height:0});
        }
        return null;
    }

    function validateObject(object) {
        const errors = [];
        if (!object || typeof object !== "object") return { valid:false, errors:["Object must be an object"] };
        if (!OBJECT_TYPE_SET.has(object.type)) errors.push(`Unsupported object type: ${String(object.type || "")}`);
        const geometry = object.geometry;
        if (!geometry || typeof geometry !== "object") errors.push("Object geometry is required");
        if (errors.length) return { valid:false, errors };
        try {
            if (object.type === "point") p(geometry.point);
            else if (object.type === "line") { p(geometry.start); p(geometry.end); if (lineLength(geometry) <= precision.EPSILON_MM) errors.push("Line length must be greater than zero"); }
            else if (object.type === "rectangle") rectanglePoints(geometry);
            else if (object.type === "circle") { p(geometry.center); if (precision.assertFinite(geometry.radius) <= 0) errors.push("Circle radius must be greater than zero"); }
            else if (object.type === "ellipse") { p(geometry.center); if (precision.assertFinite(geometry.rx) <= 0 || precision.assertFinite(geometry.ry) <= 0) errors.push("Ellipse radii must be greater than zero"); }
            else if (object.type === "arc") { p(geometry.center); if (precision.assertFinite(geometry.radius) <= 0) errors.push("Arc radius must be greater than zero"); arcLength(geometry); }
            else if (object.type === "polyline") { if (normalizePoints(geometry.points).length < 2) errors.push("Polyline needs at least two points"); }
            else if (object.type === "polygon") { if (normalizePoints(geometry.points).length < 3) errors.push("Polygon needs at least three points"); else if (polygonArea(geometry.points) <= precision.EPSILON_MM) errors.push("Polygon area must be greater than zero"); }
            else if (object.type === "bezier") {
                if (!Array.isArray(geometry.segments) || !geometry.segments.length) errors.push("Bezier needs at least one segment");
                else geometry.segments.forEach(segment => { p(segment.start); p(segment.control1); p(segment.control2); p(segment.end); });
            } else if (object.type === "text") p(geometry.position);
            else if (object.type === "dimension") {
                if (!["horizontal", "vertical", "aligned", "angular", "radius", "diameter"].includes(geometry.kind)) errors.push("Dimension kind is invalid");
                if (!geometry.from || !geometry.to) errors.push("Dimension references are required");
            } else if (object.type === "guide") {
                if (!["x", "y"].includes(geometry.axis)) errors.push("Guide axis must be x or y");
                precision.assertFinite(geometry.value);
            }
        } catch (error) {
            errors.push(error.message || "Invalid geometry");
        }
        return { valid: errors.length === 0, errors };
    }

    root.Geometry = Object.freeze({
        OBJECT_TYPES,
        distance,
        normalizeAngleDeg,
        lineLength,
        lineAngleDeg,
        pointAt,
        positiveSweep,
        arcLength,
        normalizePoints,
        signedPolygonArea,
        polygonArea,
        polylineLength,
        cubicBezierPoint,
        flattenCubicBezier,
        rectanglePoints,
        bounds,
        validateObject,
    });
})();
