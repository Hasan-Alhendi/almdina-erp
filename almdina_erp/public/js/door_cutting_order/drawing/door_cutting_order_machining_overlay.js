/* Shared machining add-ons. Geometry stays in AlmdinaLinerGeometry. */
(() => {
    "use strict";

    if (window.AlmdinaMachiningOverlay) return;

    const ADDONS = Object.freeze([
        Object.freeze({
            kind: "liner",
            layer: "Liner",
            field: "extra_liner",
            enabled: "extra_liner",
            side: "liner_reference_side",
            offset: "liner_offset_cm",
            width: "liner_width_cm",
            start: "liner_start_cm",
            length: "liner_length_cm",
            title: "Liner",
            nounMessageId: "the liner",
            nounAr: "اللاينر",
        }),
        Object.freeze({
            kind: "back_groove",
            layer: "Rear Groove",
            field: "extra_back_groove",
            enabled: "extra_back_groove",
            side: "back_groove_reference_side",
            offset: "back_groove_offset_cm",
            width: "back_groove_width_cm",
            start: "back_groove_start_cm",
            length: "back_groove_length_cm",
            title: "Back Groove",
            nounMessageId: "the back groove",
            nounAr: "فرزة الظهر",
        }),
        Object.freeze({
            kind: "recessed_handle_cutout",
            layer: "Handle Recess",
            field: "extra_recessed_handle_cutout",
            enabled: "extra_recessed_handle_cutout",
            side: "recessed_handle_reference_side",
            offset: "recessed_handle_offset_cm",
            width: "recessed_handle_width_cm",
            start: "recessed_handle_start_cm",
            length: "recessed_handle_length_cm",
            title: "Recessed Handle",
            nounMessageId: "the recessed handle",
            nounAr: "مسكة الغطس",
        }),
    ]);
    const BY_KIND = Object.freeze(Object.fromEntries(ADDONS.map(addon => [addon.kind, addon])));
    const BY_FIELD = Object.freeze(Object.fromEntries(ADDONS.map(addon => [addon.field, addon])));

    function geometry() {
        return window.AlmdinaLinerGeometry;
    }

    function addon(kind) {
        return BY_KIND[kind || "liner"] || null;
    }

    function kindForField(fieldname) {
        const found = BY_FIELD[fieldname];
        return found ? found.kind : "";
    }

    function num(value) {
        const parsed = Number(value);
        return Number.isFinite(parsed) ? parsed : 0;
    }

    function requested(row, kind) {
        const spec = addon(kind);
        if (!spec || !row) return false;
        return Boolean(num(row[spec.enabled]))
            && Boolean(String(row[spec.side] || "").trim())
            && num(row[spec.width]) > 0;
    }

    function specFrom(row, kind) {
        const spec = addon(kind);
        if (!spec) return null;
        return {
            kind: spec.kind,
            layer: spec.layer,
            side: row && row[spec.side],
            offsetCm: row && row[spec.offset],
            widthCm: row && row[spec.width],
            startCm: row && row[spec.start],
            lengthCm: row && row[spec.length],
        };
    }

    function applySpecs(piece, row) {
        const copy = Object.assign({}, piece);
        if (!row) return copy;
        ADDONS.forEach(spec => {
            copy[spec.enabled] = row[spec.enabled];
            copy[spec.side] = row[spec.side];
            copy[spec.offset] = row[spec.offset];
            copy[spec.width] = row[spec.width];
            copy[spec.start] = row[spec.start];
            copy[spec.length] = row[spec.length];
        });
        return copy;
    }

    function generateToolpath(options) {
        const api = geometry();
        const spec = options || {};
        if (!api || typeof api.generateToolpath !== "function") return null;
        addon(spec.type || spec.kind || "liner");
        return api.generateToolpath(spec);
    }

    function overlayFor(piece, kind, mode) {
        const api = geometry();
        const spec = specFrom(piece, kind);
        if (!api || !spec || typeof api.buildMachiningOverlay !== "function") return null;
        return api.buildMachiningOverlay(piece, spec, mode);
    }

    function visualOverlays(piece) {
        return ADDONS.map(spec => overlayFor(piece, spec.kind, "visual")).filter(Boolean);
    }

    function syntheticOverlays(piece) {
        return ADDONS.map(spec => overlayFor(piece, spec.kind, "toolpath")).filter(Boolean);
    }

    function completeToolpaths(piece, existing, kerfMm, board) {
        const next = Array.isArray(existing) ? existing.slice() : [];
        const host = Object.assign({}, piece, {
            kerf_mm: num(kerfMm),
            board: board || null,
        });
        for (let index = 0; index < ADDONS.length; index += 1) {
            const spec = ADDONS[index];
            if (next.some(item => item && item.kind === spec.kind)) continue;
            const synthetic = overlayFor(host, spec.kind, "toolpath");
            if (requested(piece, spec.kind) && (!synthetic || synthetic.error)) {
                return {
                    error: {
                        code: (synthetic && synthetic.error) || "liner_extension_unsafe",
                        addon: spec,
                    },
                };
            }
            if (synthetic && !synthetic.error) next.push(synthetic);
        }
        return { overlays: next };
    }

    function summary(row, fieldname) {
        const spec = BY_FIELD[fieldname] || addon("liner");
        const api = geometry();
        if (!spec || !row || !num(row[spec.enabled]) || !row[spec.side] || !api) return "";
        if (spec.kind === "liner" && typeof api.summary === "function") return api.summary(row);
        const piece = api.pieceFromRow(row);
        return `${api.sideLabel(row[spec.side], piece.pieceType)} · ${num(row[spec.offset])} / ${num(row[spec.width])} سم`;
    }

    function openDialog(frm, row, kind) {
        const editor = window.AlmdinaLinerEditor;
        if (!editor || typeof editor.open !== "function") return false;
        return editor.open(frm, row, kind || "liner");
    }

    window.AlmdinaMachiningOverlay = Object.freeze({
        ADDONS,
        addon,
        kindForField,
        requested,
        specFrom,
        applySpecs,
        generateToolpath,
        visualOverlays,
        syntheticOverlays,
        completeToolpaths,
        summary,
        openDialog,
    });
})();
