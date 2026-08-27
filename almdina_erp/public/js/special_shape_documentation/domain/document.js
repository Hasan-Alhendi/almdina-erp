(() => {
    "use strict";

    const root = window.AlmdinaSpecialShapeDocumentation = window.AlmdinaSpecialShapeDocumentation || Object.create(null);
    const SCHEMA = "almdina.special-shape-documentation";
    const VERSION = 1;

    function clone(value) { return JSON.parse(JSON.stringify(value)); }
    function number(value, fallback = 0) {
        const resolved = Number(value);
        return Number.isFinite(resolved) ? resolved : fallback;
    }
    function create(piece = {}) {
        return {
            schema: SCHEMA,
            version: VERSION,
            canvas: {
                widthMm: Math.max(1, number(piece.width_cm) * 10),
                heightMm: Math.max(1, number(piece.length_cm) * 10),
            },
            reference: null,
            elements: [],
            notes: "",
            source: "mixed",
            templateId: null,
        };
    }
    function normalizeReference(value) {
        if (!value || !String(value.fileUrl || "").startsWith("/private/files/")) return null;
        const cropContract = root.ReferenceCrop;
        if (!cropContract) throw new Error("Reference crop contract is unavailable");
        const rawSize = value.imageSize && typeof value.imageSize === "object" ? value.imageSize : {};
        const widthPx = Math.round(number(rawSize.widthPx));
        const heightPx = Math.round(number(rawSize.heightPx));
        return {
            fileUrl: String(value.fileUrl),
            rotationDeg: Math.max(-360, Math.min(360, number(value.rotationDeg))),
            // Keep the field for backward-compatible stored JSON, but reference
            // images are always presented at full opacity.
            opacity: 1,
            locked: value.locked !== false,
            crop: cropContract.normalize(value.crop),
            imageSize: widthPx > 0 && heightPx > 0 ? { widthPx, heightPx } : null,
        };
    }
    function normalize(raw, piece = {}) {
        const base = create(piece);
        if (!raw || raw.schema !== SCHEMA || Number(raw.version) !== VERSION) return base;
        base.reference = normalizeReference(raw.reference);
        base.elements = Array.isArray(raw.elements) ? clone(raw.elements) : [];
        base.notes = String(raw.notes || "").slice(0, 2000);
        base.source = ["image", "template", "pen", "mixed"].includes(raw.source) ? raw.source : "mixed";
        base.templateId = raw.templateId || null;
        return base;
    }
    function fromStored(raw, piece = {}) {
        if (!raw) return create(piece);
        try { return normalize(typeof raw === "string" ? JSON.parse(raw) : raw, piece); }
        catch (error) { return create(piece); }
    }
    function toStored(document) { return JSON.stringify(normalize(document, { width_cm: document.canvas.widthMm / 10, length_cm: document.canvas.heightMm / 10 })); }
    function id(prefix = "el") {
        const uuid = typeof crypto !== "undefined" && crypto.randomUUID ? crypto.randomUUID() : `${Date.now()}-${Math.random().toString(16).slice(2)}`;
        return `${prefix}-${uuid}`.slice(0, 80);
    }
    function update(document, changes) { return { ...clone(document), ...clone(changes) }; }
    function setReference(document, reference) { return update(document, { reference: normalizeReference(reference), source: reference ? (document.elements.length ? "mixed" : "image") : (document.elements.length ? document.source : "mixed") }); }
    function setNotes(document, notes) { return update(document, { notes: String(notes || "").slice(0, 2000) }); }
    function addElement(document, element) {
        const next = clone(element);
        next.id = String(next.id || id(next.type || "el"));
        return update(document, { elements: [...document.elements, next], source: document.reference ? "mixed" : (document.templateId ? "template" : "pen") });
    }
    function replaceElements(document, elements, metadata = {}) { return update(document, { elements: clone(elements), ...metadata }); }
    function removeElement(document, elementId) { return update(document, { elements: document.elements.filter(item => item.id !== elementId) }); }
    function hasContent(document) { return Boolean(document && (document.reference || (Array.isArray(document.elements) && document.elements.length))); }

    root.Document = Object.freeze({
        SCHEMA, VERSION, create, fromStored, toStored, normalize, clone, id, update,
        setReference, setNotes, addElement, replaceElements, removeElement, hasContent,
    });
})();
