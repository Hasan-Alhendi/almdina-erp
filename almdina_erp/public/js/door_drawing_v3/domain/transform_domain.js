(() => {
    "use strict";

    const root = window.AlmdinaDoorDrawingV3 = window.AlmdinaDoorDrawingV3 || Object.create(null);
    const G = root.Geometry;
    if (!G || !G.path || !G.pathNodes) throw new Error("Door Drawing V3 Bezier geometry must load before transform domain");

    const EPS = G.EPSILON_MM || 0.001;
    const KAPPA = 0.5522847498307936;

    function matrix(a = 1, b = 0, c = 0, d = 1, e = 0, f = 0) {
        return Object.freeze({ a: G.number(a), b: G.number(b), c: G.number(c), d: G.number(d), e: G.number(e), f: G.number(f) });
    }
    function identity() { return matrix(); }
    function multiply(left, right) {
        return matrix(
            left.a * right.a + left.c * right.b,
            left.b * right.a + left.d * right.b,
            left.a * right.c + left.c * right.d,
            left.b * right.c + left.d * right.d,
            left.a * right.e + left.c * right.f + left.e,
            left.b * right.e + left.d * right.f + left.f
        );
    }
    function translation(dx, dy) { return matrix(1, 0, 0, 1, dx, dy); }
    function scaling(sx, sy = sx) { return matrix(sx, 0, 0, sy, 0, 0); }
    function rotation(angleDeg) {
        const radians = G.number(angleDeg) * Math.PI / 180;
        const cos = Math.cos(radians), sin = Math.sin(radians);
        return matrix(cos, sin, -sin, cos, 0, 0);
    }
    function around(pivot, operation) {
        const p = G.point(pivot && pivot.x, pivot && pivot.y);
        return multiply(translation(p.x, p.y), multiply(operation, translation(-p.x, -p.y)));
    }
    function scaleAround(pivot, sx, sy = sx) { return around(pivot, scaling(sx, sy)); }
    function rotateAround(pivot, angleDeg) { return around(pivot, rotation(angleDeg)); }
    function determinant(value) { return value.a * value.d - value.b * value.c; }
    function transformPoint(value, m) {
        const p = G.point(value && value.x, value && value.y);
        return G.point(m.a * p.x + m.c * p.y + m.e, m.b * p.x + m.d * p.y + m.f);
    }
    function transformVector(value, m) {
        if (!value) return null;
        const x = m.a * G.number(value.x) + m.c * G.number(value.y);
        const y = m.b * G.number(value.x) + m.d * G.number(value.y);
        return Math.hypot(x, y) < EPS ? null : Object.freeze({ x: G.roundMm(x), y: G.roundMm(y) });
    }
    function isAxisAligned(m) { return Math.abs(m.b) < 1e-9 && Math.abs(m.c) < 1e-9; }
    function similarityScale(m) {
        const sx = Math.hypot(m.a, m.b), sy = Math.hypot(m.c, m.d);
        const dot = m.a * m.c + m.b * m.d;
        const tolerance = Math.max(1e-7, Math.max(sx, sy) * 1e-7);
        return Math.abs(sx - sy) <= tolerance && Math.abs(dot) <= tolerance ? (sx + sy) / 2 : null;
    }

    function rectanglePath(object) {
        const g = object.geometry, x = g.origin.x, y = g.origin.y, w = g.widthMm, h = g.heightMm;
        return G.path(object.id, [G.point(x, y), G.point(x + w, y), G.point(x + w, y + h), G.point(x, y + h)], true, object.style);
    }
    function circlePath(object) {
        const g = object.geometry, cx = g.center.x, cy = g.center.y, r = g.radiusMm, k = r * KAPPA;
        const points = [G.point(cx + r, cy), G.point(cx, cy + r), G.point(cx - r, cy), G.point(cx, cy - r)];
        const nodes = [
            { type: G.NODE_SMOOTH, in: { x: 0, y: -k }, out: { x: 0, y: k } },
            { type: G.NODE_SMOOTH, in: { x: k, y: 0 }, out: { x: -k, y: 0 } },
            { type: G.NODE_SMOOTH, in: { x: 0, y: k }, out: { x: 0, y: -k } },
            { type: G.NODE_SMOOTH, in: { x: -k, y: 0 }, out: { x: k, y: 0 } },
        ];
        return G.path(object.id, points, true, object.style, nodes);
    }
    function arcPath(object) {
        const g = object.geometry;
        const count = Math.max(1, Math.ceil(Math.abs(g.sweepAngleDeg) / 90));
        const step = g.sweepAngleDeg / count;
        const points = [], nodes = [];
        for (let index = 0; index <= count; index += 1) {
            const angleDeg = g.startAngleDeg + step * index;
            const angle = angleDeg * Math.PI / 180;
            points.push(G.point(g.center.x + Math.cos(angle) * g.radiusMm, g.center.y + Math.sin(angle) * g.radiusMm));
            nodes.push({ type: G.NODE_SMOOTH, in: null, out: null });
        }
        for (let index = 0; index < count; index += 1) {
            const startAngle = (g.startAngleDeg + step * index) * Math.PI / 180;
            const endAngle = (g.startAngleDeg + step * (index + 1)) * Math.PI / 180;
            const alpha = 4 / 3 * Math.tan((endAngle - startAngle) / 4) * g.radiusMm;
            nodes[index].out = { x: -Math.sin(startAngle) * alpha, y: Math.cos(startAngle) * alpha };
            nodes[index + 1].in = { x: Math.sin(endAngle) * alpha, y: -Math.cos(endAngle) * alpha };
        }
        return G.path(object.id, points, false, object.style, nodes);
    }
    function transformPath(object, m) {
        const points = object.geometry.points.map(point => transformPoint(point, m));
        const nodes = G.pathNodes(object).map(node => ({
            type: node.type,
            in: transformVector(node.in, m),
            out: transformVector(node.out, m),
        }));
        return G.path(object.id, points, object.geometry.closed, object.style, nodes);
    }

    function transformObject(object, m) {
        if (!object || !m) throw new Error("Expected a drawing object and transform matrix");
        if (object.type === "line") return G.line(object.id, transformPoint(object.geometry.start, m), transformPoint(object.geometry.end, m), object.style);
        if (object.type === G.PATH_TYPE) return transformPath(object, m);
        if (object.type === "rectangle") {
            if (isAxisAligned(m)) {
                const first = transformPoint(object.geometry.origin, m);
                const opposite = transformPoint(G.point(object.geometry.origin.x + object.geometry.widthMm, object.geometry.origin.y + object.geometry.heightMm), m);
                const width = Math.abs(opposite.x - first.x), height = Math.abs(opposite.y - first.y);
                if (width >= EPS && height >= EPS) return G.rectangle(object.id, G.point(Math.min(first.x, opposite.x), Math.min(first.y, opposite.y)), width, height, object.style);
            }
            return transformPath(rectanglePath(object), m);
        }
        if (object.type === "circle") {
            const scale = similarityScale(m);
            if (scale != null && scale >= EPS) return G.circle(object.id, transformPoint(object.geometry.center, m), object.geometry.radiusMm * scale, object.style);
            return transformPath(circlePath(object), m);
        }
        if (object.type === "arc") {
            const scale = similarityScale(m);
            if (scale != null && scale >= EPS) {
                const center = transformPoint(object.geometry.center, m);
                const start = transformPoint(G.arcStart(object), m);
                const sign = determinant(m) < 0 ? -1 : 1;
                return G.arc(object.id, center, object.geometry.radiusMm * scale, G.angleDeg(center, start), object.geometry.sweepAngleDeg * sign, object.style);
            }
            return transformPath(arcPath(object), m);
        }
        if (G.TEXT_TYPE && object.type === G.TEXT_TYPE && G.setText) {
            const position = transformPoint(object.geometry.position, m);
            const scale = similarityScale(m);
            return G.setText(object, {
                x: position.x,
                y: position.y,
                fontSizeMm: scale != null ? object.style.fontSizeMm * scale : object.style.fontSizeMm,
            });
        }
        throw new Error(`Unsupported transform object type: ${object.type}`);
    }

    function transformObjects(objects, m) { return Object.freeze((objects || []).map(object => transformObject(object, m))); }
    function flipHorizontal(bounds) { return scaleAround(G.point(bounds.cx, bounds.cy), -1, 1); }
    function flipVertical(bounds) { return scaleAround(G.point(bounds.cx, bounds.cy), 1, -1); }

    root.TransformDomain = Object.freeze({
        matrix, identity, multiply, translation, scaling, rotation, around, scaleAround, rotateAround,
        determinant, transformPoint, transformVector, transformObject, transformObjects,
        rectanglePath, circlePath, arcPath, flipHorizontal, flipVertical, similarityScale, isAxisAligned,
    });
})();
