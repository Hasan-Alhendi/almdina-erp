(() => {
    "use strict";

    // Canonical cutting-plan renderer shared by the order and shop-floor views.
    function num(value) {
        if (value === null || value === undefined) return 0;
        return parseFloat(String(value).replace(/,/g, "")) || 0;
    }

    function round(value, decimals = 3) {
        const factor = Math.pow(10, decimals);
        return Math.round(num(value) * factor) / factor;
    }

    function escape_html(value) {
        return String(value || "")
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;")
            .replace(/'/g, "&#039;");
    }

    function translate(message, replacements) {
        const locale = window.AlmdinaLocale;
        if (locale && typeof locale.translate === "function") {
            return locale.translate(message, replacements);
        }
        if (typeof __ === "function") {
            return replacements === undefined ? __(message) : __(message, replacements);
        }
        let text = String(message == null ? "" : message);
        if (Array.isArray(replacements)) {
            replacements.forEach((value, index) => {
                text = text.split(`{${index}}`).join(String(value));
            });
        }
        return text;
    }

    function uiDirection() {
        const locale = window.AlmdinaLocale;
        if (locale && typeof locale.direction === "function") {
            const value = locale.direction();
            if (value === "ltr" || value === "rtl") return value;
        }
        const root = typeof document !== "undefined" ? document.documentElement : null;
        const dir = root && root.getAttribute("dir");
        return dir === "ltr" ? "ltr" : "rtl";
    }

    function uiLanguage() {
        const locale = window.AlmdinaLocale;
        if (locale && typeof locale.currentLanguage === "function") {
            const value = String(locale.currentLanguage() || "").trim();
            if (value) return value;
        }
        const root = typeof document !== "undefined" ? document.documentElement : null;
        const lang = root && root.getAttribute("lang");
        return String(lang || "");
    }

    function htmlText(message, replacements) {
        return escape_html(translate(message, replacements));
    }

    const STRATEGY_MESSAGE_IDS = Object.freeze({
        Auto: "Auto",
        "Auto Pro": "Auto Pro",
        "Deep Search": "Deep Search",
        "Optimal Search": "Optimal Search",
        "MaxRects Best Short Side": "MaxRects Best Short Side",
        "MaxRects Best Area": "MaxRects Best Area",
        "MaxRects Bottom Left": "MaxRects Bottom Left",
        "MaxRects Contact Point": "MaxRects Contact Point",
        "MaxRects Width": "MaxRects Width",
        "MaxRects Length": "MaxRects Length",
        "Shelf Horizontal": "Shelf Horizontal",
        "Shelf Vertical": "Shelf Vertical",
        "Shelf First Fit": "Shelf First Fit",
        "Shelf Next Fit": "Shelf Next Fit",
        "Guillotine Short Axis": "Guillotine Short Axis",
        "Guillotine Long Axis": "Guillotine Long Axis",
        "Guillotine Best Area Fit": "Guillotine Best Area Fit",
        "Guillotine Best Short Side Fit": "Guillotine Best Short Side Fit",
        "Guillotine Best Long Side Fit": "Guillotine Best Long Side Fit",
        "Skyline Bottom Left": "Skyline Bottom Left",
        "Skyline Best Fit": "Skyline Best Fit",
    });

    function knownStrategyText(methodKey, methodLabel) {
        const key = String(methodKey ?? "").trim();
        const messageId = key && STRATEGY_MESSAGE_IDS[key];
        if (messageId) return translate(messageId);
        const label = String(methodLabel ?? "").trim();
        if (label) return label;
        return key;
    }

    // Domain nesting depth is capped at 2. Paint nested guests above their Glass
    // hosts so adversarial snapshot order cannot hide doors inside openings.
    const MAX_GLASS_NEST_PAINT_DEPTH = 2;

    function glassNestPaintDepth(piece, piecesById) {
        let depth = 0;
        let hostId = piece && piece.glass_host_piece_id;
        const seen = new Set();
        while (hostId !== undefined && hostId !== null && hostId !== "") {
            const key = String(hostId);
            if (seen.has(key) || depth >= MAX_GLASS_NEST_PAINT_DEPTH) {
                break;
            }
            seen.add(key);
            depth += 1;
            const host = piecesById.get(Number(hostId));
            hostId = host && host.glass_host_piece_id;
        }
        return depth;
    }

    function physicalCutQuantity(row) {
        const extra = window.AlmdinaExtraDoorAddonsUX;
        if (extra && typeof extra.physicalCutQuantity === "function") {
            return extra.physicalCutQuantity(row);
        }
        const qty = Math.max(0, Math.floor(num(row && row.qty)));
        return qty * (Number(row && row.extra_full_door_double) ? 2 : 1);
    }

    function parse_plan(frm) {
        const raw = frm.doc.cutting_plan_json;
        if (!raw) return null;

        if (typeof raw === "object") return raw;

        try {
            return JSON.parse(raw);
        } catch (error) {
            console.error("Invalid cutting_plan_json", error);
            return null;
        }
    }

    // =====================================================
    // Cutting plan rendering
    // =====================================================

    function piece_edge_flags(piece, geometryModel = null) {
        let left = 0;
        let right = 0;
        let top = 0;
        let bottom = 0;
        let edgeBreak = piece.edge_break ? 1 : 0;
        let edgeBreakOnly = piece.edge_break_only ? 1 : 0;

        if (geometryModel && geometryModel.source === "dxf"
            && Number.isInteger(piece.rotation_quarter_turns)) {
            // Imported DXF geometry is already physically oriented. Rotate
            // the original semantic bands only, never its stored contour.
            const turns = ((piece.rotation_quarter_turns % 4) + 4) % 4;
            left = piece.edge_long_left ? 1 : 0;
            right = piece.edge_long_right ? 1 : 0;
            top = piece.edge_width_top ? 1 : 0;
            bottom = piece.edge_width_bottom ? 1 : 0;
            for (let turn = 0; turn < turns; turn += 1) {
                const previous = { left, top, right, bottom };
                left = previous.bottom;
                top = previous.left;
                right = previous.top;
                bottom = previous.right;
            }
        } else if (!piece.rotated) {
            left = piece.edge_long_left ? 1 : 0;
            right = piece.edge_long_right ? 1 : 0;
            top = piece.edge_width_top ? 1 : 0;
            bottom = piece.edge_width_bottom ? 1 : 0;
        } else {
            // 90 degrees clockwise, preserving the physical edge meaning.
            top = piece.edge_long_left ? 1 : 0;
            bottom = piece.edge_long_right ? 1 : 0;
            right = piece.edge_width_top ? 1 : 0;
            left = piece.edge_width_bottom ? 1 : 0;
        }

        return { left, right, top, bottom, edgeBreak, edgeBreakOnly };
    }

    function render_clipped_corner_edge_lines(piece, geometryModel, clipId) {
        const geometry = window.AlmdinaClippedCornerGeometry;
        if (!geometry || typeof geometry.edgeBandSvgMarkup !== "function") return "";
        const isCorner = (
            (typeof geometry.isCornerCut === "function" && geometry.isCornerCut(piece))
            || (typeof geometry.isClipped === "function" && geometry.isClipped(piece))
        );
        if (!isCorner) return "";

        // System plans encode only 0°/90° in `rotated`, and both the outline and
        // the bands are generated from that flag. An imported DXF contour is
        // already in its drawn orientation, so its bands follow the stored
        // quarter-turn and single reflection instead of transforming it again.
        let edgePiece = piece;
        if (geometryModel && geometryModel.source === "dxf") {
            edgePiece = typeof geometry.pieceForQuarterTurns === "function"
                ? geometry.pieceForQuarterTurns(
                    piece,
                    piece.corner_rotation_quarter_turns,
                    piece.corner_mirrored
                )
                : null;
            if (!edgePiece) return "";
        } else if (piece.rotated) {
            edgePiece = {
                ...piece,
                edge_width_top: piece.edge_long_left,
                edge_width_bottom: piece.edge_long_right,
                edge_long_right: piece.edge_width_top,
                edge_long_left: piece.edge_width_bottom,
            };
        }
        const markup = geometry.edgeBandSvgMarkup(edgePiece, 100, 100, { inheritStroke: true });
        if (!markup) return "";
        const pathData = (
            geometryModel
            && geometryModel.geometry
            && geometryModel.geometry.pathData
        ) || "";
        const clipDef = pathData
            ? `<defs><clipPath id="${clipId}"><path d="${pathData}" fill-rule="evenodd" clip-rule="evenodd"/></clipPath></defs>`
            : "";
        const clipAttr = pathData ? ` clip-path="url(#${clipId})"` : "";
        // Same stroke contract as regular-door vector edges in render_piece_edge_lines.
        return `
            <svg class="dco-piece-edge-svg" viewBox="0 0 100 100" preserveAspectRatio="none" aria-hidden="true" style="position:absolute;inset:0;width:100%;height:100%;z-index:3;overflow:hidden;">
                ${clipDef}
                <g${clipAttr} fill="none" stroke="#d00000" stroke-width="3" vector-effect="non-scaling-stroke">${markup}</g>
            </svg>
        `;
    }

    function render_piece_edge_lines(piece, geometryModel = null, clipId = "") {
        const { left, right, top, bottom, edgeBreak, edgeBreakOnly } = piece_edge_flags(piece, geometryModel);
        const geometry = window.AlmdinaClippedCornerGeometry;
        const isCornerPiece = Boolean(
            geometry
            && (
                (typeof geometry.isCornerCut === "function" && geometry.isCornerCut(piece))
                || (typeof geometry.isClipped === "function" && geometry.isClipped(piece))
            )
        );
        if (isCornerPiece && (left || right || top || bottom || edgeBreak || edgeBreakOnly)) {
            return render_clipped_corner_edge_lines(piece, geometryModel, clipId);
        }

        const color = "#d00000";
        const thickness = "3px";
        const inset = "3px";
        const EDGE_LINE_PERCENT = 66.666;
        const EDGE_LINE_START = (100 - EDGE_LINE_PERCENT) / 2;
        let html = "";

        if (geometryModel && geometryModel.vector) {
            const lines = [];
            const end = EDGE_LINE_START + EDGE_LINE_PERCENT;
            if (left) lines.push(`<line class="dco-edge-line-svg" vector-effect="non-scaling-stroke" x1="1" y1="${EDGE_LINE_START}" x2="1" y2="${end}"/>`);
            if (right) lines.push(`<line class="dco-edge-line-svg" vector-effect="non-scaling-stroke" x1="99" y1="${EDGE_LINE_START}" x2="99" y2="${end}"/>`);
            if (top) lines.push(`<line class="dco-edge-line-svg" vector-effect="non-scaling-stroke" x1="${EDGE_LINE_START}" y1="1" x2="${end}" y2="1"/>`);
            if (bottom) lines.push(`<line class="dco-edge-line-svg" vector-effect="non-scaling-stroke" x1="${EDGE_LINE_START}" y1="99" x2="${end}" y2="99"/>`);
            if (!lines.length) return "";
            return `
                <svg class="dco-piece-edge-svg" viewBox="0 0 100 100" preserveAspectRatio="none" aria-hidden="true" style="position:absolute;inset:0;width:100%;height:100%;z-index:3;overflow:hidden;">
                    <defs><clipPath id="${clipId}"><path d="${geometryModel.geometry.pathData}" fill-rule="evenodd" clip-rule="evenodd"/></clipPath></defs>
                    <g clip-path="url(#${clipId})" fill="none" stroke="${color}" stroke-width="3" vector-effect="non-scaling-stroke">${lines.join("")}</g>
                </svg>
            `;
        }

        if (left) {
            html += `<span class="dco-edge-line" style="position:absolute;left:${inset};top:${EDGE_LINE_START}%;height:${EDGE_LINE_PERCENT}%;border-left:${thickness} solid ${color};z-index:3;"></span>`;
        }
        if (right) {
            html += `<span class="dco-edge-line" style="position:absolute;right:${inset};top:${EDGE_LINE_START}%;height:${EDGE_LINE_PERCENT}%;border-right:${thickness} solid ${color};z-index:3;"></span>`;
        }
        if (top) {
            html += `<span class="dco-edge-line" style="position:absolute;top:${inset};left:${EDGE_LINE_START}%;width:${EDGE_LINE_PERCENT}%;border-top:${thickness} solid ${color};z-index:3;"></span>`;
        }
        if (bottom) {
            html += `<span class="dco-edge-line" style="position:absolute;bottom:${inset};left:${EDGE_LINE_START}%;width:${EDGE_LINE_PERCENT}%;border-bottom:${thickness} solid ${color};z-index:3;"></span>`;
        }

        return html;
    }

    function double_edge_sides(piece) {
        if (!piece || !Number(piece.extra_double)) return [];
        const liner = window.AlmdinaLinerGeometry;
        if (liner && typeof liner.normalizeSideSelection === "function") {
            return liner.normalizeSideSelection(
                piece.extra_double_reference_sides,
                piece.piece_type || "Regular",
                true,
            );
        }
        const available = ["edge_width_top", "edge_width_bottom", "edge_long_left", "edge_long_right"];
        if (piece.piece_type === "Clipped Corner") available.push("edge_break", "edge_break_only");
        if (piece.piece_type === "L-Shaped Corner") available.push("edge_break");
        if (piece.extra_double_reference_sides) {
            try {
                const selected = JSON.parse(piece.extra_double_reference_sides);
                if (Array.isArray(selected)) return available.filter(side => selected.includes(side));
            } catch (error) {
                return [];
            }
        }
        return available;
    }

    function double_edge_flags(piece, geometryModel) {
        const sides = double_edge_sides(piece);
        const liner = window.AlmdinaLinerGeometry;
        if (liner && typeof liner.sideFlagsForSelection === "function") {
            const rotated = geometryModel && geometryModel.source === "dxf"
                ? false
                : Boolean(piece && piece.rotated);
            const flags = liner.sideFlagsForSelection({
                pieceType: piece && piece.piece_type,
            }, sides, rotated);
            if (geometryModel && geometryModel.source === "dxf"
                && Number.isInteger(piece.rotation_quarter_turns)) {
                const turns = ((piece.rotation_quarter_turns % 4) + 4) % 4;
                let { left, top, right, bottom } = flags;
                for (let turn = 0; turn < turns; turn += 1) {
                    const previous = { left, top, right, bottom };
                    left = previous.bottom;
                    top = previous.left;
                    right = previous.top;
                    bottom = previous.right;
                }
                return { left, right, top, bottom, edgeBreak: flags.edgeBreak, edgeBreakOnly: flags.edgeBreakOnly };
            }
            return flags;
        }
        return piece_edge_flags({
            ...piece,
            edge_long_left: sides.includes("edge_long_left"),
            edge_long_right: sides.includes("edge_long_right"),
            edge_width_top: sides.includes("edge_width_top"),
            edge_width_bottom: sides.includes("edge_width_bottom"),
            edge_break: sides.includes("edge_break"),
            edge_break_only: sides.includes("edge_break_only"),
        }, geometryModel);
    }

    function render_piece_double_edge_lines(piece, geometryModel = null, clipId = "") {
        const sides = double_edge_sides(piece);
        if (!sides.length) return "";
        const flags = double_edge_flags(piece, geometryModel);
        const geometry = window.AlmdinaClippedCornerGeometry;
        const isCornerPiece = Boolean(
            geometry
            && ((typeof geometry.isCornerCut === "function" && geometry.isCornerCut(piece))
                || (typeof geometry.isClipped === "function" && geometry.isClipped(piece)))
        );
        if (isCornerPiece && geometry && typeof geometry.edgeBandSvgMarkup === "function") {
            let edgePiece = { ...piece, ...flags };
            if (geometryModel && geometryModel.source === "dxf") {
                const liner = window.AlmdinaLinerGeometry;
                const sourceFlags = liner && typeof liner.sideFlagsForSelection === "function"
                    ? liner.sideFlagsForSelection(
                        { pieceType: piece && piece.piece_type },
                        sides,
                        false,
                    )
                    : flags;
                edgePiece = typeof geometry.pieceForQuarterTurns === "function"
                    ? geometry.pieceForQuarterTurns(
                        { ...piece, ...sourceFlags },
                        piece.corner_rotation_quarter_turns,
                        piece.corner_mirrored,
                    )
                    : null;
                if (!edgePiece) return "";
            }
            const normalFlags = piece_edge_flags(piece, geometryModel);
            const hasNormalBand = ["left", "right", "top", "bottom", "edgeBreak", "edgeBreakOnly"]
                .some(side => flags[side] && normalFlags[side]);
            const insets = hasNormalBand ? [7, 9.5] : [4, 6.5];
            const markup = insets.map(inset => geometry.edgeBandSvgMarkup(edgePiece, 100, 100, {
                inheritStroke: false,
                color: EXTRA_DOUBLE_MARK_COLOR,
                strokeWidth: DOUBLE_EDGE_STROKE_WIDTH,
                insetPx: inset,
                endTrimPx: DOUBLE_EDGE_END_TRIM,
            })).filter(Boolean).join("");
            if (!markup) return "";
            const pathData = geometryModel && geometryModel.geometry && geometryModel.geometry.pathData;
            const clipDef = pathData
                ? `<defs><clipPath id="${clipId}-double"><path d="${pathData}" fill-rule="evenodd" clip-rule="evenodd"/></clipPath></defs>`
                : "";
            const clipAttr = pathData ? ` clip-path="url(#${clipId}-double)"` : "";
            return `<svg class="dco-piece-double-edge-svg" data-double-edge-lines="1" viewBox="0 0 100 100" preserveAspectRatio="none" aria-hidden="true" style="position:absolute;inset:0;width:100%;height:100%;z-index:4;overflow:hidden;pointer-events:none;">${clipDef}<g${clipAttr}>${markup}</g></svg>`;
        }

        const color = EXTRA_DOUBLE_MARK_COLOR;
        const thickness = `${DOUBLE_EDGE_STROKE_WIDTH}px`;
        const start = 16.667;
        const length = 66.666;
        if (geometryModel && geometryModel.vector) {
            const lines = [];
            const addPair = (side, active, axis) => {
                if (!active) return;
                const normal = piece_edge_flags(piece, geometryModel);
                const hasNormal = Boolean(normal[axis]);
                const insets = hasNormal ? [4.5, 7] : [3, 5.5];
                insets.forEach((inset, index) => {
                    const line = axis === "left"
                        ? `x1="${inset}" y1="${start}" x2="${inset}" y2="${start + length}"`
                        : axis === "right"
                            ? `x1="${100 - inset}" y1="${start}" x2="${100 - inset}" y2="${start + length}"`
                            : axis === "top"
                                ? `x1="${start}" y1="${inset}" x2="${start + length}" y2="${inset}"`
                                : `x1="${start}" y1="${100 - inset}" x2="${start + length}" y2="${100 - inset}"`;
                    lines.push(`<line data-double-edge-side="${side}" data-double-edge-line-index="${index}" ${line}/>`);
                });
            };
            addPair("edge_long_left", flags.left, "left");
            addPair("edge_long_right", flags.right, "right");
            addPair("edge_width_top", flags.top, "top");
            addPair("edge_width_bottom", flags.bottom, "bottom");
            if (!lines.length) return "";
            return `<svg class="dco-piece-double-edge-svg" data-double-edge-lines="1" viewBox="0 0 100 100" preserveAspectRatio="none" aria-hidden="true" style="position:absolute;inset:0;width:100%;height:100%;z-index:4;overflow:hidden;pointer-events:none;"><defs><clipPath id="${clipId}-double"><path d="${geometryModel.geometry.pathData}" fill-rule="evenodd" clip-rule="evenodd"/></clipPath></defs><g clip-path="url(#${clipId}-double)" fill="none" stroke="${color}" stroke-width="${DOUBLE_EDGE_STROKE_WIDTH}" vector-effect="non-scaling-stroke">${lines.join("")}</g></svg>`;
        }
        let html = `<span data-double-edge-lines="1" style="position:absolute;inset:0;z-index:4;pointer-events:none;">`;
        const addHtmlPair = (side, active, cssSide, border, normal) => {
            if (!active) return;
            const insets = normal ? [4.5, 7] : [3, 5.5];
            insets.forEach((inset, index) => {
                html += `<span data-double-edge-side="${side}" data-double-edge-line-index="${index}" style="position:absolute;${cssSide}:${inset}px;${cssSide === "left" || cssSide === "right" ? `top:${start}%;height:${length}%;` : `left:${start}%;width:${length}%;`}border-${border}:${thickness} solid ${color};"></span>`;
            });
        };
        const normalFlags = piece_edge_flags(piece, geometryModel);
        addHtmlPair("edge_long_left", flags.left, "left", "left", normalFlags.left);
        addHtmlPair("edge_long_right", flags.right, "right", "right", normalFlags.right);
        addHtmlPair("edge_width_top", flags.top, "top", "top", normalFlags.top);
        addHtmlPair("edge_width_bottom", flags.bottom, "bottom", "bottom", normalFlags.bottom);
        return `${html}</span>`;
    }

    function print_piece_number(value) {
        const label = String(value || "—").trim();
        const primary = label.split(".")[0].trim();
        return primary || "—";
    }

    const EXTRA_OVERLAY_STROKE_BY_KIND = Object.freeze({
        liner: "#1d6fbf",
        back_groove: "#2a7d4f",
        recessed_handle_cutout: "#c45c12",
    });
    const EXTRA_DOUBLE_MARK_COLOR = "#5a2d82";
    const DOUBLE_EDGE_STROKE_WIDTH = 1.4;
    const DOUBLE_EDGE_END_TRIM = 6;
    const EXTRA_FULL_DOOR_DOUBLE_MARK_COLOR = "#1a5f4a";
    const EXTRA_ADDON_LEGEND_ITEMS = Object.freeze([
        Object.freeze({ fieldname: "extra_liner", label: "Liner", overlayKind: "liner" }),
        Object.freeze({ fieldname: "extra_back_groove", label: "Back groove", overlayKind: "back_groove" }),
        Object.freeze({
            fieldname: "extra_recessed_handle_cutout",
            label: "Recessed handle",
            overlayKind: "recessed_handle_cutout",
        }),
        Object.freeze({ fieldname: "extra_double", label: "Double Edge", addonKind: "double" }),
        Object.freeze({
            fieldname: "extra_full_door_double",
            label: "Full door double",
            addonKind: "full_door_double",
        }),
    ]);

    function extraAddonLegendItem(fieldname) {
        return EXTRA_ADDON_LEGEND_ITEMS.find(item => item.fieldname === fieldname) || null;
    }

    function extraAddonLegendLabel(itemOrFieldname) {
        const item = typeof itemOrFieldname === "string"
            ? extraAddonLegendItem(itemOrFieldname)
            : itemOrFieldname;
        return item ? translate(item.label) : "";
    }

    function extraGroupNo(piece) {
        const sourceNo = Math.floor(Number(piece && piece.source_piece_no));
        if (sourceNo >= 1) return sourceNo;
        const group = Math.floor(Number(String((piece && piece.label) || "").split(".")[0]));
        return group >= 1 ? group : 0;
    }

    function extraOrderRowForPiece(frm, piece) {
        const rows = (frm && frm.doc && frm.doc.pieces) || [];
        const groupNo = extraGroupNo(piece);
        if (!(groupNo >= 1) || groupNo > rows.length) return null;
        return rows[groupNo - 1] || null;
    }

    function extraAddonFlags(frm, piece) {
        const row = extraOrderRowForPiece(frm, piece);
        if (!row) return { double: false, fullDoorDouble: false };
        return {
            double: Boolean(Number(row.extra_double)),
            fullDoorDouble: Boolean(Number(row.extra_full_door_double)),
        };
    }

    function extraOverlayStrokeSample(color) {
        return `<svg class="dco-extra-addon-legend-swatch" viewBox="0 0 28 10" width="28" height="10" aria-hidden="true"><path d="M2 5 H26" fill="none" stroke="${escape_html(color)}" stroke-width="1" stroke-dasharray="3 2.2" stroke-linecap="round"/></svg>`;
    }

    function extraDoubleLegendSwatch() {
        return `<svg class="dco-extra-addon-legend-swatch" viewBox="0 0 28 10" width="28" height="10" aria-hidden="true"><path d="M2 3.5 H26 M2 6.5 H26" fill="none" stroke="${EXTRA_DOUBLE_MARK_COLOR}" stroke-width="1.1" stroke-linecap="round"/></svg>`;
    }

    function extraHandleLegendSwatch() {
        const color = EXTRA_OVERLAY_STROKE_BY_KIND.recessed_handle_cutout;
        return `<svg class="dco-extra-addon-legend-swatch" viewBox="0 0 28 10" width="28" height="10" aria-hidden="true"><rect x="6" y="2.2" width="16" height="5.6" fill="none" stroke="${color}" stroke-width="0.9"/></svg>`;
    }

    function extraAddonTextColor(kind) {
        return kind === "double" ? EXTRA_DOUBLE_MARK_COLOR : EXTRA_FULL_DOOR_DOUBLE_MARK_COLOR;
    }

    function extraAddonTextMark(kind, label) {
        return `<span class="dco-extra-addon-text" data-addon-kind="${escape_html(kind)}" style="display:block;color:${extraAddonTextColor(kind)};font-size:9px;font-weight:900;line-height:1.15;white-space:nowrap;padding:1px 3px;font-family:Tahoma,Arial,sans-serif;">${escape_html(label)}</span>`;
    }

    function extraAddonLegendSwatch(item) {
        if (item.addonKind === "double") return extraDoubleLegendSwatch();
        if (item.overlayKind === "recessed_handle_cutout") return extraHandleLegendSwatch();
        if (item.overlayKind) {
            return extraOverlayStrokeSample(EXTRA_OVERLAY_STROKE_BY_KIND[item.overlayKind]);
        }
        return "";
    }

    function render_extra_addon_legend() {
        const items = EXTRA_ADDON_LEGEND_ITEMS.map(item => {
            const label = extraAddonLegendLabel(item);
            if (item.addonKind) {
                return `
            <span class="dco-extra-addon-legend-item">
                ${item.addonKind === "double" ? extraAddonLegendSwatch(item) : ""}
                ${extraAddonTextMark(item.addonKind, label)}
            </span>`;
            }
            return `
            <span class="dco-extra-addon-legend-item">
                ${extraAddonLegendSwatch(item)}
                <span>${escape_html(label)}</span>
            </span>`;
        }).join("");
        return `<div class="dco-extra-addon-legend" dir="${escape_html(uiDirection())}">
            <span class="dco-extra-addon-legend-title">${htmlText("Door add-on symbols")}</span>
            ${items}
        </div>`;
    }

    function render_plan_meta_strip(frm, plan) {
        const coverage = render_special_raw_coverage(frm, plan);
        const legend = render_extra_addon_legend();
        if (!coverage && !legend) return "";
        return `<div class="dco-plan-meta-strip" dir="${escape_html(uiDirection())}">${coverage}${legend}</div>`;
    }

    function extraAddonMarkPlate(slot, kind, innerHtml) {
        const corner = slot === "top-start"
            ? "top:4%;left:4%;right:auto;"
            : "top:4%;right:4%;left:auto;";
        return `<div class="dco-extra-addon-mark" data-addon-kind="${escape_html(kind)}" data-addon-slot="${escape_html(slot)}" style="position:absolute;${corner}z-index:5;background:#fff;border:0.6px solid #c5ccd3;border-radius:2px;padding:1px;line-height:1.1;">${innerHtml}</div>`;
    }

    function render_piece_addon_marks(frm, piece) {
        const flags = extraAddonFlags(frm, piece);
        const marks = [];
        if (flags.fullDoorDouble) {
            marks.push(extraAddonMarkPlate(
                "top-start",
                "full_door_double",
                extraAddonTextMark(
                    "full_door_double",
                    extraAddonLegendLabel("extra_full_door_double")
                )
            ));
        }
        if (flags.double) {
            marks.push(extraAddonMarkPlate(
                "top-end",
                "double",
                extraAddonTextMark(
                    "double",
                    extraAddonLegendLabel("extra_double")
                )
            ));
        }
        if (!marks.length) return "";
        return `<div class="dco-extra-addon-marks" aria-hidden="true" style="position:absolute;inset:0;z-index:5;pointer-events:none;">${marks.join("")}</div>`;
    }

    function overlayRegionCenterline(local, closed) {
        if (!closed || local.length < 4 || local.length % 2 !== 0) return local;
        const half = local.length / 2;
        const near = local.slice(0, half);
        const far = local.slice(half).slice().reverse();
        return near.map((point, index) => [
            (point[0] + far[index][0]) / 2,
            (point[1] + far[index][1]) / 2,
        ]);
    }

    function overlaySingleLine(local, closed) {
        return overlayRegionCenterline(local, closed);
    }

    function axisAlignedPolygon(local) {
        if (!local || local.length < 4) return false;
        return local.every((point, index) => {
            const next = local[(index + 1) % local.length];
            return Math.abs(point[0] - next[0]) <= 0.05 || Math.abs(point[1] - next[1]) <= 0.05;
        });
    }

    function overlayHandleRect(local) {
        const xs = local.map(point => point[0]);
        const ys = local.map(point => point[1]);
        let minX = Math.min(...xs);
        let maxX = Math.max(...xs);
        let minY = Math.min(...ys);
        let maxY = Math.max(...ys);
        const minSize = 1.1;
        if (maxX - minX < minSize) {
            const mid = (minX + maxX) / 2;
            minX = mid - (minSize / 2);
            maxX = mid + (minSize / 2);
        }
        if (maxY - minY < minSize) {
            const mid = (minY + maxY) / 2;
            minY = mid - (minSize / 2);
            maxY = mid + (minSize / 2);
        }
        return { x: minX, y: minY, w: maxX - minX, h: maxY - minY };
    }

    function pieceWithLinerSpec(frm, piece) {
        // A plan snapshot is frozen manufacturing evidence. Do not let later
        // edits in the live order rewrite its machining path in Preview while
        // DXF continues to consume the persisted piece. Old snapshots without
        // add-on fields retain the order-row compatibility fallback below.
        if (piece && [
            "extra_liner",
            "extra_back_groove",
            "extra_recessed_handle_cutout",
        ].some(field => Object.prototype.hasOwnProperty.call(piece, field))) {
            return piece;
        }
        const row = extraOrderRowForPiece(frm, piece);
        if (!row) return piece;
        const engine = window.AlmdinaMachiningOverlay;
        const copy = engine && typeof engine.applySpecs === "function"
            ? engine.applySpecs(piece, row)
            : Object.assign({}, piece, {
            extra_liner: row.extra_liner,
            liner_reference_side: row.liner_reference_side,
            liner_offset_cm: row.liner_offset_cm,
            liner_width_cm: row.liner_width_cm,
            liner_start_cm: row.liner_start_cm,
            liner_length_cm: row.liner_length_cm,
            kerf_mm: num(frm && frm.doc && frm.doc.kerf_mm),
            piece_type: row.piece_type || piece.piece_type,
            clipped_corner_position: row.clipped_corner_position || piece.clipped_corner_position,
            clipped_corner_width_cm: row.clipped_corner_width_cm,
            clipped_corner_length_cm: row.clipped_corner_length_cm,
        });
        if (engine && typeof engine.applySpecs === "function") {
            copy.kerf_mm = num(frm && frm.doc && frm.doc.kerf_mm);
            copy.piece_type = row.piece_type || piece.piece_type;
            copy.clipped_corner_position = row.clipped_corner_position || piece.clipped_corner_position;
            copy.clipped_corner_width_cm = row.clipped_corner_width_cm;
            copy.clipped_corner_length_cm = row.clipped_corner_length_cm;
        }
        const liner = window.AlmdinaLinerGeometry;
        if (liner && typeof liner.contourNotchFromOrder === "function") {
            const notch = liner.contourNotchFromOrder(frm, row);
            copy.clipped_corner_width_cm = notch.cutWidthCm;
            copy.clipped_corner_length_cm = notch.cutLengthCm;
        }
        return copy;
    }

    function pieceWithDoubleSpec(frm, piece) {
        if (piece && ["extra_double", "extra_double_reference_sides"].some(field => (
            Object.prototype.hasOwnProperty.call(piece, field)
        ))) return piece;
        const row = extraOrderRowForPiece(frm, piece);
        if (!row) return piece;
        return Object.assign({}, piece, {
            extra_double: row.extra_double,
            extra_double_reference_sides: row.extra_double_reference_sides,
        });
    }

    function planCutterDiameterMm(plan, frm) {
        const millimetres = num(plan && plan.kerf_mm);
        if (millimetres > 0) return millimetres;
        const centimetres = num(plan && plan.kerf_cm);
        if (centimetres > 0) return centimetres * 10;
        return num(frm && frm.doc && frm.doc.kerf_mm);
    }

    function drawingOverlays(piece) {
        const overlays = Array.isArray(piece && piece.overlays) ? piece.overlays.slice() : [];
        const engine = window.AlmdinaMachiningOverlay;
        if (engine && typeof engine.visualOverlays === "function") {
            const visuals = engine.visualOverlays(piece);
            if (!visuals.length) return overlays;
            const kinds = new Set(visuals.map(item => item && item.kind));
            return overlays.filter(item => !(item && kinds.has(item.kind))).concat(visuals);
        }
        const liner = window.AlmdinaLinerGeometry;
        const drawCenter = liner && typeof liner.visualCenterline === "function"
            ? liner.visualCenterline
            : null;
        const visual = drawCenter ? drawCenter(piece) : null;
        if (!visual) return overlays;
        return overlays.filter(item => !(item && item.kind === "liner")).concat(visual);
    }

    const LINER_TOOLPATH_MESSAGES = Object.freeze({
        cutter_diameter_invalid: "Specify a saw blade thickness above zero for {0} toolpaths",
        liner_narrower_than_cutter: "The width of {0} is less than the saw blade thickness",
        liner_extension_hits_piece: "The {0} extension overlaps another piece",
        liner_extension_unsafe: "Could not extend the {0} toolpath safely",
        strip_outside: "The {0} strip extends beyond the door",
        offset_invalid: "The {0} offset is invalid",
        width_invalid: "The {0} width is invalid",
        side_unavailable: "The {0} side is unavailable for this door",
        liner_start_invalid: "The {0} start position is invalid",
        liner_length_invalid: "The {0} length is invalid",
        liner_span_exceeds_edge: "The start and length exceed the side length",
        liner_flat_end_unmachinable: "The flat {0} end cannot be machined with this cutter",
        liner_span_on_corner: "The {0} start or end falls on a corner without one direction",
    });

    function samePlacedPiece(left, right) {
        const liner = window.AlmdinaLinerGeometry;
        if (liner && typeof liner.samePlacedPiece === "function") {
            return liner.samePlacedPiece(left, right);
        }
        if (!left || !right) return false;
        if (left === right) return true;
        if (left.id != null && right.id != null && String(left.id) !== "" && String(left.id) === String(right.id)) {
            return true;
        }
        return Boolean(left.label)
            && String(left.label) === String(right.label || "")
            && Number(left.x) === Number(right.x)
            && Number(left.y) === Number(right.y);
    }

    function overlayObstacles(sheet, piece) {
        const liner = window.AlmdinaLinerGeometry;
        if (liner && typeof liner.sheetObstaclesMm === "function") {
            return liner.sheetObstaclesMm(sheet, piece);
        }
        return (sheet.pieces || []).filter(other => !samePlacedPiece(other, piece)).map(other => {
            const geometry = liner && typeof liner.obstacleGeometryMm === "function"
                ? liner.obstacleGeometryMm(other)
                : null;
            const polygon = geometry && Array.isArray(geometry.outer)
                ? geometry.outer
                : (liner && typeof liner.obstaclePolygonMm === "function"
                    ? liner.obstaclePolygonMm(other)
                    : (liner && typeof liner.placedPolygonMm === "function" ? liner.placedPolygonMm(other) : []));
            if (polygon.length >= 3) return { polygon, holes: (geometry && geometry.holes) || [] };
            return {
                minX: num(other.x) * 10,
                minY: num(other.y) * 10,
                maxX: (num(other.x) + num(other.w)) * 10,
                maxY: (num(other.y) + num(other.h)) * 10,
            };
        });
    }

    function logLinerConflict(piece, path, details) {
        console.error("[liner-extension-conflict]", {
            host: {
                pieceId: piece && piece.id,
                label: String((piece && piece.label) || ""),
                positionCm: {
                    x: num(piece && piece.x),
                    y: num(piece && piece.y),
                    w: num(piece && piece.w),
                    h: num(piece && piece.h),
                },
            },
            neighbour: details && details.obstacle,
            linerPathMm: path.map(point => point.slice()),
            minimumDistanceMm: details && details.minimumDistanceMm,
            cutterRadiusMm: details && details.cutterRadiusMm,
            rejectionThresholdMm: details && details.rejectionThresholdMm,
            rejectCondition: details && details.rejectCondition,
            segmentIndex: details && details.segmentIndex,
        });
    }

    function guardLinerToolpath(frm, piece, sheet, frame, overlays) {
        const liner = window.AlmdinaLinerGeometry;
        const cutterMm = num(frame && frame.cutterMm) || num(piece && piece.kerf_mm);
        const kept = overlays.filter(overlay => !(overlay && overlay.geometry && overlay.geometry.toolpath));
        const engine = window.AlmdinaMachiningOverlay;
        if (engine && typeof engine.syntheticOverlays === "function" && sheet && frame) {
            if (kept.some(item => item && item.error)) return kept;
            const board = {
                minX: -num(frame.insetX) * 10,
                minY: -num(frame.insetY) * 10,
                maxX: (num(frame.drawW) - num(frame.insetX)) * 10,
                maxY: (num(frame.drawH) - num(frame.insetY)) * 10,
            };
            const tools = engine.syntheticOverlays(Object.assign({}, piece, {
                board,
                kerf_mm: cutterMm,
            }));
            const obstacles = overlayObstacles(sheet, piece);
            const result = kept.slice();
            tools.forEach(tool => {
                if (!tool) return;
                if (tool.error) {
                    result.push(tool);
                    return;
                }
                if (liner && typeof liner.extensionConflict === "function" && tool.geometry) {
                    let conflictDetails = null;
                    const conflict = liner.extensionConflict(
                        tool.geometry.path,
                        cutterMm,
                        board,
                        obstacles,
                        details => { conflictDetails = details; }
                    );
                    if (conflict) {
                        logLinerConflict(piece, tool.geometry.path, conflictDetails);
                        result.push({ kind: tool.kind, layer: tool.layer, synthetic: true, error: conflict });
                        return;
                    }
                }
                result.push(tool);
            });
            return result;
        }
        if (!liner || typeof liner.syntheticOverlay !== "function" || !sheet || !frame) return kept;
        if (kept.some(item => item && item.error)) return kept;
        const board = {
            minX: -num(frame.insetX) * 10,
            minY: -num(frame.insetY) * 10,
            maxX: (num(frame.drawW) - num(frame.insetX)) * 10,
            maxY: (num(frame.drawH) - num(frame.insetY)) * 10,
        };
        const tool = liner.syntheticOverlay(Object.assign({}, piece, { board }));
        if (!tool) return kept;
        if (tool.error) {
            return kept.concat({ kind: "liner", layer: "Liner", synthetic: true, error: tool.error });
        }
        if (typeof liner.extensionConflict !== "function" || !tool.geometry) {
            return kept.concat(tool);
        }
        const obstacles = overlayObstacles(sheet, piece);
        let conflictDetails = null;
        const conflict = liner.extensionConflict(
            tool.geometry.path,
            cutterMm,
            board,
            obstacles,
            details => { conflictDetails = details; }
        );
        if (conflict) {
            logLinerConflict(piece, tool.geometry.path, conflictDetails);
            return kept.concat({ kind: "liner", layer: "Liner", synthetic: true, error: conflict });
        }
        return kept.concat(tool);
    }

    function render_piece_overlays(frm, piece, geometryModel, sheet, frame) {
        const spec = pieceWithLinerSpec(frm, piece);
        // DXF paths are imported physical evidence. A synthetic redraw from
        // order-side settings can reverse their orientation after a half-turn.
        const overlays = geometryModel && geometryModel.source === "dxf"
            ? (Array.isArray(piece.overlays) ? piece.overlays : [])
            : guardLinerToolpath(
                frm,
                spec,
                sheet,
                frame,
                drawingOverlays(spec)
            );
        if (!overlays.length || !geometryModel) return "";
        const originX = num(geometryModel.placement.xCm) * 10;
        const originY = num(geometryModel.placement.yCm) * 10;
        const widthMm = num(geometryModel.placement.widthCm) * 10;
        const heightMm = num(geometryModel.placement.heightCm) * 10;
        if (!(widthMm > 0) || !(heightMm > 0)) return "";
        const paths = overlays.map((overlay, index) => {
            const kind = String((overlay && overlay.kind) || "").trim();
            const geometry = overlay && overlay.geometry;
            if (overlay && overlay.error) {
                const engine = window.AlmdinaMachiningOverlay;
                const addon = engine && typeof engine.addon === "function" ? engine.addon(kind) : null;
                const noun = translate(addon && addon.nounMessageId || "the liner");
                const message = translate(LINER_TOOLPATH_MESSAGES[overlay.error] || overlay.error, [noun]);
                return `<text data-liner-toolpath-error="${escape_html(overlay.error)}" x="50" y="50" text-anchor="middle" font-size="8" fill="#9a6207">${escape_html(message)}</text>`;
            }
            const points = geometry && Array.isArray(geometry.path)
                ? geometry.path
                : (geometry && Array.isArray(geometry.outer) ? geometry.outer : []);
            if (points.length < 2) return "";
            const local = points.map(point => [
                ((Number(point[0]) - originX) / widthMm) * 100,
                ((Number(point[1]) - originY) / heightMm) * 100,
            ]);
            const stroke = EXTRA_OVERLAY_STROKE_BY_KIND[kind] || "#5c4d2e";
            const layer = String((overlay && overlay.layer) || kind || "overlay");
            const attrs = `data-overlay-kind="${escape_html(kind)}" data-overlay-layer="${escape_html(layer)}" data-overlay-index="${index}" fill="none" stroke="${stroke}" vector-effect="non-scaling-stroke"`;
            const closed = Boolean(geometry && geometry.closed) && local.length >= 3;
            const isToolpath = Boolean(geometry && geometry.toolpath);
            if (isToolpath) return "";
            if (kind === "recessed_handle_cutout") {
                if (axisAlignedPolygon(local)) {
                    const box = overlayHandleRect(local);
                    return `<rect class="dco-extra-overlay-path dco-extra-overlay-handle" ${attrs} x="${box.x}" y="${box.y}" width="${box.w}" height="${box.h}" stroke-width="0.65" stroke-linejoin="miter"/>`;
                }
                const outline = local
                    .map((point, pointIndex) => `${pointIndex ? "L" : "M"}${point[0]} ${point[1]}`)
                    .join(" ") + (closed ? " Z" : "");
                return `<path class="dco-extra-overlay-path dco-extra-overlay-handle" ${attrs} d="${outline}" stroke-width="0.65" stroke-linejoin="miter"/>`;
            }
            const machiningKind = kind === "liner" || kind === "back_groove";
            const strokePoints = machiningKind ? overlaySingleLine(local, closed) : local;
            const d = strokePoints
                .map((point, pointIndex) => `${pointIndex ? "L" : "M"}${point[0]} ${point[1]}`)
                .join(" ") + (machiningKind ? "" : (closed ? " Z" : ""));
            const dash = machiningKind ? ` stroke-dasharray="3 2.2" stroke-linecap="round"` : "";
            return `<path class="dco-extra-overlay-path" ${attrs} d="${d}" stroke-width="0.7"${dash} stroke-linejoin="round"/>`;
        }).filter(Boolean).join("");
        if (!paths) return "";
        return `<svg class="dco-extra-overlay" viewBox="0 0 100 100" preserveAspectRatio="none" aria-hidden="true" style="position:absolute;inset:0;width:100%;height:100%;z-index:2;overflow:visible;pointer-events:none">${paths}</svg>`;
    }

    function render_piece_label(piece, geometryModel) {
        const exact_special = piece.piece_type === "Special"
            && geometryModel
            && geometryModel.exact;
        const special = piece.piece_type === "Special"
            ? `<span class="dco-piece-kind-badge" style="display:inline-block;margin-bottom:2px;padding:2px 6px;border-radius:999px;background:#7a4c13;color:#fff;font-size:9px;font-weight:900">${exact_special ? htmlText("Special door · geometric path") : htmlText("Special door · CNC raw")}</span><br>`
            : "";
        const invalidGeometry = geometryModel && geometryModel.invalid
            ? `<span class="dco-geometry-error-badge" style="display:inline-block;margin-bottom:2px;padding:2px 6px;border-radius:999px;background:#a61b1b;color:#fff;font-size:9px;font-weight:900">${htmlText("Could not display the geometric path")}</span><br>`
            : "";
        const clippedGeometry = window.AlmdinaClippedCornerGeometry;
        const clipped = Boolean(clippedGeometry && clippedGeometry.isCornerCut(piece));
        const clippedLabel = clipped
            ? `<span class="dco-piece-kind-badge" style="display:inline-block;margin-bottom:2px;padding:2px 6px;border-radius:999px;background:#8a5700;color:#fff;font-size:9px;font-weight:900">${clippedGeometry.typeIcon(piece)} ${clippedGeometry.typeLabel(piece)}</span><br>`
            : "";
        const piece_number = print_piece_number(piece.label);
        const labelStyle = geometryModel && geometryModel.vector
            ? `position:absolute;left:${geometryModel.labelPoint.xPercent}%;top:${geometryModel.labelPoint.yPercent}%;transform:translate(-50%,-50%);max-width:84%;`
            : "position:relative;";
        return `
            <div class="dco-piece-label" style="${labelStyle}z-index:4;direction:ltr;text-align:center;">
                ${invalidGeometry}${special}${clippedLabel}
                <span class="dco-piece-size">${round(piece.original_w, 1)}*${round(piece.original_h, 1)}</span>
                <span class="dco-piece-size-mm" style="display:none">${round(num(piece.original_w) * 10, 0)} × ${round(num(piece.original_h) * 10, 0)}</span>
                <span class="dco-piece-number" style="display:none">${escape_html(piece_number)}</span>
            </div>
        `;
    }

    function render_special_raw_coverage(frm, plan) {
        const requested_from_rows = (frm.doc.pieces || []).reduce((total, row) => {
            if ((row.piece_type || "Regular") !== "Special") return total;
            return total + Math.max(0, Math.floor(num(row.qty)));
        }, 0);
        const placed_from_plan = (plan.sheets || []).reduce((total, sheet) => {
            return total + (sheet.pieces || []).filter(piece => piece.piece_type === "Special").length;
        }, 0);
        const snapshot = plan.special_shape_raw_summary || {};
        const requested = Number.isFinite(Number(snapshot.requested))
            ? Number(snapshot.requested)
            : requested_from_rows;
        const placed = Number.isFinite(Number(snapshot.placed))
            ? Number(snapshot.placed)
            : placed_from_plan;
        if (!requested) return "";

        const complete = Boolean(snapshot.complete ?? (placed === requested));
        const tone = complete
            ? "border-color:#c9a66b;background:linear-gradient(135deg,#fff8e8,#fffdf8);color:#684117"
            : "border-color:#dc7b72;background:#fff4f2;color:#9b2f26";
        const counts = `<b>${escape_html(translate("{0} of {1}", [placed, requested]))}</b>`;
        const message = complete
            ? `${htmlText("All special doors were placed in the cutting plan:")} ${counts}`
            : `${htmlText("Warning: only")} ${counts} ${htmlText("special doors were placed in the cutting plan. Review the measurements and the unplaced pieces.")}`;

        return `
            <div class="dco-special-raw-coverage" style="direction:${escape_html(uiDirection())};border:1px solid;border-radius:10px;padding:7px 10px;font-size:12px;font-weight:700;${tone}">
                <span style="font-size:16px;margin-left:6px">✦</span>${message}
            </div>
        `;
    }

    function render_piece_groups_summary(frm) {
        const rows = (frm.doc.pieces || []).filter(row => {
            return num(row.width_cm) || num(row.length_cm) || num(row.qty);
        });

        if (!rows.length) return "";

        let html = `
            <div class="dco-piece-groups" style="border:1px solid #ddd;border-radius:8px;padding:8px;margin:8px 0 12px 0;font-size:12px;line-height:1.8;background:#fafafa;">
                <b>${htmlText("Door list:")}</b><br>
        `;

        rows.forEach((row, index) => {
            const cornerGeometry = window.AlmdinaClippedCornerGeometry;
            const typeLabel = row.piece_type === "Special"
                ? ` · ${htmlText("Special (CNC)")}`
                : (cornerGeometry && cornerGeometry.isCornerCut(row)
                    ? ` · ${cornerGeometry.typeIcon(row)} ${escape_html(cornerGeometry.typeLabel(row))}`
                    : "");
            html += `
                <span style="display:inline-block;margin-inline-start:16px;white-space:nowrap;direction:ltr;">
                    ${index + 1}- ${round(row.width_cm, 1)}*${round(row.length_cm, 1)} ${htmlText("Qty {0}", [physicalCutQuantity(row)])}${typeLabel}
                </span>
            `;
        });

        html += "</div>";
        return html;
    }

    function format_order_date(frm) {
        const raw = frm && frm.doc && frm.doc.order_date;
        if (!raw) return "—";
        if (window.frappe && frappe.datetime && typeof frappe.datetime.str_to_user === "function") {
            return frappe.datetime.str_to_user(raw);
        }
        return String(raw);
    }

    function render_plan_header_cards(frm) {
        const cards = [
            { label: translate("Order number"), value: frm.doc.name || "—" },
            { label: translate("Customer name"), value: frm.doc.customer || "—" },
            { label: translate("Order date"), value: format_order_date(frm) },
            { label: translate("Board type"), value: frm.doc.board_description || "—" },
            { label: translate("Edge color"), value: frm.doc.edge_color || "—" },
        ];

        return `
            <div class="dco-plan-header-cards" style="display:grid;grid-template-columns:repeat(5,minmax(0,1fr));gap:8px;margin:8px 0 12px 0;">
                ${cards.map(card => `
                    <div class="dco-plan-header-card" style="border:1px solid #ddd;border-radius:8px;padding:8px;background:#f8fafc;min-width:0;">
                        <b style="display:block;font-size:10px;color:#555;margin-bottom:4px;">${escape_html(card.label)}</b>
                        <span style="display:block;font-size:12px;font-weight:700;line-height:1.35;word-break:break-word;">${escape_html(card.value)}</span>
                    </div>
                `).join("")}
            </div>
        `;
    }

    function hasOwn(source, key) {
        return Boolean(source) && Object.prototype.hasOwnProperty.call(source, key);
    }

    function resolvedTrimCm(plan, sheet, axis) {
        // Usable-frame coordinates. Physical inset is this trim. An explicit
        // sheet value, including 0, wins. A missing value is recovered from
        // full - usable before the plan-level applied trim, so a plan-wide 0
        // does not hide a sheet that recovered leftover edge space.
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
        const minX = Math.min(...pieces.map(piece => num(piece.x)));
        const maxX = Math.max(...pieces.map(piece => num(piece.x) + num(piece.w)));
        const minY = Math.min(...pieces.map(piece => num(piece.y)));
        const maxY = Math.max(...pieces.map(piece => num(piece.y) + num(piece.h)));
        return {
            left: roundMm((trimW + minX) * 10),
            right: roundMm((fullW - trimW - maxX) * 10),
            top: roundMm((trimH + minY) * 10),
            bottom: roundMm((fullH - trimH - maxY) * 10),
        };
    }

    function originalEdges(plan, sheet) {
        const margins = physicalMarginsMm(plan, sheet);
        return ["right", "left", "top", "bottom"].filter(edge => Math.abs(margins[edge]) <= 0.001);
    }

    function sheetBoardFrame(plan, sheet, frm) {
        const fullW = num(sheet && sheet.full_width_cm) || num(plan.full_board_width_cm);
        const fullH = num(sheet && sheet.full_length_cm) || num(plan.full_board_length_cm);
        const usableW = num(sheet && sheet.usable_width_cm) || num(sheet && sheet.w) || num(plan.usable_board_width_cm) || fullW;
        const usableH = num(sheet && sheet.usable_length_cm) || num(sheet && sheet.h) || num(plan.usable_board_length_cm) || fullH;
        const drawW = fullW > 0 ? fullW : usableW;
        const drawH = fullH > 0 ? fullH : usableH;
        let insetX = resolvedTrimCm(plan, sheet, "x");
        let insetY = resolvedTrimCm(plan, sheet, "y");
        insetX = Math.max(0, Math.min(insetX, drawW / 2));
        insetY = Math.max(0, Math.min(insetY, drawH / 2));
        const innerW = usableW > 0 ? Math.min(usableW, Math.max(0, drawW - (insetX * 2))) : Math.max(0, drawW - (insetX * 2));
        const innerH = usableH > 0 ? Math.min(usableH, Math.max(0, drawH - (insetY * 2))) : Math.max(0, drawH - (insetY * 2));
        return {
            drawW,
            drawH,
            usableW: innerW > 0 ? innerW : usableW,
            usableH: innerH > 0 ? innerH : usableH,
            insetX,
            insetY,
            innerW: innerW > 0 ? innerW : usableW,
            innerH: innerH > 0 ? innerH : usableH,
            cutterMm: planCutterDiameterMm(plan, frm),
        };
    }

    function build_cutting_plan_html(frm, plan) {
        if (!plan || !plan.sheets || !plan.sheets.length) return "";

        const board_w_cm = num(plan.usable_board_width_cm);
        const board_h_cm = num(plan.usable_board_length_cm);
        const full_board_w_cm = num(plan.full_board_width_cm);
        const full_board_h_cm = num(plan.full_board_length_cm);
        const board_area_m2 = (board_w_cm * board_h_cm) / 10000;
        const fullBoardSheets = (plan.sheets || []).filter(
            sheet => String(sheet.resource_kind || "FULL_BOARD").toUpperCase() === "FULL_BOARD"
        );
        const used_area_m2 = round(plan.used_area_m2, 3);
        const total_board_area_m2 = round(plan.total_board_area_m2, 3);
        const waste_area_m2 = round(plan.waste_area_m2, 3);
        const waste_percent = total_board_area_m2 ? round((waste_area_m2 / total_board_area_m2) * 100, 2) : 0;

        const board_width_px = 560;

        let html = `
            <div class="dco-cutting-plan" dir="${escape_html(uiDirection())}" data-almdina-order="${escape_html(frm.doc.name || "")}" style="font-family:Arial,Tahoma,sans-serif;color:#111;background:#fff;">
                <h2 style="margin:0 0 8px 0;font-size:18px;">${htmlText("Cutting plan")}</h2>
                ${render_plan_header_cards(frm)}

                <div class="dco-summary-grid" style="display:grid;grid-template-columns:repeat(4,1fr);gap:8px;margin:8px 0 12px 0;">
                    <div class="dco-summary-card" style="border:1px solid #ddd;border-radius:8px;padding:8px;background:#f8fafc;"><b>${htmlText("Board count")}</b><span style="direction:ltr;">${fullBoardSheets.length}</span></div>
                    <div class="dco-summary-card" style="border:1px solid #ddd;border-radius:8px;padding:8px;background:#f8fafc;"><b>${htmlText("Cut area")}</b><span style="direction:ltr;">${htmlText("{0} m²", [used_area_m2])}</span></div>
                    <div class="dco-summary-card" style="border:1px solid #ddd;border-radius:8px;padding:8px;background:#f8fafc;"><b>${htmlText("Waste area")}</b><span style="direction:ltr;">${htmlText("{0} m²", [waste_area_m2])}</span></div>
                    <div class="dco-summary-card" style="border:1px solid #ddd;border-radius:8px;padding:8px;background:#f8fafc;"><b>${htmlText("Waste percent")}</b><span style="direction:ltr;">${waste_percent}%</span></div>
                </div>

                ${render_piece_groups_summary(frm)}
                ${render_plan_meta_strip(frm, plan)}

                <div class="dco-plan-method-line" style="font-size:12px;margin-bottom:8px;"><b>${htmlText("Layout method:")}</b> ${escape_html(knownStrategyText(plan.method_key, plan.method_label || frm.doc.packing_method || ""))}</div>
        `;

        plan.sheets.forEach(sheet => {
            const isOffcut = String(sheet.resource_kind || "FULL_BOARD").toUpperCase() === "OFFCUT";
            const sheetTitle = isOffcut ? translate("Offcut") : translate("Board {0}", [sheet.sheet_no]);
            const sheet_used_area_m2 = round((sheet.pieces || []).reduce((sum, p) => sum + num(p.area_m2), 0), 3);
            const sheet_waste_area_m2 = round(Math.max(0, board_area_m2 - sheet_used_area_m2), 3);
            const sheet_waste_percent = board_area_m2 ? round((sheet_waste_area_m2 / board_area_m2) * 100, 2) : 0;
            const frame = sheetBoardFrame(plan, sheet, frm);
            const board_height_px = Math.max(260, Math.round(board_width_px * (frame.drawH / frame.drawW)));
            const usableLeft = frame.drawW ? (frame.insetX / frame.drawW) * 100 : 0;
            const usableTop = frame.drawH ? (frame.insetY / frame.drawH) * 100 : 0;
            const usableWidth = frame.drawW ? (frame.innerW / frame.drawW) * 100 : 100;
            const usableHeight = frame.drawH ? (frame.innerH / frame.drawH) * 100 : 100;
            const caption_width_cm = frame.drawW || full_board_w_cm || board_w_cm;
            const caption_length_cm = frame.drawH || full_board_h_cm || board_h_cm;
            const board_caption = caption_width_cm && caption_length_cm
                ? `${round(caption_length_cm * 10, 0)} × ${round(caption_width_cm * 10, 0)}`
                : "";

            html += `
                <div class="dco-sheet-card" data-resource-kind="${isOffcut ? "OFFCUT" : "FULL_BOARD"}" style="border:1px solid #bbb;border-radius:10px;padding:10px;margin:14px 0;background:#fff;page-break-inside:avoid;break-inside:avoid;">
                    <div class="dco-sheet-title" style="display:flex;justify-content:space-between;gap:10px;margin-bottom:8px;font-size:13px;font-weight:bold;">
                        <div>${escape_html(sheetTitle)}</div>
                        <div>
                            <span class="dco-sheet-stats-read" style="direction:ltr;">${htmlText("Pieces: {0} | waste: {1} m² ({2}%)", [(sheet.pieces || []).length, sheet_waste_area_m2, sheet_waste_percent])}</span>
                            <span class="dco-sheet-stats-edit" style="display:none;direction:ltr;">${htmlText("Cuts: {0} | waste: {1} m² ({2}%)", [(sheet.pieces || []).length, sheet_waste_area_m2, sheet_waste_percent])}</span>
                        </div>
                    </div>
                    <div class="dco-sheet-board" data-trim-width-cm="${frame.insetX}" data-trim-length-cm="${frame.insetY}" style="position:relative;direction:ltr;width:${board_width_px}px;height:${board_height_px}px;max-width:100%;border:2px solid #111;background:#fff;overflow:hidden;margin:0 auto 8px auto;">
                        <div class="dco-board-waste-hatch" aria-hidden="true" style="position:absolute;inset:0;z-index:0;pointer-events:none;background-image:repeating-linear-gradient(45deg,rgba(71,85,105,.18) 0 1px,transparent 1px 8px);"></div>
                        ${board_caption ? `<div class="dco-board-size-caption" aria-hidden="true" style="display:none">${escape_html(board_caption)}</div>` : ""}
                        <div class="dco-usable-sheet" style="position:absolute;z-index:1;left:${usableLeft}%;top:${usableTop}%;width:${usableWidth}%;height:${usableHeight}%;box-sizing:border-box;overflow:visible;">
            `;

            const sheetPieces = sheet.pieces || [];
            const piecesById = new Map();
            sheetPieces.forEach(piece => {
                if (piece && piece.id != null && piece.id !== "") {
                    piecesById.set(Number(piece.id), piece);
                }
            });
            sheetPieces.forEach(piece => {
                const geometry = window.AlmdinaCuttingPlanPieceGeometry;
                if (!geometry || typeof geometry.resolve !== "function") {
                    throw new Error("Canonical cutting-plan piece geometry is unavailable");
                }
                const manufacturingPiece = pieceWithDoubleSpec(frm, pieceWithLinerSpec(frm, piece));
                const geometryModel = geometry.resolve(manufacturingPiece);
                const placement = geometryModel.placement;
                const left = (num(placement.xCm) / frame.usableW) * 100;
                const top = (num(placement.yCm) / frame.usableH) * 100;
                const width = (num(placement.widthCm) / frame.usableW) * 100;
                const height = (num(placement.heightCm) / frame.usableH) * 100;
                const special_piece_style = piece.piece_type === "Special"
                    ? "border:2px solid #7a4c13;background:linear-gradient(135deg,#fff2cf,#ffe2a3);box-shadow:inset 0 0 0 2px rgba(255,255,255,.45);"
                    : "border:1px solid #111;background:#e4f5ff;";
                const clippedGeometry = window.AlmdinaClippedCornerGeometry;
                const clipped = Boolean(clippedGeometry && clippedGeometry.isCornerCut(piece));
                const exactSpecial = piece.piece_type === "Special"
                    && geometryModel.exact;
                const shaped = geometryModel.vector;
                const nestDepth = glassNestPaintDepth(piece, piecesById);
                const shapeOutline = shaped
                    ? `<svg class="dco-shaped-piece-outline" viewBox="0 0 100 100" preserveAspectRatio="none" aria-hidden="true" style="position:absolute;inset:0;width:100%;height:100%;z-index:1;overflow:visible"><path d="${geometryModel.geometry.pathData}" fill="${exactSpecial ? "#ffe5ad" : "#fff0c7"}" fill-rule="evenodd" clip-rule="evenodd" stroke="${exactSpecial ? "#7a4c13" : "#8a5700"}" stroke-width="2" vector-effect="non-scaling-stroke" stroke-linejoin="round"/></svg>`
                    : "";
                const pieceStyle = shaped
                    ? "border:0;background:transparent;box-shadow:none;"
                    : special_piece_style;
                const clipId = `dco-clip-${sheet.sheet_no || 0}-${piece.id || piece.label || 0}-${geometryModel.geometryIdentity}`
                    .replace(/[^a-zA-Z0-9_-]/g, "-");
                const edgeLines = render_piece_edge_lines(manufacturingPiece, geometryModel, clipId);
                const doubleEdgeLines = render_piece_double_edge_lines(manufacturingPiece, geometryModel, clipId);
                const hostAttr = piece.glass_host_piece_id != null && piece.glass_host_piece_id !== ""
                    ? ` data-glass-host="${escape_html(piece.glass_host_piece_id)}"`
                    : "";

                html += `
                    <div class="dco-piece ${piece.piece_type === "Special" ? "dco-special-raw-piece" : ""} ${exactSpecial ? "dco-special-exact-piece" : ""} ${clipped ? "dco-clipped-corner-piece" : ""} ${shaped ? "dco-vector-piece" : ""}" data-piece-type="${escape_html(piece.piece_type || "Regular")}" data-geometry-source="${escape_html(geometryModel.source)}" data-geometry-id="${escape_html(geometryModel.geometryIdentity)}" data-nest-depth="${nestDepth}"${hostAttr} style="position:absolute;left:${left}%;top:${top}%;width:${width}%;height:${height}%;z-index:${2 + nestDepth};${pieceStyle}color:#111;overflow:visible;padding:2px;font-size:10px;line-height:1.2;text-align:center;box-sizing:border-box;display:flex;align-items:center;justify-content:center;">
                        ${shapeOutline}
                        ${render_piece_overlays(frm, manufacturingPiece, geometryModel, sheet, frame)}
                        ${edgeLines}
                        ${doubleEdgeLines}
                        ${render_piece_addon_marks(frm, manufacturingPiece)}
                        ${render_piece_label(piece, geometryModel)}
                    </div>
                `;
            });

            html += "</div></div></div>";
        });

        if (plan.unplaced && plan.unplaced.length) {
            html += `<div style="border:1px solid #d9534f;background:#fff5f5;color:#a94442;padding:8px;border-radius:8px;margin-top:12px;"><b>${htmlText("Warning:")}</b> ${htmlText("{0} pieces were not placed on the boards. Review the measurements, the board size, or the rotation allowance.", [plan.unplaced.length])}</div>`;
        }

        html += "</div>";
        return html;
    }

    // =====================================================
    // Print cutting plan — dynamic A4 landscape, max 10 boards per page
    // =====================================================

    const MAX_SHEETS_PER_PAGE = 10;

    function planRootFromVisibleDom(frm) {
        const field = frm.fields_dict && frm.fields_dict.cutting_plan_html;
        const root = field && field.$wrapper && field.$wrapper.get(0);
        if (!root) return null;
        const planRoot = root.querySelector(".dco-cutting-plan");
        return planRoot ? planRoot.cloneNode(true) : null;
    }

    function planRootFromPlan(frm, plan) {
        if (!plan || !plan.sheets || !plan.sheets.length) return null;
        const holder = document.createElement("div");
        const markup = build_cutting_plan_html(frm, plan);
        const presentation = window.AlmdinaPlanSourcePresentation;
        // Decorate only the verified, frozen plan. OFFCUT assignment labels
        // used to come from a visible DOM clone, which is not a print source.
        holder.innerHTML = presentation?.decorateHtml
            ? presentation.decorateHtml(markup, plan) : markup;
        return holder.querySelector(".dco-cutting-plan");
    }

    function printRowSizes(count) {
        if (count <= 0) return [];
        if (count <= 6) return [count];
        if (count === 7) return [4, 3];
        if (count === 8) return [4, 4];
        if (count === 9) return [5, 4];
        return [5, Math.max(0, count - 5)].filter(Boolean);
    }

    function printGridColumns(count) {
        const rows = printRowSizes(count);
        return rows.length ? Math.max(...rows) : 1;
    }

    function requestedPieceCount(frm) {
        return (frm.doc.pieces || []).reduce(
            (total, row) => total + physicalCutQuantity(row),
            0
        );
    }

    function printBoardSize(frm, plan) {
        const width = num(plan && plan.full_board_width_cm) || num(frm.doc.board_width_cm);
        const length = num(plan && plan.full_board_length_cm) || num(frm.doc.board_length_cm);
        if (!width || !length) return "—";
        return translate("{0} × {1} cm", [round(width, 1), round(length, 1)]);
    }

    function printThemeApi() {
        return window.AlmdinaOrderDocumentPrintTheme || null;
    }

    function printHeaderHtml(identity, title, meta) {
        const theme = printThemeApi();
        if (!theme || typeof theme.headerHtml !== "function") {
            throw new Error("Unified factory print header is unavailable");
        }
        return theme.headerHtml(identity, { title, meta });
    }

    function printHeaderCss() {
        const theme = printThemeApi();
        if (!theme || typeof theme.headerCss !== "function") {
            throw new Error("Unified factory print header styles are unavailable");
        }
        return theme.headerCss();
    }

    function printOrderMetaHtml(frm, plan, totalSheets, _source) {
        // Plan name / revision stay in the verified print source for freshness
        // checks, but are intentionally omitted from the printed header.
        const items = [
            [translate("Order number"), frm.doc.name || "—"],
            [translate("Customer name"), frm.doc.customer || "—"],
            [translate("Board color"), frm.doc.board_description || "—"],
            [translate("Board count"), totalSheets],
            [translate("Piece count"), requestedPieceCount(frm)],
            [translate("Board size"), printBoardSize(frm, plan)],
        ];
        return `<div class="dco-print-order-meta">${items.map(([label, value]) => `
            <div><b>${escape_html(label)}</b><span>${escape_html(value)}</span></div>
        `).join("")}</div>`;
    }

    function stripPrintOnlyBoardChrome(card) {
        // OFFCUT source/execution labels remain in the in-app preview; print
        // drops them entirely so they cannot occupy space or leak into PDF text.
        card.querySelectorAll(".dco-offcut-business-context").forEach(node => {
            if (typeof node.remove === "function") {
                node.remove();
                return;
            }
            if (node.parentNode && typeof node.parentNode.removeChild === "function") {
                node.parentNode.removeChild(node);
            }
        });
        return card;
    }

    function printCardHtml(card) {
        return String(card.outerHTML || "").replace(
            /<div class="dco-offcut-business-context\b[^>]*>[\s\S]*?<\/div>/g,
            ""
        );
    }

    function boardAspectFromCards(cards, frm, plan) {
        const firstBoard = cards[0] && cards[0].querySelector(".dco-sheet-board");
        const renderedW = parseFloat(firstBoard && firstBoard.style.width);
        const renderedH = parseFloat(firstBoard && firstBoard.style.height);
        if (renderedW > 0 && renderedH > 0) return renderedH / renderedW;

        const width = num(plan && plan.full_board_width_cm)
            || num(plan && plan.usable_board_width_cm)
            || num(frm.doc.board_width_cm);
        const length = num(plan && plan.full_board_length_cm)
            || num(plan && plan.usable_board_length_cm)
            || num(frm.doc.board_length_cm);
        return width > 0 && length > 0 ? length / width : 2;
    }

    function sizeBoardsForPage(cards, frm, plan) {
        const count = cards.length;
        const rowSizes = printRowSizes(count);
        const cols = printGridColumns(count);
        const rows = rowSizes.length;
        const aspect = Math.max(0.15, boardAspectFromCards(cards, frm, plan));
        const pageGridWidthMm = 281;
        const pageGridHeightMm = 157;
        const columnGapMm = 2.2;
        const rowGapMm = 2.2;
        const titleHeightMm = 4.2;
        const cardHorizontalSpaceMm = 1;

        const widthLimit = (
            pageGridWidthMm
            - (cols - 1) * columnGapMm
            - cols * cardHorizontalSpaceMm
        ) / cols;
        const heightPerRow = (
            pageGridHeightMm
            - (rows - 1) * rowGapMm
        ) / Math.max(rows, 1);
        const heightLimit = Math.max(12, heightPerRow - titleHeightMm);
        const boardWmm = Math.max(8, Math.min(widthLimit, heightLimit / aspect));
        const boardHmm = boardWmm * aspect;
        const cardWmm = boardWmm + cardHorizontalSpaceMm;

        let boardIndex = 0;
        cards.forEach(card => {
            stripPrintOnlyBoardChrome(card);
            const board = card.querySelector(".dco-sheet-board");
            const title = card.querySelector(".dco-sheet-title");
            const isOffcut = card.dataset.resourceKind === "OFFCUT";
            if (!isOffcut) boardIndex += 1;
            if (title) title.innerHTML = `<div class="dco-print-sheet-number">${isOffcut ? htmlText("Offcut") : htmlText("Board {0}", [boardIndex])}</div>`;
            if (board) {
                board.style.width = `${boardWmm}mm`;
                board.style.height = `${boardHmm}mm`;
                board.style.maxWidth = "100%";
                board.style.margin = "0 auto";
            }
            card.style.setProperty("--print-card-width", `${cardWmm}mm`);
            card.style.margin = "0";
            card.style.padding = ".4mm";
        });
        return { cols, rows, rowSizes };
    }

    function pageChunks(cards) {
        const chunks = [];
        for (let index = 0; index < cards.length; index += MAX_SHEETS_PER_PAGE) {
            chunks.push(cards.slice(index, index + MAX_SHEETS_PER_PAGE));
        }
        return chunks;
    }

    function buildPrintPages(frm, planRoot, plan, identity, source) {
        const sourceCards = [...planRoot.querySelectorAll(".dco-sheet-card")]
            .map(card => card.cloneNode(true));
        const totalSheets = sourceCards.filter(
            card => card.dataset.resourceKind !== "OFFCUT"
        ).length;
        const chunks = pageChunks(sourceCards);
        let globalBoardIndex = 0;

        return chunks.map((cards, pageIndex) => {
            const layout = sizeBoardsForPage(cards, frm, plan);
            let cardOffset = 0;
            const gridRows = layout.rowSizes.map(rowSize => {
                const rowCards = cards.slice(cardOffset, cardOffset + rowSize);
                cardOffset += rowSize;
                const rowHtml = rowCards.map(card => {
                    stripPrintOnlyBoardChrome(card);
                    const title = card.querySelector(".dco-sheet-title");
                    const isOffcut = card.dataset.resourceKind === "OFFCUT";
                    if (!isOffcut) globalBoardIndex += 1;
                    if (title) title.innerHTML = `<div class="dco-print-sheet-number">${isOffcut ? htmlText("Offcut") : htmlText("Board {0}", [globalBoardIndex])}</div>`;
                    return printCardHtml(card);
                }).join("");
                return `<div class="dco-print-sheets-row">${rowHtml}</div>`;
            }).join("");
            return `<section class="dco-print-page" data-page="${pageIndex + 1}">
                ${printHeaderHtml(identity, translate("Cutting plan"), translate("Page {0} of {1}", [pageIndex + 1, chunks.length]))}
                ${printOrderMetaHtml(frm, plan, totalSheets, source)}
                ${render_extra_addon_legend()}
                <div class="dco-print-sheets-grid">${gridRows}</div>
            </section>`;
        }).join("");
    }

    function buildPrintDocument(title, frm, planRoot, plan, identity, source) {
        const pages = buildPrintPages(frm, planRoot, plan, identity, source);
        const language = uiLanguage();
        const direction = uiDirection();
        return `<!DOCTYPE html>
<html lang="${escape_html(language)}" dir="${escape_html(direction)}">
<head>
<meta charset="UTF-8">
<title>${escape_html(title)}</title>
<style>
@page { size: A4 landscape; margin: 6mm; }
* { box-sizing: border-box !important; }
html, body {
    margin: 0;
    padding: 0;
    background: #fff !important;
    color: #111 !important;
    font-family: Tahoma, Arial, sans-serif;
    direction: ${direction};
    -webkit-print-color-adjust: exact !important;
    print-color-adjust: exact !important;
}
${printHeaderCss()}
.dco-print-page {
    width: 100%;
    min-height: 198mm;
    display: flex;
    flex-direction: column;
    break-after: page;
    page-break-after: always;
}
.dco-print-page:last-child {
    break-after: auto;
    page-break-after: auto;
}
.dco-print-order-meta {
    display: grid;
    grid-template-columns: repeat(6, minmax(0, 1fr));
    gap: 1mm;
    margin: 1.25mm 0 1.4mm;
}
.dco-print-order-meta > div {
    min-width: 0;
    padding: .8mm 1mm;
    border: .45pt solid #aab0b6;
    border-radius: 1mm;
    background: #fff;
    line-height: 1.1;
}
.dco-print-order-meta b { display: block; margin-bottom: .35mm; font-size: 5.4pt; color: #4d555c; }
.dco-print-order-meta span { display: block; font-size: 6.9pt; font-weight: 850; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.dco-extra-addon-legend {
    display: flex !important;
    flex-wrap: wrap !important;
    align-items: center !important;
    gap: 1.2mm 3.2mm !important;
    margin: 0 0 1mm !important;
    padding: .45mm 1.1mm !important;
    border: .45pt solid #aab0b6 !important;
    border-radius: 1mm !important;
    background: #fff !important;
    font-size: 6.2pt !important;
    font-weight: 750 !important;
    line-height: 1.1 !important;
    color: #111 !important;
}
.dco-extra-addon-legend-title { font-weight: 900 !important; white-space: nowrap !important; }
.dco-extra-addon-legend-item {
    display: inline-flex !important;
    align-items: center !important;
    gap: .8mm !important;
    white-space: nowrap !important;
    flex: 0 0 auto !important;
}
.dco-extra-addon-legend-swatch { width: 7mm !important; height: 2.4mm !important; }
.dco-extra-overlay { display: block !important; }
.dco-extra-addon-marks {
    display: block !important;
    position: absolute !important;
    inset: 0 !important;
    z-index: 5 !important;
    pointer-events: none !important;
}
.dco-extra-addon-mark {
    position: absolute !important;
    z-index: 5 !important;
    background: #fff !important;
    border: .3pt solid #c5ccd3 !important;
    border-radius: .4mm !important;
    padding: .15mm .4mm !important;
    line-height: 1.1 !important;
}
.dco-extra-addon-mark[data-addon-slot="top-start"] {
    top: 4% !important;
    left: 4% !important;
    right: auto !important;
}
.dco-extra-addon-mark[data-addon-slot="top-end"] {
    top: 4% !important;
    right: 4% !important;
    left: auto !important;
}
.dco-extra-addon-text {
    display: block !important;
    font-size: 5.2pt !important;
    font-weight: 900 !important;
    line-height: 1.1 !important;
    white-space: nowrap !important;
    font-family: Tahoma, Arial, sans-serif !important;
}
.dco-extra-addon-legend .dco-extra-addon-text {
    font-size: 6.2pt !important;
    padding: 0 !important;
}
.dco-print-sheets-grid {
    flex: 1 1 auto;
    min-height: 0;
    display: flex;
    flex-direction: column;
    justify-content: flex-start;
    align-content: stretch;
    align-items: stretch;
    gap: 2.2mm;
    padding-top: .8mm;
}
.dco-print-sheets-row {
    width: 100%;
    display: flex;
    flex: 0 0 auto;
    flex-wrap: nowrap;
    justify-content: center;
    align-items: flex-start;
    gap: 2.2mm;
}
.dco-sheet-card {
    flex: 0 0 var(--print-card-width, auto);
    width: var(--print-card-width, auto) !important;
    max-width: var(--print-card-width, 100%) !important;
    margin: 0 !important;
    padding: .4mm !important;
    border: 0 !important;
    border-radius: 0 !important;
    background: #fff !important;
    box-shadow: none !important;
    break-inside: avoid !important;
    page-break-inside: avoid !important;
}
.dco-sheet-title {
    display: block !important;
    margin: 0 0 .6mm !important;
    text-align: center !important;
    font-size: 8.5pt !important;
    font-weight: 950 !important;
    line-height: 1 !important;
}
.dco-print-sheet-number { text-align: center; }
.dco-board-original-edges {
    display: flex !important;
    flex-wrap: wrap;
    gap: .2mm .8mm;
    margin: 0 0 .25mm !important;
    padding: 0 !important;
    direction: inherit;
    line-height: 1 !important;
}
.dco-board-original-edge {
    position: static !important;
    color: #6b4a12 !important;
    font-size: 5.4pt !important;
    font-weight: 700 !important;
    line-height: 1 !important;
    white-space: nowrap !important;
}
.dco-sheet-board {
    position: relative !important;
    direction: ltr !important;
    display: block !important;
    border: 1.05pt solid #111 !important;
    background: #fff !important;
    overflow: hidden !important;
    box-shadow: none !important;
    -webkit-print-color-adjust: exact !important;
    print-color-adjust: exact !important;
}
.dco-sheet-card[data-resource-kind="OFFCUT"] .dco-sheet-board {
    background: #E5E7EB !important;
}
.dco-sheet-card[data-resource-kind="OFFCUT"] .dco-board-waste-hatch {
    display: none !important;
    background: none !important;
    background-image: none !important;
}
.dco-offcut-business-context {
    display: none !important;
    margin: 0 !important;
    padding: 0 !important;
    height: 0 !important;
    overflow: hidden !important;
    border: 0 !important;
}
.dco-usable-sheet {
    position: absolute !important;
    overflow: visible !important;
    border: 0 !important;
    background: transparent !important;
}
.dco-piece {
    overflow: visible !important;
    background: #fff !important;
    border-color: #111 !important;
    color: #111 !important;
    box-shadow: none !important;
    padding: 0 !important;
}
.dco-vector-piece { background: transparent !important; border: 0 !important; }
.dco-shaped-piece-outline path { fill: #fff !important; stroke: #111 !important; }
.dco-piece-label {
    direction: ltr !important;
    text-align: center !important;
    line-height: 1 !important;
    color: #111 !important;
    white-space: nowrap !important;
}
.dco-piece-kind-badge,
.dco-piece-size { display: none !important; }
.dco-piece-size-mm,
.dco-board-size-caption,
.dco-sheet-stats-edit { display: none !important; }
.dco-piece-number {
    display: block !important;
    padding: 0 !important;
    border: 0 !important;
    background: transparent !important;
    color: #111 !important;
    font-size: 6.6pt !important;
    font-weight: 950 !important;
    line-height: 1 !important;
}
.dco-edge-line {
    border-color: #e00000 !important;
    border-width: .45pt !important;
}
.dco-edge-line-svg {
    stroke: #e00000 !important;
    stroke-width: .45pt !important;
}
@media print {
    a { color: inherit !important; text-decoration: none !important; }
}
</style>
</head>
<body>${pages}<script>window.onload=function(){setTimeout(function(){window.focus();window.print();},350);};<\/script></body>
</html>`;
    }

    function printPlanRow(frm, tab) {
        return window.AlmdinaPlanWorkspaceState?.displayedPlanForTab?.(frm, tab) || null;
    }

    function rowGeometry(row) {
        const raw = row?.snapshot_json;
        if (!raw) return null;
        try {
            return typeof raw === "string" ? JSON.parse(raw) : raw;
        } catch (error) {
            return null;
        }
    }

    function rowAssignmentJson(row) {
        return JSON.stringify(Array.isArray(row?.offcut?.assignments)
            ? row.offcut.assignments : []);
    }

    function printAllowed(frm) {
        const permissions = window.AlmdinaPermissions;
        return Boolean(permissions && (typeof permissions.canDocument === "function"
            ? permissions.canDocument(frm, "print_cutting_plan")
            : permissions.can?.("print_cutting_plan")));
    }

    function printableDoc(doc) {
        return {
            name: doc.name, modified: doc.modified, customer: doc.customer,
            order_date: doc.order_date, board_description: doc.board_description,
            board_width_cm: doc.board_width_cm, board_length_cm: doc.board_length_cm,
            kerf_mm: doc.kerf_mm, default_edge_type: doc.default_edge_type,
            edge_color: doc.edge_color, packing_method: doc.packing_method,
            pieces: doc.pieces || [],
        };
    }

    function printableEdgeProfiles(frm) {
        const profiles = frm && frm._dco_side_edge_profiles;
        if (!(profiles instanceof Map)) return [];
        return [...profiles].map(([name, profile]) => [String(name), Number(profile?.thickness_mm) || 0])
            .sort(([left], [right]) => left.localeCompare(right));
    }

    function printSource(frm, planOverride, hint) {
        const context = window.AlmdinaDocumentContext;
        const owner = window.AlmdinaPlanWorkspaceState;
        const token = context?.capture?.(frm);
        const state = owner?.snapshot?.(frm);
        const tab = hint?.tab || window.AlmdinaPlanTabsUX?.activeTab?.(frm) || "System";
        const row = printPlanRow(frm, tab);
        const geometry = rowGeometry(row);
        if (!token || !context.isCurrent(frm, token) || !printAllowed(frm)
            || !state || state.status !== "ready" || state.freshness === "stale"
            || state.data?.order_name !== frm.doc?.name
            || state.data?.capabilities?.print === false
            || !row?.name || !geometry?.sheets?.length
            || (row.board?.description && row.board.description !== frm.doc.board_description)
            || (hint?.row && (hint.row.name !== row.name
                || hint.row.revision !== row.revision
                || JSON.stringify(rowGeometry(hint.row)) !== JSON.stringify(geometry)))
            || (planOverride && JSON.stringify(planOverride) !== JSON.stringify(geometry))) return null;
        const plan = JSON.parse(JSON.stringify(geometry));
        // Presentation labels are owned by the selected Workspace row. A
        // caller's non-enumerable plan metadata is outside the geometry check.
        const assignmentJson = rowAssignmentJson(row);
        Object.defineProperty(plan, "__offcut_assignments", {
            value: JSON.parse(assignmentJson), enumerable: false,
        });
        const frozenDoc = JSON.parse(JSON.stringify(printableDoc(frm.doc)));
        const edgeProfilesJson = JSON.stringify(printableEdgeProfiles(frm));
        return { token, tab, orderName: frm.doc.name, planName: row.name,
            revision: row.revision, geometryJson: JSON.stringify(geometry), assignmentJson,
            documentJson: JSON.stringify(frozenDoc), edgeProfilesJson, plan,
            frm: { doc: frozenDoc, _dco_side_edge_profiles: new Map(JSON.parse(edgeProfilesJson)
                .map(([name, thickness_mm]) => [name, { thickness_mm }])) } };
    }

    function printSourceStillCurrent(frm, source) {
        const context = window.AlmdinaDocumentContext;
        const state = window.AlmdinaPlanWorkspaceState?.snapshot?.(frm);
        const row = printPlanRow(frm, source.tab);
        return Boolean(context?.isCurrent(frm, source.token)
            && printAllowed(frm) && frm.doc.name === source.orderName
            && JSON.stringify(printableDoc(frm.doc)) === source.documentJson
            && JSON.stringify(printableEdgeProfiles(frm)) === source.edgeProfilesJson
            && state?.status === "ready" && state.freshness !== "stale"
            && state.data?.order_name === source.orderName
            && state.data?.capabilities?.print !== false
            && row?.name === source.planName && row.revision === source.revision
            && (!row.board?.description || row.board.description === frm.doc.board_description)
            && JSON.stringify(rowGeometry(row)) === source.geometryJson
            && rowAssignmentJson(row) === source.assignmentJson);
    }

    async function print_cutting_plan(frm, planOverride = null, hint = null) {
        const source = printSource(frm, planOverride, hint);
        if (!source) {
            frappe.msgprint(translate("Could not prepare printing."));
            return false;
        }
        const plan = source.plan;
        const frozenFrm = source.frm;
        // Always build from the verified Plan row. A visible DOM node may
        // outlive its owning document or represent a different plan revision.
        const planRoot = planRootFromPlan(frozenFrm, plan);
        if (!planRoot || !planRoot.querySelector(".dco-sheet-card")) {
            frappe.msgprint(translate("There is no cutting plan to print. Recalculate the cutting plan first."));
            return false;
        }

        const title = translate("Cutting plan - {0}", [source.orderName]);
        const print_window = window.open("", "_blank");
        if (!print_window) {
            frappe.msgprint(translate("The browser blocked the print window. Allow pop-ups and try again."));
            return false;
        }

        print_window.document.open();
        const language = uiLanguage();
        const direction = uiDirection();
        print_window.document.write(`<!doctype html><html lang="${escape_html(language)}" dir="${escape_html(direction)}"><head><meta charset="utf-8"><title>${htmlText("Preparing the cutting plan…")}</title></head><body style="font-family:Tahoma,Arial,sans-serif;padding:24px">${htmlText("Preparing the cutting plan for printing…")}</body></html>`);
        print_window.document.close();

        try {
            const identityApi = window.AlmdinaFactoryPrintIdentity;
            const identity = identityApi && typeof identityApi.get === "function"
                ? await identityApi.get()
                : (identityApi && typeof identityApi.fallback === "function" ? identityApi.fallback() : {});
            if (!printSourceStillCurrent(frm, source)) {
                print_window.close();
                return false;
            }
            print_window.document.open();
            print_window.document.write(buildPrintDocument(title, frozenFrm, planRoot, plan, identity, source));
            print_window.document.close();
            return true;
        } catch (error) {
            console.error("Cutting plan print preparation failed", error);
            try { print_window.close(); } catch (closeError) { /* ignored */ }
            frappe.msgprint(translate("Could not prepare the cutting plan for printing. Reload the page and try again."));
            return false;
        }
    }

    window.AlmdinaCuttingPlanRender = {
        build: build_cutting_plan_html,
        parse: parse_plan,
        print: print_cutting_plan,
        physicalMarginsMm,
        originalEdges,
    };
})();
