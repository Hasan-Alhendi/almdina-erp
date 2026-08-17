(() => {
    "use strict";

    const root = window.AlmdinaDoorDrawingReference = window.AlmdinaDoorDrawingReference || Object.create(null);
    const domain = root.Domain;
    const cropper = root.Cropper;
    if (!domain || !cropper) throw new Error("Reference image dependencies are incomplete");

    function blobToDataUrl(blob) {
        return new Promise((resolve, reject) => {
            const reader = new FileReader();
            reader.onload = () => resolve(String(reader.result || ""));
            reader.onerror = () => reject(reader.error || new Error("تعذر تجهيز الصورة للرفع."));
            reader.readAsDataURL(blob);
        });
    }

    function chooseFile() {
        return new Promise(resolve => {
            const input = document.createElement("input");
            input.type = "file";
            input.accept = "image/png,image/jpeg,.png,.jpg,.jpeg";
            input.hidden = true;
            input.addEventListener("change", () => {
                const file = input.files && input.files[0] ? input.files[0] : null;
                input.remove();
                resolve(file);
            }, { once: true });
            document.body.appendChild(input);
            input.click();
        });
    }

    function confirmAsync(message) {
        return new Promise(resolve => frappe.confirm(message, () => resolve(true), () => resolve(false)));
    }

    function openPanel(reference = {}, options = {}) {
        return new Promise(resolve => {
            const overlay = document.createElement("div");
            overlay.className = "ald-ref-panel-overlay";
            const imageUrl = String(reference.file_url || "");
            const readOnly = Boolean(options.readOnly);
            const editActions = readOnly
                ? '<span class="ald-ref-readonly-note">عرض فقط</span>'
                : `<button type="button" class="ald-ref-primary-button" data-upload>${imageUrl ? "استبدال الصورة" : "رفع صورة"}</button>`;
            overlay.innerHTML = `
                <section class="ald-ref-panel" dir="rtl" role="dialog" aria-modal="true" aria-label="الصورة المرجعية للدرفة">
                    <header><div><strong>الصورة المرجعية</strong><span>صورة الورقة أو الرسم الذي استلمته من الزبون</span></div><button type="button" data-close aria-label="إغلاق">×</button></header>
                    <div class="ald-ref-panel-body">
                        ${imageUrl ? `<div class="ald-ref-preview"><img src="${frappe.utils.escape_html(imageUrl)}" alt="الصورة المرجعية الحالية"></div>` : `<div class="ald-ref-empty-state"><span class="ald-ref-empty-icon">▧</span><strong>لا توجد صورة مرجعية بعد</strong><p>${readOnly ? "لم تُرفق صورة مرجعية بهذه الدرفة." : "ارفع صورة من الكمبيوتر، ثم قص الجزء المهم قبل الحفظ."}</p></div>`}
                    </div>
                    <footer>
                        <div><button type="button" class="ald-ref-secondary-button" data-close>إغلاق</button>${imageUrl && !readOnly ? '<button type="button" class="ald-ref-danger-button" data-remove>حذف الصورة</button>' : ""}</div>
                        <div>${editActions}</div>
                    </footer>
                </section>`;
            let settled = false;
            function finish(action) {
                if (settled) return;
                settled = true;
                overlay.remove();
                resolve(action);
            }
            overlay.addEventListener("click", event => {
                if (event.target === overlay || event.target.closest("[data-close]")) finish("close");
                else if (!readOnly && event.target.closest("[data-upload]")) finish("upload");
                else if (!readOnly && event.target.closest("[data-remove]")) finish("remove");
            });
            document.body.appendChild(overlay);
        });
    }

    function create(options = {}) {
        if (!options.api) throw new Error("Reference image controller requires workspace API");
        let busy = false;

        async function upload(context) {
            if (busy || !context || !context.permissions || !context.permissions.can_edit) return context;
            const file = await chooseFile();
            if (!file) return context;
            const validation = domain.validateFile(file);
            if (!validation.ok) {
                frappe.msgprint(validation.message);
                return context;
            }
            let cropped;
            try {
                cropped = await cropper.open(file, { source: domain.SOURCES.UPLOAD });
            } catch (error) {
                console.error("Reference image crop failed", error);
                frappe.msgprint(error && error.message ? error.message : "تعذر فتح الصورة للاقتصاص.");
                return context;
            }
            if (!cropped) return context;
            busy = true;
            try {
                const imageDataUrl = await blobToDataUrl(cropped.blob);
                const result = await options.api.saveReferenceImage(
                    context.order.name,
                    context.piece.name,
                    imageDataUrl,
                    cropped.metadata
                );
                frappe.show_alert({ message: "تم حفظ الصورة المرجعية.", indicator: "green" }, 3);
                return { ...context, reference: result.reference };
            } catch (error) {
                console.error("Reference image save failed", error);
                frappe.msgprint("تعذر حفظ الصورة المرجعية. تحقق من الصلاحيات وحجم الصورة ثم حاول مرة أخرى.");
                return context;
            } finally {
                busy = false;
            }
        }

        async function remove(context) {
            if (busy || !context || !context.permissions || !context.permissions.can_edit) return context;
            const accepted = await confirmAsync("هل تريد حذف الصورة المرجعية؟ لن يتم حذف الرسم الهندسي.");
            if (!accepted) return context;
            busy = true;
            try {
                const result = await options.api.removeReferenceImage(context.order.name, context.piece.name);
                frappe.show_alert({ message: "تم حذف الصورة المرجعية.", indicator: "green" }, 3);
                return { ...context, reference: result.reference };
            } catch (error) {
                console.error("Reference image removal failed", error);
                frappe.msgprint("تعذر حذف الصورة المرجعية.");
                return context;
            } finally {
                busy = false;
            }
        }

        async function open(context) {
            if (!context) return context;
            const action = await openPanel(context.reference || {}, { readOnly: !context.permissions.can_edit });
            if (action === "upload") return upload(context);
            if (action === "remove") return remove(context);
            return context;
        }

        return Object.freeze({ open, upload, remove, isBusy: () => busy });
    }

    root.ReferenceController = Object.freeze({ create, blobToDataUrl });
})();
