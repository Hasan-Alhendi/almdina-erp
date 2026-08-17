(() => {
    "use strict";

    const root = window.AlmdinaDoorDrawingReference = window.AlmdinaDoorDrawingReference || Object.create(null);

    function parseMetadata(raw) {
        if (!raw) return {};
        if (typeof raw === "object") return raw;
        try { return JSON.parse(raw); } catch (_) { return {}; }
    }

    function sourceLabel(metadata) {
        if (metadata.source === "scanner") return "Scanner";
        if (metadata.source === "recrop") return "إعادة قص";
        return "الجهاز";
    }

    function mount(container, context, options = {}) {
        if (!container) throw new Error("Reference image view container is required");
        const piece = context && context.piece || {};
        const metadata = parseMetadata(piece.special_shape_reference_image_meta_json);
        const readOnly = Boolean(options.readOnly);
        container.innerHTML = `
            <section class="ald-ref-view" dir="ltr" aria-label="الصورة المرجعية للدرفة">
                <aside class="ald-ref-side ald-ref-side-left" dir="rtl">
                    <div class="ald-ref-side-header">
                        <strong>التوثيق</strong>
                    </div>
                    <div class="ald-ref-layer-row is-selected">
                        <span class="ald-ref-layer-icon">▣</span>
                        <div>
                            <strong>صورة الدرفة</strong>
                            <span>${sourceLabel(metadata)}</span>
                        </div>
                    </div>
                    <div class="ald-ref-mode-note">
                        <strong>وضع الصورة</strong>
                        <span>أدوات الرسم اليدوي متوقفة حتى حذف الصورة.</span>
                    </div>
                </aside>

                <main class="ald-ref-canvas-region" dir="rtl">
                    <div class="ald-ref-image-stage">
                        <img src="${String(piece.special_shape_reference_image || "")}" alt="صورة الدرفة الخاصة" data-ref-image>
                        <div class="ald-ref-image-badge">مرجع صورة · محفوظ</div>
                    </div>
                    <div class="ald-ref-bottom-toolbar" dir="rtl" role="toolbar" aria-label="أدوات الصورة">
                        <button type="button" data-ref-action="recrop" ${readOnly ? "disabled" : ""}>قص من جديد</button>
                        <button type="button" data-ref-action="replace" ${readOnly ? "disabled" : ""}>استبدال من الجهاز</button>
                        <button type="button" data-ref-action="scan" ${readOnly ? "disabled" : ""}>سحب من Scanner</button>
                        <span></span>
                        <button type="button" class="is-danger" data-ref-action="remove" ${readOnly ? "disabled" : ""}>حذف الصورة</button>
                    </div>
                </main>

                <aside class="ald-ref-side ald-ref-side-right" dir="rtl">
                    <div class="ald-ref-side-header">
                        <strong>الخصائص</strong>
                    </div>
                    <section class="ald-ref-property-section">
                        <span class="ald-ref-property-title">الدرفة</span>
                        <div class="ald-ref-property-grid">
                            <label><span>العرض</span><strong>${Number(piece.width_cm || 0)} سم</strong></label>
                            <label><span>الطول</span><strong>${Number(piece.length_cm || 0)} سم</strong></label>
                        </div>
                    </section>
                    <section class="ald-ref-property-section">
                        <span class="ald-ref-property-title">الصورة</span>
                        <div class="ald-ref-property-stack">
                            <label><span>المصدر</span><strong>${sourceLabel(metadata)}</strong></label>
                            <label><span>الدقة</span><strong>${metadata.output ? `${Number(metadata.output.width_px || 0)} × ${Number(metadata.output.height_px || 0)} px` : "—"}</strong></label>
                            ${metadata.scanner && metadata.scanner.dpi ? `<label><span>DPI</span><strong>${Number(metadata.scanner.dpi)}</strong></label>` : ""}
                        </div>
                    </section>
                </aside>
            </section>`;

        const clickHandler = event => {
            const button = event.target.closest("[data-ref-action]");
            if (!button || button.disabled || typeof options.onAction !== "function") return;
            options.onAction(button.dataset.refAction);
        };
        container.addEventListener("click", clickHandler);

        return Object.freeze({
            destroy() {
                container.removeEventListener("click", clickHandler);
                container.innerHTML = "";
            },
        });
    }

    root.ReferenceView = Object.freeze({ mount });
})();