(() => {
    "use strict";

    const root = window.AlmdinaDoorDrawingV2 = window.AlmdinaDoorDrawingV2 || Object.create(null);
    const precision = root.Precision;
    const geometry = root.Geometry;
    const documents = root.DocumentModel;
    const legacyAdapter = root.LegacyAdapter;
    const lineModel = window.AlmdinaExactLineModel;
    if (!precision || !geometry || !documents || !legacyAdapter || !lineModel) {
        throw new Error("Door Drawing V2 legacy runtime bridge dependencies are missing");
    }

    function clone(value) {
        return value == null ? value : JSON.parse(JSON.stringify(value));
    }

    function rowDimensionsMm(row) {
        const widthCm = precision.toNumber(row && row.width_cm);
        const heightCm = precision.toNumber(row && row.length_cm);
        return {
            width: Math.max(1, Number.isFinite(widthCm) ? precision.cmToMm(widthCm) : 1),
            height: Math.max(1, Number.isFinite(heightCm) ? precision.cmToMm(heightCm) : 1),
        };
    }

    function legacyTransform(row) {
        const dimensions = lineModel.pieceDimensions(row || {});
        return lineModel.createTransform(dimensions.width, dimensions.length, { freeWorkspace: true });
    }

    function toV2Object(element) {
        if (!element) return null;
        return legacyAdapter.exactArcElement(element) || legacyAdapter.exactLineElement(element) || null;
    }

    function documentFromLegacy(row, elements, context = {}) {
        const dimensions = rowDimensionsMm(row);
        let document = documents.createDocument({
            orderId: context.orderId || "",
            rowId: row && row.name || context.rowId || "",
            widthMm: dimensions.width,
            heightMm: dimensions.height,
            quantity: row && row.qty || 1,
            createdFrom: "legacy-runtime-bridge",
            metadata: { workspace: "free" },
        });
        (Array.isArray(elements) ? elements : []).forEach(element => {
            const object = toV2Object(element);
            if (!object) return;
            if (document.objects.some(item => item.id === object.id)) return;
            document = documents.addObject(document, object);
        });
        return document;
    }

    function canvasPointToWorldMm(row, canvasPoint) {
        const transform = legacyTransform(row);
        if (!transform) throw new Error("Legacy drawing transform is unavailable");
        const cm = lineModel.canvasToCm(transform, [Number(canvasPoint[0]), Number(canvasPoint[1])]);
        return precision.point({ x: precision.cmToMm(cm[0]), y: precision.cmToMm(cm[1]) });
    }

    function worldMmToCanvas(row, worldPoint) {
        const transform = legacyTransform(row);
        if (!transform) throw new Error("Legacy drawing transform is unavailable");
        const point = precision.point(worldPoint);
        return lineModel.cmToCanvas(transform, [precision.mmToCm(point.x), precision.mmToCm(point.y)]);
    }

    function applyLineObjectToLegacy(v2Object, legacyElement, row) {
        if (!v2Object || v2Object.type !== "line") throw new TypeError("V2 object must be a line");
        const transform = legacyTransform(row);
        if (!transform) throw new Error("Legacy drawing transform is unavailable");
        const startMm = precision.point(v2Object.geometry.start, "line.start");
        const endMm = precision.point(v2Object.geometry.end, "line.end");
        const startCm = [precision.mmToCm(startMm.x), precision.mmToCm(startMm.y)];
        const endCm = [precision.mmToCm(endMm.x), precision.mmToCm(endMm.y)];
        const startCanvas = lineModel.cmToCanvas(transform, startCm);
        const endCanvas = lineModel.cmToCanvas(transform, endCm);
        const next = clone(legacyElement || {});
        next.id = String(v2Object.id || next.id || `exact-line-${Date.now()}`);
        next.type = "line";
        next.x1 = startCanvas[0];
        next.y1 = startCanvas[1];
        next.x2 = endCanvas[0];
        next.y2 = endCanvas[1];
        next.exact_line = {
            ...(next.exact_line || {}),
            version: 1,
            units: "cm",
            start_cm: startCm,
            end_cm: endCm,
            length_cm: precision.mmToCm(geometry.lineLength(v2Object.geometry)),
            angle_deg: geometry.lineAngleDeg(v2Object.geometry),
            blank_width_cm: Number(transform.widthCm),
            blank_length_cm: Number(transform.lengthCm),
            workspace: "free",
        };
        delete next.exact_arc;
        delete next.points;
        return next;
    }

    function replaceLegacyElement(elements, objectId, replacement) {
        const source = Array.isArray(elements) ? elements : [];
        let found = false;
        const next = source.map(element => {
            if (String(element && element.id || "") !== String(objectId || "")) return clone(element);
            found = true;
            return clone(replacement);
        });
        if (!found) throw new Error(`Legacy element not found: ${objectId}`);
        return next;
    }

    root.LegacyRuntimeBridge = Object.freeze({
        rowDimensionsMm,
        legacyTransform,
        toV2Object,
        documentFromLegacy,
        canvasPointToWorldMm,
        worldMmToCanvas,
        applyLineObjectToLegacy,
        replaceLegacyElement,
    });
})();
