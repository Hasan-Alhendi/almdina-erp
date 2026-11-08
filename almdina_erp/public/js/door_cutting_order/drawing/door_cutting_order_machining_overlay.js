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
            specs: "liner_specs_json",
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
        if (kind === "liner") {
            const liners = linerSpecsFrom(row);
            return liners.some(item => item && String(item.side || "").trim() && num(item.widthCm) > 0);
        }
        return Boolean(num(row[spec.enabled]))
            && Boolean(String(row[spec.side] || "").trim())
            && num(row[spec.width]) > 0;
    }

    function specFrom(row, kind) {
        const spec = addon(kind);
        if (!spec) return null;
        if (kind === "liner") {
            const liners = linerSpecsFrom(row);
            return liners[0] || {
                kind: spec.kind,
                layer: spec.layer,
                side: row && row[spec.side],
                offsetCm: row && row[spec.offset],
                widthCm: row && row[spec.width],
                startCm: row && row[spec.start],
                lengthCm: row && row[spec.length],
            };
        }
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

    function linerSpecsFrom(row) {
        const api = geometry();
        if (api && typeof api.parseDoorLiners === "function") {
            const parsed = api.parseDoorLiners(row || {});
            if (!parsed.enabled) return [];
            return (parsed.liners || []).map(item => ({
                kind: "liner",
                layer: "Liner",
                id: item.id,
                side: item.side,
                offsetCm: item.offsetCm,
                widthCm: parsed.widthCm,
                startCm: item.startCm,
                lengthCm: item.lengthCm,
            })).filter(item => String(item.side || "").trim() && num(item.widthCm) > 0);
        }
        const spec = addon("liner");
        if (!spec || !row) return [];
        if (!(num(row[spec.enabled]) && String(row[spec.side] || "").trim() && num(row[spec.width]) > 0)) {
            return [];
        }
        return [{
            kind: spec.kind,
            layer: spec.layer,
            side: row[spec.side],
            offsetCm: row[spec.offset],
            widthCm: row[spec.width],
            startCm: row[spec.start],
            lengthCm: row[spec.length],
        }];
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
            if (spec.specs) copy[spec.specs] = row[spec.specs];
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

    function toolDiameterMm(piece, kind) {
        const map = piece && piece.tool_diameters;
        const raw = map && map[kind];
        const parsed = Number(raw);
        if (Number.isFinite(parsed) && parsed > 0) return parsed;
        return num(piece && piece.kerf_mm);
    }

    function overlayPathPresent(overlay) {
        const geometry = overlay && overlay.geometry;
        if (!geometry || typeof geometry !== "object") return false;
        const path = geometry.path || geometry.outer;
        return Array.isArray(path) && path.length >= 2;
    }

    function planBody(plan) {
        if (!plan || typeof plan !== "object") return null;
        if (Array.isArray(plan.sheets)) return plan;
        const raw = plan.snapshot_json != null ? plan.snapshot_json : plan.snapshot;
        if (raw && typeof raw === "object" && Array.isArray(raw.sheets)) return raw;
        if (typeof raw === "string" && raw.trim()) {
            try {
                const parsed = JSON.parse(raw);
                if (parsed && typeof parsed === "object" && Array.isArray(parsed.sheets)) return parsed;
            } catch (error) {
                return null;
            }
        }
        return null;
    }

    function layersInPlan(plan) {
        const present = {
            readable: false,
            cut: false,
            liner: false,
            recessed_handle_cutout: false,
            back_groove: false,
        };
        const body = planBody(plan);
        if (!body) return present;
        present.readable = true;
        (body.sheets || []).forEach(sheet => {
            (sheet && sheet.pieces || []).forEach(piece => {
                if (!piece || typeof piece !== "object") return;
                const outer = piece.geometry && (piece.geometry.outer || piece.geometry.path);
                if ((Array.isArray(outer) && outer.length >= 2) || (num(piece.w) > 0 && num(piece.h) > 0)) {
                    present.cut = true;
                }
                ADDONS.forEach(spec => {
                    if (present[spec.kind]) return;
                    if (requested(piece, spec.kind)) present[spec.kind] = true;
                    const overlays = Array.isArray(piece.overlays) ? piece.overlays : [];
                    if (overlays.some(item => item && item.kind === spec.kind && overlayPathPresent(item))) {
                        present[spec.kind] = true;
                    }
                });
            });
        });
        return present;
    }

    function linerOverlays(piece, mode) {
        const api = geometry();
        const specs = linerSpecsFrom(piece);
        if (!api || !specs.length) return [];
        if (mode === "toolpath" && specs.length === 1) {
            const overlay = overlayForSpec(piece, specs[0], mode);
            return overlay ? [overlay] : [];
        }
        if (mode === "toolpath" && typeof api.mergedToolpathsMm === "function") {
            const host = linerViewHost(piece, specs[0]);
            const geomPiece = typeof api.pieceFromRow === "function" ? api.pieceFromRow(host) : host;
            try {
                const diameter = toolDiameterMm(piece, "liner");
                if (!(diameter > 0)) {
                    return [{ kind: "liner", layer: "Liner", synthetic: true, error: "cutter_diameter_invalid" }];
                }
                const sawnEnds = piece && piece.board && typeof api.sawnBoundaryEnds === "function"
                    ? specs.map(spec => api.sawnBoundaryEnds(linerViewHost(piece, spec), geomPiece, piece.board))
                    : null;
                const sheetObstacles = piece.machining_obstacles || piece.obstacles;
                const localObstacles = sheetObstacles && sheetObstacles.length && typeof api.sheetObstaclesToLocal === "function"
                    ? api.sheetObstaclesToLocal(piece, geomPiece, sheetObstacles)
                    : null;
                const endsByIndex = localObstacles && localObstacles.length
                    ? specs.map((_spec, index) => Object.assign({}, (sawnEnds && sawnEnds[index]) || {}, {
                        obstacles: localObstacles,
                    }))
                    : sawnEnds;
                const paths = api.mergedToolpathsMm(
                    geomPiece,
                    specs.map(spec => ({
                        side: spec.side,
                        offsetCm: spec.offsetCm,
                        startCm: spec.startCm,
                        lengthCm: spec.lengthCm,
                    })),
                    specs[0].widthCm,
                    diameter,
                    endsByIndex
                );
                return paths.map(local => ({
                    kind: "liner",
                    layer: "Liner",
                    synthetic: true,
                    geometry: {
                        schema_version: 1,
                        unit: "mm",
                        coordinate_space: "usable_sheet",
                        closed: false,
                        toolpath: true,
                        path: typeof api.placeLocalPath === "function"
                            ? api.placeLocalPath(piece, geomPiece, local)
                            : local,
                    },
                }));
            } catch (error) {
                return [{
                    kind: "liner",
                    layer: "Liner",
                    synthetic: true,
                    error: error.code || "liner_extension_unsafe",
                }];
            }
        }
        return specs.map(spec => overlayForSpec(piece, spec, mode)).filter(Boolean);
    }

    function linerViewHost(piece, spec) {
        return Object.assign({}, piece, {
            liner_reference_side: spec.side,
            liner_offset_cm: spec.offsetCm,
            liner_width_cm: spec.widthCm,
            liner_start_cm: spec.startCm,
            liner_length_cm: spec.lengthCm,
        });
    }

    function overlayForSpec(piece, spec, mode) {
        const api = geometry();
        if (!api || !spec || typeof api.buildMachiningOverlay !== "function") return null;
        return api.buildMachiningOverlay(piece, spec, mode);
    }

    function isSpecialPiece(piece) {
        return String((piece && piece.piece_type) || "") === "Special";
    }

    function visualOverlays(piece) {
        if (isSpecialPiece(piece)) return [];
        const overlays = [];
        ADDONS.forEach(spec => {
            if (spec.kind === "liner") {
                linerOverlays(piece, "visual").forEach(item => overlays.push(item));
                return;
            }
            const overlay = overlayFor(piece, spec.kind, "visual");
            if (overlay) overlays.push(overlay);
        });
        return overlays;
    }

    function syntheticOverlays(piece) {
        if (isSpecialPiece(piece)) return [];
        const overlays = [];
        ADDONS.forEach(spec => {
            if (spec.kind === "liner") {
                linerOverlays(piece, "toolpath").forEach(item => overlays.push(item));
                return;
            }
            const overlay = overlayFor(piece, spec.kind, "toolpath");
            if (overlay) overlays.push(overlay);
        });
        return overlays;
    }

    function completeToolpaths(piece, existing, kerfMm, board, diameters, obstacles) {
        const next = Array.isArray(existing) ? existing.slice() : [];
        if (isSpecialPiece(piece)) return { overlays: next };
        const host = Object.assign({}, piece, {
            kerf_mm: num(kerfMm),
            tool_diameters: diameters || (piece && piece.tool_diameters) || null,
            board: board || null,
            machining_obstacles: obstacles || piece.machining_obstacles || null,
        });
        for (let index = 0; index < ADDONS.length; index += 1) {
            const spec = ADDONS[index];
            if (next.some(item => item && item.kind === spec.kind)) continue;
            const synthetics = spec.kind === "liner"
                ? linerOverlays(host, "toolpath")
                : [overlayFor(host, spec.kind, "toolpath")].filter(Boolean);
            const failed = synthetics.find(item => item && item.error);
            if (requested(piece, spec.kind) && (failed || !synthetics.length)) {
                return {
                    error: {
                        code: (failed && failed.error) || "liner_extension_unsafe",
                        addon: spec,
                    },
                };
            }
            synthetics.forEach(synthetic => {
                if (synthetic && !synthetic.error) next.push(synthetic);
            });
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
        toolDiameterMm,
        layersInPlan,
        specFrom,
        linerSpecsFrom,
        applySpecs,
        generateToolpath,
        visualOverlays,
        syntheticOverlays,
        completeToolpaths,
        summary,
        openDialog,
    });
})();
