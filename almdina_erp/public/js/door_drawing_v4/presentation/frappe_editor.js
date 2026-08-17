(() => {
    "use strict";

    const root = window.AlmdinaDoorDrawingV4 = window.AlmdinaDoorDrawingV4 || Object.create(null);
    const persistence = root.PersistenceAdapter;
    const manufacturingProjection = root.ManufacturingProjection;
    const editorController = root.EditorController;
    if (!persistence || !manufacturingProjection || !editorController) {
        throw new Error("Drawing V4 persistence, manufacturing projection and controller must load before Frappe editor");
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

    let activeSession = null;

    function shellHtml(readOnly) {
        return `
            <div class="ald-v4-frappe-host" dir="rtl">
                <div class="ald-v4-editor-host" data-ald-v4-editor-host></div>
                <div class="ald-v4-dialog-actions">
                    <div class="ald-v4-dialog-message">${readOnly ? "وضع العرض فقط" : "P القلم الذكي · اكتب الطول ثم Enter"}</div>
                    <div class="ald-v4-dialog-buttons">
                        <button type="button" class="ald-v4-action ald-v4-action-secondary" data-ald-v4-close>إغلاق</button>
                        ${readOnly ? "" : '<button type="button" class="ald-v4-action ald-v4-action-primary" data-ald-v4-save>حفظ الرسم</button>'}
                    </div>
                </div>
            </div>`;
    }

    function closeActiveSession() {
        if (!activeSession) return;
        const current = activeSession;
        activeSession = null;
        current.allowClose = true;
        try { current.controller.destroy(); } catch (error) { /* best-effort cleanup */ }
        try { current.dialog.hide(); } catch (error) { /* best-effort cleanup */ }
    }

    function documentHasGeometry(document) {
        return Boolean(document && Array.isArray(document.segments) && document.segments.length);
    }

    function refreshOrderUi(frm) {
        try {
            if (window.AlmdinaDoorCuttingFastEntry && typeof window.AlmdinaDoorCuttingFastEntry.render === "function") {
                window.AlmdinaDoorCuttingFastEntry.render(frm);
            }
        } catch (error) {
            console.error("Door Drawing V4 failed to refresh fast-entry UI", error);
        }
    }

    function projectionMessage(result) {
        return PROJECTION_MESSAGES[result && result.code] || "تعذر تحويل الرسم إلى هندسة تصنيع صالحة.";
    }

    function manufacturingGeometry(document, row) {
        const projected = manufacturingProjection.project(document);
        if (!projected.ok) {
            return Object.freeze({ ok: false, message: projectionMessage(projected) });
        }

        const contract = window.AlmdinaSpecialShapeGeometry;
        if (!contract || typeof contract.validate !== "function" || typeof contract.serialize !== "function") {
            throw new Error("Special shape manufacturing geometry contract is not available");
        }

        const validation = contract.validate(projected.geometry, row.width_cm, row.length_cm);
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

    function saveSession(session) {
        if (!session || session.readOnly) return;
        const document = session.controller.state().interaction.document;
        if (!documentHasGeometry(document)) {
            frappe.msgprint("ارسم محيط الدرفة قبل الحفظ.");
            return;
        }

        let manufacturing;
        try {
            manufacturing = manufacturingGeometry(document, session.row);
        } catch (error) {
            console.error("Door Drawing V4 manufacturing projection failed", error);
            frappe.msgprint("تعذر تجهيز هندسة الدرفة للتصنيع. أعد تحميل الصفحة ثم حاول مرة أخرى.");
            return;
        }
        if (!manufacturing.ok) {
            frappe.msgprint(manufacturing.message);
            return;
        }

        session.row.special_shape_drawing_json = persistence.toStored(document);
        session.row.special_shape_geometry_json = manufacturing.serialized;
        session.row.special_shape_status = "Documented";
        session.frm.dirty();
        session.dirty = false;
        session.allowClose = true;

        Promise.resolve(session.frm.script_manager.trigger("piece_type", session.row.doctype, session.row.name))
            .catch(error => console.error("Door Drawing V4 piece_type refresh failed", error));

        session.dialog.hide();
        refreshOrderUi(session.frm);
        frappe.show_alert({ message: "تم حفظ الرسم وهندسة التصنيع.", indicator: "green" }, 3);
    }

    function requestClose(session) {
        if (!session || session.allowClose || session.readOnly || !session.dirty) {
            if (session) {
                session.allowClose = true;
                session.dialog.hide();
            }
            return;
        }
        frappe.confirm(
            "لديك تعديلات غير محفوظة. هل تريد إغلاق الرسم دون حفظ؟",
            () => {
                session.allowClose = true;
                session.dialog.hide();
            }
        );
    }

    function bindDialog(session, host) {
        const saveButton = host.querySelector("[data-ald-v4-save]");
        const closeButton = host.querySelector("[data-ald-v4-close]");
        if (saveButton) saveButton.addEventListener("click", () => saveSession(session));
        if (closeButton) closeButton.addEventListener("click", () => requestClose(session));

        if (session.dialog.$wrapper && typeof session.dialog.$wrapper.on === "function") {
            session.dialog.$wrapper.on("hide.bs.modal.aldDoorDrawingV4", event => {
                if (!session.allowClose && !session.readOnly && session.dirty) {
                    event.preventDefault();
                    requestClose(session);
                }
            });
            session.dialog.$wrapper.on("hidden.bs.modal.aldDoorDrawingV4", () => {
                try { session.controller.destroy(); } catch (error) { /* best-effort cleanup */ }
                if (activeSession === session) activeSession = null;
            });
        }
    }

    function open(frm, row, options = {}) {
        if (!window.frappe || !frappe.ui || !frappe.ui.Dialog) {
            throw new Error("Frappe dialog API is required for Door Drawing V4");
        }
        if ((row && row.piece_type || "Regular") !== "Special") {
            frappe.msgprint("حوّل نوع الدرفة إلى «خاصة» أولًا.");
            return null;
        }

        closeActiveSession();
        const readOnly = Boolean(options.readOnly);
        const initial = persistence.fromStored(row.special_shape_drawing_json, row);
        const dialog = new frappe.ui.Dialog({
            title: readOnly ? "عرض رسم الدرفة الخاصة" : "رسم الدرفة الخاصة",
            size: "extra-large",
            fields: [{ fieldname: "door_drawing_v4", fieldtype: "HTML", options: shellHtml(readOnly) }],
        });
        dialog.$wrapper.addClass("dco-special-shape-modal ald-v4-modal");
        if (readOnly) dialog.$wrapper.addClass("dco-special-shape-readonly");
        dialog.show();

        const fieldWrapper = dialog.fields_dict.door_drawing_v4.$wrapper.get(0);
        const host = fieldWrapper && fieldWrapper.querySelector(".ald-v4-frappe-host");
        const editorHost = host && host.querySelector("[data-ald-v4-editor-host]");
        if (!host || !editorHost) {
            dialog.hide();
            frappe.msgprint("تعذر فتح محرر رسم الدرفة.");
            return null;
        }

        const session = {
            frm,
            row,
            dialog,
            readOnly,
            dirty: false,
            allowClose: false,
            controller: null,
        };
        session.controller = editorController.create({
            container: editorHost,
            document: initial,
            readOnly,
            onChange() {
                session.dirty = true;
            },
        });
        activeSession = session;
        bindDialog(session, host);
        return session;
    }

    root.Editor = Object.freeze({
        open,
        view(frm, row) {
            return open(frm, row, { readOnly: true });
        },
    });
})();
