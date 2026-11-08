(() => {
    "use strict";

    const REASON_REMOVED = "removed_from_distribution";
    const REASON_WITH_HOST = "removed_with_host";

    function clone(value) {
        return JSON.parse(JSON.stringify(value));
    }

    function isExcluded(piece) {
        return Boolean(piece && piece.distribution === "excluded");
    }

    function keyboardDeleteApplies(target) {
        if (!target || !target.tagName) return true;
        const tag = String(target.tagName).toLowerCase();
        if (tag === "input" || tag === "textarea" || tag === "select") return false;
        return !target.isContentEditable;
    }

    function markStale(session, sheetNo) {
        if (sheetNo == null || sheetNo === "") return;
        const key = String(sheetNo);
        if (!Array.isArray(session.stale_cut_path_sheets)) session.stale_cut_path_sheets = [];
        if (!Array.isArray(session.stale_unbound_text_sheets)) session.stale_unbound_text_sheets = [];
        if (!session.stale_cut_path_sheets.includes(key)) session.stale_cut_path_sheets.push(key);
        if (!session.stale_unbound_text_sheets.includes(key)) session.stale_unbound_text_sheets.push(key);
    }

    function descendantKeys(pieces, hostKey) {
        const ordered = [];
        const stack = Object.keys(pieces).filter((key) => pieces[key].glass_host_key === hostKey);
        const seen = new Set();
        while (stack.length) {
            const key = stack.shift();
            if (seen.has(key)) continue;
            seen.add(key);
            ordered.push(key);
            Object.keys(pieces).forEach((childKey) => {
                if (pieces[childKey].glass_host_key === key) stack.push(childKey);
            });
        }
        return ordered;
    }

    function releaseToWorld(piece, boards) {
        const MoveGeometry = window.AlmdinaBoardEditor.MoveGeometry;
        const fromSheet = piece.sheet_no;
        if (fromSheet == null || fromSheet === "") {
            piece.sheet_no = null;
            return;
        }
        MoveGeometry.reframePieceGeometry(piece, boards, fromSheet, null, 0, 0);
        const bounds = MoveGeometry.footprint(piece).bounds;
        piece.sheet_no = null;
        piece.local_x_mm = bounds.x;
        piece.local_y_mm = bounds.y;
    }

    function sameSheet(left, right) {
        const a = left == null || left === "" ? null : Number(left);
        const b = right == null || right === "" ? null : Number(right);
        return a === b;
    }

    function excludePiece(session, pieceKey) {
        const MoveGeometry = window.AlmdinaBoardEditor.MoveGeometry;
        if (!session || !session.pieces) return { ok: false, code: "missing" };
        const key = MoveGeometry.resolvePieceKey(session, pieceKey);
        const piece = key && session.pieces[key];
        if (!piece || !piece.editable) return { ok: false, code: "not_editable" };
        if (isExcluded(piece)) return { ok: false, code: "noop" };
        const next = clone(session);
        const target = next.pieces[key];
        const host = target.glass_host_key ? next.pieces[target.glass_host_key] : null;
        let keys;
        if (host && !isExcluded(host)) {
            target.glass_host_key = null;
            target.glass_host_piece_id = null;
            target.exclusion_reason = REASON_REMOVED;
            keys = [key];
        } else {
            keys = [key].concat(descendantKeys(next.pieces, key));
            target.exclusion_reason = REASON_REMOVED;
            keys.slice(1).forEach((guestKey) => {
                next.pieces[guestKey].exclusion_reason = REASON_WITH_HOST;
            });
        }
        keys.forEach((itemKey) => {
            const row = next.pieces[itemKey];
            markStale(next, row.sheet_no);
            row.distribution = "excluded";
        });
        return { ok: true, session: next, piece_keys: keys };
    }

    function returnPieceToStaging(session, pieceKey) {
        const MoveGeometry = window.AlmdinaBoardEditor.MoveGeometry;
        if (!session || !session.pieces) return { ok: false, code: "missing" };
        const key = MoveGeometry.resolvePieceKey(session, pieceKey);
        const piece = key && session.pieces[key];
        if (!piece || !isExcluded(piece)) return { ok: false, code: "noop" };
        const next = clone(session);
        const row = next.pieces[key];
        const fromSheet = row.sheet_no;
        releaseToWorld(row, next.boards);
        row.distribution = "active";
        row.exclusion_reason = null;
        const host = row.glass_host_key ? next.pieces[row.glass_host_key] : null;
        if (!host || isExcluded(host) || !sameSheet(host.sheet_no, row.sheet_no)) {
            row.glass_host_key = null;
            row.glass_host_piece_id = null;
        }
        markStale(next, fromSheet);
        return { ok: true, session: next, piece_key: key };
    }

    function removeBoard(session, sheetNo) {
        if (sheetNo == null || sheetNo === "") return { ok: false, code: "missing" };
        const boardKey = String(sheetNo);
        if (!session || !session.boards || !session.boards[boardKey]) return { ok: false, code: "noop" };
        const next = clone(session);
        const onBoard = Object.keys(next.pieces).filter((key) => String(next.pieces[key].sheet_no) === boardKey);
        const moving = onBoard.filter((key) => !isExcluded(next.pieces[key]));
        const movingSet = new Set(moving);
        onBoard.forEach((key) => {
            const piece = next.pieces[key];
            releaseToWorld(piece, next.boards);
            if (isExcluded(piece)) return;
            const hostKey = piece.glass_host_key;
            if (hostKey && !movingSet.has(hostKey)) {
                piece.glass_host_key = null;
                piece.glass_host_piece_id = null;
            }
        });
        markStale(next, sheetNo);
        delete next.boards[boardKey];
        return { ok: true, session: next, piece_keys: moving, sheet_no: Number(sheetNo) };
    }

    window.AlmdinaBoardEditor = window.AlmdinaBoardEditor || {};
    window.AlmdinaBoardEditor.Distribution = Object.freeze({
        REASON_REMOVED,
        REASON_WITH_HOST,
        isExcluded,
        keyboardDeleteApplies,
        excludePiece,
        returnPieceToStaging,
        removeBoard,
    });
})();
