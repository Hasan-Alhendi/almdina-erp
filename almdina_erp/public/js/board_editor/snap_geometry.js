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

    // Lower rank wins ties after magnitude: board/kerf (0), edge align, center align.
    // top/left beat bottom/right when the resulting translation magnitude is identical.
    const ALIGN_MODE_RANK = Object.freeze({
        top: 1,
        left: 1,
        bottom: 1.25,
        right: 1.25,
        centerX: 2,
        centerY: 2,
    });

    function candidateKey(dx, dy, source, side, rank) {
        return [
            Math.abs(dx) + Math.abs(dy),
            rank == null ? 0 : num(rank),
            Math.abs(dx),
            Math.abs(dy),
            source,
            side,
            Number(dx.toFixed(6)),
            Number(dy.toFixed(6)),
        ];
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
            kind: "edge",
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

    function aabbMetrics(bounds) {
        const minX = num(bounds.x);
        const minY = num(bounds.y);
        const maxX = minX + num(bounds.w);
        const maxY = minY + num(bounds.h);
        return {
            minX,
            minY,
            maxX,
            maxY,
            centerX: (minX + maxX) * 0.5,
            centerY: (minY + maxY) * 0.5,
        };
    }

    function sameSheetScope(a, b) {
        const left = a == null || a === "" ? null : String(a);
        const right = b == null || b === "" ? null : String(b);
        return left === right;
    }

    function alignmentGuide(mode, movingBounds, targetBounds, dx, dy, sourcePieceKey, targetPieceKey) {
        const moving = aabbMetrics({
            x: num(movingBounds.x) + dx,
            y: num(movingBounds.y) + dy,
            w: movingBounds.w,
            h: movingBounds.h,
        });
        const target = aabbMetrics(targetBounds);
        let x1;
        let y1;
        let x2;
        let y2;
        if (mode === "top" || mode === "bottom" || mode === "centerY") {
            const y = mode === "top"
                ? target.minY
                : (mode === "bottom" ? target.maxY : target.centerY);
            x1 = Math.min(moving.minX, target.minX);
            x2 = Math.max(moving.maxX, target.maxX);
            y1 = y;
            y2 = y;
        } else {
            const x = mode === "left"
                ? target.minX
                : (mode === "right" ? target.maxX : target.centerX);
            y1 = Math.min(moving.minY, target.minY);
            y2 = Math.max(moving.maxY, target.maxY);
            x1 = x;
            x2 = x;
        }
        return {
            kind: "alignment",
            mode,
            sourcePieceKey,
            targetPieceKey,
            x1,
            y1,
            x2,
            y2,
        };
    }

    function alignmentDeltas(movingBounds, targetBounds) {
        const moving = aabbMetrics(movingBounds);
        const target = aabbMetrics(targetBounds);
        return [
            { mode: "top", axis: "y", dx: 0, dy: target.minY - moving.minY },
            { mode: "bottom", axis: "y", dx: 0, dy: target.maxY - moving.maxY },
            { mode: "left", axis: "x", dx: target.minX - moving.minX, dy: 0 },
            { mode: "right", axis: "x", dx: target.maxX - moving.maxX, dy: 0 },
            { mode: "centerX", axis: "x", dx: target.centerX - moving.centerX, dy: 0 },
            { mode: "centerY", axis: "y", dx: 0, dy: target.centerY - moving.centerY },
        ];
    }

    function aabbNear(a, b, pad) {
        return !(
            b.x - pad >= a.x + a.w + pad
            || b.x + b.w + pad <= a.x - pad
            || b.y - pad >= a.y + a.h + pad
            || b.y + b.h + pad <= a.y - pad
        );
    }

    function aabbOverlapArea(a, b) {
        const w = Math.max(0, Math.min(a.x + a.w, b.x + b.w) - Math.max(a.x, b.x));
        const h = Math.max(0, Math.min(a.y + a.h, b.y + b.h) - Math.max(a.y, b.y));
        return w * h;
    }

    function aabbSeparationMm(a, b) {
        if (aabbOverlapArea(a, b) > 0) return 0;
        const dx = Math.max(0, Math.max(a.x - (b.x + b.w), b.x - (a.x + a.w)));
        const dy = Math.max(0, Math.max(a.y - (b.y + b.h), b.y - (a.y + a.h)));
        const overlapX = Math.max(0, Math.min(a.x + a.w, b.x + b.w) - Math.max(a.x, b.x));
        const overlapY = Math.max(0, Math.min(a.y + a.h, b.y + b.h) - Math.max(a.y, b.y));
        if (overlapX > 0) return dy;
        if (overlapY > 0) return dx;
        return Math.hypot(dx, dy);
    }

    // Large near-board-size pieces stay "near" multiple sheets across the
    // editor gap. Prefer the board with the greatest overlap (then closest).
    function pickPrimaryNearBoard(nearRows) {
        if (!nearRows.length) return null;
        if (nearRows.length === 1) return nearRows[0].sheetNo;
        const ranked = nearRows.slice().sort((left, right) => {
            if (right.overlapArea !== left.overlapArea) return right.overlapArea - left.overlapArea;
            if (left.separation !== right.separation) return left.separation - right.separation;
            return Number(left.sheetNo) - Number(right.sheetNo);
        });
        return ranked[0].sheetNo;
    }

    // Near-full doors can sit a few centimetres off a usable edge while that
    // error still exceeds the screen-pixel threshold. Assist only that near
    // miss (the 55mm fixture). Stay under half the leftover gap so the
    // opposite usable edge is outside the same catch radius. Neighbour snaps
    // keep the pixel threshold.
    const USABLE_EDGE_ASSIST_MM = 60;

    function usableEdgeThresholdMm(thresholdMm, pieceBounds, usable) {
        const base = num(thresholdMm);
        const uw = num(usable && usable.w);
        const uh = num(usable && usable.h);
        if (!(uw > 0) || !(uh > 0)) return base;
        const fillX = num(pieceBounds.w) / uw;
        const fillY = num(pieceBounds.h) / uh;
        if (fillX < 0.8 && fillY < 0.8) return base;
        const slackX = Math.max(0, uw - num(pieceBounds.w));
        const slackY = Math.max(0, uh - num(pieceBounds.h));
        const tightSlack = Math.min(slackX, slackY);
        let assist = Math.max(base, USABLE_EDGE_ASSIST_MM);
        if (tightSlack > 0) assist = Math.min(assist, Math.max(base, tightSlack / 2 - 1));
        return Math.max(base, assist);
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

        const nearRows = [];
        Object.entries(session.boards || {}).forEach(([sheetNo, board]) => {
            const ox = num(board.origin_x_mm) + num(board.trim_x_mm);
            const oy = num(board.origin_y_mm) + num(board.trim_y_mm);
            const usable = {
                x: ox,
                y: oy,
                w: num(board.usable_width_mm) || num(board.width_mm),
                h: num(board.usable_length_mm) || num(board.height_mm),
            };
            if (!aabbNear(proposed.bounds, usable, thresholdMm)) return;
            nearRows.push({
                sheetNo: String(sheetNo),
                overlapArea: aabbOverlapArea(proposed.bounds, usable),
                separation: aabbSeparationMm(proposed.bounds, usable),
            });
        });

        // Prefer the dominant nearby board so near-board-size doors still get
        // usable-edge magnetism when the editor gap keeps a neighbour "near".
        const primaryBoard = pickPrimaryNearBoard(nearRows);
        const sheetScope = primaryBoard != null
            ? String(primaryBoard)
            : (piece.sheet_no == null || piece.sheet_no === "" ? null : String(piece.sheet_no));

        const movingEdges = primaryBoard != null ? footprintEdges(proposed) : [];
        const targets = [];
        let primaryUsable = null;
        let usableThresholdMm = thresholdMm;
        if (primaryBoard != null) {
            const board = session.boards[primaryBoard];
            primaryUsable = {
                x: num(board.origin_x_mm) + num(board.trim_x_mm),
                y: num(board.origin_y_mm) + num(board.trim_y_mm),
                w: num(board.usable_width_mm) || num(board.width_mm),
                h: num(board.usable_length_mm) || num(board.height_mm),
            };
            usableThresholdMm = usableEdgeThresholdMm(thresholdMm, proposed.bounds, primaryUsable);
            usableEdgesWorld(board).forEach((edge) => {
                targets.push(["usable", edge, 0]);
            });
        }

        const movingKeys = new Set(MoveGeometry.draggedPieceIds(session, pieceKey));
        if (opts.ignoreKeys && typeof opts.ignoreKeys.forEach === "function") {
            opts.ignoreKeys.forEach((key) => movingKeys.add(key));
        }
        const pad = thresholdMm + Math.max(proposed.bounds.w, proposed.bounds.h);
        const nearbyPieces = [];
        Object.entries(session.pieces || {}).forEach(([otherKey, other]) => {
            if (movingKeys.has(otherKey)) return;
            if (other.distribution === "excluded") return;
            if (!sameSheetScope(other.sheet_no, sheetScope)) return;
            if (other.glass_host_key === pieceKey || piece.glass_host_key === otherKey) return;
            const otherFp = MoveGeometry.worldFootprint(other, session.boards);
            if (!aabbNear(proposed.bounds, otherFp.bounds, pad)) return;
            nearbyPieces.push({ key: otherKey, footprint: otherFp });
            if (primaryBoard != null) {
                footprintEdges(otherFp).forEach((edge) => {
                    targets.push([`piece:${otherKey}`, edge, num(session.kerf_mm)]);
                });
            }
        });

        const axisCandidates = { x: [], y: [], n: [] };
        targets.forEach(([source, targetEdge, gap]) => {
            movingEdges.forEach((movingEdge) => {
                if (!parallel(movingEdge, targetEdge)) return;
                const delta = edgeDelta(movingEdge, targetEdge, gap);
                if (!delta) return;
                const [dx, dy] = delta;
                const limit = source === "usable" ? usableThresholdMm : thresholdMm;
                if (hypot(dx, dy) > limit + EPS) return;
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
                    key: candidateKey(absDx, absDy, source, axis, 0),
                });
            });
        });

        // Alignment snap: same-side edges and centers (AABB discovery; MoveGeometry validates).
        nearbyPieces.forEach(({ key: otherKey, footprint: otherFp }) => {
            alignmentDeltas(proposed.bounds, otherFp.bounds).forEach((row) => {
                const rel = hypot(row.dx, row.dy);
                // Skip already-aligned axes so zero-delta centers do not hijack combined picks.
                if (rel <= EPS || rel > thresholdMm + EPS) return;
                const absDx = rawDx + row.dx;
                const absDy = rawDy + row.dy;
                const source = `align:${row.mode}:${otherKey}`;
                const guideRow = alignmentGuide(
                    row.mode,
                    proposed.bounds,
                    otherFp.bounds,
                    row.dx,
                    row.dy,
                    pieceKey,
                    otherKey
                );
                const rank = ALIGN_MODE_RANK[row.mode] == null ? 1 : ALIGN_MODE_RANK[row.mode];
                axisCandidates[row.axis].push({
                    dx: absDx,
                    dy: absDy,
                    source,
                    guide: guideRow,
                    key: candidateKey(absDx, absDy, source, row.axis, rank),
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
        const combinedLimit = Math.max(thresholdMm, usableThresholdMm) * 1.5;
        xs.forEach((xRow) => {
            ys.forEach((yRow) => {
                const dx = xRow.dx;
                const dy = yRow.dy;
                if (hypot(dx - rawDx, dy - rawDy) > combinedLimit + EPS) return;
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
        if (!found) found = firstValid(axisCandidates.x) || firstValid(axisCandidates.y) || firstValid(axisCandidates.n);
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
        alignmentDeltas,
        alignmentGuide,
    });
})();
