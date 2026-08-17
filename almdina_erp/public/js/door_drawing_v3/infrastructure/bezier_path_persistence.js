(() => {
    "use strict";

    const root = window.AlmdinaDoorDrawingV3 = window.AlmdinaDoorDrawingV3 || Object.create(null);
    const Base = root.PersistenceAdapter;
    const G = root.Geometry;
    if (!Base || !G || !G.flattenPath) throw new Error("Door Drawing V3 Bezier domain and smart path persistence must load first");

    function scaledPoint(point) { return [G.roundMm(point.x * 0.1), G.roundMm(point.y * 0.1)]; }
    function compatibilityElement(object) {
        if (object && object.type === G.PATH_TYPE) {
            // Legacy consumers (including older export/preview paths) receive a geometry-faithful
            // polyline approximation while the authoritative V3 document retains cubic Bezier data.
            const flattened = G.flattenPath(object, 0.2);
            const points = flattened.map(scaledPoint);
            if (object.geometry.closed && points.length) points.push([...points[0]]);
            return { id: String(object.id), type: "pen", points, color: "#172033" };
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
    root.BezierPathPersistence = Object.freeze({ compatibilityElement, toStored });
})();
