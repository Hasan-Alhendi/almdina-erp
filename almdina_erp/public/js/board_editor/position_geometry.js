(() => {
    "use strict";

    const AXES = Object.freeze(["x", "y"]);
    const STEP_MM = 1;

    function num(value) {
        const n = Number(value);
        return Number.isFinite(n) ? n : 0;
    }

    function formatMm(value) {
        const n = num(value);
        if (!Number.isFinite(n)) return "0";
        const rounded = Math.round(n * 1000) / 1000;
        if (Object.is(rounded, -0)) return "0";
        let text = String(rounded);
        if (text.indexOf(".") >= 0) {
            text = text.replace(/\.?0+$/, "");
        }
        return text || "0";
    }

    function parseMm(text) {
        if (text == null) return null;
        const raw = String(text).trim().replace(",", ".");
        if (!raw.length) return null;
        if (!/^[+-]?(?:\d+(?:\.\d*)?|\.\d+)$/.test(raw)) return null;
        const n = Number(raw);
        if (!Number.isFinite(n)) return null;
        return n;
    }

    function pieceDimensionsMm(piece) {
        const placement = (piece && piece.placement_cm) || {};
        return {
            widthMm: Math.max(0, num(placement.w) * 10),
            lengthMm: Math.max(0, num(placement.h) * 10),
        };
    }

    function boardPositionForPiece(session, pieceKeyOrInstance) {
        // X/Y are editor UI coords in usable-sheet millimetres:
        //   (0,0) = top-left of usable area (after trim)
        //   X+ right, Y+ down
        // Values are the AABB min corner after rotation/mirror (outline_mm).
        const MoveGeometry = window.AlmdinaBoardEditor && window.AlmdinaBoardEditor.MoveGeometry;
        if (!MoveGeometry || !session || !session.pieces) return null;
        const pieceKey = MoveGeometry.resolvePieceKey(session, pieceKeyOrInstance);
        const piece = pieceKey && session.pieces[pieceKey];
        if (!piece || piece.distribution === "excluded") return null;
        if (piece.sheet_no == null || piece.sheet_no === "") return null;
        const board = session.boards && session.boards[String(piece.sheet_no)];
        if (!board) return null;

        const local = MoveGeometry.footprint(piece);
        const bounds = local && local.bounds;
        if (!bounds) return null;

        const dims = pieceDimensionsMm(piece);
        return {
            pieceKey,
            sheetNo: Number(piece.sheet_no),
            label: piece.label || piece.piece_instance_id || String(piece.piece_id || ""),
            editable: Boolean(piece.editable),
            widthMm: dims.widthMm,
            lengthMm: dims.lengthMm,
            x: num(bounds.x),
            y: num(bounds.y),
        };
    }

    function selectionPositionModel(session, selectedPieceKeys) {
        const keys = Array.isArray(selectedPieceKeys) ? selectedPieceKeys.filter(Boolean) : [];
        if (keys.length !== 1) return null;
        return boardPositionForPiece(session, keys[0]);
    }

    function worldDeltaForAxis(current, axis, nextValue) {
        if (!current) {
            return { ok: false, code: "no_selection", dx: 0, dy: 0 };
        }
        const target = num(nextValue);
        if (!Number.isFinite(target)) {
            return { ok: false, code: "invalid_value", dx: 0, dy: 0 };
        }
        const name = String(axis || "").toLowerCase();
        let dx = 0;
        let dy = 0;
        if (name === "x") dx = target - num(current.x);
        else if (name === "y") dy = target - num(current.y);
        else return { ok: false, code: "invalid_axis", dx: 0, dy: 0 };

        if (Math.abs(dx) < 1e-9 && Math.abs(dy) < 1e-9) {
            return { ok: true, code: "unchanged", dx: 0, dy: 0, unchanged: true };
        }
        return { ok: true, code: "ok", dx, dy, unchanged: false };
    }

    function proposeDeltaMove(session, pieceKeyOrInstance, dx, dy) {
        // Exact millimetre delta through MoveGeometry — no magnet/snap.
        const MoveGeometry = window.AlmdinaBoardEditor && window.AlmdinaBoardEditor.MoveGeometry;
        if (!MoveGeometry) {
            return { ok: false, code: "missing_geometry", reason: "Move geometry unavailable." };
        }
        const current = boardPositionForPiece(session, pieceKeyOrInstance);
        if (!current) {
            return { ok: false, code: "no_board_piece", reason: "Select one piece on a board." };
        }
        if (!current.editable) {
            return {
                ok: false,
                code: MoveGeometry.DROP_NOT_EDITABLE,
                reason: MoveGeometry.reasonMessage(MoveGeometry.DROP_NOT_EDITABLE),
            };
        }
        const shiftX = num(dx);
        const shiftY = num(dy);
        if (!(Math.abs(shiftX) > 1e-9 || Math.abs(shiftY) > 1e-9)) {
            return { ok: true, unchanged: true, current, commands: [], dx: 0, dy: 0 };
        }
        const proposal = MoveGeometry.proposeGroupMove(session, [current.pieceKey], shiftX, shiftY);
        if (!proposal.ok) {
            return {
                ok: false,
                code: proposal.code,
                reason: proposal.reason || "Drop rejected.",
                current,
                dx: shiftX,
                dy: shiftY,
            };
        }
        return {
            ok: true,
            unchanged: false,
            current,
            dx: shiftX,
            dy: shiftY,
            commands: proposal.commands || [],
        };
    }

    function proposeAxisMove(session, pieceKeyOrInstance, axis, nextValue) {
        const current = boardPositionForPiece(session, pieceKeyOrInstance);
        if (!current) {
            return { ok: false, code: "no_board_piece", reason: "Select one piece on a board." };
        }
        const delta = worldDeltaForAxis(current, axis, nextValue);
        if (!delta.ok) {
            return {
                ok: false,
                code: delta.code,
                reason: delta.code === "invalid_value"
                    ? "Enter a valid millimetre value."
                    : "Position update rejected.",
            };
        }
        if (delta.unchanged) {
            return { ok: true, unchanged: true, current, commands: [], dx: 0, dy: 0 };
        }
        return proposeDeltaMove(session, current.pieceKey, delta.dx, delta.dy);
    }

    function proposeKeyboardNudge(session, pieceKeyOrInstance, key) {
        const code = String(key || "");
        let dx = 0;
        let dy = 0;
        if (code === "ArrowRight") dx = STEP_MM;
        else if (code === "ArrowLeft") dx = -STEP_MM;
        else if (code === "ArrowDown") dy = STEP_MM;
        else if (code === "ArrowUp") dy = -STEP_MM;
        else return { ok: false, code: "invalid_key", reason: "Position update rejected." };
        return proposeDeltaMove(session, pieceKeyOrInstance, dx, dy);
    }

    window.AlmdinaBoardEditor = window.AlmdinaBoardEditor || {};
    window.AlmdinaBoardEditor.PositionGeometry = Object.freeze({
        AXES,
        STEP_MM,
        formatMm,
        parseMm,
        pieceDimensionsMm,
        boardPositionForPiece,
        // Alias kept for callers/tests that still name the helper generically.
        boardInsetsForPiece: boardPositionForPiece,
        selectionPositionModel,
        worldDeltaForAxis,
        proposeAxisMove,
        proposeDeltaMove,
        proposeKeyboardNudge,
    });
})();
