(() => {
    "use strict";

    const root = window.AlmdinaDoorDrawingV3 = window.AlmdinaDoorDrawingV3 || Object.create(null);
    const G = root.Geometry;
    const T = root.TransformDomain;
    const Selection = root.VectorSelectionGeometry;
    if (!G || !T || !Selection) throw new Error("Door Drawing V3 transform geometry must load before oriented transform domain");

    const SAMPLE_STEPS = 12;
    const MIN_SIZE = G.EPSILON_MM || 0.001;

    function rad(deg) { return G.number(deg) * Math.PI / 180; }
    function deg(value) { return value * 180 / Math.PI; }
    function normalize180(angle) {
        let value = G.number(angle) % 180;
        if (value >= 90) value -= 180;
        if (value < -90) value += 180;
        return value;
    }
    function normalize360(angle) {
        let value = G.number(angle) % 360;
        if (value > 180) value -= 360;
        if (value <= -180) value += 360;
        return value;
    }
    function rotateVector(point, angleDeg) {
        const a = rad(angleDeg), cos = Math.cos(a), sin = Math.sin(a);
        return G.point(point.x * cos - point.y * sin, point.x * sin + point.y * cos);
    }
    function rotateAround(point, center, angleDeg) {
        const local = G.point(point.x - center.x, point.y - center.y);
        const rotated = rotateVector(local, angleDeg);
        return G.point(center.x + rotated.x, center.y + rotated.y);
    }

    function sampleArc(object) {
        const sweep = Math.abs(object.geometry.sweepAngleDeg);
        const count = Math.max(2, Math.ceil(sweep / 15));
        return Array.from({ length: count + 1 }, (_, index) => {
            const angle = object.geometry.startAngleDeg + object.geometry.sweepAngleDeg * index / count;
            return G.pointAt(object.geometry.center, object.geometry.radiusMm, angle);
        });
    }
    function samplePath(object) {
        const points = [];
        const segments = typeof G.pathSegments === "function" ? G.pathSegments(object) : [];
        segments.forEach(segment => {
            if (!segment.curved || typeof G.pathPointAtSegment !== "function") {
                points.push(segment.start, segment.end);
                return;
            }
            for (let step = 0; step <= SAMPLE_STEPS; step += 1) points.push(G.pathPointAtSegment(object, segment.index, step / SAMPLE_STEPS));
        });
        return points;
    }
    function pointsForObject(object) {
        if (!object || !object.geometry) return [];
        const g = object.geometry;
        if (object.type === "line") return [g.start, g.end];
        if (object.type === "rectangle") return [
            g.origin,
            G.point(g.origin.x + g.widthMm, g.origin.y),
            G.point(g.origin.x + g.widthMm, g.origin.y + g.heightMm),
            G.point(g.origin.x, g.origin.y + g.heightMm),
        ];
        if (object.type === "circle") return Array.from({ length: 16 }, (_, index) => G.pointAt(g.center, g.radiusMm, index * 22.5));
        if (object.type === "arc") return sampleArc(object);
        if (G.PATH_TYPE && object.type === G.PATH_TYPE) return samplePath(object);
        const box = Selection.boundsOfObject(object);
        return box ? [G.point(box.left, box.bottom), G.point(box.right, box.bottom), G.point(box.right, box.top), G.point(box.left, box.top)] : [];
    }
    function pointsForObjects(objects) { return (objects || []).flatMap(pointsForObject).filter(Boolean); }

    function cross(o, a, b) { return (a.x - o.x) * (b.y - o.y) - (a.y - o.y) * (b.x - o.x); }
    function convexHull(points) {
        const sorted = points.slice().sort((a, b) => a.x - b.x || a.y - b.y);
        if (sorted.length <= 2) return sorted;
        const lower = [];
        for (const point of sorted) {
            while (lower.length >= 2 && cross(lower[lower.length - 2], lower[lower.length - 1], point) <= 0) lower.pop();
            lower.push(point);
        }
        const upper = [];
        for (let index = sorted.length - 1; index >= 0; index -= 1) {
            const point = sorted[index];
            while (upper.length >= 2 && cross(upper[upper.length - 2], upper[upper.length - 1], point) <= 0) upper.pop();
            upper.push(point);
        }
        lower.pop(); upper.pop();
        return lower.concat(upper);
    }

    function frameAtAngleFromPoints(points, angleDeg) {
        if (!points.length) return null;
        const local = points.map(point => rotateVector(point, -angleDeg));
        const minX = Math.min(...local.map(point => point.x)), maxX = Math.max(...local.map(point => point.x));
        const minY = Math.min(...local.map(point => point.y)), maxY = Math.max(...local.map(point => point.y));
        const centerLocal = G.point((minX + maxX) / 2, (minY + maxY) / 2);
        const center = rotateVector(centerLocal, angleDeg);
        const width = Math.max(MIN_SIZE, maxX - minX), height = Math.max(MIN_SIZE, maxY - minY);
        return Object.freeze({ center, width, height, angleDeg: normalize360(angleDeg), minX, maxX, minY, maxY, area: width * height });
    }
    function frameAtAngle(objects, angleDeg) { return frameAtAngleFromPoints(pointsForObjects(objects), angleDeg); }
    function minimumFrame(objects) {
        const points = pointsForObjects(objects);
        if (!points.length) return null;
        const hull = convexHull(points);
        if (hull.length < 2) return frameAtAngleFromPoints(points, 0);
        let best = null;
        for (let index = 0; index < hull.length; index += 1) {
            const a = hull[index], b = hull[(index + 1) % hull.length];
            const angle = normalize180(deg(Math.atan2(b.y - a.y, b.x - a.x)));
            const candidate = frameAtAngleFromPoints(points, angle);
            if (!best || candidate.area < best.area - G.EPSILON_MM) best = candidate;
        }
        return best;
    }
    function frameForObjects(objects, preferredAngle = null) {
        if (Number.isFinite(Number(preferredAngle))) return frameAtAngle(objects, Number(preferredAngle));
        return minimumFrame(objects);
    }

    function localPoint(frame, world) {
        const translated = G.point(world.x - frame.center.x, world.y - frame.center.y);
        return rotateVector(translated, -frame.angleDeg);
    }
    function worldPoint(frame, local) {
        const rotated = rotateVector(local, frame.angleDeg);
        return G.point(frame.center.x + rotated.x, frame.center.y + rotated.y);
    }
    function corners(frame) {
        const hw = frame.width / 2, hh = frame.height / 2;
        return Object.freeze([
            worldPoint(frame, G.point(-hw, -hh)),
            worldPoint(frame, G.point(hw, -hh)),
            worldPoint(frame, G.point(hw, hh)),
            worldPoint(frame, G.point(-hw, hh)),
        ]);
    }
    function handleLocal(frame, role) {
        const x = role.includes("w") ? -frame.width / 2 : role.includes("e") ? frame.width / 2 : 0;
        const y = role.includes("s") ? -frame.height / 2 : role.includes("n") ? frame.height / 2 : 0;
        return G.point(x, y);
    }
    function handleWorld(frame, role) { return worldPoint(frame, handleLocal(frame, role)); }
    function oppositeLocal(frame, role, fromCenter = false) {
        if (fromCenter) return G.point(0, 0);
        const x = role.includes("w") ? frame.width / 2 : role.includes("e") ? -frame.width / 2 : 0;
        const y = role.includes("s") ? frame.height / 2 : role.includes("n") ? -frame.height / 2 : 0;
        return G.point(x, y);
    }

    function composeLocalScale(frame, pivotLocal, sx, sy) {
        const toCenter = T.translation(frame.center.x, frame.center.y);
        const fromCenter = T.translation(-frame.center.x, -frame.center.y);
        const rotate = T.rotation(frame.angleDeg), unrotate = T.rotation(-frame.angleDeg);
        const aroundPivot = T.multiply(T.translation(pivotLocal.x, pivotLocal.y), T.multiply(T.scaling(sx, sy), T.translation(-pivotLocal.x, -pivotLocal.y)));
        return T.multiply(toCenter, T.multiply(rotate, T.multiply(aroundPivot, T.multiply(unrotate, fromCenter))));
    }
    function resizeMatrix(frame, role, pointerWorld, options = {}) {
        const start = handleLocal(frame, role);
        const pointer = localPoint(frame, pointerWorld);
        const pivot = oppositeLocal(frame, role, Boolean(options.fromCenter));
        const useX = role.includes("e") || role.includes("w");
        const useY = role.includes("n") || role.includes("s");
        let sx = 1, sy = 1;
        if (useX && Math.abs(start.x - pivot.x) >= MIN_SIZE) sx = (pointer.x - pivot.x) / (start.x - pivot.x);
        if (useY && Math.abs(start.y - pivot.y) >= MIN_SIZE) sy = (pointer.y - pivot.y) / (start.y - pivot.y);
        const safe = value => Math.abs(value) < 0.001 ? (value < 0 ? -0.001 : 0.001) : value;
        sx = safe(sx); sy = safe(sy);
        if (options.keepAspect) {
            if (useX && useY) {
                const magnitude = Math.abs(Math.abs(sx) - 1) >= Math.abs(Math.abs(sy) - 1) ? Math.abs(sx) : Math.abs(sy);
                sx = Math.sign(sx || 1) * magnitude;
                sy = Math.sign(sy || 1) * magnitude;
            } else if (useX) sy = Math.abs(sx);
            else if (useY) sx = Math.abs(sy);
        }
        return Object.freeze({ matrix: composeLocalScale(frame, pivot, sx, sy), sx, sy, pivotLocal: pivot });
    }
    function rotationDelta(pivot, startPointer, pointer) {
        const start = G.angleDeg(pivot, startPointer), current = G.angleDeg(pivot, pointer);
        return normalize360(current - start);
    }
    function snapAngle(angle, incrementDeg = 15) {
        const increment = Math.max(1, Math.abs(G.number(incrementDeg, 15)));
        return Math.round(angle / increment) * increment;
    }

    root.OrientedTransformDomain = Object.freeze({
        normalize180, normalize360, rotateVector, rotateAround, pointsForObject, pointsForObjects, convexHull,
        frameAtAngleFromPoints, frameAtAngle, minimumFrame, frameForObjects, localPoint, worldPoint, corners,
        handleLocal, handleWorld, oppositeLocal, composeLocalScale, resizeMatrix, rotationDelta, snapAngle,
    });
})();
