(() => {
    "use strict";

    const workspace = window.AlmdinaDoorDrawingWorkspace = window.AlmdinaDoorDrawingWorkspace || Object.create(null);
    const api = workspace.Api;
    const shellFactory = workspace.Shell;
    const referenceFactory = workspace.ReferenceController;
    const referenceRuntime = window.AlmdinaDoorDrawingReference;
    if (!api || !shellFactory || !referenceFactory || !referenceRuntime || !referenceRuntime.Domain) {
        throw new Error("Door drawing workspace dependencies must load before session controller");
    }

    const PROJECTION_MESSAGES = Object.freeze({
        "invalid-document": "بيانات الرسم غير صالحة. أعد فتح الرسم وحاول مرة أخرى.",
        "invalid-blank": "أدخل عرض الدرفة وطولها قبل حفظ الرسم.",
        "missing-boundary": "ارسم محيط الدرفة كاملًا قبل الحفظ.",
        "ambiguous-boundary": "يجب أن يحتوي الرسم على محيط مغلق واحد للدرفة. احذف المسارات الزائدة ثم احفظ.",
        "open-boundary": "أغلق محيط الدرفة بالعودة إلى نقطة البداية قبل الحفظ.",
        "too-few-edges": "محيط الدرفة يحتاج ثلاثة أضلاع على الأقل.",
        "missing-start-node": "الرسم يحتوي نقطة بداية غير صالحة.",
        "duplicate-segment": "الرسم يحتوي ضلعًا مكررًا داخل المسار.",
        "missing-segment": "الرسم يحتوي ضلعًا مفقودًا.",
        "unsupported-segment": "الرسم يحتوي نوع ضلع غير مدعوم للتصنيع حاليًا.",
        "disconnected-boundary": "محيط الدرفة غير متصل بالكامل. صِل جميع الزوايا ثم حاول الحفظ.",
        "missing-node": "الرسم يحتوي نقطة مفقودة.",
        "zero-length-edge": "الرسم يحتوي ضلعًا بطول صفر. احذفه أو حرّك إحدى نقطتيه.",
        "unclosed-boundary": "محيط الدرفة غير مغلق هندسيًا.",
    });

    function v4() {
        const root = window.AlmdinaDoorDrawingV4;
        if (!root || !root.PersistenceAdapter || !root.ManufacturingProjection || !root.EditorController) {
            throw new Error("Door Drawing V4 runtime is incomplete");
        }
        return root;
    }

    function documentHasGeometry(document) {
        return Boolean(document && Array.isArray(document.segments) && document.segments.length);
    }

    function projectionMessage(result) {
        return PROJECTION_MESSAGES[result && result.code] || "تعذر تحويل الرسم إلى هندسة تصنيع صالحة.";
    }

    function manufacturingGeometry(document, piece) {
        const runtime = v4();
        const projected = runtime.ManufacturingProjection.project(document);
        if (!projected.ok) return Object.freeze({ ok: false, message: projectionMessage(projected) });

        const contract = window.AlmdinaSpecialShapeGeometry;
        if (!contract || typeof contract.validate !== "function" || typeof contract.serialize !== "function") {
            throw new Error("Special shape manufacturing geometry contract is not available");
        }
        const validation = contract.validate(projected.geometry, piece.width_cm, piece.length_cm);
        if (!validation.valid) {
            return Object.freeze({
                ok: false,
                message: (validation.errors || []).join("\n") || "هندسة الدرفة غير صالحة للتصنيع.",
            });
        }
        const serialized = contract.serialize(validation.geometry);
        if (!serialized) throw new Error("Failed to serialize special shape manufacturing geometry");
        return Object.freeze({ ok: true, serialized });
    }

    function confirmAsync(message) {
        return new Promise(resolve => frappe.confirm(message, () => resolve(true), () => resolve(false)));
    }

    function create(options = {}) {
        if (!options.container) throw new Error("Door drawing workspace session requires a container");
        const shell = shellFactory.create(options.container);
        let editor = null;
        let referenceController = null;
        let context = null;
        let readOnly = true;
        let dirty = false;
        let activeContent = "drawing";
        let loadToken = 0;
        let destroyed = false;

        function orderName() {
            return context && context.order && context.order.name;
        }

        function pieceName() {
            return context && context.piece && context.piece.name;
        }

        function refreshSaveState() {
            if (readOnly) shell.setSaveState("readonly", "للعرض فقط");
            else if (activeContent === "image") shell.setSaveState("saved", "الصورة محفوظة");
            else if (dirty) shell.setSaveState("dirty", "غير محفوظ");
            else shell.setSaveState("saved", "محفوظ");
        }

        function setDirty(next) {
            dirty = Boolean(next);
            refreshSaveState();
        }

        function notify(message, level = "info") {
            if (level === "success") {
                frappe.show_alert({ message, indicator: "green" }, 3);
                return;
            }
            const scannerUnavailable = level === "scanner-unavailable";
            frappe.msgprint({
                title: scannerUnavailable ? "Scanner غير متصل" : (level === "error" ? "تعذر تنفيذ العملية" : "معلومة"),
                message,
                indicator: scannerUnavailable ? "orange" : (level === "error" ? "red" : "blue"),
            });
        }

        function destroyEditor() {
            if (editor) {
                try { editor.destroy(); } catch (error) { console.warn("Door drawing editor cleanup failed", error); }
            }
            editor = null;
        }

        function destroyReferenceController() {
            if (referenceController) {
                try { referenceController.destroy(); } catch (error) { console.warn("Reference image controller cleanup failed", error); }
            }
            referenceController = null;
        }

        function clearContent() {
            destroyEditor();
            destroyReferenceController();
            shell.elements.editorHost.innerHTML = "";
        }

        function returnToOrder(force = false) {
            const target = orderName();
            if (!target) return;
            const navigate = () => frappe.set_route("Form", "Door Cutting Order", target);
            if (force || readOnly || !dirty || activeContent === "image") {
                navigate();
                return;
            }
            frappe.confirm(
                "لديك تعديلات غير محفوظة. هل تريد العودة إلى الطلب دون حفظها؟",
                navigate
            );
        }

        function currentDocument() {
            return editor && editor.state().interaction.document;
        }

        function onSourceBusy(isBusy, label) {
            shell.setSourceBusy(isBusy, label);
            if (isBusy) shell.setSaveState("saving", label || "جارٍ التنفيذ…");
            else refreshSaveState();
        }

        async function beforeReferencePersist() {
            if (activeContent !== "drawing") return true;
            const hasDrawing = dirty || documentHasGeometry(currentDocument());
            if (!hasDrawing) return true;
            return confirmAsync(
                "سيتم اعتماد الصورة بدل الرسم اليدوي الحالي، وسيتم مسح هندسة الرسم الحالية حتى لا تُستخدم هندسة قديمة مع صورة جديدة. هل تريد المتابعة؟"
            );
        }

        function schedule(callback) {
            if (typeof window.queueMicrotask === "function") window.queueMicrotask(callback);
            else window.setTimeout(callback, 0);
        }

        function createReferenceActions(renderView) {
            destroyReferenceController();
            referenceController = referenceFactory.create({
                container: shell.elements.editorHost,
                notify,
                confirm: confirmAsync,
                onBusy: onSourceBusy,
                beforePersist: beforeReferencePersist,
                onSaved(nextContext) {
                    context = nextContext;
                    shell.setContext(context);
                    setDirty(false);
                    if (activeContent !== "image") schedule(() => activateContent("image"));
                    else {
                        shell.setMode("image");
                        refreshSaveState();
                    }
                },
                onRemoved(nextContext) {
                    context = nextContext;
                    shell.setContext(context);
                    setDirty(false);
                    schedule(() => activateContent("drawing"));
                },
            });
            referenceController.setContext(context, readOnly, renderView);
        }

        function activateDrawing() {
            clearContent();
            activeContent = "drawing";
            shell.setMode("drawing");
            const runtime = v4();
            const initial = runtime.PersistenceAdapter.fromStored(
                context.piece.special_shape_drawing_json,
                context.piece
            );
            editor = runtime.EditorController.create({
                container: shell.elements.editorHost,
                document: initial,
                readOnly,
                onChange() {
                    if (!readOnly) setDirty(true);
                },
            });
            createReferenceActions(false);
            setDirty(false);
        }

        function activateImage() {
            clearContent();
            activeContent = "image";
            shell.setMode("image");
            createReferenceActions(true);
            setDirty(false);
        }

        function activateContent(forceMode = "") {
            if (!context || destroyed) return;
            const imageMode = forceMode === "image" || (
                forceMode !== "drawing" && referenceRuntime.Domain.active(context.piece)
            );
            if (imageMode) activateImage();
            else activateDrawing();
        }

        async function save(options = {}) {
            if (readOnly || !context) return false;
            if (activeContent === "image") {
                refreshSaveState();
                if (options.returnAfter) returnToOrder(true);
                return true;
            }
            if (!editor) return false;
            if (!dirty) {
                if (options.returnAfter) returnToOrder(true);
                return true;
            }

            const document = currentDocument();
            if (!documentHasGeometry(document)) {
                frappe.msgprint("ارسم محيط الدرفة قبل الحفظ.");
                return false;
            }

            let manufacturing;
            try {
                manufacturing = manufacturingGeometry(document, context.piece);
            } catch (error) {
                console.error("Door drawing manufacturing projection failed", error);
                frappe.msgprint("تعذر تجهيز هندسة الدرفة للتصنيع. أعد تحميل الصفحة ثم حاول مرة أخرى.");
                return false;
            }
            if (!manufacturing.ok) {
                frappe.msgprint(manufacturing.message);
                return false;
            }

            shell.setSaveState("saving", "جارٍ الحفظ…");
            try {
                const runtime = v4();
                const result = await api.save(
                    orderName(),
                    pieceName(),
                    runtime.PersistenceAdapter.toStored(document),
                    manufacturing.serialized
                );
                if (result && result.piece) context = { ...context, piece: result.piece };
                setDirty(false);
                frappe.show_alert({ message: "تم حفظ الرسم وهندسة التصنيع.", indicator: "green" }, 3);
                if (options.returnAfter) returnToOrder(true);
                return true;
            } catch (error) {
                console.error("Door drawing workspace save failed", error);
                shell.setSaveState("dirty", "فشل الحفظ");
                frappe.msgprint("تعذر حفظ الرسم. راجع الصلاحيات وحالة الطلب ثم حاول مرة أخرى.");
                return false;
            }
        }

        async function load(order, piece, mode = "edit") {
            const token = ++loadToken;
            clearContent();
            context = null;
            readOnly = true;
            dirty = false;
            activeContent = "drawing";
            shell.setLoading();

            if (!order || !piece) {
                shell.setEmpty("افتح الرسم من زر «ارسم» داخل طلب القص.");
                return null;
            }

            try {
                const loaded = await api.load(order, piece);
                if (destroyed || token !== loadToken) return null;
                context = loaded;
                shell.setContext(context);

                const requestedViewOnly = String(mode || "edit").toLowerCase() === "view";
                readOnly = requestedViewOnly || !Boolean(context.permissions && context.permissions.can_edit);
                activateContent();

                if (readOnly) {
                    shell.markReadOnlyControls();
                    shell.setReadOnly(
                        requestedViewOnly
                            ? "تم فتح التوثيق في وضع العرض فقط."
                            : (context.permissions && context.permissions.edit_reason) || "لا يمكن تعديل توثيق الدرفة في حالة الطلب الحالية."
                    );
                    shell.setSaveState("readonly", "للعرض فقط");
                } else {
                    refreshSaveState();
                }
                return context;
            } catch (error) {
                if (destroyed || token !== loadToken) return null;
                console.error("Door drawing workspace load failed", error);
                shell.setError("تعذر تحميل بيانات الطلب أو لا تملك الصلاحية المطلوبة.");
                return null;
            }
        }

        shell.elements.back.addEventListener("click", () => returnToOrder(false));
        shell.elements.save.addEventListener("click", () => save({ returnAfter: false }));
        shell.elements.saveReturn.addEventListener("click", () => save({ returnAfter: true }));
        shell.elements.uploadImage.addEventListener("click", () => {
            if (referenceController) referenceController.uploadFromDevice();
        });
        shell.elements.scan.addEventListener("click", () => {
            if (referenceController) referenceController.scanFromScanner();
        });

        function destroy() {
            if (destroyed) return;
            destroyed = true;
            loadToken += 1;
            clearContent();
        }

        return Object.freeze({
            load,
            save,
            returnToOrder,
            destroy,
            state() {
                return Object.freeze({ context, readOnly, dirty, activeContent });
            },
        });
    }

    workspace.SessionController = Object.freeze({ create });
})();