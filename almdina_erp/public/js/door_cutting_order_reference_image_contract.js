(() => {
    "use strict";

    const VERSION = 1;
    const DEFAULT_OPACITY = 0.34;
    const MIN_OPACITY = 0.12;
    const MAX_OPACITY = 0.85;
    const DEFAULT_CANVAS = Object.freeze({ width: 1000, height: 650 });

    function clone(value) {
        try {
            return value == null ? value : JSON.parse(JSON.stringify(value));
        } catch (error) {
            return null;
        }
    }

    function clampOpacity(value) {
        const numeric = Number(value);
        if (!Number.isFinite(numeric)) return DEFAULT_OPACITY;
        return Math.max(MIN_OPACITY, Math.min(MAX_OPACITY, numeric));
    }

    function safeFileUrl(value) {
        const url = String(value || "").trim();
        if (!url) return "";
        return /^\/(?:private\/files|files)\//.test(url) ? url : "";
    }

    function safeFileName(value, fileUrl = "") {
        const explicit = String(value || "").trim();
        if (explicit) return explicit.slice(0, 180);
        const fallback = String(fileUrl || "").split("/").pop() || "reference-image";
        try {
            return decodeURIComponent(fallback).slice(0, 180);
        } catch (error) {
            return fallback.slice(0, 180);
        }
    }

    function normalize(reference) {
        if (!reference || typeof reference !== "object" || Array.isArray(reference)) return null;
        const fileUrl = safeFileUrl(reference.file_url || reference.url);
        if (!fileUrl) return null;
        const source = reference.source === "scanner" ? "scanner" : "file";
        return Object.freeze({
            version: VERSION,
            file_url: fileUrl,
            file_name: safeFileName(reference.file_name || reference.name, fileUrl),
            source,
            opacity: clampOpacity(reference.opacity),
            visible: reference.visible !== false,
        });
    }

    function parseDrawing(raw) {
        const output = window.AlmdinaShapeOutputContract;
        if (output && typeof output.parseDrawing === "function") {
            const parsed = output.parseDrawing(raw);
            return parsed ? clone(parsed) : null;
        }
        if (!raw) return null;
        try {
            const parsed = typeof raw === "string" ? JSON.parse(raw) : clone(raw);
            return parsed && Number(parsed.version) === 1 && Array.isArray(parsed.elements)
                ? parsed
                : null;
        } catch (error) {
            return null;
        }
    }

    function fromDrawing(raw) {
        const drawing = parseDrawing(raw);
        return normalize(drawing && drawing.reference_image);
    }

    function fromRow(row) {
        return fromDrawing(row && row.special_shape_drawing_json);
    }

    function buildDrawing(raw, row, reference) {
        const current = parseDrawing(raw);
        const payload = current || {
            version: 1,
            canvas: { ...DEFAULT_CANVAS },
            elements: [],
            meta: {},
        };
        payload.version = 1;
        payload.canvas = payload.canvas && Number(payload.canvas.width) > 0 && Number(payload.canvas.height) > 0
            ? payload.canvas
            : { ...DEFAULT_CANVAS };
        payload.elements = Array.isArray(payload.elements) ? payload.elements : [];
        payload.meta = payload.meta && typeof payload.meta === "object" && !Array.isArray(payload.meta)
            ? payload.meta
            : {};
        if (row) {
            payload.meta = {
                purpose: payload.meta.purpose || "operator_documentation_only",
                piece_no: Number(row.idx || row.piece_no) || 0,
                blank_width_cm: Number(row.width_cm) || 0,
                blank_length_cm: Number(row.length_cm) || 0,
                ...payload.meta,
            };
        }
        const normalized = normalize(reference);
        if (normalized) payload.reference_image = clone(normalized);
        else delete payload.reference_image;
        return payload;
    }

    function writeToRow(row, reference) {
        if (!row) return null;
        const normalized = normalize(reference);
        const current = parseDrawing(row.special_shape_drawing_json);
        if (!normalized && (!current || !Array.isArray(current.elements) || !current.elements.length)) {
            row.special_shape_drawing_json = "";
            return null;
        }
        const payload = buildDrawing(row.special_shape_drawing_json, row, normalized);
        row.special_shape_drawing_json = JSON.stringify(payload);
        return normalize(payload.reference_image);
    }

    function hasDrawingElements(rowOrRaw) {
        const raw = rowOrRaw && typeof rowOrRaw === "object" && !Array.isArray(rowOrRaw)
            && Object.prototype.hasOwnProperty.call(rowOrRaw, "special_shape_drawing_json")
            ? rowOrRaw.special_shape_drawing_json
            : rowOrRaw;
        const drawing = parseDrawing(raw);
        return Boolean(drawing && Array.isArray(drawing.elements) && drawing.elements.length);
    }

    window.AlmdinaReferenceImageContract = Object.freeze({
        VERSION,
        DEFAULT_OPACITY,
        MIN_OPACITY,
        MAX_OPACITY,
        DEFAULT_CANVAS,
        clampOpacity,
        safeFileUrl,
        normalize,
        parseDrawing,
        fromDrawing,
        fromRow,
        buildDrawing,
        writeToRow,
        hasDrawingElements,
    });
})();
