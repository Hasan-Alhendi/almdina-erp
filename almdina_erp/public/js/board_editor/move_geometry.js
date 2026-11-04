(() => {
    "use strict";

    // Mirrors domain/cutting/board_editor_session_edit.py for session-local preview.
    // Saved manufacturing plans never consume this path; nothing is persisted here.

    const DROP_OK = "ok";
    const DROP_PARTIAL_BOARD = "partial_board_overlap";
    const DROP_AMBIGUOUS_BOARD = "ambiguous_board_target";
    const DROP_OVERLAP = "piece_overlap";
    const DROP_KERF = "kerf_clearance";
    const DROP_BOARD_OVERLAP = "board_overlap";
    const DROP_NOT_EDITABLE = "not_editable";

    const REASON_LABELS = Object.freeze({
        [DROP_PARTIAL_BOARD]: "Drop rejected: the piece crosses a board edge.",
        [DROP_AMBIGUOUS_BOARD]: "Drop rejected: the piece overlaps more than one board.",
        [DROP_OVERLAP]: "Drop rejected: the piece overlaps another piece.",
        [DROP_KERF]: "Drop rejected: kerf clearance is insufficient.",
        [DROP_BOARD_OVERLAP]: "Drop rejected: boards would overlap.",
        [DROP_NOT_EDITABLE]: "This piece cannot be moved in the session.",
    });

    function num(value) {
        const n = Number(value);
        return Number.isFinite(n) ? n : 0;
    }

    function reasonMessage(code) {
        return REASON_LABELS[code] || "Drop rejected.";
    }

    function pieceKeyFromInstance(pieceInstanceId) {
        const id = String(pieceInstanceId || "").trim();
        return id ? `instance:${id}` : null;
    }

    function resolvePieceKey(session, pieceKeyOrInstance) {
        const raw = String(pieceKeyOrInstance || "").trim();
        if (!raw) return null;
        if (session.pieces[raw]) return raw;
        const asInstance = pieceKeyFromInstance(raw);
        if (asInstance && session.pieces[asInstance]) return asInstance;
        return null;
    }

    function rectIntersects(a, b) {
        return !(
            b.x >= a.x + a.w
            || b.x + b.w <= a.x
            || b.y >= a.y + a.h
            || b.y + b.h <= a.y
        );
    }

    function isContained(a, b) {
        return a.x >= b.x
            && a.y >= b.y
            && a.x + a.w <= b.x + b.w
            && a.y + a.h <= b.y + b.h;
    }

    function rectsHaveClearance(a, b, clearance) {
        const gap = Math.max(0, num(clearance));
        return (
            a.x + a.w + gap <= b.x
            || b.x + b.w + gap <= a.x
            || a.y + a.h + gap <= b.y
            || b.y + b.h + gap <= a.y
        );
    }

    function footprint(piece) {
        if (Array.isArray(piece.outline_mm) && piece.outline_mm.length >= 3) {
            const xs = piece.outline_mm.map((point) => num(point[0]));
            const ys = piece.outline_mm.map((point) => num(point[1]));
            return {
                kind: "polygon",
                points: piece.outline_mm.map((point) => [num(point[0]), num(point[1])]),
                bounds: {
                    x: Math.min(...xs),
                    y: Math.min(...ys),
                    w: Math.max(...xs) - Math.min(...xs),
                    h: Math.max(...ys) - Math.min(...ys),
                },
            };
        }
        const placement = piece.placement_cm || {};
        let w = num(placement.w) * 10;
        let h = num(placement.h) * 10;
        if (placement.rotated) {
            const swap = w;
            w = h;
            h = swap;
        }
        return {
            kind: "rect",
            points: null,
            bounds: {
                x: piece.local_x_mm != null ? num(piece.local_x_mm) : num(placement.x) * 10,
                y: piece.local_y_mm != null ? num(piece.local_y_mm) : num(placement.y) * 10,
                w,
                h,
            },
        };
    }

    function sheetOriginMm(boards, sheetNo) {
        if (sheetNo == null || sheetNo === "") return { x: 0, y: 0 };
        const board = (boards && boards[String(sheetNo)]) || {};
        return {
            x: num(board.origin_x_mm) + num(board.trim_x_mm),
            y: num(board.origin_y_mm) + num(board.trim_y_mm),
        };
    }

    function pointsToWorld(points, sheetNo, boards) {
        if (!Array.isArray(points)) return points;
        const origin = sheetOriginMm(boards, sheetNo);
        return points.map((point) => [num(point[0]) + origin.x, num(point[1]) + origin.y]);
    }

    function pointsFromWorld(points, sheetNo, boards) {
        if (!Array.isArray(points)) return points;
        const origin = sheetOriginMm(boards, sheetNo);
        return points.map((point) => [num(point[0]) - origin.x, num(point[1]) - origin.y]);
    }

    function pivotInWorld(piece, boards) {
        const origin = sheetOriginMm(boards, piece && piece.sheet_no);
        const pivot = (piece && piece.pivot_mm) || {};
        if (pivot.x != null && pivot.y != null) {
            return { x: num(pivot.x) + origin.x, y: num(pivot.y) + origin.y };
        }
        const local = footprint(piece);
        return {
            x: local.bounds.x + local.bounds.w * 0.5 + origin.x,
            y: local.bounds.y + local.bounds.h * 0.5 + origin.y,
        };
    }

    function worldFootprint(piece, boards) {
        const local = footprint(piece);
        if (piece.sheet_no == null || piece.sheet_no === "") return local;
        const origin = sheetOriginMm(boards, piece.sheet_no);
        return {
            kind: local.kind,
            points: local.points
                ? local.points.map((point) => [point[0] + origin.x, point[1] + origin.y])
                : null,
            bounds: {
                x: local.bounds.x + origin.x,
                y: local.bounds.y + origin.y,
                w: local.bounds.w,
                h: local.bounds.h,
            },
        };
    }

    function reframePoints(points, boards, fromSheet, toSheet, worldDx, worldDy) {
        if (!Array.isArray(points)) return points;
        const from = sheetOriginMm(boards, fromSheet);
        const to = sheetOriginMm(boards, toSheet);
        return points.map((point) => [
            num(point[0]) + from.x + num(worldDx) - to.x,
            num(point[1]) + from.y + num(worldDy) - to.y,
        ]);
    }

    function reframePieceGeometry(piece, boards, fromSheet, toSheet, worldDx, worldDy) {
        piece.outline_mm = reframePoints(piece.outline_mm, boards, fromSheet, toSheet, worldDx, worldDy);
        piece.base_outline_mm = reframePoints(
            piece.base_outline_mm,
            boards,
            fromSheet,
            toSheet,
            worldDx,
            worldDy
        );
        piece.glass_hole_local_mm = reframePoints(
            piece.glass_hole_local_mm,
            boards,
            fromSheet,
            toSheet,
            worldDx,
            worldDy
        );
        piece.base_hole_mm = reframePoints(
            piece.base_hole_mm,
            boards,
            fromSheet,
            toSheet,
            worldDx,
            worldDy
        );
        if (piece.pivot_mm && typeof piece.pivot_mm === "object") {
            const from = sheetOriginMm(boards, fromSheet);
            const to = sheetOriginMm(boards, toSheet);
            piece.pivot_mm = {
                x: num(piece.pivot_mm.x) + from.x + num(worldDx) - to.x,
                y: num(piece.pivot_mm.y) + from.y + num(worldDy) - to.y,
            };
        }
        // entry_pivot_mm stays in the immutable entry usable-sheet frame.
    }

    function pieceWorldOrigin(session, pieceKeyOrInstance) {
        const key = resolvePieceKey(session, pieceKeyOrInstance);
        const piece = key && session.pieces[key];
        if (!piece) return { x: 0, y: 0 };
        const world = worldFootprint(piece, session.boards);
        return { x: world.bounds.x, y: world.bounds.y };
    }

    function draggedPieceIds(session, pieceKeyOrInstance) {
        const key = resolvePieceKey(session, pieceKeyOrInstance);
        if (!key) return [];
        const ids = [key];
        Object.keys(session.pieces || {}).forEach((guestKey) => {
            if (
                session.pieces[guestKey].glass_host_key === key
                && session.pieces[guestKey].distribution !== "excluded"
            ) ids.push(guestKey);
        });
        return ids;
    }

    function groupMovePlan(session, selectedKeys, pressedKey) {
        const selectedList = (selectedKeys || []).filter((key) => session && session.pieces && session.pieces[key]);
        const selected = new Set(selectedList);
        const pressed = resolvePieceKey(session, pressedKey);
        const useSelection = Boolean(pressed && selected.has(pressed));
        const seeds = useSelection ? selectedList.slice() : (pressed ? [pressed] : []);
        const seedSet = new Set(seeds);
        const roots = [];
        seeds.forEach((key) => {
            const piece = session.pieces[key];
            if (!piece || piece.distribution === "excluded") return;
            const hostKey = piece.glass_host_key;
            if (
                hostKey
                && seedSet.has(hostKey)
                && session.pieces[hostKey]
                && session.pieces[hostKey].distribution !== "excluded"
            ) {
                return;
            }
            roots.push(key);
        });
        const moving = [];
        const seen = new Set();
        roots.forEach((key) => {
            draggedPieceIds(session, key).forEach((id) => {
                if (seen.has(id)) return;
                seen.add(id);
                moving.push(id);
            });
        });
        const locked = seeds.length > 1 && seeds.some((key) => {
            const piece = session.pieces[key];
            return piece && !piece.editable;
        });
        return { roots, moving, locked, seeds };
    }

    function proposeGroupMove(session, rootKeys, dx, dy) {
        const roots = (rootKeys || []).filter((key) => session && session.pieces && session.pieces[key]);
        if (!roots.length) {
            return { ok: false, code: DROP_NOT_EDITABLE, reason: reasonMessage(DROP_NOT_EDITABLE), commands: [] };
        }
        const moving = new Set();
        roots.forEach((key) => draggedPieceIds(session, key).forEach((id) => moving.add(id)));
        const commands = [];
        for (let index = 0; index < roots.length; index += 1) {
            const key = roots[index];
            const origin = pieceWorldOrigin(session, key);
            const decision = validatePieceDrop(session, key, origin.x + num(dx), origin.y + num(dy), moving);
            if (!decision.ok) {
                return { ok: false, code: decision.code, reason: reasonMessage(decision.code), commands: [] };
            }
            const piece = session.pieces[key];
            let detachHost = false;
            const host = piece.glass_host_key ? session.pieces[piece.glass_host_key] : null;
            if (host && !moving.has(piece.glass_host_key)) {
                const trial = {
                    ...piece,
                    sheet_no: decision.sheet_no,
                    local_x_mm: decision.local_x_mm,
                    local_y_mm: decision.local_y_mm,
                };
                if (
                    Number(trial.sheet_no) !== Number(host.sheet_no)
                    || !guestRemainsInHost(trial, host)
                ) {
                    detachHost = true;
                }
            }
            commands.push({
                piece_key: key,
                target_sheet_no: decision.sheet_no,
                local_x_mm: decision.local_x_mm,
                local_y_mm: decision.local_y_mm,
                delta_x_mm: decision.delta_x_mm,
                delta_y_mm: decision.delta_y_mm,
                detach_host: detachHost,
            });
        }
        return { ok: true, commands, dx: num(dx), dy: num(dy) };
    }

    function boardsOverlap(a, b, gapMm) {
        const pad = Math.max(0, num(gapMm));
        const titleA = num(a.title_band_mm) || 36;
        const titleB = num(b.title_band_mm) || 36;
        const ra = {
            x: num(a.origin_x_mm) - pad,
            y: num(a.origin_y_mm) - titleA - pad,
            w: num(a.width_mm) + pad * 2,
            h: num(a.height_mm) + titleA + pad * 2,
        };
        const rb = {
            x: num(b.origin_x_mm) - pad,
            y: num(b.origin_y_mm) - titleB - pad,
            w: num(b.width_mm) + pad * 2,
            h: num(b.height_mm) + titleB + pad * 2,
        };
        return rectIntersects(ra, rb);
    }

    function validateBoardPlacement(boards, sheetNo, originX, originY) {
        const moving = { ...(boards[String(sheetNo)] || {}), origin_x_mm: originX, origin_y_mm: originY };
        for (const [otherNo, other] of Object.entries(boards || {})) {
            if (String(otherNo) === String(sheetNo)) continue;
            if (boardsOverlap(moving, other, 8)) {
                return { ok: false, code: DROP_BOARD_OVERLAP };
            }
        }
        return { ok: true, code: DROP_OK };
    }

    function proposeBoardDrop(session, sheetNo, originX, originY) {
        const check = validateBoardPlacement(session.boards, sheetNo, originX, originY);
        if (!check.ok) {
            return { ok: false, reason: reasonMessage(check.code), code: check.code };
        }
        return {
            ok: true,
            origin_x_mm: num(originX),
            origin_y_mm: num(originY),
        };
    }

    function insideUsable(localFootprint, board) {
        const usable = {
            x: 0,
            y: 0,
            w: num(board.usable_width_mm) || num(board.width_mm),
            h: num(board.usable_length_mm) || num(board.height_mm),
        };
        return isContained(localFootprint.bounds, usable);
    }

    function intersectsUsable(localFootprint, board) {
        const usable = {
            x: 0,
            y: 0,
            w: num(board.usable_width_mm) || num(board.width_mm),
            h: num(board.usable_length_mm) || num(board.height_mm),
        };
        return rectIntersects(localFootprint.bounds, usable);
    }

    function resolveDropSheet(footprintWorld, boards) {
        const inside = [];
        const partial = [];
        Object.entries(boards || {}).forEach(([sheetNo, board]) => {
            const ox = num(board.origin_x_mm) + num(board.trim_x_mm);
            const oy = num(board.origin_y_mm) + num(board.trim_y_mm);
            const local = {
                kind: footprintWorld.kind,
                points: footprintWorld.points
                    ? footprintWorld.points.map((point) => [point[0] - ox, point[1] - oy])
                    : null,
                bounds: {
                    x: footprintWorld.bounds.x - ox,
                    y: footprintWorld.bounds.y - oy,
                    w: footprintWorld.bounds.w,
                    h: footprintWorld.bounds.h,
                },
            };
            if (insideUsable(local, board)) inside.push(sheetNo);
            else if (intersectsUsable(local, board)) partial.push(sheetNo);
        });
        if (partial.length) return { ok: false, code: DROP_PARTIAL_BOARD };
        if (inside.length > 1) return { ok: false, code: DROP_AMBIGUOUS_BOARD };
        if (inside.length === 1) {
            const sheetNo = inside[0];
            const board = boards[sheetNo];
            const ox = num(board.origin_x_mm) + num(board.trim_x_mm);
            const oy = num(board.origin_y_mm) + num(board.trim_y_mm);
            return {
                ok: true,
                code: DROP_OK,
                sheet_no: Number(sheetNo),
                local_x_mm: footprintWorld.bounds.x - ox,
                local_y_mm: footprintWorld.bounds.y - oy,
            };
        }
        return {
            ok: true,
            code: DROP_OK,
            sheet_no: null,
            local_x_mm: footprintWorld.bounds.x,
            local_y_mm: footprintWorld.bounds.y,
        };
    }

    function segmentsIntersect(a1, a2, b1, b2) {
        function cross(o, a, b) {
            return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0]);
        }
        const d1 = cross(a1, a2, b1);
        const d2 = cross(a1, a2, b2);
        const d3 = cross(b1, b2, a1);
        const d4 = cross(b1, b2, a2);
        return (
            ((d1 > 0 && d2 < 0) || (d1 < 0 && d2 > 0))
            && ((d3 > 0 && d4 < 0) || (d3 < 0 && d4 > 0))
        );
    }

    function pointInPolygon(point, polygon) {
        let inside = false;
        for (let i = 0, j = polygon.length - 1; i < polygon.length; j = i, i += 1) {
            const xi = num(polygon[i][0]);
            const yi = num(polygon[i][1]);
            const xj = num(polygon[j][0]);
            const yj = num(polygon[j][1]);
            const intersect = ((yi > point[1]) !== (yj > point[1]))
                && (point[0] < ((xj - xi) * (point[1] - yi)) / ((yj - yi) || 1e-12) + xi);
            if (intersect) inside = !inside;
        }
        return inside;
    }

    function polygonsOverlap(a, b) {
        if (!Array.isArray(a) || !Array.isArray(b) || a.length < 3 || b.length < 3) return false;
        for (let i = 0; i < a.length; i += 1) {
            const a1 = a[i];
            const a2 = a[(i + 1) % a.length];
            for (let j = 0; j < b.length; j += 1) {
                if (segmentsIntersect(a1, a2, b[j], b[(j + 1) % b.length])) return true;
            }
        }
        return pointInPolygon(a[0], b) || pointInPolygon(b[0], a);
    }

    function pointSegmentDistance(point, a, b) {
        const dx = num(b[0]) - num(a[0]);
        const dy = num(b[1]) - num(a[1]);
        const denom = (dx * dx) + (dy * dy);
        if (denom <= 1e-18) {
            return Math.hypot(num(point[0]) - num(a[0]), num(point[1]) - num(a[1]));
        }
        let t = (
            ((num(point[0]) - num(a[0])) * dx) + ((num(point[1]) - num(a[1])) * dy)
        ) / denom;
        t = Math.max(0, Math.min(1, t));
        return Math.hypot(
            num(point[0]) - (num(a[0]) + (t * dx)),
            num(point[1]) - (num(a[1]) + (t * dy))
        );
    }

    function segmentDistance(a1, a2, b1, b2) {
        if (segmentsIntersect(a1, a2, b1, b2)) return 0;
        return Math.min(
            pointSegmentDistance(a1, b1, b2),
            pointSegmentDistance(a2, b1, b2),
            pointSegmentDistance(b1, a1, a2),
            pointSegmentDistance(b2, a1, a2)
        );
    }

    function polygonDistance(a, b) {
        if (!Array.isArray(a) || !Array.isArray(b) || a.length < 2 || b.length < 2) {
            return Number.POSITIVE_INFINITY;
        }
        let min = Number.POSITIVE_INFINITY;
        for (let i = 0; i < a.length; i += 1) {
            const a1 = a[i];
            const a2 = a[(i + 1) % a.length];
            for (let j = 0; j < b.length; j += 1) {
                const distance = segmentDistance(a1, a2, b[j], b[(j + 1) % b.length]);
                if (distance < min) min = distance;
            }
        }
        return min;
    }

    function pairConflict(a, b, kerfMm) {
        // Material overlap via polygons; AABB only early-accepts far pairs for kerf.
        const gap = Math.max(0, num(kerfMm));
        if (a.kind === "polygon" && b.kind === "polygon" && a.points && b.points) {
            if (polygonsOverlap(a.points, b.points)) return DROP_OVERLAP;
            if (rectsHaveClearance(a.bounds, b.bounds, gap)) return null;
            if (polygonDistance(a.points, b.points) + 1e-9 < gap) return DROP_KERF;
            return null;
        }
        if (rectIntersects(a.bounds, b.bounds)) return DROP_OVERLAP;
        if (!rectsHaveClearance(a.bounds, b.bounds, gap)) return DROP_KERF;
        return null;
    }

    function validatePieceDrop(session, pieceKeyOrInstance, worldX, worldY, ignoreKeys) {
        const pieceKey = resolvePieceKey(session, pieceKeyOrInstance);
        const piece = pieceKey && session.pieces[pieceKey];
        if (!piece || !piece.editable || piece.distribution === "excluded") {
            return { ok: false, code: DROP_NOT_EDITABLE };
        }
        const current = worldFootprint(piece, session.boards);
        const dx = num(worldX) - current.bounds.x;
        const dy = num(worldY) - current.bounds.y;
        const proposed = {
            kind: current.kind,
            points: current.points
                ? current.points.map((point) => [point[0] + dx, point[1] + dy])
                : null,
            bounds: {
                x: current.bounds.x + dx,
                y: current.bounds.y + dy,
                w: current.bounds.w,
                h: current.bounds.h,
            },
        };
        const target = resolveDropSheet(proposed, session.boards);
        if (!target.ok) return { ok: false, code: target.code, delta_x_mm: dx, delta_y_mm: dy };

        const moved = {
            ...piece,
            sheet_no: target.sheet_no,
            local_x_mm: target.local_x_mm,
            local_y_mm: target.local_y_mm,
            outline_mm: reframePoints(
                piece.outline_mm,
                session.boards,
                piece.sheet_no,
                target.sheet_no,
                dx,
                dy
            ),
            pivot_mm: piece.pivot_mm
                ? {
                    x: num(piece.pivot_mm.x)
                        + sheetOriginMm(session.boards, piece.sheet_no).x
                        + dx
                        - sheetOriginMm(session.boards, target.sheet_no).x,
                    y: num(piece.pivot_mm.y)
                        + sheetOriginMm(session.boards, piece.sheet_no).y
                        + dy
                        - sheetOriginMm(session.boards, target.sheet_no).y,
                }
                : piece.pivot_mm,
        };
        const movedLocal = footprint(moved);
        const movingKeys = ignoreKeys && typeof ignoreKeys.has === "function"
            ? ignoreKeys
            : new Set(draggedPieceIds(session, pieceKey));
        if (target.sheet_no != null) {
            for (const [otherKey, other] of Object.entries(session.pieces)) {
                if (movingKeys.has(otherKey)) continue;
                if (other.distribution === "excluded") continue;
                if (Number(other.sheet_no) !== Number(target.sheet_no)) continue;
                if (other.glass_host_key === pieceKey || piece.glass_host_key === otherKey) continue;
                const conflict = pairConflict(movedLocal, footprint(other), session.kerf_mm || 0);
                if (conflict) return { ok: false, code: conflict, delta_x_mm: dx, delta_y_mm: dy };
            }
        }
        return {
            ok: true,
            code: DROP_OK,
            sheet_no: target.sheet_no,
            local_x_mm: target.local_x_mm,
            local_y_mm: target.local_y_mm,
            delta_x_mm: dx,
            delta_y_mm: dy,
        };
    }

    function proposePieceDrop(session, pieceKeyOrInstance, worldX, worldY) {
        const pieceKey = resolvePieceKey(session, pieceKeyOrInstance);
        const decision = validatePieceDrop(session, pieceKey, worldX, worldY);
        if (!decision.ok) {
            return {
                ok: false,
                reason: reasonMessage(decision.code),
                code: decision.code,
            };
        }
        const piece = session.pieces[pieceKey];
        let detachHost = false;
        if (piece && piece.glass_host_key && session.pieces[piece.glass_host_key]) {
            const trial = {
                ...piece,
                sheet_no: decision.sheet_no,
                local_x_mm: decision.local_x_mm,
                local_y_mm: decision.local_y_mm,
            };
            if (
                Number(trial.sheet_no) !== Number(session.pieces[piece.glass_host_key].sheet_no)
                || !guestRemainsInHost(trial, session.pieces[piece.glass_host_key])
            ) {
                detachHost = true;
            }
        }
        return {
            ok: true,
            target_sheet_no: decision.sheet_no,
            local_x_mm: decision.local_x_mm,
            local_y_mm: decision.local_y_mm,
            delta_x_mm: decision.delta_x_mm,
            delta_y_mm: decision.delta_y_mm,
            detach_host: detachHost,
            piece_key: pieceKey,
        };
    }

    function guestRemainsInHost(guest, host) {
        const hole = host.glass_hole_local_mm;
        const guestFp = footprint(guest);
        if (Array.isArray(hole) && hole.length >= 3) {
            const xs = hole.map((point) => num(point[0]));
            const ys = hole.map((point) => num(point[1]));
            const holeRect = {
                x: Math.min(...xs),
                y: Math.min(...ys),
                w: Math.max(...xs) - Math.min(...xs),
                h: Math.max(...ys) - Math.min(...ys),
            };
            return isContained(guestFp.bounds, holeRect);
        }
        return Number(guest.sheet_no) === Number(host.sheet_no);
    }

    function applyPieceMove(session, command) {
        const next = JSON.parse(JSON.stringify(session));
        const pieceKey = resolvePieceKey(next, command.piece_key || command.piece_instance_id);
        const piece = pieceKey && next.pieces[pieceKey];
        if (!piece) return session;
        const previousSheet = piece.sheet_no;
        const dx = num(command.delta_x_mm != null
            ? command.delta_x_mm
            : (num(command.local_x_mm) - num(piece.local_x_mm)));
        const dy = num(command.delta_y_mm != null
            ? command.delta_y_mm
            : (num(command.local_y_mm) - num(piece.local_y_mm)));
        const targetSheet = command.target_sheet_no !== undefined
            ? command.target_sheet_no
            : command.sheet_no;
        // World delta must be reframed when the usable-sheet origin changes
        // (board ↔ board or board ↔ outside). Same-sheet reduces to a plain translate.
        reframePieceGeometry(piece, next.boards, previousSheet, targetSheet, dx, dy);
        piece.sheet_no = targetSheet;
        piece.local_x_mm = num(command.local_x_mm);
        piece.local_y_mm = num(command.local_y_mm);

        Object.values(next.pieces).forEach((guest) => {
            if (guest.glass_host_key !== pieceKey) return;
            if (guest.distribution === "excluded") return;
            const guestFrom = guest.sheet_no;
            reframePieceGeometry(guest, next.boards, guestFrom, targetSheet, dx, dy);
            guest.sheet_no = targetSheet;
            const guestFp = footprint(guest);
            guest.local_x_mm = guestFp.bounds.x;
            guest.local_y_mm = guestFp.bounds.y;
        });

        if (command.detach_host || (piece.glass_host_key && next.pieces[piece.glass_host_key])) {
            const host = piece.glass_host_key ? next.pieces[piece.glass_host_key] : null;
            if (
                command.detach_host
                || !host
                || Number(piece.sheet_no) !== Number(host.sheet_no)
                || !guestRemainsInHost(piece, host)
            ) {
                piece.glass_host_key = null;
                piece.glass_host_piece_id = null;
            }
        }

        function mark(sheetNo) {
            if (sheetNo == null || sheetNo === "") return;
            const key = String(sheetNo);
            if (!next.stale_cut_path_sheets.includes(key)) next.stale_cut_path_sheets.push(key);
            if (!next.stale_unbound_text_sheets.includes(key)) next.stale_unbound_text_sheets.push(key);
        }
        mark(previousSheet);
        mark(targetSheet);
        return next;
    }

    function applyBoardMove(session, commandOrSheetNo, originX, originY) {
        const next = JSON.parse(JSON.stringify(session));
        const isObject = commandOrSheetNo && typeof commandOrSheetNo === "object";
        const sheetNo = isObject ? commandOrSheetNo.sheet_no : commandOrSheetNo;
        const board = next.boards[String(sheetNo)];
        if (!board) return session;
        board.origin_x_mm = num(isObject ? commandOrSheetNo.origin_x_mm : originX);
        board.origin_y_mm = num(isObject ? commandOrSheetNo.origin_y_mm : originY);
        board.user_moved = true;
        return next;
    }

    window.AlmdinaBoardEditor = window.AlmdinaBoardEditor || {};
    window.AlmdinaBoardEditor.MoveGeometry = Object.freeze({
        DROP_OK,
        DROP_PARTIAL_BOARD,
        DROP_AMBIGUOUS_BOARD,
        DROP_OVERLAP,
        DROP_KERF,
        DROP_BOARD_OVERLAP,
        DROP_NOT_EDITABLE,
        reasonMessage,
        footprint,
        worldFootprint,
        sheetOriginMm,
        pointsToWorld,
        pointsFromWorld,
        pivotInWorld,
        reframePoints,
        reframePieceGeometry,
        pieceWorldOrigin,
        draggedPieceIds,
        groupMovePlan,
        validatePieceDrop,
        validateBoardPlacement,
        proposePieceDrop,
        proposeGroupMove,
        proposeBoardDrop,
        applyPieceMove,
        applyBoardMove,
        boardsOverlap,
        pairConflict,
        polygonDistance,
        resolvePieceKey,
        pieceKeyFromInstance,
    });
})();
