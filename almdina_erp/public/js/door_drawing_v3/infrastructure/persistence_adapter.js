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
        if (parsed && parsed.schema === documentModel.SCHEMA) return documentModel.normalize(parsed, blank);
        const embedded = parsed && parsed.meta && parsed.meta.door_drawing_v3;
        return documentModel.normalize(embedded, blank);
    }

    function scaledPoint(point) {
        return [geometry.roundMm(point.x * 0.1), geometry.roundMm(point.y * 0.1)];
    }

    function compatibilityElement(object) {
        if (!object) return null;
        const scale = 0.1; // Compatibility projection only; V3 document remains authoritative in mm.
        if (object.type === "line") {
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
        if (object.type === "rectangle") {
            return {
                id: String(object.id),
                type: "rectangle",
                x: geometry.roundMm(object.geometry.origin.x * scale),
                y: geometry.roundMm(object.geometry.origin.y * scale),
                width: geometry.roundMm(object.geometry.widthMm * scale),
                height: geometry.roundMm(object.geometry.heightMm * scale),
                color: "#172033",
            };
        }
        if (object.type === "circle") {
            return {
                id: String(object.id),
                type: "ellipse",
                cx: geometry.roundMm(object.geometry.center.x * scale),
                cy: geometry.roundMm(object.geometry.center.y * scale),
                rx: geometry.roundMm(object.geometry.radiusMm * scale),
                ry: geometry.roundMm(object.geometry.radiusMm * scale),
                color: "#172033",
            };
        }
        if (object.type === "arc") {
            const samples = [];
            const count = Math.max(8, Math.ceil(Math.abs(object.geometry.sweepAngleDeg) / 10));
            for (let index = 0; index <= count; index += 1) {
                const angle = object.geometry.startAngleDeg + object.geometry.sweepAngleDeg * index / count;
                samples.push(scaledPoint(geometry.arcPoint(object, angle)));
            }
            return {
                id: String(object.id),
                type: "pen",
                points: samples,
                color: "#172033",
            };
        }
        return null;
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

    root.PersistenceAdapter = Object.freeze({ rowBlankMm, fromStored, toStored, compatibilityElement });
})();
