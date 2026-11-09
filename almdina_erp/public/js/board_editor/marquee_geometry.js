(() => {
    "use strict";

    function num(value) {
        const n = Number(value);
        return Number.isFinite(n) ? n : 0;
    }

    function normalizeRect(x1, y1, x2, y2) {
        const ax = num(x1);
        const ay = num(y1);
        const bx = num(x2);
        const by = num(y2);
        const x = Math.min(ax, bx);
        const y = Math.min(ay, by);
        return {
            x,
            y,
            w: Math.abs(bx - ax),
            h: Math.abs(by - ay),
        };
    }

    function rectIntersects(a, b) {
        if (!a || !b) return false;
        return !(
            num(b.x) >= num(a.x) + num(a.w)
            || num(b.x) + num(b.w) <= num(a.x)
            || num(b.y) >= num(a.y) + num(a.h)
            || num(b.y) + num(b.h) <= num(a.y)
        );
    }

    function pointInRect(point, rect) {
        if (!point || !rect) return false;
        const x = num(point[0]);
        const y = num(point[1]);
        return (
            x >= num(rect.x) - 1e-9
            && y >= num(rect.y) - 1e-9
            && x <= num(rect.x) + num(rect.w) + 1e-9
            && y <= num(rect.y) + num(rect.h) + 1e-9
        );
    }

    function pointInPolygon(point, polygon) {
        if (!Array.isArray(polygon) || polygon.length < 3) return false;
        let inside = false;
        for (let i = 0, j = polygon.length - 1; i < polygon.length; j = i, i += 1) {
            const xi = num(polygon[i][0]);
            const yi = num(polygon[i][1]);
            const xj = num(polygon[j][0]);
            const yj = num(polygon[j][1]);
            const intersect = ((yi > num(point[1])) !== (yj > num(point[1])))
                && (num(point[0]) < (((xj - xi) * (num(point[1]) - yi)) / ((yj - yi) || 1e-12)) + xi);
            if (intersect) inside = !inside;
        }
        return inside;
    }

    function orientation(a, b, c) {
        const value = ((num(b[1]) - num(a[1])) * (num(c[0]) - num(b[0])))
            - ((num(b[0]) - num(a[0])) * (num(c[1]) - num(b[1])));
        if (Math.abs(value) < 1e-12) return 0;
        return value > 0 ? 1 : 2;
    }

    function onSegment(a, b, c) {
        return (
            Math.min(num(a[0]), num(b[0])) - 1e-9 <= num(c[0])
            && num(c[0]) <= Math.max(num(a[0]), num(b[0])) + 1e-9
            && Math.min(num(a[1]), num(b[1])) - 1e-9 <= num(c[1])
            && num(c[1]) <= Math.max(num(a[1]), num(b[1])) + 1e-9
        );
    }

    function segmentsIntersect(a1, a2, b1, b2) {
        const o1 = orientation(a1, a2, b1);
        const o2 = orientation(a1, a2, b2);
        const o3 = orientation(b1, b2, a1);
        const o4 = orientation(b1, b2, a2);
        if (o1 !== o2 && o3 !== o4) return true;
        if (o1 === 0 && onSegment(a1, a2, b1)) return true;
        if (o2 === 0 && onSegment(a1, a2, b2)) return true;
        if (o3 === 0 && onSegment(b1, b2, a1)) return true;
        if (o4 === 0 && onSegment(b1, b2, a2)) return true;
        return false;
    }

    function rectPolygon(rect) {
        const x = num(rect.x);
        const y = num(rect.y);
        const w = num(rect.w);
        const h = num(rect.h);
        return [
            [x, y],
            [x + w, y],
            [x + w, y + h],
            [x, y + h],
        ];
    }

    function footprintPoints(footprint) {
        if (!footprint) return null;
        if (Array.isArray(footprint.points) && footprint.points.length >= 3) {
            return footprint.points.map((point) => [num(point[0]), num(point[1])]);
        }
        if (!footprint.bounds) return null;
        return rectPolygon(footprint.bounds);
    }

    function polygonIntersectsRect(points, rect) {
        if (!Array.isArray(points) || points.length < 3 || !rect) return false;
        if (!(num(rect.w) > 0) && !(num(rect.h) > 0)) {
            // Degenerate zero-area "rect" (click): treat as a point probe.
            return pointInPolygon([num(rect.x), num(rect.y)], points);
        }
        const bounds = {
            x: Math.min(...points.map((point) => num(point[0]))),
            y: Math.min(...points.map((point) => num(point[1]))),
            w: Math.max(...points.map((point) => num(point[0])))
                - Math.min(...points.map((point) => num(point[0]))),
            h: Math.max(...points.map((point) => num(point[1])))
                - Math.min(...points.map((point) => num(point[1]))),
        };
        if (!rectIntersects(bounds, rect)) return false;

        for (let i = 0; i < points.length; i += 1) {
            if (pointInRect(points[i], rect)) return true;
        }

        const corners = rectPolygon(rect);
        for (let i = 0; i < corners.length; i += 1) {
            if (pointInPolygon(corners[i], points)) return true;
        }

        for (let i = 0; i < points.length; i += 1) {
            const a1 = points[i];
            const a2 = points[(i + 1) % points.length];
            for (let j = 0; j < corners.length; j += 1) {
                if (segmentsIntersect(a1, a2, corners[j], corners[(j + 1) % corners.length])) {
                    return true;
                }
            }
        }
        return false;
    }

    function footprintIntersectsRect(footprint, rect) {
        const points = footprintPoints(footprint);
        if (!points) return false;
        return polygonIntersectsRect(points, rect);
    }

    function isSelectablePiece(piece) {
        // Outside-board pieces keep sheet_no null/"" and remain marquee-selectable.
        // Only excluded/removed distribution rows are skipped.
        if (!piece) return false;
        if (piece.distribution === "excluded") return false;
        return true;
    }

    function hitTestPieceKeys(session, rect) {
        const MoveGeometry = window.AlmdinaBoardEditor && window.AlmdinaBoardEditor.MoveGeometry;
        if (!session || !session.pieces || !MoveGeometry || typeof MoveGeometry.worldFootprint !== "function") {
            return [];
        }
        if (!rect || (!(num(rect.w) > 0) && !(num(rect.h) > 0))) {
            return [];
        }
        const keys = [];
        const seen = new Set();
        Object.keys(session.pieces).forEach((key) => {
            const piece = session.pieces[key];
            if (!isSelectablePiece(piece)) return;
            const world = MoveGeometry.worldFootprint(piece, session.boards);
            if (!footprintIntersectsRect(world, rect)) return;
            if (seen.has(key)) return;
            seen.add(key);
            keys.push(key);
        });
        return keys;
    }

    function mergePieceKeys(existingKeys, nextKeys, mode) {
        const incoming = [];
        const seenIncoming = new Set();
        (Array.isArray(nextKeys) ? nextKeys : []).forEach((key) => {
            const value = String(key || "").trim();
            if (!value || seenIncoming.has(value)) return;
            seenIncoming.add(value);
            incoming.push(value);
        });
        if (mode !== "add") return incoming;
        const merged = [];
        const seen = new Set();
        (Array.isArray(existingKeys) ? existingKeys : []).forEach((key) => {
            const value = String(key || "").trim();
            if (!value || seen.has(value)) return;
            seen.add(value);
            merged.push(value);
        });
        incoming.forEach((key) => {
            if (seen.has(key)) return;
            seen.add(key);
            merged.push(key);
        });
        return merged;
    }

    window.AlmdinaBoardEditor = window.AlmdinaBoardEditor || {};
    window.AlmdinaBoardEditor.MarqueeGeometry = Object.freeze({
        normalizeRect,
        rectIntersects,
        pointInRect,
        pointInPolygon,
        polygonIntersectsRect,
        footprintIntersectsRect,
        hitTestPieceKeys,
        mergePieceKeys,
        isSelectablePiece,
        rectPolygon,
    });
})();
