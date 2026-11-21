(() => {
    "use strict";

    const BOARD = "board";
    const DRAWING = "drawing";

    const FUTURE_TOOLS = Object.freeze([
        Object.freeze({ id: "select", labelKey: "Select tool" }),
        Object.freeze({ id: "polyline", labelKey: "Polyline" }),
        Object.freeze({ id: "shapes", labelKey: "Shapes" }),
        Object.freeze({ id: "pen", labelKey: "Pen" }),
        Object.freeze({ id: "text", labelKey: "Text" }),
        Object.freeze({ id: "node_edit", labelKey: "Node edit" }),
        Object.freeze({ id: "snap", labelKey: "Snap tool" }),
        Object.freeze({ id: "reference_image", labelKey: "Reference image" }),
    ]);

    function normalize(mode) {
        return mode === DRAWING ? DRAWING : BOARD;
    }

    function layoutCommandsAllowed(mode) {
        return normalize(mode) !== DRAWING;
    }

    function distributionGesturesAllowed(snapshotOrMode) {
        const mode = snapshotOrMode && typeof snapshotOrMode === "object"
            ? snapshotOrMode.editorMode
            : snapshotOrMode;
        return layoutCommandsAllowed(mode);
    }

    function finiteNumber(value) {
        if (typeof value === "boolean" || value == null || value === "") return null;
        const number = Number(value);
        return Number.isFinite(number) && number > 0 ? number : null;
    }

    function selectedKeys(session, keys) {
        const listed = Array.isArray(keys) ? keys.filter((key) => session && session.pieces && session.pieces[key]) : [];
        return listed;
    }

    function projectionPiece(projection, piece) {
        const rows = (projection && projection.pieces) || [];
        return rows.find((row) => {
            if (!row) return false;
            if (piece.piece_instance_id && row.piece_instance_id === piece.piece_instance_id) return true;
            return piece.piece_id != null && Number(row.piece_id) === Number(piece.piece_id);
        }) || null;
    }

    function blankSize(piece, projected) {
        const widthCm = finiteNumber(projected && (projected.original_w != null ? projected.original_w : projected.width_cm));
        const lengthCm = finiteNumber(projected && (projected.original_h != null ? projected.original_h : projected.length_cm));
        if (widthCm == null || lengthCm == null) {
            return { widthCm: null, lengthCm: null };
        }
        return { widthCm, lengthCm };
    }

    function emptyTarget(status, messageKey) {
        return {
            status,
            pieceKey: null,
            pieceInstanceId: "",
            label: "",
            widthCm: null,
            lengthCm: null,
            canEdit: false,
            messageKey: messageKey || "",
        };
    }

    function resolveDrawingTarget(input) {
        const source = input || {};
        const mode = normalize(source.mode);
        if (mode !== DRAWING) return emptyTarget("board", "");
        const session = source.session;
        const keys = selectedKeys(session, source.selectedPieceKeys);
        if (!keys.length) {
            return emptyTarget("none", "Select a special piece to start drawing.");
        }
        if (keys.length > 1) {
            return emptyTarget("multiple", "Select one special piece. Group drawing is not available.");
        }
        const piece = session.pieces[keys[0]];
        const projected = projectionPiece(source.projection, piece);
        const pieceType = String(piece.piece_type || (projected && projected.piece_type) || "");
        const size = blankSize(piece, projected);
        const identity = {
            pieceKey: piece.piece_key,
            pieceInstanceId: String(piece.piece_instance_id || ""),
            label: String(piece.label || piece.piece_instance_id || ""),
            widthCm: size.widthCm,
            lengthCm: size.lengthCm,
        };
        if (pieceType !== "Special") {
            return {
                status: "regular",
                ...identity,
                canEdit: false,
                messageKey: "Geometric drawing is available for special pieces only.",
            };
        }
        const canEdit = source.canEditLayout === true;
        return {
            status: "special",
            ...identity,
            canEdit,
            messageKey: canEdit
                ? "This special piece is selected for drawing."
                : "Drawing edits stay unavailable while this layout is read-only.",
        };
    }

    window.AlmdinaBoardEditor = window.AlmdinaBoardEditor || {};
    window.AlmdinaBoardEditor.EditorMode = Object.freeze({
        BOARD,
        DRAWING,
        futureTools: FUTURE_TOOLS,
        normalize,
        layoutCommandsAllowed,
        distributionGesturesAllowed,
        resolveDrawingTarget,
    });
})();
