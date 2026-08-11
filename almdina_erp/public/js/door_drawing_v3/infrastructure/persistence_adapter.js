(() => {
    "use strict";

    const root = window.AlmdinaDoorDrawingV3 = window.AlmdinaDoorDrawingV3 || Object.create(null);
    const documentModel = root.DocumentModel;
    const geometry = root.Geometry;
    if (!documentModel || !geometry) throw new Error("Drawing V3 domain must load before persistence adapter");

    function rowBlankMm(row) {
        return {
            widthMm: Math.max(0, geometry.number(row && row.width_cm) * 10),
            heightMm: Math.max(0, geometry.number(row && row.length_cm) * 10),
        };
    }

    function parseJson(raw) {
        if (!raw) return null;
        if (typeof raw === "object") return raw;
        try { return JSON.parse(String(raw)); } catch (error) { return null; }
    }

    function fromStored(raw, row) {
        const blank = rowBlankMm(row);
        const parsed = parseJson(raw);
        if (parsed && parsed.schema === documentModel.SCHEMA) {
            return documentModel.normalize(parsed, blank);
        }
        const embedded = parsed && parsed.meta && parsed.meta.door_drawing_v3;
        return documentModel.normalize(embedded, blank);
    }

    function compatibilityElement(object) {
        if (!object || object.type !== "line") return null;
        const scale = 0.1; // Compatibility projection only; V3 document remains authoritative in mm.
        return {
            id: String(object.id),
            type: "line",
            x1: geometry.roundMm(object.geometry.start.x * scale),
            y1: geometry.roundMm(object.geometry.start.y * scale),
            x2: geometry.roundMm(object.geometry.end.x * scale),
            y2: geometry.roundMm(object.geometry.end.y * scale),
            color: "#172033",
        };
    }

    function toStored(document, row) {
        const elements = document.objects.map(compatibilityElement).filter(Boolean);
        return JSON.stringify({
            version: 1,
            canvas: { width: 1000, height: 650 },
            elements,
            meta: {
                purpose: "door_drawing_v3_compatibility_envelope",
                authoritative: "door_drawing_v3",
                units: "mm",
                piece_no: row && (row.idx || row.piece_no || 0),
                blank_width_mm: document.blank.widthMm,
                blank_height_mm: document.blank.heightMm,
                door_drawing_v3: document,
            },
        });
    }

    root.PersistenceAdapter = Object.freeze({ rowBlankMm, fromStored, toStored });
})();
