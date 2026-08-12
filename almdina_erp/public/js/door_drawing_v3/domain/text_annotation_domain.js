(() => {
    "use strict";

    const root = window.AlmdinaDoorDrawingV3 = window.AlmdinaDoorDrawingV3 || Object.create(null);
    const BaseG = root.Geometry;
    const BaseD = root.DocumentModel;
    if (!BaseG || !BaseD) throw new Error("Door Drawing V3 domain must load before text annotations");

    const TEXT_TYPE = "text";
    const DEFAULT_FONT_SIZE_MM = 32;

    function textStyle(style = {}) {
        return Object.freeze({
            fill: String(style.fill || "#1e1e1e"),
            fontSizeMm: Math.max(4, BaseG.roundMm(style.fontSizeMm || DEFAULT_FONT_SIZE_MM)),
            fontWeight: String(style.fontWeight || "400"),
        });
    }

    function text(id, position, value, style = {}) {
        return Object.freeze({
            id: String(id || `text-${Date.now()}`),
            type: TEXT_TYPE,
            geometry: Object.freeze({ position: BaseG.point(position && position.x, position && position.y) }),
            text: String(value ?? ""),
            style: textStyle(style),
        });
    }

    function setText(object, patch = {}) {
        if (!object || object.type !== TEXT_TYPE) throw new Error("Expected a text annotation");
        return text(
            object.id,
            BaseG.point(
                patch.x ?? object.geometry.position.x,
                patch.y ?? object.geometry.position.y
            ),
            patch.text ?? object.text,
            {
                ...object.style,
                fontSizeMm: patch.fontSizeMm ?? object.style.fontSizeMm,
                fill: patch.fill ?? object.style.fill,
                fontWeight: patch.fontWeight ?? object.style.fontWeight,
            }
        );
    }

    const Geometry = Object.freeze({
        ...BaseG,
        TEXT_TYPE,
        DEFAULT_TEXT_FONT_SIZE_MM: DEFAULT_FONT_SIZE_MM,
        text,
        setText,
        translateObject(object, dxMm, dyMm) {
            if (object && object.type === TEXT_TYPE) {
                return setText(object, {
                    x: object.geometry.position.x + BaseG.number(dxMm),
                    y: object.geometry.position.y + BaseG.number(dyMm),
                });
            }
            return BaseG.translateObject(object, dxMm, dyMm);
        },
        cloneObject(object, id = object && object.id) {
            if (object && object.type === TEXT_TYPE) return text(id, object.geometry.position, object.text, object.style);
            return BaseG.cloneObject(object, id);
        },
    });

    const SUPPORTED_TYPES = Object.freeze([...BaseD.SUPPORTED_TYPES.filter(type => type !== TEXT_TYPE), TEXT_TYPE]);

    function freezeDocument(document) {
        return Object.freeze({
            schema: BaseD.SCHEMA,
            version: BaseD.VERSION,
            units: BaseD.UNITS,
            blank: Object.freeze({
                widthMm: Geometry.roundMm(document.blank && document.blank.widthMm),
                heightMm: Geometry.roundMm(document.blank && document.blank.heightMm),
            }),
            objects: Object.freeze((document.objects || []).map(object => Geometry.cloneObject(object))),
        });
    }

    function create(options = {}) {
        return freezeDocument({
            blank: {
                widthMm: Math.max(0, Geometry.number(options.widthMm)),
                heightMm: Math.max(0, Geometry.number(options.heightMm)),
            },
            objects: Array.isArray(options.objects) ? options.objects : [],
        });
    }

    function normalizeObject(item) {
        if (!item || !SUPPORTED_TYPES.includes(item.type)) return null;
        if (item.type === TEXT_TYPE) {
            const position = item.geometry && item.geometry.position;
            if (!position) return null;
            return Geometry.text(item.id, position, item.text, item.style || {});
        }
        const normalized = BaseD.normalize({
            schema: BaseD.SCHEMA,
            version: BaseD.VERSION,
            units: BaseD.UNITS,
            blank: { widthMm: 1, heightMm: 1 },
            objects: [item],
        });
        return normalized.objects[0] || null;
    }

    function normalize(raw, fallback = {}) {
        if (!raw || typeof raw !== "object") return create(fallback);
        if (raw.schema !== BaseD.SCHEMA || Number(raw.version) !== BaseD.VERSION || raw.units !== BaseD.UNITS) return create(fallback);
        const objects = [];
        for (const item of Array.isArray(raw.objects) ? raw.objects : []) {
            try {
                const object = normalizeObject(item);
                if (object) objects.push(object);
            } catch (error) {
                // Corrupt annotations are skipped without invalidating the rest of the drawing.
            }
        }
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
        return freezeDocument({ ...document, objects: [...document.objects, Geometry.cloneObject(object)] });
    }

    function replaceObject(document, object) {
        let found = false;
        const objects = document.objects.map(item => {
            if (String(item.id) !== String(object.id)) return item;
            found = true;
            return Geometry.cloneObject(object);
        });
        if (!found) throw new Error("Drawing object not found");
        return freezeDocument({ ...document, objects });
    }

    function removeObject(document, id) {
        return freezeDocument({ ...document, objects: document.objects.filter(object => String(object.id) !== String(id)) });
    }

    root.Geometry = Geometry;
    root.DocumentModel = Object.freeze({
        ...BaseD,
        SUPPORTED_TYPES,
        create,
        normalize,
        objectById,
        addObject,
        replaceObject,
        removeObject,
        serialize: document => JSON.stringify(document),
    });
    root.TextAnnotationDomain = Object.freeze({ TEXT_TYPE, DEFAULT_FONT_SIZE_MM, text, setText });
})();
