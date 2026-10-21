/* Liner settings dialog. Reuses the clipped-corner dialog shell and styles. */
(() => {
    "use strict";

    if (window.AlmdinaLinerEditor) return;

    const geometry = () => window.AlmdinaLinerGeometry;
    const LINER_ADDON = Object.freeze({
        kind: "liner",
        layer: "Liner",
        enabled: "extra_liner",
        side: "liner_reference_side",
        offset: "liner_offset_cm",
        width: "liner_width_cm",
        start: "liner_start_cm",
        length: "liner_length_cm",
        title: "Liner",
        nounAr: "اللاينر",
    });

    function addonFor(kind) {
        const engine = window.AlmdinaMachiningOverlay;
        const resolved = engine && typeof engine.addon === "function" ? engine.addon(kind || "liner") : null;
        return resolved || LINER_ADDON;
    }

    function noun(kind) {
        return addonFor(kind).nounAr || "اللاينر";
    }

    function localize(text, kind) {
        const resolved = __(text);
        if (!kind || kind === "liner") return resolved;
        return String(resolved).replaceAll("اللاينر", noun(kind)).replaceAll("Liner", noun(kind));
    }
    const MESSAGES = {
        missing_dimensions: "أدخل عرض الدرفة وطولها قبل ضبط اللاينر.",
        missing_corner: "اضبط زاوية الدرفة أولًا، ثم حدّد اللاينر.",
        invalid_corner: "موضع الزاوية غير صالح للاينر.",
        side_unavailable: "الجهة المختارة غير متاحة لهذا النوع من الدرفات.",
        choose_side: "Choose a reference side.",
        offset_invalid: "المسافة يجب أن تكون صفرًا أو أكبر.",
        width_invalid: "عرض اللاينر يجب أن يكون أكبر من صفر.",
        strip_outside: "اللاينر يخرج خارج الدرفة. قلّل المسافة أو العرض.",
        liner_start_invalid: "Liner start must be zero or greater.",
        liner_length_invalid: "Liner length must be greater than zero.",
        liner_span_exceeds_edge: "Liner start plus length exceeds the reference side.",
        liner_span_exceeds_edge_detail: "{0}: reference side length is {1} cm, start is {2} cm, entered length is {3} cm; maximum allowed length is {4} cm.",
        liner_flat_end_unmachinable: "A flat end cannot be machined with this bit and length.",
        liner_span_on_corner: "The liner limit sits on a bend that has no single direction.",
    };

    const DIRECTION = {
        edge_long_right: "Top to bottom",
        edge_long_left: "Top to bottom",
        edge_width_top: "Left to right",
        edge_width_bottom: "Left to right",
    };
    const HANDLE_STANDARD_SIZES_MM = Object.freeze([
        Object.freeze({ id: "38x329", widthMm: 38, lengthMm: 329 }),
        Object.freeze({ id: "38x296", widthMm: 38, lengthMm: 296 }),
        Object.freeze({ id: "38x230.5", widthMm: 38, lengthMm: 230.5 }),
        Object.freeze({ id: "38x199", widthMm: 38, lengthMm: 199 }),
        Object.freeze({ id: "38x167", widthMm: 38, lengthMm: 167 }),
        Object.freeze({ id: "38x136", widthMm: 38, lengthMm: 136 }),
        Object.freeze({ id: "37x103", widthMm: 37, lengthMm: 103 }),
    ]);
    const CENTER_HANDLE_MESSAGES = {
        unsupported_piece_type: "Cannot center the handle on this door type.",
        side_unavailable: "Cannot center the handle because the reference side is unavailable.",
        door_width_invalid: "Cannot center the handle because the door width is missing or invalid.",
        door_height_invalid: "Cannot center the handle because the door height is missing or invalid.",
        handle_length_invalid: "Cannot center the handle because its length is missing or invalid.",
        handle_width_invalid: "Cannot center the handle because its width is missing or invalid.",
        length_exceeds_door_width: "Cannot center the handle because its length exceeds the door width.",
        length_exceeds_door_height: "Cannot center the handle because its length exceeds the door height.",
        width_exceeds_door_height: "Cannot center the handle because its width exceeds the door height.",
        width_exceeds_door_width: "Cannot center the handle because its width exceeds the door width.",
        center_rejected: "Cannot center the handle.",
    };

    function edgeCm(piece, side) {
        return geometry().edgeLengthMm(piece, side) / 10;
    }

    function num(value) {
        const parsed = Number(value);
        return Number.isFinite(parsed) ? parsed : 0;
    }

    function rounded(value) {
        return Math.round(num(value) * 10) / 10;
    }

    function formatInput(value, places) {
        if (!Number.isFinite(Number(value))) return "";
        return Number(Number(value).toFixed(places)).toString();
    }

    function inputNumber(input) {
        if (!input || String(input.value).trim() === "") return NaN;
        const value = Number(input.value);
        return Number.isFinite(value) ? value : NaN;
    }

    function storedNumber(value, fallback) {
        if (value === undefined || value === null || String(value).trim() === "") return fallback;
        const parsed = Number(value);
        return Number.isFinite(parsed) ? parsed : NaN;
    }

    function widthMm(cm) {
        return rounded(num(cm) * 10);
    }

    function esc(value) {
        return frappe.utils.escape_html(value == null ? "" : String(value));
    }

    function dimensions(row) {
        const cutWidth = row && row.cut_width_cm;
        const cutLength = row && row.cut_length_cm;
        return {
            width: cutWidth !== undefined && cutWidth !== null ? num(cutWidth) : num(row && row.width_cm),
            length: cutLength !== undefined && cutLength !== null ? num(cutLength) : num(row && row.length_cm),
        };
    }

    function draftFromRow(row, kind, options) {
        const api = geometry();
        const addon = addonFor(kind);
        const piece = api.pieceFromRow(row);
        const sides = api.availableSides(piece.pieceType);
        const rawSide = row && row[addon.side] ? String(row[addon.side]) : "";
        const validStored = Boolean(rawSide) && sides.includes(rawSide);
        let side = "";
        if (validStored) side = rawSide;
        else if (!rawSide && !(options && options.blankWhenMissing)) side = sides[0] || "";
        const edge = edgeCm(piece, side);
        const rawLength = row && row[addon.length];
        const storedLength = Number(rawLength);
        const missingLength = rawLength === undefined || rawLength === null || String(rawLength).trim() === "";
        const validStoredLength = missingLength || Number.isFinite(storedLength);
        const fullLength = missingLength || (validStoredLength && storedLength === 0);
        const hasStoredValues = Boolean(
            rawSide
            || Number(row && row[addon.enabled])
            || num(row && row[addon.offset])
            || num(row && row[addon.width])
            || num(row && row[addon.start])
            || (!missingLength && storedLength !== 0)
        );
        const startCm = storedNumber(row && row[addon.start], 0);
        const legacyCheckboxOnly = Boolean(
            row && row.name && !row.__islocal
            && Number(row && row[addon.enabled])
            && !rawSide
            && num(row && row[addon.offset]) <= 0
            && num(row && row[addon.width]) <= 0
        );
        return {
            piece,
            row,
            kind: addon.kind,
            side,
            offsetCm: hasStoredValues ? storedNumber(row && row[addon.offset], 0) : 2,
            widthCm: hasStoredValues ? storedNumber(row && row[addon.width], 0) : 1.5,
            startCm,
            lengthCm: fullLength ? Math.max(0, edge - startCm) : storedLength,
            fullLength,
            legacyCheckboxOnly,
            edgeCm: edge,
            enabled: Boolean(Number(row && row[addon.enabled])),
        };
    }

    function validationIssue(draft) {
        if (!draft) return { code: "missing_draft", field: "side", fields: ["side"], message: localize(MESSAGES.choose_side, "liner") };
        if (draft.legacyCheckboxOnly) return null;
        if (!draft.side) return { code: "choose_side", field: "side", fields: ["side"], message: localize(MESSAGES.choose_side, draft.kind) };
        const availableSides = geometry().availableSides(draft.piece && draft.piece.pieceType);
        if (!availableSides.includes(draft.side)) {
            return { code: "side_unavailable", field: "side", fields: ["side"], message: localize(MESSAGES.side_unavailable, draft.kind) };
        }
        if (!Number.isFinite(draft.offsetCm) || draft.offsetCm < 0) {
            return { code: "offset_invalid", field: "offset", fields: ["offset"], message: localize(MESSAGES.offset_invalid, draft.kind) };
        }
        if (!Number.isFinite(draft.widthCm) || draft.widthCm <= 0) {
            return { code: "width_invalid", field: "width", fields: ["width"], message: localize(MESSAGES.width_invalid, draft.kind) };
        }
        if (!Number.isFinite(draft.startCm) || draft.startCm < 0) {
            return { code: "liner_start_invalid", field: "start", fields: ["start"], message: localize(MESSAGES.liner_start_invalid, draft.kind) };
        }
        const availableLengthCm = edgeCm(draft.piece, draft.side);
        const maximumLengthCm = availableLengthCm - draft.startCm;
        if (maximumLengthCm <= 0) {
            return { code: "liner_length_invalid", field: "start", fields: ["start", "length"], message: localize(MESSAGES.liner_length_invalid, draft.kind) };
        }
        if (!Number.isFinite(draft.lengthCm) || draft.lengthCm <= 0) {
            return { code: "liner_length_invalid", field: "length", fields: ["length"], message: localize(MESSAGES.liner_length_invalid, draft.kind) };
        }
        const spanToleranceCm = geometry().toleranceMm / 10;
        if (!draft.fullLength && draft.lengthCm > maximumLengthCm + spanToleranceCm) {
            const issueText = __(MESSAGES.liner_span_exceeds_edge_detail, [
                noun(draft.kind),
                formatInput(availableLengthCm, 3),
                formatInput(draft.startCm, 3),
                formatInput(draft.lengthCm, 3),
                formatInput(Math.max(0, maximumLengthCm), 3),
            ]);
            return {
                code: "liner_span_exceeds_edge",
                field: "length",
                fields: ["start", "length"],
                message: issueText,
                availableLengthCm,
                maximumLengthCm,
            };
        }
        const code = geometry().validationCode(draft.piece, draft.side, draft.offsetCm, draft.widthCm);
        if (code) {
            const field = code === "offset_invalid" ? "offset" : code === "width_invalid" ? "width" : "side";
            return { code, field, fields: [field], message: localize(MESSAGES[code] || code, draft.kind) };
        }
        try {
            geometry().centerlineMm(
                draft.piece,
                draft.side,
                draft.offsetCm,
                draft.widthCm,
                draft.startCm,
                draft.fullLength ? 0 : draft.lengthCm
            );
        } catch (error) {
            const field = error.code === "liner_start_invalid" ? "start" : "length";
            return {
                code: error.code || "invalid_geometry",
                field,
                fields: [field],
                message: localize(MESSAGES[error.code] || error.code || "Liner settings are invalid.", draft.kind),
            };
        }
        return null;
    }

    function validationMessage(draft) {
        const issue = validationIssue(draft);
        return issue ? issue.message : "";
    }

    function mapPoint(point, frame, piece) {
        return [
            frame.x + ((point[0] / (piece.widthCm * 10)) * frame.width),
            frame.y + ((point[1] / (piece.lengthCm * 10)) * frame.height),
        ];
    }

    function pointsAttr(points) {
        return points.map(point => `${rounded(point[0])},${rounded(point[1])}`).join(" ");
    }

    function machiningTone(kind) {
        if (kind === "back_groove") return { fill: "rgba(15,122,74,.2)", stroke: "#0f7a4a" };
        if (kind === "recessed_handle_cutout") return { fill: "rgba(194,106,18,.2)", stroke: "#c26a12" };
        return { fill: "rgba(29,111,191,.22)", stroke: "#1d6fbf" };
    }

    function machiningLayer(draft, frame, piece, role) {
        const api = geometry();
        const paths = api.edgePaths(piece);
        if (!draft || !draft.side || !paths[draft.side] || validationMessage(draft)) return "";
        const tone = role === "legacy"
            ? { fill: "rgba(29,111,191,.22)", stroke: "#1d6fbf" }
            : machiningTone(draft.kind);
        const width = role === "active" ? 2.2 : (role === "quiet" ? 1.2 : 1.4);
        let center = "";
        if (draft.kind !== "recessed_handle_cutout") {
            try {
                const line = api.centerlineMm(
                    piece,
                    draft.side,
                    draft.offsetCm,
                    draft.widthCm,
                    draft.startCm,
                    draft.lengthCm
                ).map(point => mapPoint(point, frame, piece));
                center = `<polyline data-liner-center="1" data-machining-kind="${esc(draft.kind)}" points="${pointsAttr(line)}" fill="none" stroke="${tone.stroke}" stroke-width="${role === "quiet" ? 1.2 : 1.8}" stroke-dasharray="5 3" stroke-linecap="butt"/>`;
            } catch (error) {
                center = "";
            }
        }
        const polygon = api.regionPolygonMm(
            piece,
            draft.side,
            draft.offsetCm,
            draft.widthCm,
            draft.startCm,
            draft.fullLength ? 0 : draft.lengthCm
        )
            .map(point => mapPoint(point, frame, piece));
        const strip = `<polygon class="dco-liner-strip" data-liner-strip="1" data-machining-kind="${esc(draft.kind)}" data-machining-role="${esc(role)}" points="${pointsAttr(polygon)}" fill="${tone.fill}" stroke="${tone.stroke}" stroke-width="${width}"/>`;
        if (role === "quiet") return `${strip}${center}`;
        const reference = api.regionReferenceMm(
            piece,
            draft.side,
            draft.startCm,
            draft.fullLength ? 0 : draft.lengthCm
        ).map(point => mapPoint(point, frame, piece));
        const near = polygon.slice(0, reference.length);
        const far = polygon.slice(reference.length).slice().reverse();
        const anchor = Math.floor(reference.length / 2);
        const from = reference[Math.min(anchor, reference.length - 1)];
        const mid = near[Math.min(anchor, near.length - 1)];
        const to = far[Math.min(anchor, far.length - 1)];
        let measures = "";
        if (from && mid && to) {
            measures = `
                <line class="dco-liner-measure" data-liner-offset-line="1" x1="${rounded(from[0])}" y1="${rounded(from[1])}" x2="${rounded(mid[0])}" y2="${rounded(mid[1])}" stroke="#9a6207" stroke-width="1.2"/>
                <line class="dco-liner-measure" data-liner-width-line="1" x1="${rounded(mid[0])}" y1="${rounded(mid[1])}" x2="${rounded(to[0])}" y2="${rounded(to[1])}" stroke="${tone.stroke}" stroke-width="1.2"/>
                <text data-liner-offset-label="1" x="${rounded((from[0] + mid[0]) / 2)}" y="${rounded((from[1] + mid[1]) / 2) - 4}" font-size="11" fill="#9a6207">${rounded(draft.offsetCm)}</text>
                <text data-liner-width-label="1" x="${rounded((mid[0] + to[0]) / 2)}" y="${rounded((mid[1] + to[1]) / 2) - 4}" font-size="11" fill="${tone.stroke}">${widthMm(draft.widthCm)} ${esc(__("mm"))}</text>`;
        }
        return `${strip}${center}${measures}`;
    }

    function previewScene(draft) {
        const api = geometry();
        const piece = draft.piece;
        const corner = window.AlmdinaClippedCornerGeometry;
        const frame = corner && typeof corner.previewFrame === "function"
            ? corner.previewFrame(piece.widthCm, piece.lengthCm)
            : { x: 30, y: 30, width: 300, height: 180, scale: 1 };
        const outline = api.piecePolygonMm(piece).map(point => mapPoint(point, frame, piece));
        const source = draft.row || {};
        const cornerPiece = corner && typeof corner.isCornerCut === "function" && corner.isCornerCut(source);
        const bands = cornerPiece && typeof corner.edgeBandSvgMarkup === "function"
            ? corner.edgeBandSvgMarkup(source, frame.width, frame.height, {
                offsetX: frame.x,
                offsetY: frame.y,
                inheritStroke: false,
                color: "#b42318",
                strokeWidth: 3,
                insetPx: 4,
                endTrimPx: 6,
            })
            : [
                [Number(source.edge_width_top), "edge_width_top", [[frame.x + 6, frame.y + 4], [frame.x + frame.width - 6, frame.y + 4]]],
                [Number(source.edge_width_bottom), "edge_width_bottom", [[frame.x + 6, frame.y + frame.height - 4], [frame.x + frame.width - 6, frame.y + frame.height - 4]]],
                [Number(source.edge_long_left), "edge_long_left", [[frame.x + 4, frame.y + 6], [frame.x + 4, frame.y + frame.height - 6]]],
                [Number(source.edge_long_right), "edge_long_right", [[frame.x + frame.width - 4, frame.y + 6], [frame.x + frame.width - 4, frame.y + frame.height - 6]]],
            ].filter(entry => entry[0]).map((entry, index) => (
                `<polyline data-liner-edge="1" data-liner-edge-side="${entry[1]}" data-liner-edge-index="${index}" points="${pointsAttr(entry[2])}" fill="none" stroke="#b42318" stroke-width="3" stroke-linecap="round"/>`
            )).join("");
        return { api, piece, frame, outline, bands };
    }

    function doubleEdgeSidesFromRow(row) {
        const source = row || {};
        const api = geometry();
        if (!Number(source.extra_double)) return [];
        if (api && typeof api.normalizeSideSelection === "function") {
            return api.normalizeSideSelection(
                source.extra_double_reference_sides,
                source.piece_type || "Regular",
                true,
            );
        }
        return [];
    }

    function doubleEdgeMarkup(row, scene, sides) {
        const selected = (sides || []).filter(Boolean);
        if (!selected.length) return "";
        const source = row || {};
        const api = scene.api;
        const flags = typeof api.sideFlagsForSelection === "function"
            ? api.sideFlagsForSelection(scene.piece, selected, false)
            : {};
        const corner = window.AlmdinaClippedCornerGeometry;
        if (corner && typeof corner.isCornerCut === "function" && corner.isCornerCut(source)
            && typeof corner.edgeBandSvgMarkup === "function") {
            const fields = ["edge_width_top", "edge_width_bottom", "edge_long_left", "edge_long_right", "edge_break", "edge_break_only"];
            const markup = fields.filter(side => flags[side]).map(side => {
                const normalBand = flagsForSource(source, side);
                const insets = normalBand ? [8, 11] : [4.5, 7.5];
                const sidePiece = { ...source };
                fields.forEach(name => {
                    sidePiece[name] = name === side ? 1 : 0;
                });
                const lines = insets.map(inset => corner.edgeBandSvgMarkup(sidePiece, scene.frame.width, scene.frame.height, {
                    offsetX: scene.frame.x,
                    offsetY: scene.frame.y,
                    inheritStroke: false,
                    color: "#5a2d82",
                    strokeWidth: 1.4,
                    insetPx: inset,
                    endTrimPx: 6,
                })).filter(Boolean).join("");
                return lines ? `<g data-double-edge-side="${side}">${lines}</g>` : "";
            }).join("");
            return markup ? `<g data-double-edge-lines="1">${markup}</g>` : "";
        }
        return selected.map((side) => {
            const normalBand = flagsForSource(source, side);
            const insetPx = normalBand ? [8, 11] : [4.5, 7.5];
            const offsetsMm = insetPx.map(offset => (offset / Math.max(Number(scene.frame.scale) || 1, 0.001)) * 10);
            const paths = typeof api.visualEdgeMarkerPaths === "function"
                ? api.visualEdgeMarkerPaths(scene.piece, side, offsetsMm)
                : [];
            return paths.map((path, index) => `<polyline data-double-edge-line="1" data-double-edge-line-index="${index}" data-double-edge-side="${side}" points="${pointsAttr(path.map(point => mapPoint(point, scene.frame, scene.piece)))}" fill="none" stroke="#5a2d82" stroke-width="1.4" vector-effect="non-scaling-stroke" stroke-linecap="round"/>`).join("");
        }).join("");
    }

    function flagsForSource(source, side) {
        return Boolean(Number(source && source[side]));
    }

    function doubleEdgeHitMarkup(scene, sides) {
        const api = scene.api;
        const selected = new Set(sides || []);
        return api.availableSides(scene.piece.pieceType).map((side) => {
            const path = api.edgePaths(scene.piece)[side];
            if (!path) return "";
            const active = selected.has(side);
            return `<polyline class="dco-double-side ${active ? "is-selected" : ""}" data-double-side="${side}" points="${pointsAttr(path.map(point => mapPoint(point, scene.frame, scene.piece)))}" fill="none" stroke="transparent" stroke-width="14" stroke-linecap="round"/>`;
        }).join("");
    }

    function previewSvg(draft, options) {
        const scene = previewScene(draft);
        const multi = Boolean(options && options.multi);
        const double = doubleEdgeMarkup(
            draft.row,
            scene,
            options && options.doubleSides,
        );
        const doubleHits = options && options.doubleInteractive
            ? doubleEdgeHitMarkup(scene, options.doubleSides)
            : "";
        const quiet = multi
            ? (options.companions || []).filter(item => (
                item && item.enabled && item.kind !== draft.kind
            )).map(item => machiningLayer(item, scene.frame, scene.piece, "quiet")).join("")
            : "";
        const active = multi
            ? (draft.enabled ? machiningLayer(draft, scene.frame, scene.piece, "active") : "")
            : machiningLayer(draft, scene.frame, scene.piece, "legacy");
        const hits = multi ? "" : scene.api.availableSides(scene.piece.pieceType).map(side => {
            const path = scene.api.edgePaths(scene.piece)[side];
            if (!path) return "";
            const selected = side === draft.side;
            return `<polyline class="dco-liner-side ${selected ? "is-selected" : ""}" data-liner-side="${side}" points="${pointsAttr(path.map(point => mapPoint(point, scene.frame, scene.piece)))}" fill="none" stroke="${selected ? "#9a6207" : "transparent"}" stroke-width="${selected ? 4 : 12}" stroke-linecap="round"/>`;
        }).join("");
        const label = multi ? __("Piece preview") : __("Liner preview");
        return `<svg viewBox="0 0 420 280" dir="ltr" role="img" aria-label="${esc(label)}">
            <polygon points="${pointsAttr(scene.outline)}" fill="#fff7e8" stroke="#8a5700" stroke-width="2"/>
            ${scene.bands}
            ${double}
            ${doubleHits}
            ${hits}
            ${quiet}
            ${active}
            <text x="210" y="268" text-anchor="middle" font-size="12" fill="#536577">${rounded(scene.piece.widthCm)} × ${rounded(scene.piece.lengthCm)} ${esc(__("cm"))}</text>
        </svg>`;
    }

    function handleSizeById(id) {
        return HANDLE_STANDARD_SIZES_MM.find(size => size.id === id) || null;
    }

    function matchingHandleSize(widthCm, lengthCm) {
        const widthMm = num(widthCm) * 10;
        const lengthMm = num(lengthCm) * 10;
        return HANDLE_STANDARD_SIZES_MM.find(size => (
            Math.abs(widthMm - size.widthMm) <= 0.05
            && Math.abs(lengthMm - size.lengthMm) <= 0.05
        )) || null;
    }

    function handleSizeLabel(size) {
        return `${formatInput(size.widthMm, 2)} × ${formatInput(size.lengthMm, 2)} ${__("mm")}`;
    }

    function handleCenteringAllowed(draft) {
        const rowType = draft && draft.row ? draft.row.piece_type : "";
        const pieceType = draft && draft.piece ? draft.piece.pieceType : "";
        return String(rowType || pieceType || "").trim() === "Regular";
    }

    function centerHandleMessage(code) {
        return __(CENTER_HANDLE_MESSAGES[code] || CENTER_HANDLE_MESSAGES.center_rejected);
    }

    function applyStandardHandleSize(draft, size) {
        return Object.assign({}, draft, {
            widthCm: size.widthMm / 10,
            lengthCm: size.lengthMm / 10,
            fullLength: false,
            legacyCheckboxOnly: false,
        });
    }

    function centerHandleDraft(draft) {
        if (!handleCenteringAllowed(draft)) {
            return { ok: false, code: "unsupported_piece_type", draft };
        }
        const api = geometry();
        const result = api && typeof api.centerRecessedHandle === "function"
            ? api.centerRecessedHandle(draft.piece, draft.side, draft.widthCm, draft.lengthCm)
            : { ok: false, code: "center_rejected" };
        if (!result.ok) return { ok: false, code: result.code, draft };
        const next = Object.assign({}, draft, {
            side: result.side,
            startCm: result.startCm,
            fullLength: false,
            legacyCheckboxOnly: false,
            edgeCm: edgeCm(draft.piece, result.side),
        });
        const issue = validationIssue(next);
        if (issue) return { ok: false, code: issue.code, message: issue.message, draft };
        return { ok: true, draft: next };
    }

    function writeMachiningInputs(root, draft) {
        if (!root || !draft) return;
        const offset = root.querySelector("[data-liner-offset]");
        const width = root.querySelector("[data-liner-width]");
        const start = root.querySelector("[data-liner-start]");
        const length = root.querySelector("[data-liner-length]");
        if (offset) offset.value = formatInput(draft.offsetCm, 3);
        if (width) width.value = formatInput(num(draft.widthCm) * 10, 2);
        if (start) start.value = formatInput(draft.startCm, 3);
        if (length) length.value = formatInput(draft.lengthCm, 3);
    }

    function handleIsCentered(draft) {
        if (!handleCenteringAllowed(draft) || !draft || !draft.piece) return false;
        const api = geometry();
        if (!api || typeof api.centerRecessedHandle !== "function") return false;
        const placed = api.centerRecessedHandle(draft.piece, draft.side, draft.widthCm, draft.lengthCm);
        if (!placed.ok || String(draft.side || "") !== placed.side) return false;
        return Math.abs(num(draft.startCm) - placed.startCm) <= 0.0001;
    }

    function syncHandleChoices(root, draft) {
        if (!root || !draft || draft.kind !== "recessed_handle_cutout") return;
        const match = matchingHandleSize(draft.widthCm, draft.lengthCm);
        root.querySelectorAll("[data-handle-size]").forEach(button => {
            const selected = Boolean(match) && button.getAttribute("data-handle-size") === match.id;
            button.classList.toggle("is-active", selected);
            button.setAttribute("aria-pressed", selected ? "true" : "false");
        });
        const center = root.querySelector("[data-handle-center]");
        if (!center) return;
        const centered = handleIsCentered(draft);
        const allowed = handleCenteringAllowed(draft);
        center.hidden = !allowed;
        center.classList.toggle("is-active", centered);
        center.setAttribute("aria-pressed", centered ? "true" : "false");
        const centerRow = center.parentElement;
        if (centerRow && centerRow.classList.contains("dco-handle-center-row")) centerRow.hidden = !allowed;
    }

    function handleChoicesHtml(draft) {
        if (!draft || draft.kind !== "recessed_handle_cutout") return "";
        const match = matchingHandleSize(draft.widthCm, draft.lengthCm);
        const chips = HANDLE_STANDARD_SIZES_MM.map(size => {
            const selected = Boolean(match) && match.id === size.id;
            return `<button type="button" class="dco-handle-size ${selected ? "is-active" : ""}" data-handle-size="${size.id}" aria-pressed="${selected ? "true" : "false"}" dir="ltr">${esc(handleSizeLabel(size))}</button>`;
        }).join("");
        const centerHidden = handleCenteringAllowed(draft) ? "" : " hidden";
        const centered = handleIsCentered(draft);
        return `<div class="dco-corner-section-label">${esc(__("Standard sizes"))}</div>
                <div class="dco-handle-size-grid" data-handle-sizes>${chips}</div>
                <div class="dco-handle-center-row"${centerHidden}><button type="button" class="dco-handle-size dco-handle-center ${centered ? "is-active" : ""}" data-handle-center="1" aria-pressed="${centered ? "true" : "false"}"${centerHidden}>${esc(__("Center Handle"))}</button></div>`;
    }

    function controlsHtml(draft) {
        const api = geometry();
        const sides = api.availableSides(draft.piece.pieceType).map(side => `
            <button type="button" class="dco-corner-position ${side === draft.side ? "is-active" : ""}" data-liner-side="${side}" aria-pressed="${side === draft.side ? "true" : "false"}">
                ${esc(api.sideLabel(side, draft.piece.pieceType))}
            </button>`).join("");
        const addon = addonFor(draft.kind);
        const widthLabel = addon.kind === "liner" ? __("Liner Width") : __("Machining Width");
        const startLabel = addon.kind === "liner" ? __("Liner Start Position") : __("Machining Start");
        const lengthLabel = addon.kind === "liner" ? __("Liner Length") : __("Machining Length");
        return `<div data-liner-fields data-machining-kind="${esc(addon.kind)}">
                <div class="dco-corner-section-label">${esc(__("Reference Side"))}</div>
                <div class="dco-corner-position-grid" data-liner-sides>${sides}</div>
                ${handleChoicesHtml(draft)}
                <div class="dco-corner-section-label">${esc(__("Distance and width"))}</div>
                <div class="dco-corner-input-grid">
                    <div class="dco-corner-input-wrap">
                        <label>${esc(__("Edge Offset"))}</label>
                        <div class="dco-corner-input-shell"><input type="number" min="0" step="1" data-liner-offset value="${formatInput(draft.offsetCm, 3)}"><span>${esc(__("cm"))}</span></div>
                    </div>
                    <div class="dco-corner-input-wrap">
                        <label>${esc(widthLabel)}</label>
                        <div class="dco-corner-input-shell"><input type="number" min="0" step="1" data-liner-width value="${formatInput(num(draft.widthCm) * 10, 2)}"><span>${esc(__("mm"))}</span></div>
                    </div>
                    <div class="dco-corner-input-wrap">
                        <label>${esc(startLabel)}</label>
                        <div class="dco-corner-input-shell"><input type="number" min="0" step="1" data-liner-start value="${formatInput(draft.startCm, 3)}"><span>${esc(__("cm"))}</span></div>
                    </div>
                    <div class="dco-corner-input-wrap">
                        <label>${esc(lengthLabel)}</label>
                        <div class="dco-corner-input-shell"><input type="number" min="0" step="1" data-liner-length value="${formatInput(draft.lengthCm, 3)}"><span>${esc(__("cm"))}</span></div>
                    </div>
                </div>
                <div class="dco-corner-help" data-liner-available>${esc(__("Available Length"))}: ${rounded(draft.edgeCm)} ${esc(__("cm"))}</div>
                <div class="dco-corner-help" data-liner-direction>${esc(__("Measurement Direction"))}: ${esc(__(DIRECTION[draft.side] || "Along the selected edge"))}</div>
                <div class="dco-corner-help" data-liner-help></div>
            </div>`;
    }

    function editorHtml(row, draft) {
        const addon = addonFor(draft.kind);
        const removeLabel = addon.kind === "liner" ? __("Remove liner") : __("Remove add-on");
        const remove = draft.enabled
            ? `<button type="button" class="btn btn-default btn-sm" data-liner-remove>${esc(removeLabel)}</button>`
            : "";
        return `<div class="dco-corner-editor" data-liner-editor data-machining-kind="${esc(addon.kind)}">
            <section class="dco-corner-preview-panel">
                <div class="dco-corner-preview-head">
                    <span class="dco-corner-badge">${esc(__(addon.title))}</span>
                </div>
                <div class="dco-corner-preview" data-liner-preview>${previewSvg(draft)}</div>
            </section>
            <section class="dco-corner-controls">
                ${controlsHtml(draft)}
                <button type="button" class="btn btn-default btn-sm" data-liner-cancel>${esc(__("Cancel"))}</button>
                ${remove}
            </section>
        </div>`;
    }

    function selectSide(draft, piece, nextSide) {
        const nextEdge = edgeCm(piece, nextSide);
        draft.side = nextSide;
        draft.edgeCm = nextEdge;
        if (draft.fullLength) draft.lengthCm = Math.max(0, nextEdge - draft.startCm);
        draft.legacyCheckboxOnly = false;
        return draft;
    }

    function readDraft(root, piece, enabled, row, kind, previous, changedField) {
        const offset = root.querySelector("[data-liner-offset]");
        const width = root.querySelector("[data-liner-width]");
        const start = root.querySelector("[data-liner-start]");
        const length = root.querySelector("[data-liner-length]");
        const active = root.querySelector("[data-liner-sides] .is-active");
        const side = active ? active.getAttribute("data-liner-side") : "";
        const startCm = inputNumber(start);
        const edge = edgeCm(piece, side);
        const fullLength = Boolean(previous && previous.fullLength && changedField !== "length");
        const rawLength = inputNumber(length);
        const lengthCm = fullLength && changedField === "start"
            ? Math.max(0, edge - startCm)
            : rawLength;
        const offsetCm = inputNumber(offset);
        const widthCm = inputNumber(width) / 10;
        return {
            piece,
            row: row || null,
            kind: kind || "liner",
            side,
            offsetCm,
            widthCm,
            startCm,
            lengthCm,
            fullLength,
            legacyCheckboxOnly: Boolean(previous && previous.legacyCheckboxOnly
                && !changedField
                && !(Number.isFinite(offsetCm) && offsetCm > 0)
                && !(Number.isFinite(widthCm) && widthCm > 0)
                && !side),
            edgeCm: edge,
            enabled,
        };
    }

    function paint(root, draft, dialog) {
        const preview = root.querySelector("[data-liner-preview]");
        if (preview) preview.innerHTML = previewSvg(draft);
        root.querySelectorAll("[data-liner-sides] [data-liner-side]").forEach(button => {
            const selected = button.getAttribute("data-liner-side") === draft.side;
            button.classList.toggle("is-active", selected);
            button.setAttribute("aria-pressed", selected ? "true" : "false");
        });
        const help = root.querySelector("[data-liner-help]");
        const available = root.querySelector("[data-liner-available]");
        const direction = root.querySelector("[data-liner-direction]");
        const message = validationMessage(draft);
        if (available) available.textContent = `${__("Available Length")}: ${formatInput(draft.edgeCm, 3)} ${__("cm")}`;
        if (direction) {
            direction.textContent = `${__("Measurement Direction")}: ${__(DIRECTION[draft.side] || "Along the selected edge")}`;
        }
        if (help) help.textContent = message;
        syncHandleChoices(root, draft);
        if (dialog && dialog.get_primary_btn) {
            dialog.get_primary_btn().prop("disabled", Boolean(message));
        }
        return message;
    }

    function refreshTable(frm) {
        if (window.AlmdinaDoorCuttingFastEntry && window.AlmdinaDoorCuttingFastEntry.render) {
            window.AlmdinaDoorCuttingFastEntry.render(frm);
        }
    }

    function hostPiece(frm, row) {
        const api = geometry();
        const banding = window.AlmdinaMultiEdgeBanding;
        const calculated = banding && typeof banding.calculate === "function"
            ? banding.calculate(frm, row)
            : null;
        const size = dimensions(row);
        const source = calculated ? {
            ...row,
            cut_width_cm: calculated.cutWidth,
            cut_length_cm: calculated.cutLength,
        } : row;
        const piece = api.pieceFromRow(source);
        piece.widthCm = calculated ? calculated.cutWidth : size.width;
        piece.lengthCm = calculated ? calculated.cutLength : size.length;
        if (typeof api.contourNotchFromOrder === "function") {
            const notch = api.contourNotchFromOrder(frm, source);
            piece.cutWidthCm = notch.cutWidthCm;
            piece.cutLengthCm = notch.cutLengthCm;
        }
        return piece;
    }

    function failureText(error, kind) {
        if (!error) {
            return addonFor(kind).kind === "liner"
                ? __("Could not save the liner.")
                : __("Could not save the add-on.");
        }
        return String(error.message || error);
    }

    function valuesFor(kind, draft, enabled) {
        const addon = addonFor(kind || (draft && draft.kind));
        const values = {};
        values[addon.enabled] = enabled ? 1 : 0;
        values[addon.side] = enabled ? draft.side : "";
        values[addon.offset] = enabled ? draft.offsetCm : 0;
        values[addon.width] = enabled ? draft.widthCm : 0;
        values[addon.start] = enabled ? draft.startCm : 0;
        values[addon.length] = enabled ? (draft.fullLength ? 0 : draft.lengthCm) : 0;
        return values;
    }

    const applyGate = { running: false };

    async function writeLiner(frm, sourceRow, values, kind) {
        const editor = window.AlmdinaClippedCornerEditor;
        const row = editor && typeof editor.resolveChildRow === "function"
            ? editor.resolveChildRow(frm, sourceRow)
            : sourceRow;
        if (!row) {
            frappe.msgprint({
                title: __(addonFor(kind).title),
                message: __("This door piece is no longer in the order."),
                indicator: "orange",
            });
            return false;
        }
        const api = geometry();
        if (!api.availableSides(row.piece_type || "Regular").length) {
            frappe.msgprint({
                title: __(addonFor(kind).title),
                message: addonFor(kind).kind === "liner"
                    ? __("This piece type no longer supports a liner.")
                    : __("This piece type does not support this add-on."),
                indicator: "orange",
            });
            return false;
        }
        const addon = addonFor(kind);
        if (Number(values[addon.enabled])) {
            const piece = hostPiece(frm, row);
            const code = api.validationCode(
                piece,
                values[addon.side],
                values[addon.offset],
                values[addon.width]
            );
            if (code) {
                frappe.msgprint({
                    title: addon.kind === "liner" ? __("Check liner") : __("Check add-on"),
                    message: localize(MESSAGES[code] || code, addon.kind),
                    indicator: "orange",
                });
                return false;
            }
        }
        if (!editor || typeof editor.commitChildValues !== "function") {
            await frappe.model.set_value(row.doctype, row.name, values);
        } else {
            await editor.commitChildValues(frm, row, values);
        }
        frm.dirty();
        refreshTable(frm);
        return true;
    }

    async function applyLiner(frm, sourceRow, values, kind) {
        if (applyGate.running) return false;
        applyGate.running = true;
        const editor = window.AlmdinaClippedCornerEditor;
        const queued = editor && typeof editor.queueChildApply === "function"
            ? editor.queueChildApply(frm, () => writeLiner(frm, sourceRow, values, kind))
            : writeLiner(frm, sourceRow, values, kind);
        try {
            const result = await queued;
            if (result && typeof result.ok === "boolean") {
                if (!result.ok) {
                    frappe.msgprint({
                    title: __(addonFor(kind).title),
                    message: failureText(result.error, kind),
                        indicator: "red",
                    });
                    return false;
                }
                return result.value !== false;
            }
            return result !== false;
        } catch (error) {
            frappe.msgprint({
            title: __(addonFor(kind).title),
            message: failureText(error, kind),
                indicator: "red",
            });
            return false;
        } finally {
            applyGate.running = false;
        }
    }

    let activeDialog = null;

    function open(frm, row, kind) {
        const api = geometry();
        if (!frm || !row || !api) return false;
        if ((row.piece_type || "Regular") === "Special") return false;
        if (!api.availableSides(row.piece_type || "Regular").length) return false;
        const size = dimensions(row);
        if (!size.width || !size.length) {
            frappe.msgprint({
                title: __("Enter dimensions first"),
                message: __("Enter the piece width and length before editing the liner."),
                indicator: "orange",
            });
            return false;
        }
        const cornerEditor = window.AlmdinaClippedCornerEditor;
        if (cornerEditor && typeof cornerEditor.ensureStyles === "function") cornerEditor.ensureStyles();
        if (activeDialog) {
            try { activeDialog.hide(); } catch (error) { /* previous dialog */ }
            activeDialog = null;
        }
        const addon = addonFor(kind);
        const piece = hostPiece(frm, row);
        let draft = draftFromRow(row, addon.kind);
        draft.piece = piece;
        draft.edgeCm = edgeCm(piece, draft.side);
        if (draft.fullLength) draft.lengthCm = Math.max(0, draft.edgeCm - draft.startCm);
        const title = addon.kind === "liner"
            ? __("Liner — Door piece {0}", [row.piece_no || row.idx || ""])
            : __("{0} — Door piece {1}", [__(addon.title), row.piece_no || row.idx || ""]);
        const dialog = new frappe.ui.Dialog({
            title,
            fields: [{ fieldname: "liner_editor", fieldtype: "HTML" }],
            primary_action_label: __("Save"),
            primary_action() {
                const root = dialog.$wrapper.find("[data-liner-editor]").get(0);
                if (!root) return;
                draft = readDraft(root, piece, true, row, addon.kind, draft);
                const message = paint(root, draft, dialog);
                if (message) {
                    frappe.msgprint({
                        title: addon.kind === "liner" ? __("Check liner") : __("Check add-on"),
                        message,
                        indicator: "orange",
                    });
                    return Promise.resolve(false);
                }
                const button = dialog.get_primary_btn && dialog.get_primary_btn();
                if (button) button.prop("disabled", true);
                return applyLiner(frm, row, valuesFor(addon.kind, draft, true), addon.kind).then(saved => {
                    if (saved) dialog.hide();
                    else if (button) button.prop("disabled", Boolean(paint(root, draft, dialog)));
                });
            },
        });
        activeDialog = dialog;
        dialog.$wrapper.addClass("dco-clipped-corner-modal");
        dialog.show();
        const field = dialog.get_field("liner_editor");
        field.$wrapper.html(editorHtml(row, draft));
        const root = field.$wrapper.find("[data-liner-editor]").get(0);
        paint(root, draft, dialog);
        root.addEventListener("click", (event) => {
            const side = event.target.closest("[data-liner-side]");
            if (side && root.contains(side)) {
                draft = readDraft(root, piece, draft.enabled, row, addon.kind, draft);
                draft = selectSide(draft, piece, side.getAttribute("data-liner-side"));
                const startInput = root.querySelector("[data-liner-start]");
                const lengthInput = root.querySelector("[data-liner-length]");
                if (startInput) startInput.value = formatInput(draft.startCm, 3);
                if (lengthInput) lengthInput.value = formatInput(draft.lengthCm, 3);
                paint(root, draft, dialog);
                return;
            }
            const sizeButton = event.target.closest("[data-handle-size]");
            if (sizeButton && root.contains(sizeButton) && addon.kind === "recessed_handle_cutout") {
                const size = handleSizeById(sizeButton.getAttribute("data-handle-size"));
                if (!size) return;
                draft = applyStandardHandleSize(
                    readDraft(root, piece, true, row, addon.kind, draft, "length"),
                    size
                );
                writeMachiningInputs(root, draft);
                paint(root, draft, dialog);
                return;
            }
            const centerButton = event.target.closest("[data-handle-center]");
            if (centerButton && root.contains(centerButton) && addon.kind === "recessed_handle_cutout") {
                const current = readDraft(root, piece, draft.enabled, row, addon.kind, draft, "offset");
                const outcome = centerHandleDraft(current);
                if (!outcome.ok) {
                    paint(root, current, dialog);
                    const message = outcome.message || centerHandleMessage(outcome.code);
                    const help = root.querySelector("[data-liner-help]");
                    if (help) help.textContent = message;
                    frappe.msgprint({
                        title: __("Center Handle"),
                        message,
                        indicator: "orange",
                    });
                    return;
                }
                draft = Object.assign({}, outcome.draft, { enabled: true });
                writeMachiningInputs(root, draft);
                paint(root, draft, dialog);
                return;
            }
            if (event.target.closest("[data-liner-cancel]")) {
                dialog.hide();
                return;
            }
            if (event.target.closest("[data-liner-remove]")) {
                const remove = event.target.closest("[data-liner-remove]");
                remove.disabled = true;
                applyLiner(frm, row, valuesFor(addon.kind, draft, false), addon.kind).then(saved => {
                    if (saved) dialog.hide();
                    else remove.disabled = false;
                });
            }
        });
        root.addEventListener("input", (event) => {
            const target = event && event.target;
            const changedField = target && target.matches && target.matches("[data-liner-start]")
                ? "start"
                : target && target.matches && target.matches("[data-liner-length]")
                    ? "length"
                    : target && target.matches && target.matches("[data-liner-offset]")
                        ? "offset"
                        : target && target.matches && target.matches("[data-liner-width]")
                            ? "width"
                            : "";
            draft = readDraft(root, piece, draft.enabled, row, addon.kind, draft, changedField);
            if (draft.fullLength && changedField === "start") {
                const lengthInput = root.querySelector("[data-liner-length]");
                if (lengthInput) lengthInput.value = formatInput(draft.lengthCm, 3);
            }
            paint(root, draft, dialog);
        });
        return true;
    }

    window.AlmdinaLinerEditor = Object.freeze({
        open,
        applyLiner,
        previewSvg,
        doubleEdgeMarkup,
        doubleEdgeSidesFromRow,
        validationMessage,
        validationIssue,
        draftFromRow,
        edgeLengthCm: edgeCm,
        valuesFor,
        formatInputCm: value => formatInput(value, 3),
        controlsHtml,
        readDraft,
        selectSide,
        hostPiece,
        paint,
        handleStandardSizes: HANDLE_STANDARD_SIZES_MM,
        matchingHandleSize,
        applyStandardHandleSize,
        centerHandleDraft,
        centerHandleMessage,
        handleCenteringAllowed,
        syncHandleChoices,
        handleIsCentered,
        writeMachiningInputs,
    });
})();
