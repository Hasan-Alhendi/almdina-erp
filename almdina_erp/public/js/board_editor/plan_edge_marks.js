(() => {
    "use strict";

    // Display-only edge bands. Manufacturing geometry stays untouched.
    // Rectangle inset matches the cutting-plan screen rule: 3px inside the
    // border, spanning the middle 66.666% of the side.
    // Corner bands call AlmdinaClippedCornerGeometry (the plan resolver).

    const SCREEN_INSET_PX = 3;
    const EDGE_SPAN = 66.666;
    const TARGET_FONT_PX = 10;
    const MIN_FONT_PX = 7;

    function measurementFontMm(shortSideMm, scale) {
        const safe = Math.max(Number(scale) || 0, 0.02);
        const shortPx = Math.max(0, Number(shortSideMm) || 0) * safe;
        let px = TARGET_FONT_PX;
        if (shortPx > 0 && shortPx < TARGET_FONT_PX * 3.2) {
            px = Math.min(TARGET_FONT_PX, shortPx * 0.72);
            if (shortPx >= 16) px = Math.max(MIN_FONT_PX, px);
        }
        return { px, mm: px / safe };
    }

    function insetMm(scale) {
        return SCREEN_INSET_PX / Math.max(Number(scale) || 0, 0.02);
    }

    function rectangleBands(rect, edges, scale) {
        if (!rect || !(rect.w > 0) || !(rect.h > 0) || !edges) return [];
        const inset = Math.min(insetMm(scale), rect.w * 0.2, rect.h * 0.2);
        const start = (100 - EDGE_SPAN) / 200;
        const end = start + EDGE_SPAN / 100;
        const x0 = rect.x + rect.w * start;
        const x1 = rect.x + rect.w * end;
        const y0 = rect.y + rect.h * start;
        const y1 = rect.y + rect.h * end;
        const bands = [];
        const add = (points, custom, side) => bands.push({ points, custom, kind: "edge", side });
        const selected = (side) => Boolean(edges[side] && edges[side].selected);
        const custom = (side) => Boolean(edges[side] && edges[side].custom);
        if (selected("top")) add([[x0, rect.y + inset], [x1, rect.y + inset]], custom("top"), "top");
        if (selected("bottom")) add([[x0, rect.y + rect.h - inset], [x1, rect.y + rect.h - inset]], custom("bottom"), "bottom");
        if (selected("left")) add([[rect.x + inset, y0], [rect.x + inset, y1]], custom("left"), "left");
        if (selected("right")) add([[rect.x + rect.w - inset, y0], [rect.x + rect.w - inset, y1]], custom("right"), "right");
        return bands;
    }

    function remapRotatedEdges(piece) {
        return Object.assign({}, piece, {
            edge_width_top: piece.edge_long_left,
            edge_width_bottom: piece.edge_long_right,
            edge_long_right: piece.edge_width_top,
            edge_long_left: piece.edge_width_bottom,
            edge_width_top_type_override: piece.edge_long_left_type_override || "",
            edge_width_bottom_type_override: piece.edge_long_right_type_override || "",
            edge_long_right_type_override: piece.edge_width_top_type_override || "",
            edge_long_left_type_override: piece.edge_width_bottom_type_override || "",
        });
    }

    function cornerSource(piece, edges, geometrySource) {
        const placement = piece.placement_cm || {};
        const source = Object.assign({}, edges || {}, {
            piece_type: piece.piece_type,
            w: Number(placement.w) || 0,
            h: Number(placement.h) || 0,
            rotated: Boolean(placement.rotated),
            original_w: piece.original_w,
            original_h: piece.original_h,
            width_cm: piece.original_w,
            length_cm: piece.original_h,
            clipped_corner_position: piece.clipped_corner_position,
            clipped_corner_width_cm: piece.clipped_corner_width_cm,
            clipped_corner_length_cm: piece.clipped_corner_length_cm,
            corner_mirrored: piece.corner_mirrored,
            corner_rotation_quarter_turns: piece.corner_rotation_quarter_turns,
        });
        const geometry = window.AlmdinaClippedCornerGeometry;
        if (!geometry) return null;
        if (geometrySource === "persisted_dxf" && typeof geometry.pieceForQuarterTurns === "function") {
            // Integer quarter-turns rename semantic sides onto an already-drawn DXF
            // contour. Missing turns are Board Editor posed copies (or unresolved
            // imports): keep semantic sides — the canvas applies session rotation.
            const raw = source.corner_rotation_quarter_turns;
            const turns = Number(raw);
            const hasImportTurns = (
                raw !== null
                && raw !== undefined
                && raw !== ""
                && Number.isInteger(turns)
                && turns >= 0
                && turns <= 3
            );
            if (hasImportTurns) {
                return geometry.pieceForQuarterTurns(
                    source,
                    source.corner_rotation_quarter_turns,
                    source.corner_mirrored
                ) || null;
            }
            return source;
        }
        if (source.rotated) return remapRotatedEdges(source);
        return source;
    }

    function displayApi() {
        return window.AlmdinaEdgeDisplay || null;
    }

    function customSide(piece, side, defaultType) {
        const display = displayApi();
        if (!display || !piece) return false;
        if (side === "break" || side === "breakOnly") return display.breakIsCustom(piece, defaultType);
        const semantic = {
            top: "width_top",
            bottom: "width_bottom",
            left: "long_left",
            right: "long_right",
        }[side];
        return semantic ? display.sideIsCustom(piece, semantic, defaultType) : false;
    }

    function mapViewPoint(point, rect) {
        return [
            rect.x + (Number(point[0]) / 100) * rect.w,
            rect.y + (Number(point[1]) / 100) * rect.h,
        ];
    }

    function cornerBands(piece, edges, geometrySource, defaultType) {
        const geometry = window.AlmdinaClippedCornerGeometry;
        if (!geometry || typeof geometry.clippedEdgePaths !== "function" || typeof geometry.isCornerCut !== "function") {
            return [];
        }
        const source = cornerSource(piece, edges, geometrySource);
        if (!source || !geometry.isCornerCut(source)) return [];
        if (!(Number(source.clipped_corner_width_cm) > 0) || !(Number(source.clipped_corner_length_cm) > 0)) {
            return [];
        }
        const rect = {
            x: (Number(piece.placement_cm && piece.placement_cm.x) || 0) * 10,
            y: (Number(piece.placement_cm && piece.placement_cm.y) || 0) * 10,
            w: (Number(piece.placement_cm && piece.placement_cm.w) || 0) * 10,
            h: (Number(piece.placement_cm && piece.placement_cm.h) || 0) * 10,
        };
        if (!(rect.w > 0) || !(rect.h > 0)) return [];
        const paths = geometry.clippedEdgePaths(source, 100, 100);
        const bands = [];
        const take = (key, flag, side) => {
            if (!flag || !paths || !Array.isArray(paths[key]) || paths[key].length < 2) return;
            bands.push({
                points: paths[key].map((point) => mapViewPoint(point, rect)),
                custom: customSide(source, side, defaultType),
                kind: "corner-edge",
                side,
            });
        };
        take("top", source.edge_width_top, "top");
        take("bottom", source.edge_width_bottom, "bottom");
        take("left", source.edge_long_left, "left");
        take("right", source.edge_long_right, "right");
        take("break", source.edge_break, "break");
        take("breakOnly", source.edge_break_only, "breakOnly");
        return bands;
    }

    function rectangleState(piece, edges, defaultType, geometrySource) {
        const display = displayApi();
        const subject = Object.assign({}, edges || {}, {
            rotated: Boolean(piece && piece.placement_cm && piece.placement_cm.rotated),
            rotation_quarter_turns: piece && piece.rotation_quarter_turns,
        });
        const model = geometrySource === "persisted_dxf" ? { source: "dxf" } : null;
        if (!display) {
            return { top: {}, bottom: {}, left: {}, right: {} };
        }
        const flags = display.pieceEdgeFlags(subject, model);
        const custom = display.pieceEdgeCustomFlags(subject, defaultType, model);
        return {
            top: { selected: Boolean(flags.top), custom: Boolean(custom.top) },
            bottom: { selected: Boolean(flags.bottom), custom: Boolean(custom.bottom) },
            left: { selected: Boolean(flags.left), custom: Boolean(custom.left) },
            right: { selected: Boolean(flags.right), custom: Boolean(custom.right) },
        };
    }

    function bandsForPiece(piece, edges, scale, geometrySource, defaultType) {
        const type = String((piece && piece.piece_type) || "");
        const geometry = window.AlmdinaClippedCornerGeometry;
        const corner = type === "L-Shaped Corner"
            || type === "Clipped Corner"
            || (geometry && typeof geometry.isCornerCut === "function" && geometry.isCornerCut(piece || {}));
        if (corner) return cornerBands(piece, edges, geometrySource, defaultType);
        const placement = (piece && piece.placement_cm) || {};
        return rectangleBands({
            x: (Number(placement.x) || 0) * 10,
            y: (Number(placement.y) || 0) * 10,
            w: (Number(placement.w) || 0) * 10,
            h: (Number(placement.h) || 0) * 10,
        }, rectangleState(piece, edges, defaultType, geometrySource), scale);
    }

    window.AlmdinaBoardEditor = window.AlmdinaBoardEditor || {};
    window.AlmdinaBoardEditor.PlanEdgeMarks = Object.freeze({
        SCREEN_INSET_PX,
        TARGET_FONT_PX,
        measurementFontMm,
        insetMm,
        rectangleBands,
        cornerBands,
        bandsForPiece,
        remapRotatedEdges,
    });
})();
