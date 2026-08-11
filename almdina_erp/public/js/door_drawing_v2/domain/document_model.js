(() => {
    "use strict";

    const root = window.AlmdinaDoorDrawingV2 = window.AlmdinaDoorDrawingV2 || Object.create(null);
    const precision = root.Precision;
    const geometry = root.Geometry;
    if (!precision || !geometry) throw new Error("Door Drawing V2 domain dependencies are missing");

    const SCHEMA = "almdina.door-drawing";
    const VERSION = 2;
    const CATEGORIES = Object.freeze(["geometry", "dimensions", "notes", "guides"]);
    const CATEGORY_SET = new Set(CATEGORIES);

    function clone(value) {
        return value == null ? value : JSON.parse(JSON.stringify(value));
    }

    function makeId(prefix = "obj") {
        if (window.crypto && typeof window.crypto.randomUUID === "function") return `${prefix}-${window.crypto.randomUUID()}`;
        return `${prefix}-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`;
    }

    function normalizeStyle(style = {}) {
        return {
            stroke: style.stroke == null ? "#111111" : String(style.stroke),
            strokeWidthMm: precision.serialized(style.strokeWidthMm == null ? 0.5 : style.strokeWidthMm),
            fill: style.fill == null ? "none" : String(style.fill),
            opacity: precision.serialized(style.opacity == null ? 1 : Math.max(0, Math.min(1, Number(style.opacity)))),
            ...(style.dash ? { dash: clone(style.dash) } : {}),
        };
    }

    function normalizeObject(object) {
        if (!object || typeof object !== "object") throw new TypeError("Drawing object is required");
        const type = String(object.type || "");
        const category = String(object.category || (type === "dimension" ? "dimensions" : type === "text" ? "notes" : type === "guide" ? "guides" : "geometry"));
        if (!CATEGORY_SET.has(category)) throw new TypeError(`Unsupported category: ${category}`);
        const normalized = {
            id: String(object.id || makeId(type || "obj")),
            type,
            category,
            name: String(object.name || ""),
            visible: object.visible !== false,
            locked: object.locked === true,
            geometry: clone(object.geometry || {}),
            style: normalizeStyle(object.style),
            metadata: clone(object.metadata || {}),
        };
        const validation = geometry.validateObject(normalized);
        if (!validation.valid) throw new TypeError(validation.errors.join("; "));
        return normalized;
    }

    function createDocument(options = {}) {
        const widthMm = precision.assertFinite(options.widthMm, "door.widthMm");
        const heightMm = precision.assertFinite(options.heightMm, "door.heightMm");
        if (widthMm <= 0 || heightMm <= 0) throw new RangeError("Door dimensions must be greater than zero");
        return {
            schema: SCHEMA,
            version: VERSION,
            units: precision.UNITS,
            door: {
                orderId: String(options.orderId || ""),
                rowId: String(options.rowId || ""),
                width: precision.serialized(widthMm),
                height: precision.serialized(heightMm),
                quantity: Math.max(1, Math.trunc(Number(options.quantity) || 1)),
            },
            objects: [],
            metadata: {
                createdFrom: String(options.createdFrom || "v2"),
                ...(clone(options.metadata || {})),
            },
        };
    }

    function createObject(type, objectGeometry, options = {}) {
        return normalizeObject({
            id: options.id || makeId(type),
            type,
            category: options.category,
            name: options.name,
            geometry: objectGeometry,
            style: options.style,
            visible: options.visible,
            locked: options.locked,
            metadata: options.metadata,
        });
    }

    function addObject(document, object) {
        const parsed = parse(document);
        const normalized = normalizeObject(object);
        if (parsed.objects.some(item => item.id === normalized.id)) throw new Error(`Duplicate object id: ${normalized.id}`);
        return { ...parsed, objects: [...parsed.objects.map(clone), normalized] };
    }

    function replaceObject(document, objectId, replacement) {
        const parsed = parse(document);
        const index = parsed.objects.findIndex(item => item.id === String(objectId));
        if (index < 0) throw new Error(`Object not found: ${objectId}`);
        const normalized = normalizeObject({ ...replacement, id: String(objectId) });
        const objects = parsed.objects.map(clone);
        objects[index] = normalized;
        return { ...parsed, objects };
    }

    function removeObject(document, objectId) {
        const parsed = parse(document);
        return { ...parsed, objects: parsed.objects.filter(item => item.id !== String(objectId)).map(clone) };
    }

    function validate(document) {
        const errors = [];
        if (!document || typeof document !== "object") return { valid:false, errors:["Drawing document is required"] };
        if (document.schema !== SCHEMA) errors.push("Unsupported drawing schema");
        if (Number(document.version) !== VERSION) errors.push("Unsupported drawing document version");
        if (document.units !== precision.UNITS) errors.push("Drawing document units must be mm");
        const door = document.door || {};
        try {
            if (precision.assertFinite(door.width, "door.width") <= 0 || precision.assertFinite(door.height, "door.height") <= 0) errors.push("Door dimensions must be greater than zero");
        } catch (error) { errors.push(error.message); }
        if (!Array.isArray(document.objects)) errors.push("Drawing document objects must be an array");
        if (Array.isArray(document.objects)) {
            const ids = new Set();
            document.objects.forEach((object, index) => {
                const id = String(object && object.id || "");
                if (!id) errors.push(`Object ${index + 1} has no id`);
                else if (ids.has(id)) errors.push(`Duplicate object id: ${id}`);
                ids.add(id);
                if (!CATEGORY_SET.has(String(object && object.category || ""))) errors.push(`Object ${id || index + 1} has invalid category`);
                const result = geometry.validateObject(object);
                result.errors.forEach(error => errors.push(`Object ${id || index + 1}: ${error}`));
            });
        }
        return { valid:errors.length === 0, errors };
    }

    function parse(raw) {
        const source = typeof raw === "string" ? JSON.parse(raw) : clone(raw);
        const result = validate(source);
        if (!result.valid) throw new TypeError(result.errors.join("; "));
        return {
            schema: SCHEMA,
            version: VERSION,
            units: precision.UNITS,
            door: {
                orderId: String(source.door.orderId || ""),
                rowId: String(source.door.rowId || ""),
                width: precision.serialized(source.door.width),
                height: precision.serialized(source.door.height),
                quantity: Math.max(1, Math.trunc(Number(source.door.quantity) || 1)),
            },
            objects: source.objects.map(normalizeObject),
            metadata: clone(source.metadata || {}),
        };
    }

    function serialize(document) {
        return JSON.stringify(parse(document));
    }

    root.DocumentModel = Object.freeze({
        SCHEMA,
        VERSION,
        CATEGORIES,
        createDocument,
        createObject,
        normalizeObject,
        addObject,
        replaceObject,
        removeObject,
        validate,
        parse,
        serialize,
    });
})();
