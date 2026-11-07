(() => {
    "use strict";

    // Screen contract copied from door_cutting_order_cutting_plan_renderer.js
    // (in-app preview, not the print stylesheet). Presentation only.

    const BOARD_STROKE = "#111111";
    const BOARD_FILL = "#ffffff";
    const HATCH = "rgba(71,85,105,.18)";
    const RECT_FILL = "#e4f5ff";
    const SHAPED_FILL = "#fff0c7";
    const SHAPED_STROKE = "#8a5700";
    const EXACT_SPECIAL_FILL = "#ffe5ad";
    const SPECIAL_STROKE = "#7a4c13";
    const EDGE_DEFAULT = "#d00000";
    const EDGE_CUSTOM = "#1d4ed8";
    const EDGE_DASH = "5 2.5 1.5 2.5";
    const LINER = "#1d6fbf";
    const BACK_GROOVE = "#2a7d4f";
    const HANDLE = "#c45c12";
    const HANDLE_FILL = "rgba(196,92,18,0.16)";
    const DOUBLE = "#5a2d82";
    const FULL_DOUBLE = "#1a5f4a";
    const EDGE_SPAN = 66.666;
    const EDGE_START = (100 - EDGE_SPAN) / 2;

    function round(value, decimals) {
        const factor = 10 ** decimals;
        const number = Number(value);
        if (!Number.isFinite(number)) return 0;
        return Math.round(number * factor) / factor;
    }

    function isShaped(outer, holes) {
        const ring = Array.isArray(outer) ? outer : [];
        const holeCount = Array.isArray(holes) ? holes.length : 0;
        if (holeCount || ring.length !== 4) return true;
        return false;
    }

    function piecePaint(role, options) {
        const shaped = Boolean(options && options.shaped);
        const exactSpecial = Boolean(options && options.exactSpecial);
        const kind = String(role || "regular");
        if (kind === "special" && exactSpecial) {
            return { fill: EXACT_SPECIAL_FILL, stroke: SPECIAL_STROKE, strokeWidth: 2 };
        }
        if (kind === "special" && !shaped) {
            return { fill: "url(#abe-special-fill)", stroke: SPECIAL_STROKE, strokeWidth: 2 };
        }
        if (shaped || kind === "l_shaped" || kind === "clipped_corner") {
            return { fill: SHAPED_FILL, stroke: SHAPED_STROKE, strokeWidth: 2 };
        }
        return { fill: RECT_FILL, stroke: BOARD_STROKE, strokeWidth: 1 };
    }

    function overlayPaint(kind) {
        const key = String(kind || "");
        if (key === "liner") return { stroke: LINER, fill: "none", dash: "3 2.2", width: 0.7 };
        if (key === "back_groove") return { stroke: BACK_GROOVE, fill: "none", dash: "3 2.2", width: 0.7 };
        if (key === "recessed_handle_cutout") {
            return { stroke: HANDLE, fill: HANDLE_FILL, dash: "", width: 0.65 };
        }
        return { stroke: "#5c4d2e", fill: "none", dash: "", width: 0.7 };
    }

    function sizeLabel(originalW, originalH, fallbackW, fallbackH) {
        const w = Number(originalW);
        const h = Number(originalH);
        const width = Number.isFinite(w) && w > 0 ? w : Number(fallbackW) || 0;
        const height = Number.isFinite(h) && h > 0 ? h : Number(fallbackH) || 0;
        return `${round(width, 1)}*${round(height, 1)}`;
    }

    function kindBadge(role, exactSpecial) {
        if (role === "special") {
            return exactSpecial ? __("Special door · geometric path") : __("Special door · CNC raw");
        }
        if (role === "l_shaped") return `⌐ ${__("L-shaped corner")}`;
        if (role === "clipped_corner") return `⌑ ${__("Clipped corner")}`;
        return "";
    }

    function sheetWaste(board, pieces) {
        const usableW = Number(board && (board.usable_width_cm || board.full_width_cm)) || 0;
        const usableH = Number(board && (board.usable_length_cm || board.full_length_cm)) || 0;
        const boardArea = (usableW * usableH) / 10000;
        const used = (pieces || []).reduce((sum, piece) => {
            const area = Number(piece && piece.area_m2);
            if (Number.isFinite(area) && area > 0) return sum + area;
            const placement = (piece && piece.placement_cm) || {};
            return sum + ((Number(placement.w) || 0) * (Number(placement.h) || 0)) / 10000;
        }, 0);
        const waste = Math.max(0, boardArea - used);
        const percent = boardArea ? (waste / boardArea) * 100 : 0;
        return {
            pieces: (pieces || []).length,
            waste: round(waste, 3),
            percent: round(percent, 2),
        };
    }

    function defs(scale) {
        const safe = Math.max(Number(scale) || 1, 0.02);
        const step = 8 / safe;
        const width = 1 / safe;
        return `<pattern id="abe-waste-hatch" patternUnits="userSpaceOnUse" width="${step}" height="${step}" patternTransform="rotate(45)">
            <line x1="0" y1="0" x2="0" y2="${step}" stroke="${HATCH}" stroke-width="${width}"/>
        </pattern>
        <linearGradient id="abe-special-fill" x1="0" y1="0" x2="1" y2="1">
            <stop offset="0%" stop-color="#fff2cf"/>
            <stop offset="100%" stop-color="#ffe2a3"/>
        </linearGradient>`;
    }

    window.AlmdinaBoardEditor = window.AlmdinaBoardEditor || {};
    window.AlmdinaBoardEditor.PlanDisplayStyle = Object.freeze({
        BOARD_STROKE,
        BOARD_FILL,
        RECT_FILL,
        SHAPED_FILL,
        SHAPED_STROKE,
        EDGE_DEFAULT,
        EDGE_CUSTOM,
        EDGE_DASH,
        EDGE_START,
        EDGE_SPAN,
        DOUBLE,
        FULL_DOUBLE,
        LINER,
        piecePaint,
        overlayPaint,
        sizeLabel,
        kindBadge,
        sheetWaste,
        isShaped,
        defs,
        round,
    });
})();
