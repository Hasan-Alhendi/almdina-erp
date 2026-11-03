(() => {
    "use strict";

    // Transient board-editor measurements only. Never enters draft/plan/DXF/NC.

    const EPS = 1e-6;
    const SAMPLE_STEP_MM = 2;

    function num(value) {
        const n = Number(value);
        return Number.isFinite(n) ? n : 0;
    }

    function distance(a, b) {
        const dx = num(b[0]) - num(a[0]);
        const dy = num(b[1]) - num(a[1]);
        return Math.hypot(dx, dy);
    }

    function formatDistanceMm(value) {
        const n = num(value);
        if (!Number.isFinite(n) || n < 0) return null;
        if (Math.abs(n - Math.round(n)) < 0.05) return `${Math.round(n)} mm`;
        return `${(Math.round(n * 10) / 10).toFixed(1)} mm`;
    }

    function boardOuterWorld(board) {
        if (!board) return null;
        const x = num(board.origin_x_mm);
        const y = num(board.origin_y_mm);
        const w = Math.max(1, num(board.width_mm) || (num(board.usable_width_mm) + 2 * num(board.trim_x_mm)));
        const h = Math.max(1, num(board.height_mm) || (num(board.usable_length_mm) + 2 * num(board.trim_y_mm)));
        return { x, y, w, h, right: x + w, bottom: y + h };
    }

    function boardUsableWorld(board) {
        if (!board) return null;
        const MoveGeometry = window.AlmdinaBoardEditor && window.AlmdinaBoardEditor.MoveGeometry;
        const origin = MoveGeometry
            ? MoveGeometry.sheetOriginMm({ 1: board }, board.sheet_no != null ? board.sheet_no : 1)
            : {
                x: num(board.origin_x_mm) + num(board.trim_x_mm),
                y: num(board.origin_y_mm) + num(board.trim_y_mm),
            };
        // Prefer explicit sheet origin helper with the real sheet key when available.
        const ox = num(board.origin_x_mm) + num(board.trim_x_mm);
        const oy = num(board.origin_y_mm) + num(board.trim_y_mm);
        const w = Math.max(1, num(board.usable_width_mm) || (num(board.width_mm) - 2 * num(board.trim_x_mm)));
        const h = Math.max(1, num(board.usable_length_mm) || (num(board.height_mm) - 2 * num(board.trim_y_mm)));
        return { x: ox, y: oy, w, h, right: ox + w, bottom: oy + h, _originHint: origin };
    }

    function pointInRect(point, rect) {
        if (!rect) return false;
        return (
            point[0] >= rect.x - EPS
            && point[1] >= rect.y - EPS
            && point[0] <= rect.right + EPS
            && point[1] <= rect.bottom + EPS
        );
    }

    function clampPointToRect(point, rect) {
        if (!rect) return [num(point[0]), num(point[1])];
        return [
            Math.min(rect.right, Math.max(rect.x, num(point[0]))),
            Math.min(rect.bottom, Math.max(rect.y, num(point[1]))),
        ];
    }

    function findBoardAtWorld(session, worldPoint) {
        const boards = (session && session.boards) || {};
        let hit = null;
        Object.keys(boards).forEach((key) => {
            const board = boards[key];
            const outer = boardOuterWorld(board);
            if (outer && pointInRect(worldPoint, outer)) {
                hit = { sheetNo: board.sheet_no != null ? board.sheet_no : Number(key), board, outer };
            }
        });
        return hit;
    }

    function pointInPolygon(point, polygon) {
        if (!Array.isArray(polygon) || polygon.length < 3) return false;
        let inside = false;
        for (let i = 0, j = polygon.length - 1; i < polygon.length; j = i++) {
            const xi = num(polygon[i][0]);
            const yi = num(polygon[i][1]);
            const xj = num(polygon[j][0]);
            const yj = num(polygon[j][1]);
            const intersect = ((yi > point[1]) !== (yj > point[1]))
                && (point[0] < ((xj - xi) * (point[1] - yi)) / ((yj - yi) || EPS) + xi);
            if (intersect) inside = !inside;
        }
        return inside;
    }

    function pieceMaterial(piece, boards) {
        const MoveGeometry = window.AlmdinaBoardEditor && window.AlmdinaBoardEditor.MoveGeometry;
        if (!MoveGeometry || !piece) return null;
        const world = MoveGeometry.worldFootprint(piece, boards);
        if (!world || !Array.isArray(world.points) || world.points.length < 3) return null;
        const holes = [];
        if (Array.isArray(piece.glass_hole_local_mm) && piece.glass_hole_local_mm.length >= 3) {
            holes.push(MoveGeometry.pointsToWorld(piece.glass_hole_local_mm, piece.sheet_no, boards));
        }
        return {
            pieceKey: piece.piece_key,
            sheetNo: piece.sheet_no,
            outer: world.points,
            holes,
            bounds: world.bounds,
        };
    }

    function pointInMaterial(point, material) {
        if (!material || !pointInPolygon(point, material.outer)) return false;
        for (let i = 0; i < (material.holes || []).length; i += 1) {
            if (pointInPolygon(point, material.holes[i])) return false;
        }
        return true;
    }

    function densifySegment(a, b, stepMm) {
        const len = distance(a, b);
        if (len < EPS) return [a];
        const step = Math.max(0.5, Number(stepMm) || SAMPLE_STEP_MM);
        const count = Math.max(1, Math.ceil(len / step));
        const points = [];
        for (let i = 0; i <= count; i += 1) {
            const t = i / count;
            points.push([num(a[0]) + (num(b[0]) - num(a[0])) * t, num(a[1]) + (num(b[1]) - num(a[1])) * t]);
        }
        return points;
    }

    function segmentBlockedByMaterials(a, b, materials, ignoreKeys) {
        const ignored = new Set((ignoreKeys || []).map(String));
        const samples = densifySegment(a, b, SAMPLE_STEP_MM);
        // Skip endpoints that sit on the measured piece boundaries.
        for (let i = 1; i < samples.length - 1; i += 1) {
            const point = samples[i];
            for (let m = 0; m < materials.length; m += 1) {
                const material = materials[m];
                if (ignored.has(String(material.pieceKey))) continue;
                if (pointInMaterial(point, material)) return true;
            }
        }
        return false;
    }

    function sampleBoundary(points, maxSamples) {
        if (!Array.isArray(points) || points.length < 2) return [];
        const out = [];
        const limit = Math.max(8, Number(maxSamples) || 48);
        const closed = points.concat([points[0]]);
        let perimeter = 0;
        for (let i = 0; i < closed.length - 1; i += 1) {
            perimeter += distance(closed[i], closed[i + 1]);
        }
        if (perimeter < EPS) return points.slice();
        const step = perimeter / limit;
        let walked = 0;
        let nextAt = 0;
        for (let i = 0; i < closed.length - 1; i += 1) {
            const a = closed[i];
            const b = closed[i + 1];
            const seg = distance(a, b);
            if (seg < EPS) continue;
            while (nextAt <= walked + seg + EPS && out.length < limit + 4) {
                const t = Math.min(1, Math.max(0, (nextAt - walked) / seg));
                out.push([num(a[0]) + (num(b[0]) - num(a[0])) * t, num(a[1]) + (num(b[1]) - num(a[1])) * t]);
                nextAt += step;
            }
            walked += seg;
        }
        return out.length ? out : points.slice();
    }

    function outwardProbe(point, direction, material) {
        const step = 0.75;
        const probe = [point[0] + direction[0] * step, point[1] + direction[1] * step];
        return !pointInMaterial(probe, material);
    }

    function edgeClearances(session, pieceKey) {
        const pieces = (session && session.pieces) || {};
        const boards = (session && session.boards) || {};
        const piece = pieces[pieceKey];
        if (!piece || piece.sheet_no == null || piece.sheet_no === "") return [];
        const board = boards[String(piece.sheet_no)];
        const outer = boardOuterWorld(board);
        const material = pieceMaterial(piece, boards);
        if (!outer || !material) return [];

        const others = Object.keys(pieces)
            .filter((key) => key !== pieceKey && Number(pieces[key].sheet_no) === Number(piece.sheet_no))
            .map((key) => pieceMaterial(pieces[key], boards))
            .filter(Boolean);

        const dirs = [
            { id: "top", vector: [0, -1], edgePoint: (p) => [p[0], outer.y] },
            { id: "bottom", vector: [0, 1], edgePoint: (p) => [p[0], outer.bottom] },
            { id: "left", vector: [-1, 0], edgePoint: (p) => [outer.x, p[1]] },
            { id: "right", vector: [1, 0], edgePoint: (p) => [outer.right, p[1]] },
        ];

        function slabBlocked(dirId, start, end) {
            const x0 = Math.min(start[0], end[0]);
            const x1 = Math.max(start[0], end[0]);
            const y0 = Math.min(start[1], end[1]);
            const y1 = Math.max(start[1], end[1]);
            return others.some((other) => {
                const b = other.bounds;
                if (!b) return false;
                if (dirId === "left" || dirId === "right") {
                    // Include grazing contact on the obstacle's top/bottom edges.
                    const yOverlap = Math.min(y1, b.y + b.h) - Math.max(y0, b.y);
                    if (yOverlap < -EPS) return false;
                    const ox0 = b.x;
                    const ox1 = b.x + b.w;
                    return ox1 > x0 + EPS && ox0 < x1 - EPS;
                }
                const xOverlap = Math.min(x1, b.x + b.w) - Math.max(x0, b.x);
                if (xOverlap < -EPS) return false;
                const oy0 = b.y;
                const oy1 = b.y + b.h;
                return oy1 > y0 + EPS && oy0 < y1 - EPS;
            });
        }

        const samples = sampleBoundary(material.outer, 64);
        const results = [];
        dirs.forEach((dir) => {
            let best = null;
            samples.forEach((point) => {
                if (!outwardProbe(point, dir.vector, material)) return;
                const end = dir.edgePoint(point);
                const gap = distance(point, end);
                if (gap < EPS) {
                    if (!best || gap < best.distance) {
                        best = { kind: "edge", direction: dir.id, start: point, end, distance: 0 };
                    }
                    return;
                }
                if (slabBlocked(dir.id, point, end)) return;
                if (segmentBlockedByMaterials(point, end, others, [pieceKey])) return;
                if (!best || gap < best.distance - EPS) {
                    best = { kind: "edge", direction: dir.id, start: point, end, distance: gap };
                }
            });
            if (best) results.push(best);
        });
        return results;
    }

    function projectPointOnSegment(point, a, b) {
        const ax = num(a[0]);
        const ay = num(a[1]);
        const bx = num(b[0]);
        const by = num(b[1]);
        const dx = bx - ax;
        const dy = by - ay;
        const len2 = dx * dx + dy * dy;
        if (len2 < EPS) return { point: [ax, ay], t: 0, distance: distance(point, a) };
        let t = ((num(point[0]) - ax) * dx + (num(point[1]) - ay) * dy) / len2;
        t = Math.min(1, Math.max(0, t));
        const proj = [ax + dx * t, ay + dy * t];
        return { point: proj, t, distance: distance(point, proj) };
    }

    function shortestClearanceBetweenPieces(session, pieceKeyA, pieceKeyB) {
        const pieces = (session && session.pieces) || {};
        const boards = (session && session.boards) || {};
        const pieceA = pieces[pieceKeyA];
        const pieceB = pieces[pieceKeyB];
        if (!pieceA || !pieceB) return null;
        if (Number(pieceA.sheet_no) !== Number(pieceB.sheet_no)) return null;
        if (pieceA.sheet_no == null || pieceA.sheet_no === "") return null;

        const matA = pieceMaterial(pieceA, boards);
        const matB = pieceMaterial(pieceB, boards);
        if (!matA || !matB) return null;

        const others = Object.keys(pieces)
            .filter((key) => key !== pieceKeyA && key !== pieceKeyB && Number(pieces[key].sheet_no) === Number(pieceA.sheet_no))
            .map((key) => pieceMaterial(pieces[key], boards))
            .filter(Boolean);

        const samplesA = sampleBoundary(matA.outer, 48);
        const samplesB = sampleBoundary(matB.outer, 48);
        let best = null;

        function consider(start, end) {
            const gap = distance(start, end);
            if (!Number.isFinite(gap) || gap < 0) return;
            if (gap > EPS && segmentBlockedByMaterials(start, end, others, [pieceKeyA, pieceKeyB])) return;
            // Reject segments that travel through either piece's solid interior.
            if (gap > EPS && densifySegment(start, end, SAMPLE_STEP_MM).some((point, index, arr) => {
                if (index === 0 || index === arr.length - 1) return false;
                return pointInMaterial(point, matA) || pointInMaterial(point, matB);
            })) return;
            if (!best || gap < best.distance - EPS) {
                best = {
                    kind: "piece",
                    start,
                    end,
                    distance: gap,
                    pieceKeyA,
                    pieceKeyB,
                };
            }
        }

        // Vertex-vertex candidates.
        samplesA.forEach((a) => {
            samplesB.forEach((b) => consider(a, b));
        });

        // Vertex-to-edge candidates for better diagonal/corner accuracy.
        function againstEdges(points, edges) {
            points.forEach((point) => {
                for (let i = 0; i < edges.length; i += 1) {
                    const a = edges[i];
                    const b = edges[(i + 1) % edges.length];
                    const proj = projectPointOnSegment(point, a, b);
                    consider(point, proj.point);
                }
            });
        }
        againstEdges(samplesA, matB.outer);
        againstEdges(samplesB, matA.outer);

        // Prefer axis-aligned facing gap when projections overlap.
        const aBounds = matA.bounds;
        const bBounds = matB.bounds;
        const yOverlap = Math.min(aBounds.y + aBounds.h, bBounds.y + bBounds.h) - Math.max(aBounds.y, bBounds.y);
        const xOverlap = Math.min(aBounds.x + aBounds.w, bBounds.x + bBounds.w) - Math.max(aBounds.x, bBounds.x);
        if (yOverlap > EPS) {
            const y0 = Math.max(aBounds.y, bBounds.y) + yOverlap * 0.5;
            const left = aBounds.x + aBounds.w <= bBounds.x + EPS ? matA : matB;
            const right = left === matA ? matB : matA;
            const leftX = left.bounds.x + left.bounds.w;
            const rightX = right.bounds.x;
            if (rightX + EPS >= leftX) {
                consider([leftX, y0], [rightX, y0]);
            }
        }
        if (xOverlap > EPS) {
            const x0 = Math.max(aBounds.x, bBounds.x) + xOverlap * 0.5;
            const top = aBounds.y + aBounds.h <= bBounds.y + EPS ? matA : matB;
            const bottom = top === matA ? matB : matA;
            const topY = top.bounds.y + top.bounds.h;
            const bottomY = bottom.bounds.y;
            if (bottomY + EPS >= topY) {
                consider([x0, topY], [x0, bottomY]);
            }
        }

        if (!best) return null;
        // Overlap / invalid negative spacing: material intersection without a clear gap.
        if (best.distance < EPS) {
            const midA = [
                aBounds.x + aBounds.w * 0.5,
                aBounds.y + aBounds.h * 0.5,
            ];
            if (pointInMaterial(midA, matB) || densifySegment(
                [aBounds.x + aBounds.w * 0.5, aBounds.y + aBounds.h * 0.5],
                [bBounds.x + bBounds.w * 0.5, bBounds.y + bBounds.h * 0.5],
                4
            ).some((point) => pointInMaterial(point, matA) && pointInMaterial(point, matB))) {
                return null;
            }
        }
        return best;
    }

    function hitTestPieceKey(session, worldPoint, preferredSheetNo) {
        const pieces = (session && session.pieces) || {};
        const boards = (session && session.boards) || {};
        let hit = null;
        Object.keys(pieces).forEach((key) => {
            const piece = pieces[key];
            if (preferredSheetNo != null && Number(piece.sheet_no) !== Number(preferredSheetNo)) return;
            const material = pieceMaterial(piece, boards);
            if (!material) return;
            if (pointInMaterial(worldPoint, material)) hit = key;
        });
        return hit;
    }

    function measureLine(start, end) {
        const length = distance(start, end);
        if (!(length > EPS)) return null;
        return {
            kind: "line",
            start: [num(start[0]), num(start[1])],
            end: [num(end[0]), num(end[1])],
            distance: length,
            label: formatDistanceMm(length),
        };
    }

    window.AlmdinaBoardEditor = window.AlmdinaBoardEditor || {};
    window.AlmdinaBoardEditor.MeasureGeometry = Object.freeze({
        distance,
        formatDistanceMm,
        boardOuterWorld,
        boardUsableWorld,
        findBoardAtWorld,
        clampPointToRect,
        pointInRect,
        pointInPolygon,
        pointInMaterial,
        pieceMaterial,
        segmentBlockedByMaterials,
        edgeClearances,
        shortestClearanceBetweenPieces,
        hitTestPieceKey,
        measureLine,
        densifySegment,
    });
})();
