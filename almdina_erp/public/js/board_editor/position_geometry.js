(() => {
    "use strict";

    const AXES = Object.freeze(["x", "y"]);
    const STEP_MM = 1;
    const MIXED_LABEL = "Mixed";

    const CODE = Object.freeze({
        OK: "ok",
        MISSING_GEOMETRY: "missing_geometry",
        NO_BOARD_PIECE: "no_board_piece",
        NEED_GROUP: "need_group_selection",
        LOCKED: "locked_selection",
        MIXED_SCOPE: "mixed_scope",
        CROSS_SHEET: "cross_sheet",
        SHEET_CHANGED: "sheet_changed",
        DETACH_HOST: "detach_host",
        INVALID_VALUE: "invalid_value",
        INVALID_AXIS: "invalid_axis",
        INVALID_KEY: "invalid_key",
        UNCHANGED: "unchanged",
    });

    const REASON_LABELS = Object.freeze({
        [CODE.MISSING_GEOMETRY]: "Move geometry unavailable.",
        [CODE.NO_BOARD_PIECE]: "Select one piece on a board.",
        [CODE.NEED_GROUP]: "Select two or more pieces to move them together.",
        [CODE.LOCKED]: "Group positioning is unavailable while a locked piece is selected.",
        [CODE.MIXED_SCOPE]: "Precise group moves are available for pieces on the same board only, or pieces outside all boards.",
        [CODE.CROSS_SHEET]: "Precise group moves are available for pieces on the same board only, or pieces outside all boards.",
        [CODE.SHEET_CHANGED]: "Precise moves must keep each piece on its current board.",
        [CODE.DETACH_HOST]: "Group move would break a glass host relationship.",
        [CODE.INVALID_VALUE]: "Enter a valid millimetre offset.",
        [CODE.INVALID_AXIS]: "Position update rejected.",
        [CODE.INVALID_KEY]: "Position update rejected.",
        [CODE.UNCHANGED]: "Position is unchanged.",
    });

    function num(value) {
        const n = Number(value);
        return Number.isFinite(n) ? n : 0;
    }

    function reasonMessage(code) {
        return REASON_LABELS[code] || "Position update rejected.";
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

    function parseRelativeOffset(text) {
        // Multi-selection input is always a relative millimetre offset.
        // Bare numbers (e.g. "5") mean +5; signs are kept as typed.
        if (text == null) return null;
        const raw = String(text).trim();
        if (!raw.length) return null;
        if (raw.toLowerCase() === MIXED_LABEL.toLowerCase()) return null;
        return parseMm(raw);
    }

    function pieceDimensionsMm(piece) {
        const placement = (piece && piece.placement_cm) || {};
        return {
            widthMm: Math.max(0, num(placement.w) * 10),
            lengthMm: Math.max(0, num(placement.h) * 10),
        };
    }

    function sheetToken(piece) {
        if (!piece || piece.sheet_no == null || piece.sheet_no === "") return null;
        return Number(piece.sheet_no);
    }

    function sameSheetIdentity(beforePiece, targetSheetNo) {
        const before = sheetToken(beforePiece);
        const after = targetSheetNo == null || targetSheetNo === "" ? null : Number(targetSheetNo);
        if (before == null && after == null) return true;
        return before != null && after != null && Number(before) === Number(after);
    }

    function moveGeometry() {
        return window.AlmdinaBoardEditor && window.AlmdinaBoardEditor.MoveGeometry;
    }

    function alignmentGeometry() {
        return window.AlmdinaBoardEditor && window.AlmdinaBoardEditor.AlignmentGeometry;
    }

    function usableHeightMm(board) {
        if (!board) return 0;
        return num(board.usable_length_mm) || num(board.height_mm);
    }

    // Position UI only: convert internal usable-sheet AABB (Y+ down) to
    // bottom-left displayed Y (Y+ up). Does not mutate stored geometry.
    function internalYToDisplayedY(usableHeight, bounds) {
        const height = num(usableHeight);
        const top = num(bounds && bounds.y);
        const pieceH = num(bounds && bounds.h);
        return height - (top + pieceH);
    }

    function displayedYDeltaToInternal(currentDisplayedY, targetDisplayedY) {
        return num(currentDisplayedY) - num(targetDisplayedY);
    }

    function boardPositionForPiece(session, pieceKeyOrInstance) {
        // Position UI coords in usable-sheet millimetres (display only):
        //   (0,0) = bottom-left of usable area (after trim)
        //   X+ right, Y+ up
        // Values use the AABB after rotation/mirror (outline_mm footprint).
        // Internal MoveGeometry / SVG / session storage stay Y+ down.
        const MoveGeometry = moveGeometry();
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

        const usableH = usableHeightMm(board);
        const x = num(bounds.x);
        const y = internalYToDisplayedY(usableH, bounds);
        const dims = pieceDimensionsMm(piece);
        return {
            mixed: false,
            mode: "absolute",
            pieceKey,
            sheetNo: Number(piece.sheet_no),
            label: piece.label || piece.piece_instance_id || String(piece.piece_id || ""),
            editable: Boolean(piece.editable),
            widthMm: dims.widthMm,
            lengthMm: dims.lengthMm,
            usableHeightMm: usableH,
            x,
            y,
            displayX: formatMm(x),
            displayY: formatMm(y),
        };
    }

    function groupScope(session, selectedPieceKeys) {
        const AG = alignmentGeometry();
        if (AG && typeof AG.selectionScope === "function") {
            return AG.selectionScope(session, selectedPieceKeys);
        }
        return {
            keys: Array.isArray(selectedPieceKeys) ? selectedPieceKeys.filter(Boolean) : [],
            locked: true,
            scope: "invalid",
            eligible: false,
        };
    }

    function selectionPositionModel(session, selectedPieceKeys) {
        const keys = Array.isArray(selectedPieceKeys) ? selectedPieceKeys.filter(Boolean) : [];
        if (!keys.length) return null;
        if (keys.length === 1) return boardPositionForPiece(session, keys[0]);

        const scope = groupScope(session, keys);
        let reason = null;
        if (scope.locked) reason = reasonMessage(CODE.LOCKED);
        else if (scope.scope === "cross_sheet") reason = reasonMessage(CODE.CROSS_SHEET);
        else if (scope.scope === "mixed" || !scope.eligible) reason = reasonMessage(CODE.MIXED_SCOPE);

        return {
            mixed: true,
            mode: "relative",
            count: (scope.keys && scope.keys.length) || keys.length,
            keys: scope.keys && scope.keys.length ? scope.keys : keys.slice(),
            editable: Boolean(scope.eligible),
            reason,
            x: null,
            y: null,
            displayX: MIXED_LABEL,
            displayY: MIXED_LABEL,
        };
    }

    function worldDeltaForAxis(current, axis, nextValue) {
        if (!current) {
            return { ok: false, code: CODE.NEED_GROUP, dx: 0, dy: 0 };
        }
        const target = num(nextValue);
        if (!Number.isFinite(target)) {
            return { ok: false, code: CODE.INVALID_VALUE, dx: 0, dy: 0 };
        }
        const name = String(axis || "").toLowerCase();
        let dx = 0;
        let dy = 0;
        if (name === "x") dx = target - num(current.x);
        else if (name === "y") dy = displayedYDeltaToInternal(current.y, target);
        else return { ok: false, code: CODE.INVALID_AXIS, dx: 0, dy: 0 };

        if (Math.abs(dx) < 1e-9 && Math.abs(dy) < 1e-9) {
            return { ok: true, code: CODE.UNCHANGED, dx: 0, dy: 0, unchanged: true };
        }
        return { ok: true, code: CODE.OK, dx, dy, unchanged: false };
    }

    function axisDelta(axis, amount) {
        const name = String(axis || "").toLowerCase();
        const value = num(amount);
        if (name === "x") return { dx: value, dy: 0 };
        // Displayed Y+ is up; internal MoveGeometry Y+ is down.
        if (name === "y") return { dx: 0, dy: -value };
        return null;
    }

    function proposeGroupDeltaMove(session, selectedPieceKeys, dx, dy) {
        const MoveGeometry = moveGeometry();
        if (!MoveGeometry) {
            return { ok: false, code: CODE.MISSING_GEOMETRY, reason: reasonMessage(CODE.MISSING_GEOMETRY), commands: [] };
        }
        const scope = groupScope(session, selectedPieceKeys);
        if (!scope.keys || scope.keys.length < 2) {
            return { ok: false, code: CODE.NEED_GROUP, reason: reasonMessage(CODE.NEED_GROUP), commands: [] };
        }
        if (scope.locked) {
            return { ok: false, code: CODE.LOCKED, reason: reasonMessage(CODE.LOCKED), commands: [] };
        }
        if (!scope.eligible) {
            const code = scope.scope === "cross_sheet" ? CODE.CROSS_SHEET : CODE.MIXED_SCOPE;
            return { ok: false, code, reason: reasonMessage(code), commands: [] };
        }

        const shiftX = num(dx);
        const shiftY = num(dy);
        if (!(Math.abs(shiftX) > 1e-9 || Math.abs(shiftY) > 1e-9)) {
            return {
                ok: true,
                unchanged: true,
                code: CODE.UNCHANGED,
                commands: [],
                dx: 0,
                dy: 0,
                mixed: true,
                current: selectionPositionModel(session, scope.keys),
            };
        }

        const plan = MoveGeometry.groupMovePlan(session, scope.keys, scope.keys[0]);
        if (plan.locked || !plan.roots.length) {
            return { ok: false, code: CODE.LOCKED, reason: reasonMessage(CODE.LOCKED), commands: [] };
        }

        const proposal = MoveGeometry.proposeGroupMove(session, plan.roots, shiftX, shiftY);
        if (!proposal.ok) {
            return {
                ok: false,
                code: proposal.code,
                reason: proposal.reason || "Drop rejected.",
                commands: [],
                dx: shiftX,
                dy: shiftY,
                mixed: true,
            };
        }

        const hostLinksBefore = {};
        Object.keys(session.pieces || {}).forEach((key) => {
            const piece = session.pieces[key];
            if (piece && piece.glass_host_key) hostLinksBefore[key] = piece.glass_host_key;
        });

        for (let index = 0; index < (proposal.commands || []).length; index += 1) {
            const command = proposal.commands[index];
            const piece = session.pieces[command.piece_key];
            if (!piece || !sameSheetIdentity(piece, command.target_sheet_no)) {
                return {
                    ok: false,
                    code: CODE.SHEET_CHANGED,
                    reason: reasonMessage(CODE.SHEET_CHANGED),
                    commands: [],
                };
            }
            if (command.detach_host) {
                return {
                    ok: false,
                    code: CODE.DETACH_HOST,
                    reason: reasonMessage(CODE.DETACH_HOST),
                    commands: [],
                };
            }
        }

        let trial = session;
        (proposal.commands || []).forEach((command) => {
            trial = MoveGeometry.applyPieceMove(trial, command);
        });
        for (const [guestKey, hostKey] of Object.entries(hostLinksBefore)) {
            const guest = trial.pieces[guestKey];
            if (!guest || guest.glass_host_key !== hostKey) {
                return {
                    ok: false,
                    code: CODE.DETACH_HOST,
                    reason: reasonMessage(CODE.DETACH_HOST),
                    commands: [],
                };
            }
        }

        return {
            ok: true,
            unchanged: false,
            code: CODE.OK,
            commands: proposal.commands || [],
            dx: shiftX,
            dy: shiftY,
            mixed: true,
            current: selectionPositionModel(trial, scope.keys),
        };
    }

    function proposeDeltaMove(session, pieceKeyOrInstance, dx, dy) {
        // Exact millimetre delta through MoveGeometry — no magnet/snap.
        const MoveGeometry = moveGeometry();
        if (!MoveGeometry) {
            return { ok: false, code: CODE.MISSING_GEOMETRY, reason: reasonMessage(CODE.MISSING_GEOMETRY) };
        }
        const current = boardPositionForPiece(session, pieceKeyOrInstance);
        if (!current) {
            return { ok: false, code: CODE.NO_BOARD_PIECE, reason: reasonMessage(CODE.NO_BOARD_PIECE) };
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
        for (let index = 0; index < (proposal.commands || []).length; index += 1) {
            const command = proposal.commands[index];
            const piece = session.pieces[command.piece_key];
            if (!piece || !sameSheetIdentity(piece, command.target_sheet_no)) {
                return {
                    ok: false,
                    code: CODE.SHEET_CHANGED,
                    reason: reasonMessage(CODE.SHEET_CHANGED),
                    current,
                };
            }
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
            return { ok: false, code: CODE.NO_BOARD_PIECE, reason: reasonMessage(CODE.NO_BOARD_PIECE) };
        }
        const delta = worldDeltaForAxis(current, axis, nextValue);
        if (!delta.ok) {
            return {
                ok: false,
                code: delta.code,
                reason: delta.code === CODE.INVALID_VALUE
                    ? reasonMessage(CODE.INVALID_VALUE)
                    : reasonMessage(CODE.INVALID_AXIS),
            };
        }
        if (delta.unchanged) {
            return { ok: true, unchanged: true, current, commands: [], dx: 0, dy: 0 };
        }
        return proposeDeltaMove(session, current.pieceKey, delta.dx, delta.dy);
    }

    function proposeGroupAxisStep(session, selectedPieceKeys, axis, stepMm) {
        const delta = axisDelta(axis, stepMm);
        if (!delta) {
            return { ok: false, code: CODE.INVALID_AXIS, reason: reasonMessage(CODE.INVALID_AXIS), commands: [] };
        }
        return proposeGroupDeltaMove(session, selectedPieceKeys, delta.dx, delta.dy);
    }

    function proposeGroupAxisRelative(session, selectedPieceKeys, axis, textOrNumber) {
        const offset = typeof textOrNumber === "number"
            ? (Number.isFinite(textOrNumber) ? textOrNumber : null)
            : parseRelativeOffset(textOrNumber);
        if (offset == null) {
            return { ok: false, code: CODE.INVALID_VALUE, reason: reasonMessage(CODE.INVALID_VALUE), commands: [] };
        }
        const delta = axisDelta(axis, offset);
        if (!delta) {
            return { ok: false, code: CODE.INVALID_AXIS, reason: reasonMessage(CODE.INVALID_AXIS), commands: [] };
        }
        return proposeGroupDeltaMove(session, selectedPieceKeys, delta.dx, delta.dy);
    }

    function proposeKeyboardNudge(session, pieceKeyOrInstance, key) {
        const code = String(key || "");
        let dx = 0;
        let dy = 0;
        if (code === "ArrowRight") dx = STEP_MM;
        else if (code === "ArrowLeft") dx = -STEP_MM;
        else if (code === "ArrowDown") dy = STEP_MM;
        else if (code === "ArrowUp") dy = -STEP_MM;
        else return { ok: false, code: CODE.INVALID_KEY, reason: reasonMessage(CODE.INVALID_KEY) };
        return proposeDeltaMove(session, pieceKeyOrInstance, dx, dy);
    }

    function proposeSelectionKeyboardNudge(session, selectedPieceKeys, key) {
        const keys = Array.isArray(selectedPieceKeys) ? selectedPieceKeys.filter(Boolean) : [];
        if (keys.length <= 1) {
            return proposeKeyboardNudge(session, keys[0], key);
        }
        const code = String(key || "");
        let dx = 0;
        let dy = 0;
        if (code === "ArrowRight") dx = STEP_MM;
        else if (code === "ArrowLeft") dx = -STEP_MM;
        else if (code === "ArrowDown") dy = STEP_MM;
        else if (code === "ArrowUp") dy = -STEP_MM;
        else return { ok: false, code: CODE.INVALID_KEY, reason: reasonMessage(CODE.INVALID_KEY) };
        return proposeGroupDeltaMove(session, keys, dx, dy);
    }

    window.AlmdinaBoardEditor = window.AlmdinaBoardEditor || {};
    window.AlmdinaBoardEditor.PositionGeometry = Object.freeze({
        AXES,
        STEP_MM,
        MIXED_LABEL,
        CODE,
        reasonMessage,
        formatMm,
        parseMm,
        parseRelativeOffset,
        pieceDimensionsMm,
        usableHeightMm,
        internalYToDisplayedY,
        displayedYDeltaToInternal,
        boardPositionForPiece,
        // Alias kept for callers/tests that still name the helper generically.
        boardInsetsForPiece: boardPositionForPiece,
        selectionPositionModel,
        worldDeltaForAxis,
        proposeAxisMove,
        proposeDeltaMove,
        proposeGroupDeltaMove,
        proposeGroupAxisStep,
        proposeGroupAxisRelative,
        proposeKeyboardNudge,
        proposeSelectionKeyboardNudge,
    });
})();
