(() => {
    "use strict";

    const root = window.AlmdinaDoorDrawingV3 = window.AlmdinaDoorDrawingV3 || Object.create(null);
    const geometry = root.Geometry;
    if (!geometry) throw new Error("Drawing V3 geometry must load before document model");

    const SCHEMA = "almdina.door-drawing";
    const VERSION = 3;
    const UNITS = "mm";
    const SUPPORTED_TYPES = Object.freeze(["line", "rectangle", "circle", "arc"]);

    function freezeDocument(document) {
        return Object.freeze({
            schema: SCHEMA,
            version: VERSION,
            units: UNITS,
            blank: Object.freeze({
                widthMm: geometry.roundMm(document.blank && document.blank.widthMm),
                heightMm: geometry.roundMm(document.blank && document.blank.heightMm),
            }),
            objects: Object.freeze((document.objects || []).map(object => geometry.cloneObject(object))),
        });
    }

    function create(options = {}) {
        return freezeDocument({
            blank: {
                widthMm: Math.max(0, geometry.number(options.widthMm)),
                heightMm: Math.max(0, geometry.number(options.heightMm)),
            },
            objects: Array.isArray(options.objects) ? options.objects : [],
        });
    }

    function normalizeObject(item) {
        if (!item || !SUPPORTED_TYPES.includes(item.type) || !item.geometry) return null;
        const style = item.style || {};
        if (item.type === "line") return geometry.line(item.id, item.geometry.start, item.geometry.end, style);
        if (item.type === "rectangle") return geometry.rectangle(
            item.id,
            item.geometry.origin,
            item.geometry.widthMm,
            item.geometry.heightMm,
            style
        );
        if (item.type === "circle") return geometry.circle(item.id, item.geometry.center, item.geometry.radiusMm, style);
        if (item.type === "arc") return geometry.arc(
            item.id,
            item.geometry.center,
            item.geometry.radiusMm,
            item.geometry.startAngleDeg,
            item.geometry.sweepAngleDeg,
            style
        );
        return null;
    }

    function normalize(raw, fallback = {}) {
        if (!raw || typeof raw !== "object") return create(fallback);
        if (raw.schema !== SCHEMA || Number(raw.version) !== VERSION || raw.units !== UNITS) return create(fallback);
        const objects = [];
        (Array.isArray(raw.objects) ? raw.objects : []).forEach(item => {
            try {
                const object = normalizeObject(item);
                if (object) objects.push(object);
            } catch (error) {
                // Skip corrupt objects instead of compromising the whole document.
            }
        });
        return create({
            widthMm: raw.blank && raw.blank.widthMm,
            heightMm: raw.blank && raw.blank.heightMm,
            objects,
        });
    }

    function objectById(document, id) {
        return (document && document.objects || []).find(object => String(object.id) === String(id || "")) || null;
    }

    function addObject(document, object) {
        if (objectById(document, object && object.id)) throw new Error("Duplicate drawing object id");
        return freezeDocument({ ...document, objects: [...document.objects, geometry.cloneObject(object)] });
    }

    function replaceObject(document, object) {
        let found = false;
        const objects = document.objects.map(item => {
            if (String(item.id) !== String(object.id)) return item;
            found = true;
            return geometry.cloneObject(object);
        });
        if (!found) throw new Error("Drawing object not found");
        return freezeDocument({ ...document, objects });
    }

    function removeObject(document, id) {
        return freezeDocument({ ...document, objects: document.objects.filter(object => String(object.id) !== String(id)) });
    }

    function serialize(document) {
        return JSON.stringify(document);
    }

    root.DocumentModel = Object.freeze({
        SCHEMA,
        VERSION,
        UNITS,
        SUPPORTED_TYPES,
        create,
        normalize,
        objectById,
        addObject,
        replaceObject,
        removeObject,
        serialize,
    });
})();
