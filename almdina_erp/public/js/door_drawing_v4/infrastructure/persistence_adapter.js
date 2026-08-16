(() => {
    "use strict";

    const root = window.AlmdinaDoorDrawingV4 = window.AlmdinaDoorDrawingV4 || Object.create(null);
    const geometry = root.Geometry;
    const documentModel = root.DocumentModel;
    if (!geometry || !documentModel) throw new Error("Drawing V4 domain must load before persistence adapter");

    function rowBlankMm(row) {
        return Object.freeze({
            widthMm: Math.max(0, geometry.finiteNumber(row && row.width_cm) * 10),
            heightMm: Math.max(0, geometry.finiteNumber(row && row.length_cm) * 10),
        });
    }

    function parseJson(raw) {
        if (!raw) return null;
        if (typeof raw === "object") return raw;
        try {
            return JSON.parse(String(raw));
        } catch (error) {
            return null;
        }
    }

    function normalizeV4(raw, blank) {
        if (!raw || raw.schema !== documentModel.SCHEMA || Number(raw.version) !== documentModel.VERSION || raw.units !== documentModel.UNITS) {
            return documentModel.create(blank);
        }
        try {
            return documentModel.create({
                widthMm: blank.widthMm || (raw.blank && raw.blank.widthMm),
                heightMm: blank.heightMm || (raw.blank && raw.blank.heightMm),
                nodes: Array.isArray(raw.nodes) ? raw.nodes : [],
                segments: Array.isArray(raw.segments) ? raw.segments : [],
                paths: Array.isArray(raw.paths) ? raw.paths : [],
                dimensions: Array.isArray(raw.dimensions) ? raw.dimensions : [],
                constraints: Array.isArray(raw.constraints) ? raw.constraints : [],
            });
        } catch (error) {
            console.warn("Ignoring invalid Door Drawing V4 payload", error);
            return documentModel.create(blank);
        }
    }

    function fromStored(raw, row) {
        return normalizeV4(parseJson(raw), rowBlankMm(row));
    }

    function toStored(document) {
        return documentModel.serialize(document);
    }

    root.PersistenceAdapter = Object.freeze({
        rowBlankMm,
        parseJson,
        fromStored,
        toStored,
    });
})();