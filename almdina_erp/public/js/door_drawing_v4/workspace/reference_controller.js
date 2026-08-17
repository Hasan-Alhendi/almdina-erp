(() => {
    "use strict";

    const workspace = window.AlmdinaDoorDrawingWorkspace = window.AlmdinaDoorDrawingWorkspace || Object.create(null);
    const reference = window.AlmdinaDoorDrawingReference;
    const api = workspace.Api;
    if (!reference || !reference.Domain || !reference.DeviceSource || !reference.ScannerBridge || !reference.Cropper || !reference.ReferenceView || !api) {
        throw new Error("Reference image runtime is incomplete");
    }

    function blobToDataUrl(blob) {
        return new Promise((resolve, reject) => {
            const reader = new FileReader();
            reader.onload = () => resolve(String(reader.result || ""));
            reader.onerror = () => reject(reader.error || new Error("Failed to encode image"));
            reader.readAsDataURL(blob);
        });
    }

    function create(options = {}) {
        if (!options.container) throw new Error("Reference controller requires a container");
        let context = null;
        let readOnly = true;
        let view = null;
        let busy = false;
        let destroyed = false;

        function notify(message, level = "info") {
            if (typeof options.notify === "function") options.notify(message, level);
        }

        function setBusy(next, label = "") {
            busy = Boolean(next);
            if (typeof options.onBusy === "function") options.onBusy(busy, label);
        }

        function destroyView() {
            if (view) view.destroy();
            view = null;
        }

        function render() {
            if (destroyed || !context) return;
            destroyView();
            view = reference.ReferenceView.mount(options.container, context, {
                readOnly,
                onAction(action) {
                    if (action === "replace") uploadFromDevice();
                    if (action === "scan") scanFromScanner();
                    if (action === "recrop") recrop();
                    if (action === "remove") remove();
                },
            });
        }

        function setContext(nextContext, nextReadOnly = false) {
            context = nextContext;
            readOnly = Boolean(nextReadOnly);
            render();
        }

        async function persist(file, cropResult) {
            if (!context || !cropResult || readOnly || busy) return null;
            setBusy(true, "يتم حفظ الصورة…");
            try {
                const imageDataUrl = await blobToDataUrl(cropResult.blob);
                const result = await api.saveReferenceImage(
                    context.order.name,
                    context.piece.name,
                    imageDataUrl,
                    cropResult.metadata
                );
                if (destroyed) return null;
                context = { ...context, piece: result.piece };
                render();
                if (typeof options.onSaved === "function") options.onSaved(context, result);
                notify("تم حفظ صورة الدرفة كمرجع رسمي.", "success");
                return result;
            } catch (error) {
                console.error("Reference image save failed", error);
                notify("تعذر حفظ صورة الدرفة. حاول مرة أخرى.", "error");
                return null;
            } finally {
                setBusy(false);
            }
        }

        async function cropAndPersist(file, source, scanner = null) {
            if (readOnly || busy || !file) return null;
            const validation = reference.Domain.validateFile(file);
            if (!validation.ok) {
                notify(validation.message, "error");
                return null;
            }
            try {
                const cropped = await reference.Cropper.open(file, { source, scanner });
                if (!cropped || destroyed) return null;
                return await persist(file, cropped);
            } catch (error) {
                console.error("Reference image crop failed", error);
                notify(error && error.message ? error.message : "تعذر قراءة الصورة أو قصها.", "error");
                return null;
            }
        }

        async function uploadFromDevice() {
            if (readOnly || busy) return null;
            const file = await reference.DeviceSource.pick();
            if (!file || destroyed) return null;
            return cropAndPersist(file, reference.Domain.SOURCES.DEVICE);
        }

        async function scanFromScanner() {
            if (readOnly || busy) return null;
            setBusy(true, "جاري الاتصال بالـScanner…");
            try {
                await reference.ScannerBridge.health();
                setBusy(true, "اختر الـScanner وابدأ المسح من النافذة المحلية…");
                const scanned = await reference.ScannerBridge.scan({ dpi: 300, showUi: true, colorMode: "color" });
                setBusy(false);
                if (destroyed) return null;
                return cropAndPersist(scanned.file, reference.Domain.SOURCES.SCANNER, scanned.scanner);
            } catch (error) {
                console.error("Scanner acquisition failed", error);
                const code = error && error.code;
                if (code === "bridge-unavailable" || code === "bridge-timeout") {
                    notify("برنامج ربط الـScanner غير متصل. ثبّت Almdina Scanner Bridge على هذا الكمبيوتر ثم أعد المحاولة.", "scanner-unavailable");
                } else if (code === "origin-denied") {
                    notify("برنامج ربط الـScanner رفض هذا الموقع. راجع قائمة المواقع المسموحة في إعدادات Scanner Bridge.", "error");
                } else {
                    notify(error && error.message ? error.message : "تعذر سحب الصورة من الـScanner.", "error");
                }
                return null;
            } finally {
                setBusy(false);
            }
        }

        async function recrop() {
            if (readOnly || busy || !context || !context.piece.special_shape_reference_image) return null;
            setBusy(true, "يتم تحميل الصورة الحالية…");
            try {
                const response = await fetch(context.piece.special_shape_reference_image, { credentials: "same-origin", cache: "no-store" });
                if (!response.ok) throw new Error("تعذر تحميل الصورة الحالية لإعادة قصها.");
                const blob = await response.blob();
                const file = new File([blob], "reference-image.jpg", { type: blob.type || "image/jpeg" });
                setBusy(false);
                return cropAndPersist(file, reference.Domain.SOURCES.RECROP);
            } catch (error) {
                console.error("Reference recrop failed", error);
                notify(error.message || "تعذر إعادة قص الصورة الحالية.", "error");
                return null;
            } finally {
                setBusy(false);
            }
        }

        async function remove() {
            if (readOnly || busy || !context) return false;
            let accepted = true;
            if (typeof options.confirm === "function") {
                accepted = await options.confirm("حذف صورة الدرفة؟ ستعود أدوات الرسم اليدوي للعمل، ولن تبقى الصورة مرجعًا رسميًا.");
            }
            if (!accepted || destroyed) return false;
            setBusy(true, "يتم حذف الصورة…");
            try {
                const result = await api.removeReferenceImage(context.order.name, context.piece.name);
                if (destroyed) return false;
                context = { ...context, piece: result.piece };
                if (typeof options.onRemoved === "function") options.onRemoved(context, result);
                notify("تم حذف الصورة. يمكنك الآن الرسم يدويًا.", "success");
                return true;
            } catch (error) {
                console.error("Reference image remove failed", error);
                notify("تعذر حذف صورة الدرفة.", "error");
                return false;
            } finally {
                setBusy(false);
            }
        }

        function destroy() {
            if (destroyed) return;
            destroyed = true;
            destroyView();
            options.container.innerHTML = "";
        }

        return Object.freeze({
            setContext,
            uploadFromDevice,
            scanFromScanner,
            recrop,
            remove,
            destroy,
            state: () => Object.freeze({ context, readOnly, busy }),
        });
    }

    workspace.ReferenceController = Object.freeze({ create });
})();