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

    function cloneRing(ring) {
        if (!Array.isArray(ring) || ring.length < 3) return null;
        return ring.map((point) => [Number(point[0]) || 0, Number(point[1]) || 0]);
    }

    function usableSheetHoleFromPieceLocal(ring, placementCm) {
        // Manufacturing glass_hole_local_mm is piece-local (see glass_hole_ring_mm /
        // opening_board_rect). Session outline_mm is usable-sheet, so lift once.
        const local = cloneRing(ring);
        if (!local) return null;
        const ox = (Number(placementCm && placementCm.x) || 0) * 10;
        const oy = (Number(placementCm && placementCm.y) || 0) * 10;
        return local.map((point) => [point[0] + ox, point[1] + oy]);
    }

    function holesFromRelatedGeometry(related) {
        // Parametric / DXF finished_outline holes are already usable-sheet mm.
        const outline = (related || []).find((element) => (
            element
            && element.kind === "finished_outline"
            && element.geometry
            && Array.isArray(element.geometry.holes)
            && element.geometry.holes.length
            && Array.isArray(element.geometry.holes[0])
            && element.geometry.holes[0].length >= 3
        ));
        if (!outline) return null;
        return outline.geometry.holes
            .map((hole) => cloneRing(hole))
            .filter(Boolean);
    }

    function resolveSessionHoleMm(piece, related) {
        const fromGeometry = holesFromRelatedGeometry(related);
        if (fromGeometry && fromGeometry.length) {
            // One authoritative Glass opening in session (matches current move/rotate APIs).
            return fromGeometry[0];
        }
        return usableSheetHoleFromPieceLocal(
            piece && piece.glass_hole_local_mm,
            piece && piece.placement_cm
        );
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

    function standardBoardDimsMm(projection) {
        const board = (projection && projection.board) || {};
        const fullW = Number(board.full_width_cm);
        const fullH = Number(board.full_length_cm);
        if (!(fullW > 0) || !(fullH > 0)) return null;
        const trimFallback = Number(board.trim_cm) || 0;
        const trimXRaw = board.applied_trim_width_cm;
        const trimYRaw = board.applied_trim_length_cm;
        const trimX = (trimXRaw == null || trimXRaw === "") ? trimFallback : Number(trimXRaw);
        const trimY = (trimYRaw == null || trimYRaw === "") ? trimFallback : Number(trimYRaw);
        let usableW = Number(board.usable_width_cm);
        let usableH = Number(board.usable_length_cm);
        if (!(usableW > 0)) usableW = Math.max(0.1, fullW - (Number(trimX) || 0) * 2);
        if (!(usableH > 0)) usableH = Math.max(0.1, fullH - (Number(trimY) || 0) * 2);
        return {
            width_mm: fullW * 10,
            height_mm: fullH * 10,
            trim_x_mm: (Number(trimX) || 0) * 10,
            trim_y_mm: (Number(trimY) || 0) * 10,
            usable_width_mm: usableW * 10,
            usable_length_mm: usableH * 10,
        };
    }

    function nextUnusedSheetNo(session) {
        const numbers = Object.keys((session && session.boards) || {})
            .map((key) => Number(key))
            .filter((number) => Number.isFinite(number) && number > 0);
        return (numbers.length ? Math.max(...numbers) : 0) + 1;
    }

    function boardOccupies(board, originX, originY, widthMm, heightMm) {
        const ax1 = Number(board.origin_x_mm) || 0;
        const ay1 = (Number(board.origin_y_mm) || 0) - (Number(board.title_band_mm) || TITLE_BAND_MM);
        const ax2 = ax1 + (Number(board.width_mm) || 0);
        const ay2 = (Number(board.origin_y_mm) || 0) + (Number(board.height_mm) || 0);
        const bx1 = originX;
        const by1 = originY - TITLE_BAND_MM;
        const bx2 = originX + widthMm;
        const by2 = originY + heightMm;
        return !(bx2 <= ax1 || bx1 >= ax2 || by2 <= ay1 || by1 >= ay2);
    }

    function outsidePieceOverlaps(session, originX, originY, widthMm, heightMm) {
        const MoveGeometry = window.AlmdinaBoardEditor && window.AlmdinaBoardEditor.MoveGeometry;
        if (!MoveGeometry || typeof MoveGeometry.footprint !== "function") return false;
        const bx1 = originX;
        const by1 = originY - TITLE_BAND_MM;
        const bx2 = originX + widthMm;
        const by2 = originY + heightMm;
        return Object.values((session && session.pieces) || {}).some((piece) => {
            if (piece.distribution === "excluded") return false;
            if (piece.sheet_no != null && piece.sheet_no !== "") return false;
            const fp = MoveGeometry.footprint(piece);
            if (!fp || !fp.bounds) return false;
            const ax1 = fp.bounds.x;
            const ay1 = fp.bounds.y;
            const ax2 = ax1 + fp.bounds.w;
            const ay2 = ay1 + fp.bounds.h;
            return !(bx2 <= ax1 || bx1 >= ax2 || by2 <= ay1 || by1 >= ay2);
        });
    }

    function freeBoardOrigin(session, widthMm, heightMm) {
        const gap = 48;
        const boards = Object.values((session && session.boards) || {});
        if (!boards.length) return { x: 0, y: TITLE_BAND_MM };
        let maxRight = 0;
        let maxBottom = 0;
        boards.forEach((board) => {
            maxRight = Math.max(maxRight, (Number(board.origin_x_mm) || 0) + (Number(board.width_mm) || 0));
            maxBottom = Math.max(
                maxBottom,
                (Number(board.origin_y_mm) || 0) + (Number(board.height_mm) || 0)
            );
        });
        const candidates = [
            { x: maxRight + gap, y: TITLE_BAND_MM },
            { x: 0, y: maxBottom + gap + TITLE_BAND_MM },
            { x: maxRight + gap, y: maxBottom + gap + TITLE_BAND_MM },
        ];
        for (let index = 0; index < candidates.length; index += 1) {
            const candidate = candidates[index];
            const blocked = boards.some((board) => boardOccupies(
                board,
                candidate.x,
                candidate.y,
                widthMm,
                heightMm
            )) || outsidePieceOverlaps(session, candidate.x, candidate.y, widthMm, heightMm);
            if (!blocked) return candidate;
        }
        return { x: maxRight + gap, y: maxBottom + gap + TITLE_BAND_MM };
    }

    function addFullBoard(session, projection) {
        const dims = standardBoardDimsMm(projection);
        if (!dims) return { ok: false, code: "standard_board_unavailable" };
        const next = clone(session);
        const sheetNo = nextUnusedSheetNo(next);
        const origin = freeBoardOrigin(next, dims.width_mm, dims.height_mm);
        next.boards[String(sheetNo)] = {
            sheet_no: sheetNo,
            origin_x_mm: origin.x,
            origin_y_mm: origin.y,
            width_mm: dims.width_mm,
            height_mm: dims.height_mm,
            trim_x_mm: dims.trim_x_mm,
            trim_y_mm: dims.trim_y_mm,
            usable_width_mm: dims.usable_width_mm,
            usable_length_mm: dims.usable_length_mm,
            title_band_mm: TITLE_BAND_MM,
            rotation_deg: 0,
            flip_h: false,
            flip_v: false,
            mirrored: false,
            user_moved: false,
            editor_origin: "full_board",
            resource_kind: "FULL_BOARD",
        };
        next.standard_board = dims;
        return { ok: true, session: next, sheet_no: sheetNo };
    }

    function classifyPiece(session, pieceKey, resourceKind, parties) {
        const next = clone(session);
        const piece = next.pieces && next.pieces[pieceKey];
        if (!piece) return { ok: false, code: "unknown_piece" };
        const kind = String(resourceKind || "").trim().toUpperCase();
        if (kind !== "FULL_BOARD" && kind !== "OFFCUT") {
            return { ok: false, code: "invalid_offcut_classification" };
        }
        piece.resource_kind = kind;
        if (kind === "FULL_BOARD") {
            piece.offcut_source_party = "UNASSIGNED";
            piece.offcut_execution_party = "UNASSIGNED";
        } else {
            const source = String((parties && parties.source_party) || "UNASSIGNED").trim().toUpperCase();
            const execution = String((parties && parties.execution_party) || "UNASSIGNED").trim().toUpperCase();
            const allowed = new Set([
                "UNASSIGNED|UNASSIGNED",
                "CUSTOMER|FACTORY",
                "CUSTOMER|CUSTOMER",
                "FACTORY|FACTORY",
            ]);
            const key = `${source}|${execution}`;
            if (!allowed.has(key)) {
                return { ok: false, code: "invalid_offcut_classification" };
            }
            piece.offcut_source_party = source;
            piece.offcut_execution_party = execution;
        }
        return { ok: true, session: next, piece_key: pieceKey };
    }

    function boardCompositionKind(session, sheetNo) {
        const pieces = Object.values((session && session.pieces) || {}).filter((piece) => (
            piece.distribution !== "excluded"
            && piece.sheet_no != null
            && piece.sheet_no !== ""
            && Number(piece.sheet_no) === Number(sheetNo)
        ));
        if (!pieces.length) return "empty";
        const kinds = new Set(pieces.map((piece) => (
            String(piece.resource_kind || "FULL_BOARD").toUpperCase() === "OFFCUT"
                ? "OFFCUT"
                : "GEOMETRY"
        )));
        if (kinds.size > 1) return "mixed";
        return kinds.has("OFFCUT") ? "OFFCUT" : "GEOMETRY";
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
        const standardBoard = standardBoardDimsMm(projection);

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
                flip_h: false,
                flip_v: false,
                mirrored: false,
                user_moved: false,
                editor_origin: null,
                resource_kind: String(sheet.resource_kind || "FULL_BOARD").toUpperCase(),
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
            // Fail closed: proven means the value is trusted; allow_rotation is permission.
            const allowProven = (
                piece.allow_rotation_proven === true
                || piece.allow_rotation_proven === 1
                || piece.allow_rotation_proven === "1"
            );
            const allowRotation = allowProven && (
                piece.allow_rotation === true
                || piece.allow_rotation === 1
                || piece.allow_rotation === "1"
            );
            // Prefer finished_outline geometry; fall back to trusted CNC-raw placement rect.
            let resolvedOutline = outlineMm;
            if (
                (!resolvedOutline || resolvedOutline.length < 3)
                && String(piece.geometry_source || "") === "cnc_raw_rect"
            ) {
                const w = (Number(placement.w) || 0) * 10;
                const h = (Number(placement.h) || 0) * 10;
                const x = (Number(placement.x) || 0) * 10;
                const y = (Number(placement.y) || 0) * 10;
                if (w > 0 && h > 0) {
                    resolvedOutline = [[x, y], [x + w, y], [x + w, y + h], [x, y + h]];
                }
            }
            const sessionHole = resolveSessionHoleMm(piece, related);
            const sessionPiece = {
                piece_key: key,
                piece_id: pieceId,
                piece_instance_id: instanceId,
                label: piece.label || instanceId,
                sheet_no: piece.sheet_no == null ? null : Number(piece.sheet_no),
                local_x_mm: (Number(placement.x) || 0) * 10,
                local_y_mm: (Number(placement.y) || 0) * 10,
                placement_cm: clone(placement),
                outline_mm: resolvedOutline,
                base_outline_mm: resolvedOutline ? clone(resolvedOutline) : null,
                glass_host_piece_id: piece.glass_host_piece_id == null ? null : Number(piece.glass_host_piece_id),
                glass_host_key: null,
                // Immutable source hosting from the projection; live glass_host_* may detach.
                source_glass_host_piece_id: piece.glass_host_piece_id == null
                    ? null
                    : Number(piece.glass_host_piece_id),
                source_glass_host_key: null,
                // Session stores the hole in the same usable-sheet frame as outline_mm.
                glass_hole_local_mm: sessionHole,
                base_hole_mm: sessionHole ? clone(sessionHole) : null,
                editable,
                block_reason: !instanceId
                    ? "missing_piece_instance_id"
                    : (specialBlocked
                        ? "special_geometry_unavailable"
                        : (geometryOk ? null : "incomplete_geometry")),
                // Session edit angle from the as-loaded pose (not source grain).
                rotation_deg: 0,
                flip_h: false,
                flip_v: false,
                mirrored: false,
                source_rotated_dims: Boolean(piece.source_rotated_dims || placement.rotated),
                source_orientation_applied: piece.source_orientation_applied !== false,
                apply_rotated_to_geometry: false,
                allow_rotation: allowProven ? allowRotation : false,
                allow_rotation_proven: Boolean(allowProven),
                piece_type: piece.piece_type || "",
                resource_kind: null,
                offcut_source_party: String(piece.offcut_source_party || "UNASSIGNED").toUpperCase() || "UNASSIGNED",
                offcut_execution_party: String(piece.offcut_execution_party || "UNASSIGNED").toUpperCase()
                    || "UNASSIGNED",
                geometry_source: piece.geometry_source || "",
                exact_geometry: Boolean(piece.exact_geometry),
                special_representation: piece.special_representation || null,
            };
            {
                const explicit = String(piece.resource_kind || "").trim().toUpperCase();
                const sheetMeta = sheets.find((row) => Number(row.sheet_no) === Number(piece.sheet_no));
                const inherited = String((sheetMeta && sheetMeta.resource_kind) || "").trim().toUpperCase();
                if (explicit === "OFFCUT" || explicit === "FULL_BOARD") {
                    sessionPiece.resource_kind = explicit;
                } else if (inherited === "OFFCUT") {
                    sessionPiece.resource_kind = "OFFCUT";
                } else {
                    sessionPiece.resource_kind = "FULL_BOARD";
                }
                if (sessionPiece.resource_kind !== "OFFCUT") {
                    sessionPiece.offcut_source_party = "UNASSIGNED";
                    sessionPiece.offcut_execution_party = "UNASSIGNED";
                }
            }
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
            piece.source_glass_host_key = piece.glass_host_key;
        });
        Object.values(pieceMap).forEach((piece) => {
            if (piece.source_glass_host_piece_id == null) return;
            if (piece.source_glass_host_key) return;
            const host = Object.values(pieceMap).find(
                (row) => Number(row.piece_id) === Number(piece.source_glass_host_piece_id)
            );
            piece.source_glass_host_key = host ? host.piece_key : null;
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
            standard_board: standardBoard,
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
            const row = {
                piece_instance_id: String(piece.piece_instance_id || ""),
                sheet_no: piece.sheet_no == null || piece.sheet_no === "" ? null : Number(piece.sheet_no),
                local_x_mm: round4(piece.local_x_mm),
                local_y_mm: round4(piece.local_y_mm),
                rotation_deg: round4(piece.rotation_deg),
                flip_h: piece.flip_h === true,
                flip_v: piece.flip_v === true,
                mirrored: piece.mirrored === true,
                distribution: excluded ? "excluded" : "active",
                exclusion_reason: excluded ? (piece.exclusion_reason || null) : null,
                glass_host_piece_id: piece.glass_host_piece_id == null || piece.glass_host_piece_id === ""
                    ? null
                    : Number(piece.glass_host_piece_id),
                resource_kind: String(piece.resource_kind || "FULL_BOARD").toUpperCase(),
                offcut_source_party: String(piece.offcut_source_party || "UNASSIGNED").toUpperCase(),
                offcut_execution_party: String(piece.offcut_execution_party || "UNASSIGNED").toUpperCase(),
            };
            if (row.resource_kind !== "OFFCUT") {
                row.resource_kind = "FULL_BOARD";
                row.offcut_source_party = "UNASSIGNED";
                row.offcut_execution_party = "UNASSIGNED";
            }
            return row;
        });
        const boards = Object.keys((session && session.boards) || {})
            .sort((left, right) => Number(left) - Number(right))
            .map((key) => {
                const board = session.boards[key];
                const row = {
                    sheet_no: Number(board.sheet_no != null ? board.sheet_no : key),
                    origin_x_mm: round4(board.origin_x_mm),
                    origin_y_mm: round4(board.origin_y_mm),
                    user_moved: board.user_moved === true,
                };
                if (board.editor_origin === "full_board") {
                    row.editor_origin = "full_board";
                }
                return row;
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
        const TransformGeometry = editor.TransformGeometry;
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
            next.pieces[key].flip_h = false;
            next.pieces[key].flip_v = false;
            next.pieces[key].mirrored = false;
        });
        rows.forEach((row) => {
            const key = byInstance[String(row.piece_instance_id)];
            if (TransformGeometry && typeof TransformGeometry.applyDraftParityToEntry === "function") {
                TransformGeometry.applyDraftParityToEntry(next.pieces[key], row);
            }
            const angle = Number(row.rotation_deg) || 0;
            if (Math.abs(angle - Number(next.pieces[key].rotation_deg || 0)) < 1e-4) return;
            const rotated = RotationGeometry.previewPieceRotation(next, key, angle);
            next.pieces[key] = rotated.pieces[key];
            next.pieces[key].flip_h = row.flip_h === true;
            next.pieces[key].flip_v = row.flip_v === true;
            next.pieces[key].mirrored = row.mirrored === true;
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
            if (row.resource_kind != null && row.resource_kind !== "") {
                const kind = String(row.resource_kind).toUpperCase();
                piece.resource_kind = kind === "OFFCUT" ? "OFFCUT" : "FULL_BOARD";
                if (piece.resource_kind === "OFFCUT") {
                    piece.offcut_source_party = String(row.offcut_source_party || "UNASSIGNED").toUpperCase();
                    piece.offcut_execution_party = String(row.offcut_execution_party || "UNASSIGNED").toUpperCase();
                } else {
                    piece.offcut_source_party = "UNASSIGNED";
                    piece.offcut_execution_party = "UNASSIGNED";
                }
            }
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
        // Defective begin-from-source drafts wrote every board at the same
        // origin. Keep the grid from buildFromProjection instead of stacking.
        // Do not touch deliberately user-moved boards or spaced saved layouts.
        const collapsedDefaults = boardsShareCollapsedDefaultOrigin(layout.boards);
        const dims = next.standard_board || null;
        (layout.boards || []).forEach((board) => {
            let target = next.boards[String(board.sheet_no)];
            if (!target && board.editor_origin === "full_board") {
                if (!dims) return;
                target = {
                    sheet_no: Number(board.sheet_no),
                    origin_x_mm: Number(board.origin_x_mm) || 0,
                    origin_y_mm: Number(board.origin_y_mm) || TITLE_BAND_MM,
                    width_mm: dims.width_mm,
                    height_mm: dims.height_mm,
                    trim_x_mm: dims.trim_x_mm,
                    trim_y_mm: dims.trim_y_mm,
                    usable_width_mm: dims.usable_width_mm,
                    usable_length_mm: dims.usable_length_mm,
                    title_band_mm: TITLE_BAND_MM,
                    rotation_deg: 0,
                    flip_h: false,
                    flip_v: false,
                    mirrored: false,
                    user_moved: board.user_moved === true,
                    editor_origin: "full_board",
                    resource_kind: "FULL_BOARD",
                };
                next.boards[String(board.sheet_no)] = target;
            }
            if (!target) return;
            if (!collapsedDefaults) {
                target.origin_x_mm = Number(board.origin_x_mm) || 0;
                target.origin_y_mm = Number(board.origin_y_mm) || 0;
            }
            target.user_moved = board.user_moved === true;
            if (board.editor_origin === "full_board") {
                target.editor_origin = "full_board";
            }
        });
        return { ok: true, session: next };
    }

    function boardsShareCollapsedDefaultOrigin(boards) {
        if (!Array.isArray(boards) || boards.length < 2) return false;
        if (boards.some((board) => board && board.user_moved === true)) return false;
        const x0 = Number(boards[0].origin_x_mm) || 0;
        const y0 = Number(boards[0].origin_y_mm) || 0;
        return boards.every((board) => (
            Math.abs((Number(board.origin_x_mm) || 0) - x0) < 1e-6
            && Math.abs((Number(board.origin_y_mm) || 0) - y0) < 1e-6
        ));
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
            const code = String((response && response.code) || "failed");
            const conflict = code === "source_conflict" || code === "version_conflict";
            return {
                session,
                draftVersion,
                savedFingerprint,
                saveState: conflict ? "conflict" : "failed",
                saveConflictCode: conflict ? code : null,
                saveInFlight: false,
            };
        }
        const current = distributionFingerprint(session);
        return {
            session,
            draftVersion: Number(response.draft_version) || draftVersion,
            savedFingerprint: sentFingerprint,
            saveState: current === sentFingerprint ? "saved" : "dirty",
            saveConflictCode: null,
            saveInFlight: false,
        };
    }

    window.AlmdinaBoardEditor = window.AlmdinaBoardEditor || {};
    window.AlmdinaBoardEditor.SessionDocument = Object.freeze({
        resolveSessionHoleMm,
        usableSheetHoleFromPieceLocal,
        standardBoardDimsMm,
        addFullBoard,
        classifyPiece,
        boardCompositionKind,
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
        boardsShareCollapsedDefaultOrigin,
        settleDraftSave,
        settleReview,
        TITLE_BAND_MM,
    });
})();
