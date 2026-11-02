(() => {
    "use strict";

    const TITLE_BAND_MM = 36;

    function clone(value) {
        return JSON.parse(JSON.stringify(value == null ? null : value));
    }

    function outlineFromGeometry(geometry) {
        if (!geometry || typeof geometry !== "object") return null;
        if (Array.isArray(geometry.outer) && geometry.outer.length >= 3) {
            return geometry.outer.map((point) => [Number(point[0]) || 0, Number(point[1]) || 0]);
        }
        return null;
    }

    function hasMovableGeometry(piece, related) {
        if (related.some((element) => (
            (element.kind === "finished_outline" || element.kind === "placement_rect")
            && (element.geometry || element.payload)
        ))) {
            return true;
        }
        const placement = piece.placement_cm || {};
        return Number(placement.w) > 0 && Number(placement.h) > 0;
    }

    function buildFromProjection(projection, boardLayout) {
        const sheets = (projection && projection.sheets) || [];
        const pieces = (projection && projection.pieces) || [];
        const elements = (projection && projection.elements) || [];
        const positions = (boardLayout && boardLayout.positions) || {};
        const boards = {};
        const pieceMap = {};
        const kerfMm = Number((projection.board && projection.board.kerf_cm) || 0) * 10;
        const boundLabelKeys = new Set();

        sheets.forEach((sheet) => {
            const sheetNo = sheet.sheet_no;
            const pos = positions[String(sheetNo)] || {};
            const widthMm = Number(pos.widthMm) || (Number(sheet.full_width_cm) || Number(sheet.w) || 122) * 10;
            const heightMm = Number(pos.heightMm) || (Number(sheet.full_length_cm) || Number(sheet.h) || 244) * 10;
            const trimX = Number(pos.trimX) || (Number(sheet.applied_trim_width_cm) || 0) * 10;
            const trimY = Number(pos.trimY) || (Number(sheet.applied_trim_length_cm) || 0) * 10;
            boards[String(sheetNo)] = {
                sheet_no: sheetNo,
                origin_x_mm: Number(pos.originX) || 0,
                origin_y_mm: Number(pos.originY) || TITLE_BAND_MM,
                width_mm: widthMm,
                height_mm: heightMm,
                trim_x_mm: trimX,
                trim_y_mm: trimY,
                usable_width_mm: Math.max(1, widthMm - trimX * 2),
                usable_length_mm: Math.max(1, heightMm - trimY * 2),
                title_band_mm: TITLE_BAND_MM,
                rotation_deg: 0,
                user_moved: false,
            };
        });

        pieces.forEach((piece) => {
            const instanceId = String(piece.piece_instance_id || "").trim();
            const pieceId = piece.piece_id == null ? null : Number(piece.piece_id);
            const related = elements.filter((element) => (
                (pieceId != null && Number(element.piece_id) === pieceId)
                || (instanceId && String(element.piece_instance_id || "").trim() === instanceId)
            ));
            const specialBlocked = related.some((element) => (
                element.kind === "unresolved"
                && element.payload
                && element.payload.reason === "special_geometry_unavailable"
            ));
            const geometryOk = hasMovableGeometry(piece, related);
            const editable = Boolean(instanceId) && !specialBlocked && geometryOk;
            const key = instanceId ? `instance:${instanceId}` : null;
            if (!key) return;
            const placement = piece.placement_cm || {};
            const outlineElement = related.find((element) => element.geometry && element.geometry.outer);
            const outlineMm = outlineFromGeometry(outlineElement && outlineElement.geometry);
            // Fail closed: only a proven order flag may enable rotation.
            const allowProven = piece.allow_rotation_proven === true;
            const allowRotation = allowProven && (
                piece.allow_rotation === true
                || piece.allow_rotation === 1
                || piece.allow_rotation === "1"
            );
            const sessionPiece = {
                piece_key: key,
                piece_id: pieceId,
                piece_instance_id: instanceId,
                label: piece.label || instanceId,
                sheet_no: piece.sheet_no == null ? null : Number(piece.sheet_no),
                local_x_mm: (Number(placement.x) || 0) * 10,
                local_y_mm: (Number(placement.y) || 0) * 10,
                placement_cm: clone(placement),
                outline_mm: outlineMm,
                base_outline_mm: outlineMm ? clone(outlineMm) : null,
                glass_host_piece_id: piece.glass_host_piece_id == null ? null : Number(piece.glass_host_piece_id),
                glass_host_key: null,
                glass_hole_local_mm: clone(piece.glass_hole_local_mm),
                base_hole_mm: piece.glass_hole_local_mm ? clone(piece.glass_hole_local_mm) : null,
                editable,
                block_reason: !instanceId
                    ? "missing_piece_instance_id"
                    : (specialBlocked
                        ? "special_geometry_unavailable"
                        : (geometryOk ? null : "incomplete_geometry")),
                // Session edit angle from the as-loaded pose (not source grain).
                rotation_deg: 0,
                source_rotated_dims: Boolean(piece.source_rotated_dims || placement.rotated),
                source_orientation_applied: piece.source_orientation_applied !== false,
                apply_rotated_to_geometry: false,
                allow_rotation: allowProven ? allowRotation : false,
                allow_rotation_proven: Boolean(allowProven),
                piece_type: piece.piece_type || "",
            };
            if (Array.isArray(sessionPiece.base_outline_mm) && sessionPiece.base_outline_mm.length >= 3) {
                const xs = sessionPiece.base_outline_mm.map((point) => Number(point[0]) || 0);
                const ys = sessionPiece.base_outline_mm.map((point) => Number(point[1]) || 0);
                sessionPiece.pivot_mm = {
                    x: (Math.min(...xs) + Math.max(...xs)) * 0.5,
                    y: (Math.min(...ys) + Math.max(...ys)) * 0.5,
                };
                sessionPiece.entry_pivot_mm = {
                    x: sessionPiece.pivot_mm.x,
                    y: sessionPiece.pivot_mm.y,
                };
            } else {
                const w = (Number(placement.w) || 0) * 10;
                const h = (Number(placement.h) || 0) * 10;
                sessionPiece.pivot_mm = {
                    x: sessionPiece.local_x_mm + w * 0.5,
                    y: sessionPiece.local_y_mm + h * 0.5,
                };
                sessionPiece.entry_pivot_mm = {
                    x: sessionPiece.pivot_mm.x,
                    y: sessionPiece.pivot_mm.y,
                };
            }
            pieceMap[key] = sessionPiece;
            boundLabelKeys.add(key);
        });

        Object.values(pieceMap).forEach((piece) => {
            if (piece.glass_host_piece_id == null) return;
            const host = Object.values(pieceMap).find((row) => Number(row.piece_id) === Number(piece.glass_host_piece_id));
            piece.glass_host_key = host ? host.piece_key : null;
        });

        // System labels carry piece_instance_id on the element. Guessing ownership
        // from layer name or visual containment is intentionally not supported.
        elements.forEach((element) => {
            if (element.kind !== "text_label") return;
            const instanceId = String(element.piece_instance_id || "").trim();
            if (instanceId) boundLabelKeys.add(`instance:${instanceId}`);
        });

        return {
            boards,
            pieces: pieceMap,
            kerf_mm: kerfMm,
            stale_cut_path_sheets: [],
            stale_unbound_text_sheets: [],
            bound_label_keys: Array.from(boundLabelKeys),
        };
    }

    function boardPositions(session) {
        const positions = {};
        Object.values((session && session.boards) || {}).forEach((board) => {
            positions[String(board.sheet_no)] = {
                originX: Number(board.origin_x_mm) || 0,
                originY: Number(board.origin_y_mm) || 0,
                titleY: (Number(board.origin_y_mm) || 0) - 10,
                widthMm: Number(board.width_mm) || 1,
                heightMm: Number(board.height_mm) || 1,
                trimX: Number(board.trim_x_mm) || 0,
                trimY: Number(board.trim_y_mm) || 0,
                sheetNo: board.sheet_no,
                userMoved: Boolean(board.user_moved),
            };
        });
        return positions;
    }

    function relayoutUnmovedBoards(session, layout) {
        if (!session || !layout || !layout.positions) return session;
        const next = clone(session);
        Object.keys(next.boards || {}).forEach((sheetKey) => {
            const board = next.boards[sheetKey];
            if (board.user_moved) return;
            const pos = layout.positions[sheetKey];
            if (!pos) return;
            board.origin_x_mm = Number(pos.originX) || 0;
            board.origin_y_mm = Number(pos.originY) || TITLE_BAND_MM;
        });
        return next;
    }

    function isExcluded(piece) {
        return Boolean(piece && piece.distribution === "excluded");
    }

    function piecesBySheet(session) {
        const groups = { outside: [], excluded: [] };
        Object.values((session && session.pieces) || {}).forEach((piece) => {
            if (isExcluded(piece)) {
                groups.excluded.push(piece);
                return;
            }
            if (piece.sheet_no == null || piece.sheet_no === "") {
                groups.outside.push(piece);
                return;
            }
            const key = String(piece.sheet_no);
            if (!groups[key]) groups[key] = [];
            groups[key].push(piece);
        });
        return groups;
    }

    function hostingRoots(session, sheetNo) {
        const pieces = Object.values((session && session.pieces) || {}).filter((piece) => {
            if (isExcluded(piece)) return false;
            return sheetNo == null
                ? piece.sheet_no == null || piece.sheet_no === ""
                : Number(piece.sheet_no) === Number(sheetNo);
        });
        const byKey = {};
        pieces.forEach((piece) => {
            byKey[piece.piece_key] = {
                piece_id: piece.piece_id,
                piece_instance_id: piece.piece_instance_id,
                piece_key: piece.piece_key,
                label: piece.label,
                glass_host_piece_id: piece.glass_host_piece_id,
                editable: piece.editable,
                block_reason: piece.block_reason,
                guests: [],
            };
        });
        const roots = [];
        Object.values(byKey).forEach((node) => {
            const hostKey = pieces.find((piece) => piece.piece_key === node.piece_key)?.glass_host_key;
            if (hostKey && byKey[hostKey]) {
                byKey[hostKey].guests.push(node);
            } else {
                roots.push(node);
            }
        });
        return roots;
    }

    function excludedRoots(session) {
        const pieces = Object.values((session && session.pieces) || {}).filter(isExcluded);
        const byKey = {};
        pieces.forEach((piece) => {
            byKey[piece.piece_key] = {
                piece_id: piece.piece_id,
                piece_instance_id: piece.piece_instance_id,
                piece_key: piece.piece_key,
                label: piece.label,
                glass_host_piece_id: piece.glass_host_piece_id,
                editable: piece.editable,
                block_reason: piece.block_reason,
                exclusion_reason: piece.exclusion_reason || "removed_from_distribution",
                guests: [],
            };
        });
        const roots = [];
        Object.values(byKey).forEach((node) => {
            const hostKey = pieces.find((piece) => piece.piece_key === node.piece_key)?.glass_host_key;
            if (hostKey && byKey[hostKey]) {
                byKey[hostKey].guests.push(node);
            } else {
                roots.push(node);
            }
        });
        return roots;
    }

    function round4(value) {
        const number = Number(value);
        if (!Number.isFinite(number)) return 0;
        return Math.round(number * 10000) / 10000;
    }

    function layoutDocument(session) {
        const pieces = Object.keys((session && session.pieces) || {}).sort().map((key) => {
            const piece = session.pieces[key];
            const excluded = piece.distribution === "excluded";
            return {
                piece_instance_id: String(piece.piece_instance_id || ""),
                sheet_no: piece.sheet_no == null || piece.sheet_no === "" ? null : Number(piece.sheet_no),
                local_x_mm: round4(piece.local_x_mm),
                local_y_mm: round4(piece.local_y_mm),
                rotation_deg: round4(piece.rotation_deg),
                distribution: excluded ? "excluded" : "active",
                exclusion_reason: excluded ? (piece.exclusion_reason || null) : null,
                glass_host_piece_id: piece.glass_host_piece_id == null || piece.glass_host_piece_id === ""
                    ? null
                    : Number(piece.glass_host_piece_id),
            };
        });
        const boards = Object.keys((session && session.boards) || {})
            .sort((left, right) => Number(left) - Number(right))
            .map((key) => {
                const board = session.boards[key];
                return {
                    sheet_no: Number(board.sheet_no != null ? board.sheet_no : key),
                    origin_x_mm: round4(board.origin_x_mm),
                    origin_y_mm: round4(board.origin_y_mm),
                    user_moved: board.user_moved === true,
                };
            });
        return { schema: 1, pieces, boards };
    }

    function distributionFingerprint(session) {
        return JSON.stringify(layoutDocument(session));
    }

    function exportLayout(session) {
        return layoutDocument(session);
    }

    function applySavedLayout(session, layout) {
        const editor = window.AlmdinaBoardEditor || {};
        const MoveGeometry = editor.MoveGeometry;
        const RotationGeometry = editor.RotationGeometry;
        if (!session || !layout || !Array.isArray(layout.pieces) || !MoveGeometry || !RotationGeometry) {
            return { ok: false, code: "invalid_layout" };
        }
        const next = clone(session);
        const byInstance = {};
        Object.keys(next.pieces || {}).forEach((key) => {
            byInstance[String(next.pieces[key].piece_instance_id || "")] = key;
        });
        const rows = layout.pieces;
        if (rows.length !== Object.keys(next.pieces || {}).length) {
            return { ok: false, code: "missing_piece" };
        }
        const seen = new Set();
        for (let index = 0; index < rows.length; index += 1) {
            const instance = String(rows[index].piece_instance_id || "");
            if (!instance || !byInstance[instance] || seen.has(instance)) {
                return { ok: false, code: "unknown_piece" };
            }
            seen.add(instance);
        }
        Object.keys(next.pieces).forEach((key) => {
            next.pieces[key].glass_host_key = null;
            next.pieces[key].glass_host_piece_id = null;
        });
        rows.forEach((row) => {
            const key = byInstance[String(row.piece_instance_id)];
            const angle = Number(row.rotation_deg) || 0;
            if (Math.abs(angle - Number(next.pieces[key].rotation_deg || 0)) < 1e-4) return;
            const rotated = RotationGeometry.previewPieceRotation(next, key, angle);
            next.pieces[key] = rotated.pieces[key];
        });
        rows.forEach((row) => {
            const piece = next.pieces[byInstance[String(row.piece_instance_id)]];
            const fromSheet = piece.sheet_no;
            const toSheet = row.sheet_no == null || row.sheet_no === "" ? null : Number(row.sheet_no);
            const fromOrigin = MoveGeometry.sheetOriginMm(next.boards, fromSheet);
            const toOrigin = MoveGeometry.sheetOriginMm(next.boards, toSheet);
            MoveGeometry.reframePieceGeometry(
                piece,
                next.boards,
                fromSheet,
                toSheet,
                (Number(row.local_x_mm) + toOrigin.x) - (Number(piece.local_x_mm) + fromOrigin.x),
                (Number(row.local_y_mm) + toOrigin.y) - (Number(piece.local_y_mm) + fromOrigin.y)
            );
            piece.sheet_no = toSheet;
            piece.local_x_mm = Number(row.local_x_mm);
            piece.local_y_mm = Number(row.local_y_mm);
            piece.distribution = row.distribution === "excluded" ? "excluded" : "active";
            piece.exclusion_reason = piece.distribution === "excluded" ? (row.exclusion_reason || null) : null;
        });
        const idToKey = {};
        Object.keys(next.pieces).forEach((key) => {
            idToKey[String(next.pieces[key].piece_id)] = key;
        });
        rows.forEach((row) => {
            if (row.glass_host_piece_id == null || row.glass_host_piece_id === "") return;
            const piece = next.pieces[byInstance[String(row.piece_instance_id)]];
            const hostKey = idToKey[String(row.glass_host_piece_id)];
            if (!hostKey) return;
            piece.glass_host_piece_id = Number(row.glass_host_piece_id);
            piece.glass_host_key = hostKey;
        });
        const kept = new Set((layout.boards || []).map((board) => String(board.sheet_no)));
        Object.keys(next.boards || {}).forEach((key) => {
            if (!kept.has(String(key))) delete next.boards[key];
        });
        (layout.boards || []).forEach((board) => {
            const target = next.boards[String(board.sheet_no)];
            if (!target) return;
            target.origin_x_mm = Number(board.origin_x_mm) || 0;
            target.origin_y_mm = Number(board.origin_y_mm) || 0;
            target.user_moved = board.user_moved === true;
        });
        return { ok: true, session: next };
    }

    function settleReview(view, request, response) {
        const session = view && view.session;
        const review = view && view.review;
        const currentSerial = view ? Number(view.reviewSerial) || 0 : 0;
        const currentFingerprint = distributionFingerprint(session);
        const currentVersion = view && view.draftVersion ? Number(view.draftVersion) : 0;
        if (!request || Number(request.serial) !== currentSerial) {
            return { ignored: true, failed: false, session, review };
        }
        if (
            request.fingerprint !== currentFingerprint
            || Number(request.draftVersion) !== currentVersion
        ) {
            return { ignored: true, failed: false, session, review };
        }
        if (!response || response.exc || (response.ok === false && !Array.isArray(response.issues))) {
            return { ignored: false, failed: true, session, review };
        }
        return { ignored: false, failed: false, session, review: response };
    }

    function settleDraftSave(view, sentFingerprint, response) {
        const session = view && view.session;
        const savedFingerprint = view && view.savedFingerprint;
        const draftVersion = view && view.draftVersion ? Number(view.draftVersion) : 0;
        if (!response || response.ok === false) {
            const code = response && response.code;
            const conflict = code === "conflict" || code === "source_conflict" || code === "version_conflict";
            return {
                session,
                draftVersion,
                savedFingerprint,
                saveState: conflict ? "conflict" : "failed",
                saveInFlight: false,
            };
        }
        const current = distributionFingerprint(session);
        return {
            session,
            draftVersion: Number(response.draft_version) || draftVersion,
            savedFingerprint: sentFingerprint,
            saveState: current === sentFingerprint ? "saved" : "dirty",
            saveInFlight: false,
        };
    }

    window.AlmdinaBoardEditor = window.AlmdinaBoardEditor || {};
    window.AlmdinaBoardEditor.SessionDocument = Object.freeze({
        buildFromProjection,
        boardPositions,
        relayoutUnmovedBoards,
        piecesBySheet,
        hostingRoots,
        excludedRoots,
        isExcluded,
        clone,
        layoutDocument,
        distributionFingerprint,
        exportLayout,
        applySavedLayout,
        settleDraftSave,
        settleReview,
        TITLE_BAND_MM,
    });
})();
