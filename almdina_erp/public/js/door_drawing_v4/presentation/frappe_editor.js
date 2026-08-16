(() => {
    "use strict";

    const root = window.AlmdinaDoorDrawingV4 = window.AlmdinaDoorDrawingV4 || Object.create(null);
    const persistence = root.PersistenceAdapter;
    const editorController = root.EditorController;
    if (!persistence || !editorController) throw new Error("Drawing V4 persistence and controller must load before Frappe editor");

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

    function saveSession(session) {
        if (!session || session.readOnly) return;
        const document = session.controller.state().interaction.document;
        if (!documentHasGeometry(document)) {
            frappe.msgprint("ارسم ضلعًا واحدًا على الأقل قبل الحفظ.");
            return;
        }

        session.row.special_shape_drawing_json = persistence.toStored(document);
        session.row.special_shape_status = "Documented";
        session.frm.dirty();
        session.dirty = false;
        session.allowClose = true;

        Promise.resolve(session.frm.script_manager.trigger("piece_type", session.row.doctype, session.row.name))
            .catch(error => console.error("Door Drawing V4 piece_type refresh failed", error));

        session.dialog.hide();
        refreshOrderUi(session.frm);
        frappe.show_alert({ message: "تم حفظ رسم الدرفة.", indicator: "green" }, 3);
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