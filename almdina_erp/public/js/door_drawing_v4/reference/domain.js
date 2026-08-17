(() => {
    "use strict";

    const root = window.AlmdinaDoorDrawingReference = window.AlmdinaDoorDrawingReference || Object.create(null);

    const VERSION = 1;
    const MAX_SOURCE_BYTES = 16 * 1024 * 1024;
    const ACCEPTED_MIME_TYPES = Object.freeze(["image/png", "image/jpeg"]);
    const ACCEPTED_EXTENSIONS = Object.freeze([".png", ".jpg", ".jpeg"]);
    const SOURCES = Object.freeze({ DEVICE: "device", SCANNER: "scanner", RECROP: "recrop" });

    function fileExtension(name) {
        const value = String(name || "").trim().toLowerCase();
        const index = value.lastIndexOf(".");
        return index >= 0 ? value.slice(index) : "";
    }

    function validateFile(file) {
        if (!file) return Object.freeze({ ok: false, code: "missing-file", message: "اختر صورة أولًا." });
        const mime = String(file.type || "").toLowerCase();
        const extension = fileExtension(file.name);
        if (!ACCEPTED_MIME_TYPES.includes(mime) && !ACCEPTED_EXTENSIONS.includes(extension)) {
            return Object.freeze({ ok: false, code: "unsupported-file", message: "الصيغ المدعومة حاليًا: PNG و JPG و JPEG." });
        }
        if (!Number.isFinite(Number(file.size)) || Number(file.size) <= 0) {
            return Object.freeze({ ok: false, code: "empty-file", message: "ملف الصورة فارغ أو غير صالح." });
        }
        if (Number(file.size) > MAX_SOURCE_BYTES) {
            return Object.freeze({ ok: false, code: "file-too-large", message: "حجم الصورة كبير جدًا. الحد الأقصى 16 MB قبل القص." });
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
        const source = Object.values(SOURCES).includes(input.source) ? input.source : SOURCES.DEVICE;
        const metadata = {
            version: VERSION,
            source,
            original_name: String(input.originalName || "image").slice(0, 180),
            original_mime: String(input.originalMime || "image/jpeg").slice(0, 80),
            source_width_px: Math.max(1, Math.round(finite(input.sourceWidthPx, 1))),
            source_height_px: Math.max(1, Math.round(finite(input.sourceHeightPx, 1))),
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

    function active(piece) {
        return Boolean(
            piece
            && String(piece.special_shape_documentation_mode || "").toLowerCase() === "image"
            && piece.special_shape_reference_image
        );
    }

    root.Domain = Object.freeze({
        VERSION,
        MAX_SOURCE_BYTES,
        ACCEPTED_MIME_TYPES,
        ACCEPTED_EXTENSIONS,
        SOURCES,
        validateFile,
        buildMetadata,
        active,
    });
})();