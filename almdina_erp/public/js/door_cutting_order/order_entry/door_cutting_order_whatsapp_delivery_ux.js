(() => {
    "use strict";

    if (window.AlmdinaOrderWhatsAppDeliveryUX) return;

    const DOCTYPE = "Door Cutting Order";
    const CHECKPOINT_KEY = "__almdina_order_checkpoint_save_in_progress";
    const FIRST_SAVE_KEY = "__almdina_whatsapp_first_save";
    const JUST_CREATED_KEY = "__almdina_whatsapp_just_created";
    const AMENDMENT_KEY = "__almdina_whatsapp_amendment";
    const STATUS_METHOD = "almdina_erp.almdina_erp.services.whatsapp_service.get_whatsapp_delivery_status";
    const SEND_METHOD = "almdina_erp.almdina_erp.services.whatsapp_service.send_order_measurements";
    const CONFIRM_MESSAGE = "هل تريد إرسال ملف القياسات للزبون؟";
    const AMENDMENT_CONFIRM_MESSAGE = "هل تريد إرسال تعديلات القياسات للزبون؟";
    const DISCONNECTED_MESSAGE = "لن يتم إرسال رسالة واتساب لأن الجلسة غير متصلة.";
    const SAVE_FIRST_MESSAGE = "احفظ الطلب أولاً ثم أرسل جدول القياسات.";
    const BUTTON_ACTION_LABEL = "إرسال القياسات عبر واتساب";
    const BUTTON_LABEL_AMENDMENT = "إرسال تعديلات القياسات عبر واتساب";
    const BUTTON_CLASS = "dco-whatsapp-send-measurements";

    let offerQueued = false;

    function frontend() {
        return window.AlmdinaFrontend || null;
    }

    function canPrintMeasurements(frm) {
        const permissions = window.AlmdinaPermissions;
        if (!permissions) return false;
        if (typeof permissions.canDocument === "function") {
            return Boolean(permissions.canDocument(frm, "print_measurements"));
        }
        return Boolean(typeof permissions.can === "function" && permissions.can("print_measurements"));
    }

    function canOfferEditSession(frm) {
        const revision = window.AlmdinaOrderRevisionUX;
        if (revision && typeof revision.canOfferEditSession === "function") {
            return Boolean(revision.canOfferEditSession(frm));
        }
        if (!frm || !frm.doc || isNewOrder(frm)) return false;
        if (Number(frm.doc.docstatus || 0) !== 0) return false;
        if ((frm.doc.revision_state || "Current") === "Superseded") return false;
        if ((frm.doc.status || "Draft") !== "Draft") return false;
        const permissions = window.AlmdinaPermissions;
        if (!permissions) return false;
        if (typeof permissions.canDocument === "function") {
            return Boolean(permissions.canDocument(frm, "edit_order"));
        }
        return Boolean(typeof permissions.can === "function" && permissions.can("edit_order"));
    }

    function isNewOrder(frm) {
        return Boolean(frm && typeof frm.is_new === "function" && frm.is_new());
    }

    function isSavedOrder(frm) {
        return Boolean(
            frm
            && frm.doc
            && frm.doctype === DOCTYPE
            && frm.doc.name
            && !isNewOrder(frm)
            && !String(frm.doc.name).startsWith("new-")
        );
    }

    function isDirty(frm) {
        if (frm && typeof frm.is_dirty === "function") return Boolean(frm.is_dirty());
        return Boolean(frm && frm.doc && frm.doc.__unsaved);
    }

    function isCheckpoint(frm) {
        return Boolean(frm && (frm[CHECKPOINT_KEY] || frm.__almdina_preserve_edit_session_after_save));
    }

    function isAmendmentContext(frm) {
        if (!frm || frm[FIRST_SAVE_KEY] || frm[JUST_CREATED_KEY]) return false;
        if (frm[AMENDMENT_KEY]) return true;
        return isSavedOrder(frm);
    }

    function confirmMessage(frm) {
        return isAmendmentContext(frm) ? AMENDMENT_CONFIRM_MESSAGE : CONFIRM_MESSAGE;
    }

    function buttonLabel(frm) {
        return isAmendmentContext(frm) ? BUTTON_LABEL_AMENDMENT : BUTTON_ACTION_LABEL;
    }

    function canShowSendButton(frm) {
        return isSavedOrder(frm) && canOfferEditSession(frm) && canPrintMeasurements(frm);
    }

    function errorMessage(error, fallback) {
        const api = frontend();
        if (api && typeof api.errorMessage === "function") {
            return api.errorMessage(error, fallback);
        }
        return String((error && error.message) || fallback || "");
    }

    function rpc(method, args) {
        const api = frontend();
        if (api && typeof api.rpc === "function") {
            return api.rpc(method, args, { freeze: true, freezeMessage: "جاري إرسال واتساب..." });
        }
        return Promise.reject(new Error("تعذر الاتصال بالخادم."));
    }

    function sendMeasurements(frm) {
        const orderName = String(frm && frm.doc && frm.doc.name || "").trim();
        if (!orderName) {
            frappe.msgprint("تعذر تحديد الطلب لإرسال القياسات.");
            return Promise.resolve(null);
        }
        return rpc(SEND_METHOD, { order_name: orderName }).then(result => {
            const payload = result || {};
            const ok = payload.ok !== false && payload.code !== "document_failed";
            frappe.show_alert({
                message: payload.message || (ok ? "تم إرسال جدول القياسات إلى الزبون عبر واتساب." : "تعذر إرسال ملف القياسات."),
                indicator: ok ? "green" : "orange",
            }, 8);
            if (!ok && payload.message) {
                frappe.msgprint({ title: "إرسال واتساب", message: payload.message, indicator: "orange" });
            }
            return payload;
        }).catch(error => {
            frappe.msgprint({
                title: "تعذر إرسال واتساب",
                message: errorMessage(error, "حدثت مشكلة أثناء إرسال جدول القياسات."),
                indicator: "red",
            });
            return null;
        });
    }

    function offerSend(frm) {
        if (!frm || frm.doctype !== DOCTYPE) return false;
        if (!canPrintMeasurements(frm)) return false;
        const api = frontend();
        if (!api || typeof api.rpc !== "function") return false;
        api.rpc(STATUS_METHOD, {}, { freeze: false }).then(status => {
            const snapshot = status || {};
            if (!snapshot.working) {
                frappe.msgprint({
                    title: "واتساب",
                    message: snapshot.reason || DISCONNECTED_MESSAGE,
                    indicator: "orange",
                });
                return;
            }
            frappe.confirm(confirmMessage(frm), () => {
                sendMeasurements(frm);
            });
        }).catch(error => {
            frappe.msgprint({
                title: "واتساب",
                message: errorMessage(error, DISCONNECTED_MESSAGE),
                indicator: "orange",
            });
        });
        return true;
    }

    function offerAfterOrderSave(frm) {
        if (!frm || frm.doctype !== DOCTYPE) return false;
        if (isCheckpoint(frm) || !canPrintMeasurements(frm)) return false;
        return offerSend(frm);
    }

    function offerFromButton(frm) {
        if (!canShowSendButton(frm)) return false;
        if (isDirty(frm)) {
            frappe.msgprint({
                title: "واتساب",
                message: SAVE_FIRST_MESSAGE,
                indicator: "orange",
            });
            return false;
        }
        return offerSend(frm);
    }

    function queueOffer(frm) {
        if (offerQueued) return false;
        offerQueued = true;
        Promise.resolve().then(() => {
            offerQueued = false;
            offerAfterOrderSave(frm);
        });
        return true;
    }

    function buttonNode(button) {
        if (!button) return null;
        if (button.nodeType) return button;
        if (button[0] && button[0].nodeType) return button[0];
        return null;
    }

    function formPageRoot(frm) {
        const wrapper = frm && frm.page && frm.page.wrapper;
        return wrapper && (wrapper.nodeType ? wrapper : wrapper[0]);
    }

    function registeredSendButton(frm) {
        if (!frm) return null;
        const owned = buttonNode(frm._almdinaWhatsAppSendButton);
        if (owned && owned.isConnected) return owned;
        const registered = frm.custom_buttons && frm.custom_buttons[BUTTON_ACTION_LABEL];
        const registeredNode = buttonNode(registered);
        if (registeredNode && registeredNode.isConnected) {
            frm._almdinaWhatsAppSendButton = registered;
            return registeredNode;
        }
        const root = formPageRoot(frm);
        const rendered = root && root.querySelector(`.${BUTTON_CLASS}`);
        if (rendered && rendered.isConnected) {
            frm._almdinaWhatsAppSendButton = rendered;
            return rendered;
        }
        return null;
    }

    function updateButtonPresentation(frm) {
        const button = registeredSendButton(frm);
        if (!button) return false;
        frm._almdinaWhatsAppSendButton = button;
        button.classList.add(BUTTON_CLASS);
        button.textContent = buttonLabel(frm);
        button.title = button.textContent;
        button.setAttribute("aria-label", button.textContent);
        return true;
    }

    function removeSendButton(frm) {
        if (!frm) return;
        const rendered = registeredSendButton(frm);
        if (typeof frm.remove_custom_button === "function") {
            try {
                frm.remove_custom_button(BUTTON_ACTION_LABEL);
            } catch (error) {
                // Nothing to remove is valid for a new or non-draft order.
            }
        }
        if (rendered && rendered.isConnected) rendered.remove();
        frm._almdinaWhatsAppSendButton = null;
    }

    function syncSendButton(frm) {
        if (!canShowSendButton(frm)) {
            removeSendButton(frm);
            return false;
        }
        if (updateButtonPresentation(frm)) return true;
        if (typeof frm.add_custom_button !== "function") return false;
        const button = frm.add_custom_button(BUTTON_ACTION_LABEL, () => offerFromButton(frm));
        frm._almdinaWhatsAppSendButton = button;
        return updateButtonPresentation(frm);
    }

    function markCreated(frm) {
        if (!frm) return;
        frm[JUST_CREATED_KEY] = true;
        frm[AMENDMENT_KEY] = false;
    }

    function markAmended(frm) {
        if (!frm) return;
        frm[JUST_CREATED_KEY] = false;
        frm[AMENDMENT_KEY] = true;
    }

    function decorateOrderSave() {
        const coordinator = window.AlmdinaDcoEditSessionCoordinator;
        if (!coordinator || typeof coordinator.decorate !== "function") return false;
        if (window.__almdinaWhatsAppSaveOfferInstalled) return true;
        const decorated = coordinator.decorate("order", current => ({
            ...current,
            async save(frm, ...args) {
                const creating = Boolean(frm && (isNewOrder(frm) || frm[FIRST_SAVE_KEY]));
                const result = await current.save(frm, ...args);
                if (result) {
                    if (creating) markCreated(frm);
                    else markAmended(frm);
                    queueOffer(frm);
                    syncSendButton(frm);
                }
                return result;
            },
        }));
        window.__almdinaWhatsAppSaveOfferInstalled = Boolean(decorated);
        return Boolean(decorated);
    }

    frappe.ui.form.on(DOCTYPE, {
        before_save(frm) {
            if (frm && isNewOrder(frm)) frm[FIRST_SAVE_KEY] = true;
        },
        after_save(frm) {
            const firstSave = Boolean(frm && frm[FIRST_SAVE_KEY]);
            if (frm) {
                if (firstSave) markCreated(frm);
                frm[FIRST_SAVE_KEY] = false;
            }
            if (firstSave && !isCheckpoint(frm)) queueOffer(frm);
            syncSendButton(frm);
        },
        onload_post_render(frm) {
            syncSendButton(frm);
        },
        refresh(frm) {
            syncSendButton(frm);
        },
    });

    decorateOrderSave();

    window.addEventListener("almdina:permissions-updated", () => {
        const frm = window.cur_frm;
        if (frm && frm.doctype === DOCTYPE) syncSendButton(frm);
    });

    window.AlmdinaOrderWhatsAppDeliveryUX = Object.freeze({
        AMENDMENT_CONFIRM_MESSAGE,
        AMENDMENT_KEY,
        BUTTON_ACTION_LABEL,
        BUTTON_CLASS,
        BUTTON_LABEL_AMENDMENT,
        CHECKPOINT_KEY,
        CONFIRM_MESSAGE,
        DISCONNECTED_MESSAGE,
        FIRST_SAVE_KEY,
        JUST_CREATED_KEY,
        SAVE_FIRST_MESSAGE,
        buttonLabel,
        canShowSendButton,
        confirmMessage,
        decorateOrderSave,
        isAmendmentContext,
        offerAfterOrderSave,
        offerFromButton,
        queueOffer,
        syncSendButton,
    });
})();
