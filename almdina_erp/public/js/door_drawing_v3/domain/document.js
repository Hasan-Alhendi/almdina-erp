(() => {
    "use strict";

    const root = window.AlmdinaDoorDrawingV3 = window.AlmdinaDoorDrawingV3 || Object.create(null);
    const geometry = root.Geometry;
    if (!geometry) throw new Error("Drawing V3 geometry must load before document model");

    const SCHEMA = "almdina.door-drawing";
    const VERSION = 3;
    const UNITS = "mm";

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

    function normalize(raw, fallback = {}) {
        if (!raw || typeof raw !== "object") return create(fallback);
        if (raw.schema !== SCHEMA || Number(raw.version) !== VERSION || raw.units !== UNITS) {
            return create(fallback);
        }
        const objects = [];
        (Array.isArray(raw.objects) ? raw.objects : []).forEach(item => {
            if (!item || item.type !== "line" || !item.geometry) return;
            try {
                objects.push(geometry.line(
                    item.id,
                    item.geometry.start,
                    item.geometry.end,
                    item.style || {}
                ));
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
        return freezeDocument({
            ...document,
            objects: document.objects.filter(object => String(object.id) !== String(id)),
        });
    }

    function serialize(document) {
        return JSON.stringify(document);
    }

    root.DocumentModel = Object.freeze({
        SCHEMA,
        VERSION,
        UNITS,
        create,
        normalize,
        objectById,
        addObject,
        replaceObject,
        removeObject,
        serialize,
    });
})();
