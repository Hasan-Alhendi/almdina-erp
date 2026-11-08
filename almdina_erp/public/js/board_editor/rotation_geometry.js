(() => {
    "use strict";

    // Interactive mirror of domain/cutting/board_editor_rotation.py.
    // Manufacturing acceptance still lives in Domain; this module mirrors
    // transform + eligibility + drop checks for the session UI.

    const ANGLE_EPS = 1e-9;
    const ROTATE_BLOCK_NOT_ALLOWED = "rotation_not_allowed";
    const ROTATE_BLOCK_GUEST_FORBIDDEN = "guest_rotation_forbidden";
    const ROTATE_BLOCK_SPECIAL = "special_geometry_unavailable";
    const ROTATE_BLOCK_INCOMPLETE = "incomplete_geometry";
    const ROTATE_BLOCK_NOT_EDITABLE = "not_editable";
    const ROTATE_BLOCK_HOSTING = "guest_outside_host_hole";

    function num(value) {
        const n = Number(value);
        return Number.isFinite(n) ? n : 0;
    }

    function normalizeAngleDeg(value) {
        const n = Number(value);
        if (!Number.isFinite(n)) return 0;
        let angle = n % 360;
        if (angle < 0) angle += 360;
        if (Math.abs(angle - 360) < ANGLE_EPS || Math.abs(angle) < ANGLE_EPS) return 0;
        return angle;
    }

    function anglesEquivalent(a, b, eps) {
        const tol = eps == null ? 1e-6 : eps;
        const first = normalizeAngleDeg(a);
        const second = normalizeAngleDeg(b);
        const delta = Math.abs(first - second);
        return Math.min(delta, 360 - delta) <= tol;
    }

    function pivotXY(pivot) {
        if (pivot && typeof pivot === "object" && !Array.isArray(pivot)) {
            return { x: num(pivot.x), y: num(pivot.y) };
        }
        return { x: num(pivot && pivot[0]), y: num(pivot && pivot[1]) };
    }

    function rotatePoint(point, pivot, angleDeg) {
        const p = pivotXY(pivot);
        const x = num(point[0]) - p.x;
        const y = num(point[1]) - p.y;
        const rad = (normalizeAngleDeg(angleDeg) * Math.PI) / 180;
        const cosA = Math.cos(rad);
        const sinA = Math.sin(rad);
        // SVG-compatible: positive angle is clockwise with Y downward.
        return [p.x + x * cosA + y * sinA, p.y - x * sinA + y * cosA];
    }

    function rotatePoints(points, pivot, angleDeg) {
        if (!Array.isArray(points)) return null;
        return points.map((point) => rotatePoint(point, pivot, angleDeg));
    }

    function aabbCenter(points) {
        const xs = points.map((point) => num(point[0]));
        const ys = points.map((point) => num(point[1]));
        return {
            x: (Math.min(...xs) + Math.max(...xs)) * 0.5,
            y: (Math.min(...ys) + Math.max(...ys)) * 0.5,
        };
    }

    function footprintOf(piece) {
        const MoveGeometry = window.AlmdinaBoardEditor.MoveGeometry;
        return MoveGeometry.footprint(piece);
    }

    function ensureBaseGeometry(piece) {
        if (!Array.isArray(piece.base_outline_mm) || piece.base_outline_mm.length < 3) {
            if (Array.isArray(piece.outline_mm) && piece.outline_mm.length >= 3) {
                piece.base_outline_mm = piece.outline_mm.map((point) => [num(point[0]), num(point[1])]);
            } else {
                const placement = piece.placement_cm || {};
                let w = num(placement.w) * 10;
                let h = num(placement.h) * 10;
                if (piece.source_rotated_dims && placement.rotated) {
                    const swap = w;
                    w = h;
                    h = swap;
                }
                const x = piece.local_x_mm != null ? num(piece.local_x_mm) : num(placement.x) * 10;
                const y = piece.local_y_mm != null ? num(piece.local_y_mm) : num(placement.y) * 10;
                piece.base_outline_mm = [[x, y], [x + w, y], [x + w, y + h], [x, y + h]];
            }
        }
        if (piece.base_hole_mm == null && Array.isArray(piece.glass_hole_local_mm)) {
            piece.base_hole_mm = piece.glass_hole_local_mm.map((point) => [num(point[0]), num(point[1])]);
        }
        if (!piece.pivot_mm || piece.pivot_mm.x == null) {
            piece.pivot_mm = aabbCenter(piece.base_outline_mm);
        }
        if (!piece.entry_pivot_mm) {
            piece.entry_pivot_mm = { x: num(piece.pivot_mm.x), y: num(piece.pivot_mm.y) };
        }
        piece.rotation_deg = normalizeAngleDeg(piece.rotation_deg);
    }

    function rederiveOutline(piece) {
        ensureBaseGeometry(piece);
        const angle = normalizeAngleDeg(piece.rotation_deg);
        piece.outline_mm = rotatePoints(piece.base_outline_mm, piece.pivot_mm, angle);
        if (Array.isArray(piece.base_hole_mm) && piece.base_hole_mm.length >= 3) {
            piece.glass_hole_local_mm = rotatePoints(piece.base_hole_mm, piece.pivot_mm, angle);
        }
        const bounds = footprintOf(piece).bounds;
        piece.local_x_mm = bounds.x;
        piece.local_y_mm = bounds.y;
    }

    function explicitAllowRotation(piece) {
        if (!piece) return false;
        if (piece.allow_rotation_proven === false) return false;
        if (piece.allow_rotation == null && piece.allow_rotation_proven == null) return false;
        const flag = piece.allow_rotation;
        return flag === true || flag === 1 || flag === "1";
    }

    function guestKeys(session, hostKey) {
        return Object.keys(session.pieces || {}).filter((key) => {
            const guest = session.pieces[key];
            return guest.glass_host_key === hostKey && guest.distribution !== "excluded";
        });
    }

    function descendantGuestKeys(session, hostKey) {
        const ordered = [];
        const stack = guestKeys(session, hostKey).slice();
        const seen = new Set();
        while (stack.length) {
            const key = stack.shift();
            if (seen.has(key)) continue;
            seen.add(key);
            ordered.push(key);
            guestKeys(session, key).forEach((child) => stack.push(child));
        }
        return ordered;
    }

    function pieceRotationEligibility(session, pieceKey) {
        const piece = session.pieces && session.pieces[pieceKey];
        if (!piece) {
            return { rotatable: false, reason: ROTATE_BLOCK_NOT_EDITABLE, affected_keys: [] };
        }
        if (!piece.editable || piece.distribution === "excluded") {
            return {
                rotatable: false,
                reason: piece.block_reason || ROTATE_BLOCK_NOT_EDITABLE,
                affected_keys: [],
            };
        }
        if (piece.block_reason === "special_geometry_unavailable") {
            return { rotatable: false, reason: ROTATE_BLOCK_SPECIAL, affected_keys: [] };
        }
        ensureBaseGeometry(piece);
        if (!Array.isArray(piece.base_outline_mm) || piece.base_outline_mm.length < 3) {
            return { rotatable: false, reason: ROTATE_BLOCK_INCOMPLETE, affected_keys: [] };
        }
        if (!explicitAllowRotation(piece)) {
            return { rotatable: false, reason: ROTATE_BLOCK_NOT_ALLOWED, affected_keys: [] };
        }
        const affected = [pieceKey].concat(descendantGuestKeys(session, pieceKey));
        for (let index = 1; index < affected.length; index += 1) {
            const guest = session.pieces[affected[index]];
            if (!explicitAllowRotation(guest)) {
                return {
                    rotatable: false,
                    reason: ROTATE_BLOCK_GUEST_FORBIDDEN,
                    blocking_guest_key: affected[index],
                    affected_keys: affected,
                };
            }
            if (!guest.editable) {
                return {
                    rotatable: false,
                    reason: guest.block_reason || ROTATE_BLOCK_NOT_EDITABLE,
                    blocking_guest_key: affected[index],
                    affected_keys: affected,
                };
            }
        }
        return { rotatable: true, reason: null, affected_keys: affected };
    }

    function applyAngleToPiece(piece, angleDeg) {
        ensureBaseGeometry(piece);
        piece.rotation_deg = normalizeAngleDeg(angleDeg);
        rederiveOutline(piece);
    }

    function rigidRotatePieceAbout(piece, hostPivot, deltaDeg) {
        ensureBaseGeometry(piece);
        const delta = Number(deltaDeg) || 0;
        if (Math.abs(delta) < ANGLE_EPS) return;
        piece.base_outline_mm = rotatePoints(piece.base_outline_mm, hostPivot, delta);
        if (Array.isArray(piece.base_hole_mm)) {
            piece.base_hole_mm = rotatePoints(piece.base_hole_mm, hostPivot, delta);
        }
        const rotatedPivot = rotatePoint(
            [num(piece.pivot_mm.x), num(piece.pivot_mm.y)],
            hostPivot,
            delta
        );
        piece.pivot_mm = { x: rotatedPivot[0], y: rotatedPivot[1] };
        piece.rotation_deg = normalizeAngleDeg(num(piece.rotation_deg) + delta);
        rederiveOutline(piece);
    }

    function previewPieceRotation(session, pieceKey, rotationDeg) {
        const next = JSON.parse(JSON.stringify(session));
        const piece = next.pieces[pieceKey];
        if (!piece) throw new Error(pieceKey);
        ensureBaseGeometry(piece);
        const target = normalizeAngleDeg(rotationDeg);
        const current = normalizeAngleDeg(piece.rotation_deg);
        let rawDelta = target - current;
        if (rawDelta > 180) rawDelta -= 360;
        else if (rawDelta <= -180) rawDelta += 360;
        const hostPivot = { x: num(piece.pivot_mm.x), y: num(piece.pivot_mm.y) };
        applyAngleToPiece(piece, target);
        descendantGuestKeys(next, pieceKey).forEach((guestKey) => {
            rigidRotatePieceAbout(next.pieces[guestKey], hostPivot, rawDelta);
        });
        return next;
    }

    function guestRemainsInHost(guest, host) {
        const MoveGeometry = window.AlmdinaBoardEditor.MoveGeometry;
        const hole = host.glass_hole_local_mm;
        const guestFp = footprintOf(guest);
        if (Array.isArray(hole) && hole.length >= 3) {
            const xs = hole.map((point) => num(point[0]));
            const ys = hole.map((point) => num(point[1]));
            const holeRect = {
                x: Math.min(...xs),
                y: Math.min(...ys),
                w: Math.max(...xs) - Math.min(...xs),
                h: Math.max(...ys) - Math.min(...ys),
            };
            return MoveGeometry
                ? (function contained(inner, outer) {
                    return (
                        inner.x >= outer.x - 1e-6
                        && inner.y >= outer.y - 1e-6
                        && inner.x + inner.w <= outer.x + outer.w + 1e-6
                        && inner.y + inner.h <= outer.y + outer.h + 1e-6
                    );
                }(guestFp.bounds, holeRect))
                : false;
        }
        return Number(guest.sheet_no) === Number(host.sheet_no);
    }

    function segmentsIntersect(a1, a2, b1, b2) {
        function cross(o, a, b) {
            return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0]);
        }
        const d1 = cross(a1, a2, b1);
        const d2 = cross(a1, a2, b2);
        const d3 = cross(b1, b2, a1);
        const d4 = cross(b1, b2, a2);
        if (((d1 > 0 && d2 < 0) || (d1 < 0 && d2 > 0))
            && ((d3 > 0 && d4 < 0) || (d3 < 0 && d4 > 0))) {
            return true;
        }
        return false;
    }

    function pointInPolygon(point, polygon) {
        let inside = false;
        for (let i = 0, j = polygon.length - 1; i < polygon.length; j = i, i += 1) {
            const xi = num(polygon[i][0]);
            const yi = num(polygon[i][1]);
            const xj = num(polygon[j][0]);
            const yj = num(polygon[j][1]);
            const intersect = ((yi > point[1]) !== (yj > point[1]))
                && (point[0] < ((xj - xi) * (point[1] - yi)) / (yj - yi + ANGLE_EPS) + xi);
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
                const b1 = b[j];
                const b2 = b[(j + 1) % b.length];
                if (segmentsIntersect(a1, a2, b1, b2)) return true;
            }
        }
        if (pointInPolygon(a[0], b) || pointInPolygon(b[0], a)) return true;
        return false;
    }

    function rectsHaveClearance(a, b, gap) {
        const g = Math.max(0, num(gap));
        return (
            a.x + a.w + g <= b.x
            || b.x + b.w + g <= a.x
            || a.y + a.h + g <= b.y
            || b.y + b.h + g <= a.y
        );
    }

    function pairConflict(a, b, kerfMm) {
        const MoveGeometry = window.AlmdinaBoardEditor && window.AlmdinaBoardEditor.MoveGeometry;
        if (MoveGeometry && typeof MoveGeometry.pairConflict === "function") {
            return MoveGeometry.pairConflict(a, b, kerfMm);
        }
        // Fallback mirrors MoveGeometry when the module order is incomplete in tests.
        const gap = Math.max(0, num(kerfMm));
        if (a.kind === "polygon" && b.kind === "polygon" && a.points && b.points) {
            if (polygonsOverlap(a.points, b.points)) return "piece_overlap";
            if (rectsHaveClearance(a.bounds, b.bounds, gap)) return null;
            return "kerf_clearance";
        }
        const ax2 = a.bounds.x + a.bounds.w;
        const ay2 = a.bounds.y + a.bounds.h;
        const bx2 = b.bounds.x + b.bounds.w;
        const by2 = b.bounds.y + b.bounds.h;
        if (!(ax2 <= b.bounds.x || bx2 <= a.bounds.x || ay2 <= b.bounds.y || by2 <= a.bounds.y)) {
            return "piece_overlap";
        }
        if (!rectsHaveClearance(a.bounds, b.bounds, gap)) return "kerf_clearance";
        return null;
    }

    function footprintInsideUsable(localFootprint, board) {
        const usable = {
            x: 0,
            y: 0,
            w: num(board.usable_width_mm) || num(board.width_mm),
            h: num(board.usable_length_mm) || num(board.height_mm),
        };
        if (localFootprint.kind === "polygon" && Array.isArray(localFootprint.points)) {
            return localFootprint.points.every((point) => (
                point[0] >= usable.x - 1e-6
                && point[1] >= usable.y - 1e-6
                && point[0] <= usable.x + usable.w + 1e-6
                && point[1] <= usable.y + usable.h + 1e-6
            ));
        }
        const b = localFootprint.bounds;
        return (
            b.x >= usable.x - 1e-6
            && b.y >= usable.y - 1e-6
            && b.x + b.w <= usable.x + usable.w + 1e-6
            && b.y + b.h <= usable.y + usable.h + 1e-6
        );
    }

    function validatePieceRotation(session, pieceKey, rotationDeg) {
        const MoveGeometry = window.AlmdinaBoardEditor.MoveGeometry;
        const piece = session.pieces && session.pieces[pieceKey];
        if (!piece) return { ok: false, code: ROTATE_BLOCK_NOT_EDITABLE };
        const eligibility = pieceRotationEligibility(session, pieceKey);
        if (!eligibility.rotatable) {
            return {
                ok: false,
                code: eligibility.reason || ROTATE_BLOCK_NOT_ALLOWED,
                blocking_guest_key: eligibility.blocking_guest_key,
            };
        }
        const target = normalizeAngleDeg(rotationDeg);
        if (anglesEquivalent(target, piece.rotation_deg)) {
            return {
                ok: true,
                code: "ok",
                noop: true,
                rotation_deg: target,
                affected_keys: eligibility.affected_keys,
            };
        }
        const trial = previewPieceRotation(session, pieceKey, target);
        const affected = new Set(eligibility.affected_keys || [pieceKey]);
        descendantGuestKeys(session, pieceKey).forEach((key) => affected.add(key));
        const kerfMm = num(session.kerf_mm);

        for (const key of affected) {
            const moved = trial.pieces[key];
            const localFp = footprintOf(moved);
            if (moved.sheet_no != null && moved.sheet_no !== "") {
                const board = session.boards[String(moved.sheet_no)] || {};
                if (!footprintInsideUsable(localFp, board)) {
                    return { ok: false, code: "partial_board_overlap", piece_key: key };
                }
            }
            if (key === pieceKey && moved.glass_host_key && trial.pieces[moved.glass_host_key]) {
                if (!guestRemainsInHost(moved, trial.pieces[moved.glass_host_key])) {
                    return { ok: false, code: ROTATE_BLOCK_HOSTING };
                }
            }
        }

        for (const key of affected) {
            const moved = trial.pieces[key];
            if (moved.sheet_no == null || moved.sheet_no === "") continue;
            const movedLocal = footprintOf(moved);
            for (const otherKey of Object.keys(trial.pieces)) {
                if (affected.has(otherKey)) continue;
                const other = trial.pieces[otherKey];
                if (Number(other.sheet_no) !== Number(moved.sheet_no)) continue;
                if (other.glass_host_key === key || moved.glass_host_key === otherKey) continue;
                if (affected.has(other.glass_host_key)) continue;
                const conflict = pairConflict(movedLocal, footprintOf(other), kerfMm);
                if (conflict) return { ok: false, code: conflict, piece_key: key };
            }
        }
        return {
            ok: true,
            code: "ok",
            noop: false,
            rotation_deg: target,
            affected_keys: Array.from(affected),
            trial,
        };
    }

    function applyPieceRotation(session, pieceKey, rotationDeg) {
        const decision = validatePieceRotation(session, pieceKey, rotationDeg);
        if (!decision.ok) return session;
        if (decision.noop) return JSON.parse(JSON.stringify(session));
        const next = decision.trial || previewPieceRotation(session, pieceKey, decision.rotation_deg);
        const sheetNo = next.pieces[pieceKey] && next.pieces[pieceKey].sheet_no;
        if (sheetNo != null && sheetNo !== "") {
            const key = String(sheetNo);
            if (!next.stale_cut_path_sheets.includes(key)) next.stale_cut_path_sheets.push(key);
            if (!next.stale_unbound_text_sheets.includes(key)) next.stale_unbound_text_sheets.push(key);
        }
        return next;
    }

    function angleFromPointer(pivotWorld, worldX, worldY) {
        const dx = num(worldX) - num(pivotWorld.x);
        const dy = num(worldY) - num(pivotWorld.y);
        // atan2 with Y-down: convert to SVG-clockwise degrees from +X.
        let deg = (Math.atan2(dy, dx) * 180) / Math.PI;
        return normalizeAngleDeg(deg);
    }

    function reasonMessage(code) {
        const MoveGeometry = window.AlmdinaBoardEditor.MoveGeometry;
        const map = {
            [ROTATE_BLOCK_NOT_ALLOWED]: "Rotation is not allowed for this piece.",
            [ROTATE_BLOCK_GUEST_FORBIDDEN]: "A nested piece does not allow rotation.",
            [ROTATE_BLOCK_SPECIAL]: "Special geometry unavailable — not rotatable.",
            [ROTATE_BLOCK_INCOMPLETE]: "Incomplete geometry — not rotatable.",
            [ROTATE_BLOCK_NOT_EDITABLE]: "This piece cannot be edited.",
            [ROTATE_BLOCK_HOSTING]: "Guest must remain inside the host opening.",
            multi_selection: "Select one piece to set its rotation angle. Group rotation is not available.",
            no_selection: "Select a piece to set its rotation angle.",
            partial_board_overlap: "Piece would leave the usable board area.",
            outside_usable_sheet: "Piece would leave the usable board area.",
            piece_overlap: "Pieces would overlap.",
            kerf_clearance: "Kerf clearance is insufficient.",
        };
        if (map[code]) return map[code];
        return MoveGeometry && MoveGeometry.reasonMessage
            ? MoveGeometry.reasonMessage(code)
            : (code || "Rotation rejected.");
    }

    function selectionFrame(piece) {
        ensureBaseGeometry(piece);
        const fp = footprintOf(piece);
        return {
            bounds: fp.bounds,
            points: fp.points,
            pivot: { x: num(piece.pivot_mm.x), y: num(piece.pivot_mm.y) },
            rotation_deg: normalizeAngleDeg(piece.rotation_deg),
        };
    }

    function handleWorldPosition(piece, boards, handleOffsetMm) {
        const MoveGeometry = window.AlmdinaBoardEditor.MoveGeometry;
        ensureBaseGeometry(piece);
        const world = MoveGeometry.worldFootprint(piece, boards);
        const pivotLocal = piece.pivot_mm;
        const board = piece.sheet_no != null ? boards[String(piece.sheet_no)] || {} : {};
        const ox = num(board.origin_x_mm) + num(board.trim_x_mm);
        const oy = num(board.origin_y_mm) + num(board.trim_y_mm);
        const pivotWorld = {
            x: (piece.sheet_no == null || piece.sheet_no === "" ? 0 : ox) + num(pivotLocal.x),
            y: (piece.sheet_no == null || piece.sheet_no === "" ? 0 : oy) + num(pivotLocal.y),
        };
        const angle = normalizeAngleDeg(piece.rotation_deg);
        const offset = Math.max(24, num(handleOffsetMm) || 28);
        // Handle sits above the unrotated top centre, then rotated with the piece.
        const topLocal = [
            num(pivotLocal.x),
            world.bounds.y - (piece.sheet_no == null || piece.sheet_no === "" ? 0 : oy) - offset,
        ];
        // Prefer offset along the "up" direction of the piece from pivot using AABB top.
        const localFp = footprintOf(piece);
        const handleLocal = rotatePoint(
            [num(localFp.bounds.x) + num(localFp.bounds.w) * 0.5, num(localFp.bounds.y) - offset],
            pivotLocal,
            0
        );
        // Place handle outside current AABB along the axis from pivot through top mid of AABB.
        const topMid = [
            localFp.bounds.x + localFp.bounds.w * 0.5,
            localFp.bounds.y,
        ];
        const vx = topMid[0] - pivotLocal.x;
        const vy = topMid[1] - pivotLocal.y;
        const len = Math.hypot(vx, vy) || 1;
        const hx = pivotLocal.x + (vx / len) * (len + offset);
        const hy = pivotLocal.y + (vy / len) * (len + offset);
        return {
            pivotWorld,
            handleWorld: {
                x: (piece.sheet_no == null || piece.sheet_no === "" ? 0 : ox) + hx,
                y: (piece.sheet_no == null || piece.sheet_no === "" ? 0 : oy) + hy,
            },
            angle,
        };
    }

    window.AlmdinaBoardEditor = window.AlmdinaBoardEditor || {};
    window.AlmdinaBoardEditor.RotationGeometry = Object.freeze({
        ROTATE_BLOCK_NOT_ALLOWED,
        ROTATE_BLOCK_GUEST_FORBIDDEN,
        ROTATE_BLOCK_SPECIAL,
        ROTATE_BLOCK_INCOMPLETE,
        ROTATE_BLOCK_NOT_EDITABLE,
        ROTATE_BLOCK_HOSTING,
        normalizeAngleDeg,
        anglesEquivalent,
        rotatePoint,
        rotatePoints,
        aabbCenter,
        ensureBaseGeometry,
        rederiveOutline,
        explicitAllowRotation,
        pieceRotationEligibility,
        previewPieceRotation,
        validatePieceRotation,
        applyPieceRotation,
        angleFromPointer,
        reasonMessage,
        selectionFrame,
        handleWorldPosition,
        descendantGuestKeys,
    });
})();
