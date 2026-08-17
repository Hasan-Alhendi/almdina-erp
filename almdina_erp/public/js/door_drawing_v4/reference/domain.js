(() => {
    "use strict";

    const root = window.AlmdinaDoorDrawingReference = window.AlmdinaDoorDrawingReference || Object.create(null);

    const VERSION = 1;
    const MAX_SOURCE_BYTES = 16 * 1024 * 1024;
    const MAX_SOURCE_PIXELS = 50 * 1000 * 1000;
    const ACCEPTED_MIME_TYPES = Object.freeze(["image/png", "image/jpeg"]);
    const ACCEPTED_EXTENSIONS = Object.freeze([".png", ".jpg", ".jpeg"]);
    const SOURCES = Object.freeze({ UPLOAD: "upload", SCANNER: "scanner", RECROP: "recrop" });

    function extension(name) {
        const value = String(name || "").trim().toLowerCase();
        const index = value.lastIndexOf(".");
        return index >= 0 ? value.slice(index) : "";
    }

    function validateFile(file) {
        if (!file) return Object.freeze({ ok: false, code: "missing-file", message: "اختر صورة أولًا." });
        const mime = String(file.type || "").toLowerCase();
        if (!ACCEPTED_MIME_TYPES.includes(mime) && !ACCEPTED_EXTENSIONS.includes(extension(file.name))) {
            return Object.freeze({ ok: false, code: "unsupported-file", message: "الصيغ المدعومة: PNG و JPG و JPEG." });
        }
        const size = Number(file.size);
        if (!Number.isFinite(size) || size <= 0) return Object.freeze({ ok: false, code: "empty-file", message: "ملف الصورة فارغ أو غير صالح." });
        if (size > MAX_SOURCE_BYTES) return Object.freeze({ ok: false, code: "file-too-large", message: "حجم الصورة قبل القص يجب ألا يتجاوز 16 MB." });
        return Object.freeze({ ok: true });
    }

    function validateDecodedDimensions(width, height) {
        const w = Number(width);
        const h = Number(height);
        if (!Number.isFinite(w) || !Number.isFinite(h) || w <= 0 || h <= 0) {
            return Object.freeze({ ok: false, code: "invalid-image-dimensions", message: "أبعاد الصورة غير صالحة." });
        }
        if (w * h > MAX_SOURCE_PIXELS) {
            return Object.freeze({ ok: false, code: "image-too-large-to-decode", message: "دقة الصورة كبيرة جدًا للمعالجة. استخدم صورة بدقة أقل من 50 مليون بكسل." });
        }
        return Object.freeze({ ok: true });
    }

    function finite(value, fallback = 0) {
        const number = Number(value);
        return Number.isFinite(number) ? number : fallback;
    }

    function normalizeCrop(crop = {}) {
        return Object.freeze({
            x: Math.max(0, finite(crop.x)),
            y: Math.max(0, finite(crop.y)),
            width: Math.max(1, finite(crop.width, 1)),
            height: Math.max(1, finite(crop.height, 1)),
        });
    }

    function buildMetadata(input = {}) {
        const source = Object.values(SOURCES).includes(input.source) ? input.source : SOURCES.UPLOAD;
        const metadata = {
            version: VERSION,
            source,
            original_name: String(input.originalName || "image").slice(0, 180),
            original_mime: String(input.originalMime || "image/jpeg").slice(0, 80),
            source_width_px: Math.max(1, Math.round(finite(input.sourceWidthPx, 1))),
            source_height_px: Math.max(1, Math.round(finite(input.sourceHeightPx, 1))),
            rotation_deg: ((Math.round(finite(input.rotationDeg)) % 360) + 360) % 360,
            crop: normalizeCrop(input.crop),
            output: Object.freeze({
                width_px: Math.max(1, Math.round(finite(input.outputWidthPx, 1))),
                height_px: Math.max(1, Math.round(finite(input.outputHeightPx, 1))),
                mime: String(input.outputMime || "image/jpeg").slice(0, 80),
            }),
        };
        if (input.scanner && typeof input.scanner === "object") {
            metadata.scanner = Object.freeze({
                provider: String(input.scanner.provider || "local-wia-bridge").slice(0, 80),
                device: String(input.scanner.device || "").slice(0, 180),
                dpi: Math.max(0, Math.round(finite(input.scanner.dpi))),
            });
        }
        return Object.freeze(metadata);
    }

    root.Domain = Object.freeze({
        VERSION,
        MAX_SOURCE_BYTES,
        MAX_SOURCE_PIXELS,
        ACCEPTED_MIME_TYPES,
        ACCEPTED_EXTENSIONS,
        SOURCES,
        validateFile,
        validateDecodedDimensions,
        buildMetadata,
    });
})();
