(() => {
    "use strict";

    // Interactive mirror of domain/cutting/board_editor_transform.py.

    const TRANSFORM_BLOCK_MIRROR = "angle_mirror_unavailable";
    const TRANSFORM_BLOCK_UNPROVEN = "transform_geometry_unproven";
    const TRANSFORM_BLOCK_HOSTING = "host_guest_transform_unproven";
    const CORNER_TYPES = new Set(["Clipped Corner", "L-Shaped Corner"]);

    function rotationApi() {
        return window.AlmdinaBoardEditor && window.AlmdinaBoardEditor.RotationGeometry;
    }

    function truthy(value) {
        return value === true || value === 1 || value === "1";
    }

    function isCornerCut(pieceType) {
        return CORNER_TYPES.has(String(pieceType || ""));
    }

    function reflectHorizontal(points, centerX) {
        if (!Array.isArray(points)) return points;
        return points.map((point) => [(2 * centerX) - Number(point[0] || 0), Number(point[1] || 0)]);
    }

    function reflectVertical(points, centerY) {
        if (!Array.isArray(points)) return points;
        return points.map((point) => [Number(point[0] || 0), (2 * centerY) - Number(point[1] || 0)]);
    }

    function reflectMachiningPaths(piece, axis) {
        if (!Array.isArray(piece.machining_paths)) return;
        const centerX = Number((piece.pivot_mm && piece.pivot_mm.x) || 0);
        const centerY = Number((piece.pivot_mm && piece.pivot_mm.y) || 0);
        piece.machining_paths = piece.machining_paths.map((item) => {
            if (!item || typeof item !== "object") return item;
            const path = axis === "v"
                ? reflectVertical(item.path_mm, centerY)
                : reflectHorizontal(item.path_mm, centerX);
            return { ...item, path_mm: path || [] };
        });
    }

    function applyLocalHorizontalMirror(piece) {
        const RG = rotationApi();
        RG.ensureBaseGeometry(piece);
        const centerX = Number(piece.pivot_mm.x || 0);
        piece.base_outline_mm = reflectHorizontal(piece.base_outline_mm, centerX);
        if (Array.isArray(piece.base_hole_mm)) {
            piece.base_hole_mm = reflectHorizontal(piece.base_hole_mm, centerX);
        }
        reflectMachiningPaths(piece, "h");
        piece.mirrored = !truthy(piece.mirrored);
        RG.rederiveOutline(piece);
    }

    function applyLocalFlipH(piece) {
        const RG = rotationApi();
        RG.ensureBaseGeometry(piece);
        const centerX = Number(piece.pivot_mm.x || 0);
        piece.base_outline_mm = reflectHorizontal(piece.base_outline_mm, centerX);
        if (Array.isArray(piece.base_hole_mm)) {
            piece.base_hole_mm = reflectHorizontal(piece.base_hole_mm, centerX);
        }
        reflectMachiningPaths(piece, "h");
        piece.flip_h = !truthy(piece.flip_h);
        RG.rederiveOutline(piece);
    }

    function applyLocalFlipV(piece) {
        const RG = rotationApi();
        RG.ensureBaseGeometry(piece);
        const centerY = Number(piece.pivot_mm.y || 0);
        piece.base_outline_mm = reflectVertical(piece.base_outline_mm, centerY);
        if (Array.isArray(piece.base_hole_mm)) {
            piece.base_hole_mm = reflectVertical(piece.base_hole_mm, centerY);
        }
        reflectMachiningPaths(piece, "v");
        piece.flip_v = !truthy(piece.flip_v);
        RG.rederiveOutline(piece);
    }

    function applyBoardAxisFlipH(piece) {
        const RG = rotationApi();
        applyLocalFlipH(piece);
        piece.rotation_deg = RG.normalizeAngleDeg(-Number(piece.rotation_deg || 0));
        RG.rederiveOutline(piece);
    }

    function applyBoardAxisFlipV(piece) {
        const RG = rotationApi();
        applyLocalFlipV(piece);
        piece.rotation_deg = RG.normalizeAngleDeg(-Number(piece.rotation_deg || 0));
        RG.rederiveOutline(piece);
    }

    function moveApi() {
        return window.AlmdinaBoardEditor && window.AlmdinaBoardEditor.MoveGeometry;
    }

    function boardFlipEligibility(session, pieceKey) {
        const RG = rotationApi();
        const piece = session.pieces && session.pieces[pieceKey];
        if (!piece) {
            return { allowed: false, reason: "not_editable", affected_keys: [] };
        }
        const eligibility = RG.pieceRotationEligibility(session, pieceKey);
        if (!eligibility.rotatable) {
            return {
                allowed: false,
                reason: eligibility.reason || "rotation_not_allowed",
                affected_keys: eligibility.affected_keys || [],
            };
        }
        if (piece.glass_host_key || (RG.descendantGuestKeys(session, pieceKey) || []).length) {
            return {
                allowed: false,
                reason: TRANSFORM_BLOCK_HOSTING,
                affected_keys: eligibility.affected_keys || [],
            };
        }
        return { allowed: true, reason: null, affected_keys: [pieceKey] };
    }

    function angleMirrorElig(session, pieceKey) {
        const RG = rotationApi();
        const piece = session.pieces && session.pieces[pieceKey];
        if (!piece) {
            return { allowed: false, reason: "not_editable" };
        }
        const eligibility = RG.pieceRotationEligibility(session, pieceKey);
        if (!eligibility.rotatable) {
            return { allowed: false, reason: eligibility.reason || "rotation_not_allowed" };
        }
        if (!isCornerCut(piece.piece_type)) {
            return { allowed: false, reason: TRANSFORM_BLOCK_MIRROR };
        }
        if (piece.glass_host_key || (RG.descendantGuestKeys(session, pieceKey) || []).length) {
            return { allowed: false, reason: TRANSFORM_BLOCK_HOSTING };
        }
        return { allowed: true, reason: null };
    }

    function previewBoardFlip(session, pieceKey, axis) {
        const next = JSON.parse(JSON.stringify(session));
        const piece = next.pieces[pieceKey];
        if (axis === "v") applyBoardAxisFlipV(piece);
        else applyBoardAxisFlipH(piece);
        return next;
    }

    function previewAngleMirror(session, pieceKey) {
        const next = JSON.parse(JSON.stringify(session));
        applyLocalHorizontalMirror(next.pieces[pieceKey]);
        return next;
    }

    function footprintInsideUsable(localFootprint, board) {
        const usable = {
            x: 0,
            y: 0,
            w: Number(board.usable_width_mm) || Number(board.width_mm) || 0,
            h: Number(board.usable_length_mm) || Number(board.height_mm) || 0,
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

    function validateTrialPose(session, trial, pieceKey, affectedKeys) {
        const MG = moveApi();
        const RG = rotationApi();
        if (!MG || typeof MG.footprint !== "function") {
            return { ok: false, code: TRANSFORM_BLOCK_UNPROVEN, message: TRANSFORM_BLOCK_UNPROVEN };
        }
        const trialPieces = trial.pieces || {};
        const boards = session.boards || {};
        const kerfMm = Number(session.kerf_mm) || 0;
        const machine = String(session.machine_type || "").trim();
        const affected = new Set(affectedKeys && affectedKeys.length ? affectedKeys : [pieceKey]);

        for (const key of affected) {
            const moved = trialPieces[key];
            if (!moved) {
                return { ok: false, code: "not_editable", message: "missing_piece" };
            }
            if (machine && RG && typeof RG.machineAcceptsRotation === "function"
                && !RG.machineAcceptsRotation(machine, moved.rotation_deg)) {
                return {
                    ok: false,
                    code: "machine_rotation_forbidden",
                    message: "machine_rotation_forbidden",
                    piece_key: key,
                };
            }
            if (machine === "Panel Saw") {
                const target = RG.normalizeAngleDeg(moved.rotation_deg);
                const allowed = [0, 90, 180, 270].some((angle) => RG.anglesEquivalent(target, angle));
                if (!allowed) {
                    return {
                        ok: false,
                        code: "machine_rotation_forbidden",
                        message: "machine_rotation_forbidden",
                        piece_key: key,
                    };
                }
            }
            if (moved.sheet_no != null && moved.sheet_no !== "") {
                const board = boards[String(moved.sheet_no)] || {};
                if (!footprintInsideUsable(MG.footprint(moved), board)) {
                    return {
                        ok: false,
                        code: "partial_board_overlap",
                        message: "partial_board_overlap",
                        piece_key: key,
                    };
                }
            }
        }

        for (const key of affected) {
            const moved = trialPieces[key];
            if (moved.sheet_no == null || moved.sheet_no === "") continue;
            const movedLocal = MG.footprint(moved);
            for (const otherKey of Object.keys(trialPieces)) {
                if (affected.has(otherKey)) continue;
                const other = trialPieces[otherKey];
                if (Number(other.sheet_no) !== Number(moved.sheet_no)) continue;
                if (other.glass_host_key === key || moved.glass_host_key === otherKey) continue;
                if (affected.has(other.glass_host_key)) continue;
                const otherLocal = MG.footprint(other);
                const a = movedLocal.bounds;
                const b = otherLocal.bounds;
                const overlaps = !(
                    a.x + a.w <= b.x
                    || b.x + b.w <= a.x
                    || a.y + a.h <= b.y
                    || b.y + b.h <= a.y
                );
                if (overlaps) {
                    return {
                        ok: false,
                        code: "piece_overlap",
                        message: "piece_overlap",
                        piece_key: key,
                    };
                }
                const gap = Math.max(0, kerfMm);
                const cleared = (
                    a.x + a.w + gap <= b.x
                    || b.x + b.w + gap <= a.x
                    || a.y + a.h + gap <= b.y
                    || b.y + b.h + gap <= a.y
                );
                if (!cleared) {
                    return {
                        ok: false,
                        code: "kerf_clearance",
                        message: "kerf_clearance",
                        piece_key: key,
                    };
                }
            }
        }
        return { ok: true, code: "ok" };
    }

    function validateBoardFlip(session, pieceKey, axis) {
        const eligibility = boardFlipEligibility(session, pieceKey);
        if (!eligibility.allowed) {
            return { ok: false, code: eligibility.reason, message: eligibility.reason };
        }
        const piece = session.pieces[pieceKey];
        if (!Array.isArray(piece.outline_mm) && !Array.isArray(piece.base_outline_mm)) {
            return { ok: false, code: TRANSFORM_BLOCK_UNPROVEN, message: TRANSFORM_BLOCK_UNPROVEN };
        }
        const trial = previewBoardFlip(session, pieceKey, axis);
        const pose = validateTrialPose(session, trial, pieceKey, eligibility.affected_keys);
        if (!pose.ok) return pose;
        return {
            ok: true,
            code: "ok",
            axis: axis === "v" ? "v" : "h",
            affected_keys: eligibility.affected_keys,
            trial,
        };
    }

    function validateAngleMirror(session, pieceKey) {
        const eligibility = angleMirrorElig(session, pieceKey);
        if (!eligibility.allowed) {
            return { ok: false, code: eligibility.reason, message: eligibility.reason };
        }
        const trial = previewAngleMirror(session, pieceKey);
        const pose = validateTrialPose(session, trial, pieceKey, [pieceKey]);
        if (!pose.ok) return pose;
        return {
            ok: true,
            code: "ok",
            affected_keys: [pieceKey],
            trial,
        };
    }

    function applyBoardFlip(session, pieceKey, axis) {
        const decision = validateBoardFlip(session, pieceKey, axis);
        if (!decision.ok) return { ok: false, session, code: decision.code, message: decision.message };
        const next = decision.trial;
        const sheetNo = next.pieces[pieceKey] && next.pieces[pieceKey].sheet_no;
        if (sheetNo != null && sheetNo !== "") {
            const key = String(sheetNo);
            next.stale_cut_path_sheets = Array.isArray(next.stale_cut_path_sheets)
                ? next.stale_cut_path_sheets.slice()
                : [];
            next.stale_unbound_text_sheets = Array.isArray(next.stale_unbound_text_sheets)
                ? next.stale_unbound_text_sheets.slice()
                : [];
            if (!next.stale_cut_path_sheets.includes(key)) next.stale_cut_path_sheets.push(key);
            if (!next.stale_unbound_text_sheets.includes(key)) next.stale_unbound_text_sheets.push(key);
        }
        return { ok: true, session: next, code: "ok" };
    }

    function applyAngleMirror(session, pieceKey) {
        const decision = validateAngleMirror(session, pieceKey);
        if (!decision.ok) return { ok: false, session, code: decision.code, message: decision.message };
        const next = decision.trial;
        const sheetNo = next.pieces[pieceKey] && next.pieces[pieceKey].sheet_no;
        if (sheetNo != null && sheetNo !== "") {
            const key = String(sheetNo);
            next.stale_cut_path_sheets = Array.isArray(next.stale_cut_path_sheets)
                ? next.stale_cut_path_sheets.slice()
                : [];
            next.stale_unbound_text_sheets = Array.isArray(next.stale_unbound_text_sheets)
                ? next.stale_unbound_text_sheets.slice()
                : [];
            if (!next.stale_cut_path_sheets.includes(key)) next.stale_cut_path_sheets.push(key);
            if (!next.stale_unbound_text_sheets.includes(key)) next.stale_unbound_text_sheets.push(key);
        }
        return { ok: true, session: next, code: "ok" };
    }

    function applyDraftParityToEntry(piece, row) {
        const RG = rotationApi();
        RG.ensureBaseGeometry(piece);
        piece.flip_h = false;
        piece.flip_v = false;
        piece.mirrored = false;
        if (truthy(row && row.mirrored)) applyLocalHorizontalMirror(piece);
        if (truthy(row && row.flip_h)) applyLocalFlipH(piece);
        if (truthy(row && row.flip_v)) applyLocalFlipV(piece);
        piece.flip_h = truthy(row && row.flip_h);
        piece.flip_v = truthy(row && row.flip_v);
        piece.mirrored = truthy(row && row.mirrored);
    }

    function reasonMessage(code) {
        const RG = rotationApi();
        const map = {
            [TRANSFORM_BLOCK_MIRROR]: "Angle mirror is only available for corner-break and L pieces.",
            [TRANSFORM_BLOCK_UNPROVEN]: "This piece cannot be flipped reliably with the available geometry.",
            [TRANSFORM_BLOCK_HOSTING]: "Host and guest pieces cannot use this transform yet.",
            multi_selection: "Select one piece to transform it.",
            no_selection: "Select a piece to transform it.",
            machine_rotation_forbidden: "This machine does not allow that rotation after the flip.",
        };
        if (map[code]) return map[code];
        return RG && RG.reasonMessage ? RG.reasonMessage(code) : (code || "Transform rejected.");
    }

    window.AlmdinaBoardEditor = window.AlmdinaBoardEditor || {};
    window.AlmdinaBoardEditor.TransformGeometry = Object.freeze({
        TRANSFORM_BLOCK_MIRROR,
        TRANSFORM_BLOCK_UNPROVEN,
        TRANSFORM_BLOCK_HOSTING,
        isCornerCut,
        boardFlipEligibility,
        angleMirrorEligibility: angleMirrorElig,
        applyBoardFlip,
        applyAngleMirror,
        applyDraftParityToEntry,
        reasonMessage,
    });
})();
