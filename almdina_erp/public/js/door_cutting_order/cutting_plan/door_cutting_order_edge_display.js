(() => {
    "use strict";

    // Pure cutting-plan display contract. Callers pass the default edge type
    // explicitly. A non-empty type name is custom only when it differs from
    // that default. An empty override inherits the default and stays solid.

    if (window.AlmdinaEdgeDisplay) return;

    const EDGE_BAND_DEFAULT_COLOR = "#d00000";
    const EDGE_BAND_CUSTOM_COLOR = "#1d4ed8";
    const EDGE_BAND_CUSTOM_DASHARRAY = "5px 2.5px 1.5px 2.5px";
    const EDGE_BAND_CUSTOM_DASH = "5 2.5 1.5 2.5";
    const EDGE_STROKE_PX = 3;
    const EDGE_INSET_PX = 3;
    const EDGE_SPAN = 66.666;
    const BOARD_TITLE_PX = 11.5;
    const BOARD_STATS_PX = 9;
    const BOARD_ORIGINAL_EDGE_PX = 9;

    const EDGE_SIDE_OVERRIDE = Object.freeze({
        long_right: "edge_long_right_type_override",
        long_left: "edge_long_left_type_override",
        width_top: "edge_width_top_type_override",
        width_bottom: "edge_width_bottom_type_override",
    });
    const EDGE_SIDE_SELECTED = Object.freeze({
        long_right: "edge_long_right",
        long_left: "edge_long_left",
        width_top: "edge_width_top",
        width_bottom: "edge_width_bottom",
    });

    function num(value) {
        if (value === null || value === undefined) return 0;
        return parseFloat(String(value).replace(/,/g, "")) || 0;
    }

    function hasOwn(source, key) {
        return Boolean(source) && Object.prototype.hasOwnProperty.call(source, key);
    }

    function edgeTypeIsNonDefault(effectiveType, defaultType) {
        const effective = String(effectiveType || "").trim();
        const fallback = String(defaultType || "").trim();
        if (!effective) return false;
        return effective !== fallback;
    }

    function effectiveSideEdgeType(piece, side, defaultType) {
        if (!piece || !EDGE_SIDE_SELECTED[side] || !piece[EDGE_SIDE_SELECTED[side]]) return "";
        const override = String(piece[EDGE_SIDE_OVERRIDE[side]] || "").trim();
        return override || String(defaultType || "").trim();
    }

    function sideIsCustom(piece, side, defaultType) {
        return edgeTypeIsNonDefault(
            effectiveSideEdgeType(piece, side, defaultType),
            defaultType
        );
    }

    function breakIsCustom(piece, defaultType) {
        if (!piece || !(piece.edge_break || piece.edge_break_only)) return false;
        const fallback = String(defaultType || "").trim();
        const effective = String(piece.edge_type || "").trim() || fallback;
        return edgeTypeIsNonDefault(effective, fallback);
    }

    function mapSemanticSidesToDisplay(semantic, piece, geometryModel) {
        let left = semantic.long_left ? 1 : 0;
        let right = semantic.long_right ? 1 : 0;
        let top = semantic.width_top ? 1 : 0;
        let bottom = semantic.width_bottom ? 1 : 0;
        if (geometryModel && geometryModel.source === "dxf"
            && Number.isInteger(piece.rotation_quarter_turns)) {
            const turns = ((piece.rotation_quarter_turns % 4) + 4) % 4;
            for (let turn = 0; turn < turns; turn += 1) {
                const previous = { left, top, right, bottom };
                left = previous.bottom;
                top = previous.left;
                right = previous.top;
                bottom = previous.right;
            }
        } else if (piece && piece.rotated) {
            top = semantic.long_left ? 1 : 0;
            bottom = semantic.long_right ? 1 : 0;
            right = semantic.width_top ? 1 : 0;
            left = semantic.width_bottom ? 1 : 0;
        }
        return {
            left,
            right,
            top,
            bottom,
            edgeBreak: semantic.edgeBreak ? 1 : 0,
            edgeBreakOnly: semantic.edgeBreakOnly ? 1 : 0,
        };
    }

    function pieceEdgeFlags(piece, geometryModel) {
        const source = piece || {};
        return mapSemanticSidesToDisplay({
            long_left: source.edge_long_left,
            long_right: source.edge_long_right,
            width_top: source.edge_width_top,
            width_bottom: source.edge_width_bottom,
            edgeBreak: source.edge_break,
            edgeBreakOnly: source.edge_break_only,
        }, source, geometryModel || null);
    }

    function pieceEdgeCustomFlags(piece, defaultType, geometryModel) {
        const source = piece || {};
        return mapSemanticSidesToDisplay({
            long_left: sideIsCustom(source, "long_left", defaultType),
            long_right: sideIsCustom(source, "long_right", defaultType),
            width_top: sideIsCustom(source, "width_top", defaultType),
            width_bottom: sideIsCustom(source, "width_bottom", defaultType),
            edgeBreak: breakIsCustom(source, defaultType),
            edgeBreakOnly: breakIsCustom(source, defaultType),
        }, source, geometryModel || null);
    }

    function bandPaint(custom) {
        if (custom) {
            return {
                custom: true,
                color: EDGE_BAND_CUSTOM_COLOR,
                dash: EDGE_BAND_CUSTOM_DASH,
                dashCss: EDGE_BAND_CUSTOM_DASHARRAY,
                widthPx: EDGE_STROKE_PX,
                insetPx: EDGE_INSET_PX,
                span: EDGE_SPAN,
            };
        }
        return {
            custom: false,
            color: EDGE_BAND_DEFAULT_COLOR,
            dash: "",
            dashCss: "",
            widthPx: EDGE_STROKE_PX,
            insetPx: EDGE_INSET_PX,
            span: EDGE_SPAN,
        };
    }

    function resolvedTrimCm(plan, sheet, axis) {
        const trimKey = axis === "x" ? "applied_trim_width_cm" : "applied_trim_length_cm";
        const fullKey = axis === "x" ? "full_width_cm" : "full_length_cm";
        const usableKey = axis === "x" ? "usable_width_cm" : "usable_length_cm";
        const sizeKey = axis === "x" ? "w" : "h";
        const planFullKey = axis === "x" ? "full_board_width_cm" : "full_board_length_cm";
        const planUsableKey = axis === "x" ? "usable_board_width_cm" : "usable_board_length_cm";
        if (hasOwn(sheet, trimKey)) return Math.max(0, num(sheet[trimKey]));
        const sheetFull = num(sheet && sheet[fullKey]);
        const sheetUsable = num(sheet && sheet[usableKey]) || num(sheet && sheet[sizeKey]);
        if (sheetFull > sheetUsable && sheetUsable > 0) return (sheetFull - sheetUsable) / 2;
        if (hasOwn(plan, trimKey)) return Math.max(0, num(plan[trimKey]));
        const planFull = num(plan && plan[planFullKey]);
        const planUsable = num(plan && plan[planUsableKey]);
        if (planFull > planUsable && planUsable > 0) return (planFull - planUsable) / 2;
        return Math.max(0, num(plan && plan.trim_cm));
    }

    function roundMm(value) {
        return Math.round(num(value) * 1000) / 1000;
    }

    function physicalMarginsMm(plan, sheet) {
        const pieces = (sheet && sheet.pieces) || [];
        const trimW = resolvedTrimCm(plan, sheet, "x");
        const trimH = resolvedTrimCm(plan, sheet, "y");
        const fullW = num(sheet && sheet.full_width_cm) || num(plan && plan.full_board_width_cm);
        const fullH = num(sheet && sheet.full_length_cm) || num(plan && plan.full_board_length_cm);
        if (!pieces.length) return { left: 0, right: 0, top: 0, bottom: 0 };
        const minX = Math.min(...pieces.map((piece) => num(piece.x)));
        const maxX = Math.max(...pieces.map((piece) => num(piece.x) + num(piece.w)));
        const minY = Math.min(...pieces.map((piece) => num(piece.y)));
        const maxY = Math.max(...pieces.map((piece) => num(piece.y) + num(piece.h)));
        return {
            left: roundMm((trimW + minX) * 10),
            right: roundMm((fullW - trimW - maxX) * 10),
            top: roundMm((trimH + minY) * 10),
            bottom: roundMm((fullH - trimH - maxY) * 10),
        };
    }

    function originalEdges(plan, sheet) {
        const margins = physicalMarginsMm(plan, sheet);
        return ["right", "left", "top", "bottom"].filter((edge) => Math.abs(margins[edge]) <= 0.001);
    }

    function screenFontMm(px, scale) {
        return Number(px) / Math.max(Number(scale) || 0, 0.02);
    }

    window.AlmdinaEdgeDisplay = Object.freeze({
        EDGE_BAND_DEFAULT_COLOR,
        EDGE_BAND_CUSTOM_COLOR,
        EDGE_BAND_CUSTOM_DASHARRAY,
        EDGE_BAND_CUSTOM_DASH,
        EDGE_STROKE_PX,
        EDGE_INSET_PX,
        EDGE_SPAN,
        BOARD_TITLE_PX,
        BOARD_STATS_PX,
        BOARD_ORIGINAL_EDGE_PX,
        edgeTypeIsNonDefault,
        effectiveSideEdgeType,
        sideIsCustom,
        breakIsCustom,
        mapSemanticSidesToDisplay,
        pieceEdgeFlags,
        pieceEdgeCustomFlags,
        bandPaint,
        resolvedTrimCm,
        physicalMarginsMm,
        originalEdges,
        screenFontMm,
    });
})();
