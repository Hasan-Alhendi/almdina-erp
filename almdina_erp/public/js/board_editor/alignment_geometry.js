(() => {
    "use strict";

    // Alignment proposes independent per-root translations (Figma-style group AABB),
    // then validates the full final session atomically — no partial commits.

    const MODES = Object.freeze([
        "align_left",
        "align_center_x",
        "align_right",
        "align_top",
        "align_center_y",
        "align_bottom",
    ]);

    const CODE = Object.freeze({
        OK: "ok",
        NEED_SELECTION: "need_multi_selection",
        LOCKED: "locked_selection",
        MIXED_SCOPE: "mixed_scope",
        CROSS_SHEET: "cross_sheet",
        UNCHANGED: "unchanged",
        DETACH_HOST: "detach_host",
        SHEET_CHANGED: "sheet_changed",
        FINAL_CONFLICT: "final_conflict",
        MISSING_GEOMETRY: "missing_geometry",
    });

    const REASON_LABELS = Object.freeze({
        [CODE.NEED_SELECTION]: "Select two or more pieces to align them.",
        [CODE.LOCKED]: "Alignment is unavailable while a locked piece is selected.",
        [CODE.MIXED_SCOPE]: "Align pieces on the same board only, or pieces outside all boards.",
        [CODE.CROSS_SHEET]: "Align pieces on the same board only, or pieces outside all boards.",
        [CODE.DETACH_HOST]: "Alignment would break a glass host relationship.",
        [CODE.SHEET_CHANGED]: "Alignment must keep each piece on its current board.",
        [CODE.FINAL_CONFLICT]: "Alignment rejected: the final layout is not manufacturable.",
        [CODE.MISSING_GEOMETRY]: "Alignment geometry is unavailable.",
        [CODE.UNCHANGED]: "Pieces are already aligned.",
    });

    function num(value) {
        const n = Number(value);
        return Number.isFinite(n) ? n : 0;
    }

    function reasonMessage(code) {
        return REASON_LABELS[code] || "Alignment rejected.";
    }

    function moveGeometry() {
        return window.AlmdinaBoardEditor && window.AlmdinaBoardEditor.MoveGeometry;
    }

    function sheetToken(piece) {
        if (!piece || piece.sheet_no == null || piece.sheet_no === "") return null;
        return Number(piece.sheet_no);
    }

    function worldBox(session, pieceKey) {
        const MG = moveGeometry();
        const piece = session.pieces[pieceKey];
        const world = MG.worldFootprint(piece, session.boards);
        const bounds = world.bounds;
        const minX = num(bounds.x);
        const minY = num(bounds.y);
        const maxX = minX + num(bounds.w);
        const maxY = minY + num(bounds.h);
        return {
            key: pieceKey,
            minX,
            maxX,
            minY,
            maxY,
            centerX: (minX + maxX) / 2,
            centerY: (minY + maxY) / 2,
            sheet: sheetToken(piece),
        };
    }

    function groupBox(boxes) {
        const minX = Math.min(...boxes.map((box) => box.minX));
        const maxX = Math.max(...boxes.map((box) => box.maxX));
        const minY = Math.min(...boxes.map((box) => box.minY));
        const maxY = Math.max(...boxes.map((box) => box.maxY));
        return {
            minX,
            maxX,
            minY,
            maxY,
            centerX: (minX + maxX) / 2,
            centerY: (minY + maxY) / 2,
        };
    }

    function deltaForMode(mode, pieceBox, group) {
        switch (mode) {
        case "align_left":
            return { dx: group.minX - pieceBox.minX, dy: 0 };
        case "align_right":
            return { dx: group.maxX - pieceBox.maxX, dy: 0 };
        case "align_center_x":
            return { dx: group.centerX - pieceBox.centerX, dy: 0 };
        case "align_top":
            return { dx: 0, dy: group.minY - pieceBox.minY };
        case "align_bottom":
            return { dx: 0, dy: group.maxY - pieceBox.maxY };
        case "align_center_y":
            return { dx: 0, dy: group.centerY - pieceBox.centerY };
        default:
            return null;
        }
    }

    function selectionScope(session, selectedKeys) {
        const MG = moveGeometry();
        const keys = (selectedKeys || [])
            .map((key) => MG.resolvePieceKey(session, key))
            .filter((key) => key && session.pieces[key] && session.pieces[key].distribution !== "excluded");
        const unique = [];
        const seen = new Set();
        keys.forEach((key) => {
            if (seen.has(key)) return;
            seen.add(key);
            unique.push(key);
        });
        const sheets = new Set();
        let outside = 0;
        let locked = false;
        unique.forEach((key) => {
            const piece = session.pieces[key];
            if (!piece.editable) locked = true;
            const sheet = sheetToken(piece);
            if (sheet == null) outside += 1;
            else sheets.add(sheet);
        });
        let scope = "invalid";
        if (unique.length >= 2 && !locked) {
            if (outside === unique.length && sheets.size === 0) scope = "outside";
            else if (outside === 0 && sheets.size === 1) scope = "board";
            else if (outside > 0 && sheets.size > 0) scope = "mixed";
            else if (sheets.size > 1) scope = "cross_sheet";
        }
        return {
            keys: unique,
            locked,
            outsideCount: outside,
            sheetCount: sheets.size,
            sheetNo: sheets.size === 1 ? [...sheets][0] : null,
            scope,
            eligible: scope === "outside" || scope === "board",
        };
    }

    function alignmentEligibility(session, selectedKeys) {
        const MG = moveGeometry();
        if (!MG) {
            return {
                ok: false,
                enabled: false,
                code: CODE.MISSING_GEOMETRY,
                reason: reasonMessage(CODE.MISSING_GEOMETRY),
            };
        }
        const info = selectionScope(session, selectedKeys);
        if (info.keys.length < 2) {
            return {
                ok: false,
                enabled: false,
                code: CODE.NEED_SELECTION,
                reason: reasonMessage(CODE.NEED_SELECTION),
                selection: info,
            };
        }
        if (info.locked) {
            return {
                ok: false,
                enabled: false,
                code: CODE.LOCKED,
                reason: reasonMessage(CODE.LOCKED),
                selection: info,
            };
        }
        if (info.scope === "mixed" || info.scope === "cross_sheet" || info.scope === "invalid") {
            const code = info.scope === "cross_sheet" ? CODE.CROSS_SHEET : CODE.MIXED_SCOPE;
            return {
                ok: false,
                enabled: false,
                code,
                reason: reasonMessage(code),
                selection: info,
            };
        }
        return {
            ok: true,
            enabled: true,
            code: CODE.OK,
            reason: null,
            selection: info,
        };
    }

    function sameSheetIdentity(before, after) {
        const a = sheetToken(before);
        const b = sheetToken(after);
        if (a == null && b == null) return true;
        return a != null && b != null && Number(a) === Number(b);
    }

    function failFinal(code, pieceKey, sheetNo) {
        return {
            ok: false,
            code,
            stage: "final_validation",
            piece_key: pieceKey || null,
            sheet_no: sheetNo == null || sheetNo === "" ? null : Number(sheetNo),
        };
    }

    function validateFinalSession(session, movingKeys, scope) {
        // Scope final checks to pieces that actually moved for this alignment.
        // Pre-existing violations on unrelated (non-moved) pieces must not reject
        // an otherwise manufacturable alignment; new violations caused by the
        // move still fail closed.
        const MG = moveGeometry();
        const kerf = session.kerf_mm || 0;
        const moved = movingKeys instanceof Set ? movingKeys : new Set(movingKeys || []);
        const keys = Object.keys(session.pieces || {});

        for (let i = 0; i < keys.length; i += 1) {
            const key = keys[i];
            if (!moved.has(key)) continue;
            const piece = session.pieces[key];
            if (!piece || piece.distribution === "excluded") continue;
            if (piece.sheet_no == null || piece.sheet_no === "") continue;
            const board = session.boards && session.boards[String(piece.sheet_no)];
            if (!board) return failFinal(CODE.FINAL_CONFLICT, key, piece.sheet_no);
            const local = MG.footprint(piece);
            const usable = {
                x: 0,
                y: 0,
                w: num(board.usable_width_mm) || num(board.width_mm),
                h: num(board.usable_length_mm) || num(board.height_mm),
            };
            if (
                local.bounds.x < usable.x - 1e-9
                || local.bounds.y < usable.y - 1e-9
                || local.bounds.x + local.bounds.w > usable.x + usable.w + 1e-9
                || local.bounds.y + local.bounds.h > usable.y + usable.h + 1e-9
            ) {
                return failFinal(
                    MG.DROP_PARTIAL_BOARD || CODE.FINAL_CONFLICT,
                    key,
                    piece.sheet_no
                );
            }
        }

        // Outside workspace may overlap freely; board scope must stay manufacturable.
        if (scope !== "board") return { ok: true, code: CODE.OK };

        for (let i = 0; i < keys.length; i += 1) {
            const keyA = keys[i];
            const a = session.pieces[keyA];
            if (!a || a.distribution === "excluded") continue;
            if (a.sheet_no == null || a.sheet_no === "") continue;
            const aMoved = moved.has(keyA);
            const fpA = MG.footprint(a);
            for (let j = i + 1; j < keys.length; j += 1) {
                const keyB = keys[j];
                const b = session.pieces[keyB];
                if (!b || b.distribution === "excluded") continue;
                if (Number(b.sheet_no) !== Number(a.sheet_no)) continue;
                // Skip stale pairs where neither piece moved for this alignment.
                if (!aMoved && !moved.has(keyB)) continue;
                if (a.glass_host_key === keyB || b.glass_host_key === keyA) continue;
                const conflict = MG.pairConflict(fpA, MG.footprint(b), kerf);
                if (conflict) {
                    return failFinal(
                        conflict,
                        aMoved ? keyA : keyB,
                        a.sheet_no
                    );
                }
            }
        }

        // Hosted guests must remain linked after independent root moves.
        for (let i = 0; i < keys.length; i += 1) {
            const key = keys[i];
            if (!moved.has(key)) continue;
            const piece = session.pieces[key];
            if (!piece || !piece.glass_host_key) continue;
            const host = session.pieces[piece.glass_host_key];
            if (!host) return failFinal(CODE.DETACH_HOST, key, piece.sheet_no);
            if (Number(piece.sheet_no) !== Number(host.sheet_no)) {
                return failFinal(CODE.DETACH_HOST, key, piece.sheet_no);
            }
        }
        return { ok: true, code: CODE.OK };
    }

    function proposeAlignment(session, selectedKeys, mode) {
        const MG = moveGeometry();
        if (!MG) {
            return { ok: false, code: CODE.MISSING_GEOMETRY, reason: reasonMessage(CODE.MISSING_GEOMETRY), commands: [] };
        }
        if (!MODES.includes(mode)) {
            return { ok: false, code: "invalid_mode", reason: "Alignment rejected.", commands: [] };
        }
        const eligibility = alignmentEligibility(session, selectedKeys);
        if (!eligibility.enabled) {
            return {
                ok: false,
                code: eligibility.code,
                reason: eligibility.reason,
                commands: [],
                selection: eligibility.selection,
            };
        }
        const selected = eligibility.selection.keys;
        const pressed = selected[0];
        const plan = MG.groupMovePlan(session, selected, pressed);
        if (plan.locked || !plan.roots.length) {
            return {
                ok: false,
                code: CODE.LOCKED,
                reason: reasonMessage(CODE.LOCKED),
                commands: [],
            };
        }

        const boxes = plan.roots.map((key) => worldBox(session, key));
        const group = groupBox(boxes);
        const moving = new Set(plan.moving);
        const commands = [];
        let anyMove = false;

        for (let index = 0; index < boxes.length; index += 1) {
            const box = boxes[index];
            const delta = deltaForMode(mode, box, group);
            if (!delta) {
                return { ok: false, code: "invalid_mode", reason: "Alignment rejected.", commands: [] };
            }
            if (Math.abs(delta.dx) < 1e-9 && Math.abs(delta.dy) < 1e-9) continue;
            anyMove = true;
            const origin = MG.pieceWorldOrigin(session, box.key);
            const decision = MG.validatePieceDrop(
                session,
                box.key,
                origin.x + delta.dx,
                origin.y + delta.dy,
                moving
            );
            if (!decision.ok) {
                return {
                    ok: false,
                    code: decision.code,
                    reason: MG.reasonMessage(decision.code),
                    commands: [],
                    stage: "piece_drop",
                    piece_key: box.key,
                    sheet_no: session.pieces[box.key]
                        ? session.pieces[box.key].sheet_no
                        : null,
                };
            }
            const piece = session.pieces[box.key];
            const trialPiece = {
                ...piece,
                sheet_no: decision.sheet_no,
                local_x_mm: decision.local_x_mm,
                local_y_mm: decision.local_y_mm,
            };
            if (!sameSheetIdentity(piece, trialPiece)) {
                return {
                    ok: false,
                    code: CODE.SHEET_CHANGED,
                    reason: reasonMessage(CODE.SHEET_CHANGED),
                    commands: [],
                    stage: "piece_drop",
                    piece_key: box.key,
                    sheet_no: piece.sheet_no,
                };
            }
            let detachHost = false;
            const host = piece.glass_host_key ? session.pieces[piece.glass_host_key] : null;
            if (host && !moving.has(piece.glass_host_key)) {
                if (
                    Number(trialPiece.sheet_no) !== Number(host.sheet_no)
                ) {
                    detachHost = true;
                }
            }
            if (detachHost) {
                return {
                    ok: false,
                    code: CODE.DETACH_HOST,
                    reason: reasonMessage(CODE.DETACH_HOST),
                    commands: [],
                    stage: "piece_drop",
                    piece_key: box.key,
                    sheet_no: piece.sheet_no,
                };
            }
            commands.push({
                piece_key: box.key,
                target_sheet_no: decision.sheet_no,
                local_x_mm: decision.local_x_mm,
                local_y_mm: decision.local_y_mm,
                delta_x_mm: decision.delta_x_mm,
                delta_y_mm: decision.delta_y_mm,
                detach_host: false,
            });
        }

        if (!anyMove || !commands.length) {
            return {
                ok: true,
                unchanged: true,
                code: CODE.UNCHANGED,
                reason: reasonMessage(CODE.UNCHANGED),
                commands: [],
                mode,
                selection: eligibility.selection,
            };
        }

        const hostLinksBefore = {};
        Object.keys(session.pieces || {}).forEach((key) => {
            const piece = session.pieces[key];
            if (piece && piece.glass_host_key) hostLinksBefore[key] = piece.glass_host_key;
        });

        let trial = session;
        const changedKeys = new Set();
        for (let index = 0; index < commands.length; index += 1) {
            const command = commands[index];
            MG.draggedPieceIds(session, command.piece_key).forEach((id) => changedKeys.add(id));
            trial = MG.applyPieceMove(trial, command);
        }

        for (const [guestKey, hostKey] of Object.entries(hostLinksBefore)) {
            const guest = trial.pieces[guestKey];
            if (!guest || guest.glass_host_key !== hostKey) {
                return {
                    ok: false,
                    code: CODE.DETACH_HOST,
                    reason: reasonMessage(CODE.DETACH_HOST),
                    commands: [],
                    stage: "final_validation",
                    piece_key: guestKey,
                    sheet_no: guest ? guest.sheet_no : null,
                };
            }
        }

        const finalCheck = validateFinalSession(
            trial,
            changedKeys,
            eligibility.selection.scope
        );
        if (!finalCheck.ok) {
            const code = finalCheck.code;
            const dropReason = typeof MG.reasonMessage === "function" ? MG.reasonMessage(code) : "";
            const reason = (dropReason && dropReason !== "Drop rejected.")
                ? dropReason
                : reasonMessage(code === CODE.FINAL_CONFLICT ? CODE.FINAL_CONFLICT : code);
            return {
                ok: false,
                code,
                reason: reason || reasonMessage(CODE.FINAL_CONFLICT),
                commands: [],
                stage: finalCheck.stage || "final_validation",
                piece_key: finalCheck.piece_key || null,
                sheet_no: finalCheck.sheet_no == null ? null : finalCheck.sheet_no,
            };
        }

        return {
            ok: true,
            unchanged: false,
            code: CODE.OK,
            commands,
            mode,
            selection: eligibility.selection,
            dxByKey: commands.reduce((map, command) => {
                map[command.piece_key] = {
                    dx: num(command.delta_x_mm),
                    dy: num(command.delta_y_mm),
                };
                return map;
            }, {}),
        };
    }

    window.AlmdinaBoardEditor = window.AlmdinaBoardEditor || {};
    window.AlmdinaBoardEditor.AlignmentGeometry = Object.freeze({
        MODES,
        CODE,
        reasonMessage,
        selectionScope,
        alignmentEligibility,
        worldBox,
        groupBox,
        deltaForMode,
        proposeAlignment,
        validateFinalSession,
    });
})();
