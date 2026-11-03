(() => {
    "use strict";

    const EDGES = Object.freeze(["left", "top", "right", "bottom"]);
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

    function boardInsetsForPiece(session, pieceKeyOrInstance) {
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

        const trimX = num(board.trim_x_mm);
        const trimY = num(board.trim_y_mm);
        const widthMm = Math.max(1, num(board.width_mm) || (num(board.usable_width_mm) + 2 * trimX));
        const heightMm = Math.max(1, num(board.height_mm) || (num(board.usable_length_mm) + 2 * trimY));
        const minX = num(bounds.x);
        const minY = num(bounds.y);
        const maxX = minX + num(bounds.w);
        const maxY = minY + num(bounds.h);
        const dims = pieceDimensionsMm(piece);

        return {
            pieceKey,
            sheetNo: Number(piece.sheet_no),
            label: piece.label || piece.piece_instance_id || String(piece.piece_id || ""),
            editable: Boolean(piece.editable),
            widthMm: dims.widthMm,
            lengthMm: dims.lengthMm,
            left: trimX + minX,
            top: trimY + minY,
            right: widthMm - (trimX + maxX),
            bottom: heightMm - (trimY + maxY),
            boardWidthMm: widthMm,
            boardHeightMm: heightMm,
        };
    }

    function selectionPositionModel(session, selectedPieceKeys) {
        const keys = Array.isArray(selectedPieceKeys) ? selectedPieceKeys.filter(Boolean) : [];
        if (keys.length !== 1) return null;
        return boardInsetsForPiece(session, keys[0]);
    }

    function worldDeltaForEdge(current, edge, nextValue) {
        if (!current) {
            return { ok: false, code: "no_selection", dx: 0, dy: 0 };
        }
        const target = num(nextValue);
        if (!Number.isFinite(target)) {
            return { ok: false, code: "invalid_value", dx: 0, dy: 0 };
        }
        const name = String(edge || "").toLowerCase();
        let dx = 0;
        let dy = 0;
        if (name === "left") dx = target - num(current.left);
        else if (name === "right") dx = num(current.right) - target;
        else if (name === "top") dy = target - num(current.top);
        else if (name === "bottom") dy = num(current.bottom) - target;
        else return { ok: false, code: "invalid_edge", dx: 0, dy: 0 };

        if (Math.abs(dx) < 1e-9 && Math.abs(dy) < 1e-9) {
            return { ok: true, code: "unchanged", dx: 0, dy: 0, unchanged: true };
        }
        return { ok: true, code: "ok", dx, dy, unchanged: false };
    }

    function proposeEdgeMove(session, pieceKeyOrInstance, edge, nextValue) {
        const MoveGeometry = window.AlmdinaBoardEditor && window.AlmdinaBoardEditor.MoveGeometry;
        if (!MoveGeometry) {
            return { ok: false, code: "missing_geometry", reason: "Move geometry unavailable." };
        }
        const current = boardInsetsForPiece(session, pieceKeyOrInstance);
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
        const delta = worldDeltaForEdge(current, edge, nextValue);
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
        const proposal = MoveGeometry.proposeGroupMove(session, [current.pieceKey], delta.dx, delta.dy);
        if (!proposal.ok) {
            return {
                ok: false,
                code: proposal.code,
                reason: proposal.reason || "Drop rejected.",
                current,
                dx: delta.dx,
                dy: delta.dy,
            };
        }
        return {
            ok: true,
            unchanged: false,
            current,
            dx: delta.dx,
            dy: delta.dy,
            commands: proposal.commands || [],
        };
    }

    window.AlmdinaBoardEditor = window.AlmdinaBoardEditor || {};
    window.AlmdinaBoardEditor.PositionGeometry = Object.freeze({
        EDGES,
        STEP_MM,
        formatMm,
        parseMm,
        pieceDimensionsMm,
        boardInsetsForPiece,
        selectionPositionModel,
        worldDeltaForEdge,
        proposeEdgeMove,
    });
})();
