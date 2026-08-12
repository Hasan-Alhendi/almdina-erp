(() => {
    "use strict";

    const root = window.AlmdinaDoorDrawingV3 = window.AlmdinaDoorDrawingV3 || Object.create(null);
    const Base = root.PersistenceAdapter;
    const G = root.Geometry;
    if (!Base || !G || !G.path) throw new Error("Door Drawing V3 smart path domain and persistence must load first");

    function scaledPoint(point) {
        return [G.roundMm(point.x * 0.1), G.roundMm(point.y * 0.1)];
    }

    function compatibilityElement(object) {
        if (object && object.type === G.PATH_TYPE) {
            const points = object.geometry.points.map(scaledPoint);
            if (object.geometry.closed && points.length) points.push([...points[0]]);
            return {
                id: String(object.id),
                type: "pen",
                points,
                color: "#172033",
            };
        }
        if (object && G.TEXT_TYPE && object.type === G.TEXT_TYPE) {
            const position = object.geometry && object.geometry.position;
            if (!position) return null;
            return {
                id: String(object.id),
                type: "note",
                x: G.roundMm(position.x * 0.1),
                y: G.roundMm(position.y * 0.1),
                text: String(object.text || ""),
                font_size: Math.max(4, G.roundMm(object.style && object.style.fontSizeMm || G.DEFAULT_TEXT_FONT_SIZE_MM || 32)),
                text_anchor: /[\u0590-\u08ff]/.test(String(object.text || "")) ? "end" : "middle",
                color: String(object.style && object.style.fill || "#172033"),
            };
        }
        return Base.compatibilityElement(object);
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

    root.PersistenceAdapter = Object.freeze({ ...Base, compatibilityElement, toStored });
    root.SmartPathPersistence = Object.freeze({ compatibilityElement, toStored });
})();
