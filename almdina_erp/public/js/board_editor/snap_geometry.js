(() => {
    "use strict";

    // Interactive mirror of domain/cutting/board_editor_snap.py.
    // Final manufacturing acceptance still goes through MoveGeometry / Domain.

    const SNAP_ENTER_PX = 8;
    const SNAP_EXIT_PX = 12;
    const EPS = 1e-6;
    const AXIS_RATIO = 25;

    function num(value) {
        const n = Number(value);
        return Number.isFinite(n) ? n : 0;
    }

    function hypot(dx, dy) {
        return Math.hypot(dx, dy);
    }

    function boundsCorners(bounds) {
        const x = num(bounds.x);
        const y = num(bounds.y);
        const w = num(bounds.w);
        const h = num(bounds.h);
        return [[x, y], [x + w, y], [x + w, y + h], [x, y + h]];
    }

    function footprintEdges(footprint) {
        const bounds = footprint.bounds;
        let points = footprint.points;
        if (!Array.isArray(points) || points.length < 3) points = boundsCorners(bounds);
        const edges = [];
        const minX = num(bounds.x);
        const maxX = minX + num(bounds.w);
        const minY = num(bounds.y);
        const maxY = minY + num(bounds.h);
        for (let index = 0; index < points.length; index += 1) {
            const a = [num(points[index][0]), num(points[index][1])];
            const b = [num(points[(index + 1) % points.length][0]), num(points[(index + 1) % points.length][1])];
            const dx = b[0] - a[0];
            const dy = b[1] - a[1];
            const length = hypot(dx, dy);
            if (length <= EPS) continue;
            const ux = dx / length;
            const uy = dy / length;
            const nx = -uy;
            const ny = ux;
            let kind;
            let coord;
            let side;
            if (Math.abs(dx) >= Math.abs(dy) * AXIS_RATIO) {
                kind = "h";
                coord = (a[1] + b[1]) * 0.5;
                side = Math.abs(coord - minY) <= Math.abs(coord - maxY) ? "min" : "max";
            } else if (Math.abs(dy) >= Math.abs(dx) * AXIS_RATIO) {
                kind = "v";
                coord = (a[0] + b[0]) * 0.5;
                side = Math.abs(coord - minX) <= Math.abs(coord - maxX) ? "min" : "max";
            } else {
                kind = "d";
                coord = 0;
                side = "n";
            }
            edges.push({
                a,
                b,
                kind,
                side,
                ux,
                uy,
                nx,
                ny,
                length,
                angle: Math.atan2(dy, dx),
                coord,
                mid: [(a[0] + b[0]) * 0.5, (a[1] + b[1]) * 0.5],
            });
        }
        return edges;
    }

    function usableEdgesWorld(board) {
        const ox = num(board.origin_x_mm) + num(board.trim_x_mm);
        const oy = num(board.origin_y_mm) + num(board.trim_y_mm);
        const w = num(board.usable_width_mm) || num(board.width_mm);
        const h = num(board.usable_length_mm) || num(board.height_mm);
        return footprintEdges({
            kind: "rect",
            bounds: { x: ox, y: oy, w, h },
            points: null,
        });
    }

    function parallel(a, b) {
        if ((a.kind === "h" || a.kind === "v") && (b.kind === "h" || b.kind === "v")) {
            return a.kind === b.kind;
        }
        let ang = Math.abs(a.angle - b.angle) % Math.PI;
        if (ang > Math.PI / 2) ang = Math.PI - ang;
        return ang < 0.07;
    }

    function edgeDelta(moving, target, gap) {
        if (moving.kind === "v" && target.kind === "v") {
            if (gap <= EPS) {
                if (moving.side !== target.side) return null;
                return [num(target.coord) - num(moving.coord), 0];
            }
            if (moving.side === "min" && target.side === "max") {
                return [num(target.coord) + gap - num(moving.coord), 0];
            }
            if (moving.side === "max" && target.side === "min") {
                return [num(target.coord) - gap - num(moving.coord), 0];
            }
            return null;
        }
        if (moving.kind === "h" && target.kind === "h") {
            if (gap <= EPS) {
                if (moving.side !== target.side) return null;
                return [0, num(target.coord) - num(moving.coord)];
            }
            if (moving.side === "min" && target.side === "max") {
                return [0, num(target.coord) + gap - num(moving.coord)];
            }
            if (moving.side === "max" && target.side === "min") {
                return [0, num(target.coord) - gap - num(moving.coord)];
            }
            return null;
        }
        if (moving.kind === "d" && target.kind === "d" && parallel(moving, target)) {
            const nx = num(target.nx);
            const ny = num(target.ny);
            const residual = (num(moving.mid[0]) - num(target.mid[0])) * nx
                + (num(moving.mid[1]) - num(target.mid[1])) * ny;
            const desired = residual >= 0 ? gap : -gap;
            const delta = desired - residual;
            return [nx * delta, ny * delta];
        }
        return null;
    }

    function candidateKey(dx, dy, source, side) {
        return [Math.abs(dx) + Math.abs(dy), Math.abs(dx), Math.abs(dy), source, side, Number(dx.toFixed(6)), Number(dy.toFixed(6))];
    }

    function keyLess(a, b) {
        for (let i = 0; i < a.length; i += 1) {
            if (a[i] < b[i]) return true;
            if (a[i] > b[i]) return false;
        }
        return false;
    }

    function sortByKey(rows) {
        return rows.slice().sort((left, right) => (keyLess(left.key, right.key) ? -1 : 1));
    }

    function guide(moving, target, dx, dy) {
        return {
            x1: num(target.a[0]),
            y1: num(target.a[1]),
            x2: num(target.b[0]),
            y2: num(target.b[1]),
            mx1: num(moving.a[0]) + dx,
            my1: num(moving.a[1]) + dy,
            mx2: num(moving.b[0]) + dx,
            my2: num(moving.b[1]) + dy,
        };
    }

    function aabbNear(a, b, pad) {
        return !(
            b.x - pad >= a.x + a.w + pad
            || b.x + b.w + pad <= a.x - pad
            || b.y - pad >= a.y + a.h + pad
            || b.y + b.h + pad <= a.y - pad
        );
    }

    function thresholdMmFromScale(scale, enterPx) {
        const px = enterPx == null ? SNAP_ENTER_PX : enterPx;
        const s = Number(scale);
        if (!(s > 0)) return px;
        return px / s;
    }

    function suggestPieceSnap(session, pieceKeyOrInstance, worldX, worldY, options) {
        const opts = options || {};
        const MoveGeometry = window.AlmdinaBoardEditor.MoveGeometry;
        const pieceKey = MoveGeometry.resolvePieceKey(session, pieceKeyOrInstance);
        const piece = pieceKey && session.pieces[pieceKey];
        if (!piece || !piece.editable || opts.magnetEnabled === false) {
            return { ok: false, dx: 0, dy: 0, guides: [], source: null };
        }

        const thresholdMm = num(opts.thresholdMm);
        const exitMm = opts.exitThresholdMm != null ? num(opts.exitThresholdMm) : thresholdMm * 1.5;
        const current = MoveGeometry.worldFootprint(piece, session.boards);
        const rawDx = num(worldX) - current.bounds.x;
        const rawDy = num(worldY) - current.bounds.y;
        const active = opts.activeSnap;

        if (active && active.ok) {
            const adx = num(active.dx);
            const ady = num(active.dy);
            if (hypot(rawDx - adx, rawDy - ady) <= exitMm) {
                const check = MoveGeometry.proposePieceDrop(
                    session,
                    pieceKey,
                    current.bounds.x + adx,
                    current.bounds.y + ady
                );
                if (check.ok) {
                    return {
                        ok: true,
                        dx: adx,
                        dy: ady,
                        guides: Array.isArray(active.guides) ? active.guides.slice() : [],
                        source: active.source || "sticky",
                    };
                }
            }
        }

        const proposed = {
            kind: current.kind,
            bounds: {
                x: current.bounds.x + rawDx,
                y: current.bounds.y + rawDy,
                w: current.bounds.w,
                h: current.bounds.h,
            },
            points: current.points
                ? current.points.map((point) => [point[0] + rawDx, point[1] + rawDy])
                : null,
        };

        const nearBoards = [];
        Object.entries(session.boards || {}).forEach(([sheetNo, board]) => {
            const ox = num(board.origin_x_mm) + num(board.trim_x_mm);
            const oy = num(board.origin_y_mm) + num(board.trim_y_mm);
            const usable = {
                x: ox,
                y: oy,
                w: num(board.usable_width_mm) || num(board.width_mm),
                h: num(board.usable_length_mm) || num(board.height_mm),
            };
            if (aabbNear(proposed.bounds, usable, thresholdMm)) nearBoards.push(sheetNo);
        });
        if (nearBoards.length !== 1) {
            return { ok: false, dx: rawDx, dy: rawDy, guides: [], source: null };
        }

        const sheetNo = nearBoards[0];
        const board = session.boards[sheetNo];
        const movingEdges = footprintEdges(proposed);
        const targets = usableEdgesWorld(board).map((edge) => ["usable", edge, 0]);
        const movingKeys = new Set(MoveGeometry.draggedPieceIds(session, pieceKey));
        const pad = thresholdMm + Math.max(proposed.bounds.w, proposed.bounds.h);
        Object.entries(session.pieces || {}).forEach(([otherKey, other]) => {
            if (movingKeys.has(otherKey)) return;
            if (other.distribution === "excluded") return;
            if (String(other.sheet_no) !== String(sheetNo)) return;
            if (other.glass_host_key === pieceKey || piece.glass_host_key === otherKey) return;
            const otherFp = MoveGeometry.worldFootprint(other, session.boards);
            if (!aabbNear(proposed.bounds, otherFp.bounds, pad)) return;
            footprintEdges(otherFp).forEach((edge) => {
                targets.push([`piece:${otherKey}`, edge, num(session.kerf_mm)]);
            });
        });

        const axisCandidates = { x: [], y: [], n: [] };
        targets.forEach(([source, targetEdge, gap]) => {
            movingEdges.forEach((movingEdge) => {
                if (!parallel(movingEdge, targetEdge)) return;
                const delta = edgeDelta(movingEdge, targetEdge, gap);
                if (!delta) return;
                const [dx, dy] = delta;
                if (hypot(dx, dy) > thresholdMm + EPS) return;
                const absDx = rawDx + dx;
                const absDy = rawDy + dy;
                const axis = Math.abs(dy) <= EPS && Math.abs(dx) > EPS
                    ? "x"
                    : (Math.abs(dx) <= EPS && Math.abs(dy) > EPS ? "y" : "n");
                axisCandidates[axis].push({
                    dx: absDx,
                    dy: absDy,
                    source,
                    guide: guide(movingEdge, targetEdge, dx, dy),
                    key: candidateKey(absDx, absDy, source, axis),
                });
            });
        });

        function firstValid(rows) {
            const ordered = sortByKey(rows);
            for (let i = 0; i < ordered.length; i += 1) {
                const row = ordered[i];
                const check = MoveGeometry.proposePieceDrop(
                    session,
                    pieceKey,
                    current.bounds.x + row.dx,
                    current.bounds.y + row.dy
                );
                if (!check.ok) continue;
                return {
                    ok: true,
                    dx: row.dx,
                    dy: row.dy,
                    guides: row.guides || [row.guide],
                    source: row.source,
                    proposal: check,
                };
            }
            return null;
        }

        const combined = [];
        const xs = sortByKey(axisCandidates.x).slice(0, 4);
        const ys = sortByKey(axisCandidates.y).slice(0, 4);
        xs.forEach((xRow) => {
            ys.forEach((yRow) => {
                const dx = xRow.dx;
                const dy = yRow.dy;
                if (hypot(dx - rawDx, dy - rawDy) > thresholdMm * 1.5 + EPS) return;
                combined.push({
                    dx,
                    dy,
                    source: `${xRow.source}+${yRow.source}`,
                    guide: xRow.guide,
                    guides: [xRow.guide, yRow.guide],
                    key: candidateKey(dx, dy, "combined", "xy"),
                });
            });
        });

        let found = firstValid(combined);
        if (found) return found;
        found = firstValid(axisCandidates.x) || firstValid(axisCandidates.y) || firstValid(axisCandidates.n);
        if (found) return found;
        return { ok: false, dx: rawDx, dy: rawDy, guides: [], source: null };
    }

    window.AlmdinaBoardEditor = window.AlmdinaBoardEditor || {};
    window.AlmdinaBoardEditor.SnapGeometry = Object.freeze({
        SNAP_ENTER_PX,
        SNAP_EXIT_PX,
        footprintEdges,
        usableEdgesWorld,
        suggestPieceSnap,
        thresholdMmFromScale,
    });
})();
