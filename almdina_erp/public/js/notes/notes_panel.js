(() => {
    "use strict";

    const METHODS = Object.freeze({
        context: "almdina_erp.almdina_erp.services.notes_service.get_order_notes_context",
        add: "almdina_erp.almdina_erp.services.notes_service.add_note",
        edit: "almdina_erp.almdina_erp.services.notes_service.edit_note",
        delete: "almdina_erp.almdina_erp.services.notes_service.delete_note",
        pin: "almdina_erp.almdina_erp.services.notes_service.set_important_note",
        clearImportant: "almdina_erp.almdina_erp.services.notes_service.clear_important_note",
    });
    const MAX_LENGTH = 500;
    const NOTE_UPDATED_EVENT = "almdina:notes-context-updated";
    const ORDER_DOCTYPE = "Door Cutting Order";
    const CUSTOMER_DOCTYPE = "Customer";

    const state = {
        root: null,
        content: null,
        isOpen: false,
        orderName: "",
        context: null,
        activeTab: "order",
        loading: false,
        mutating: false,
        error: "",
        loadGeneration: 0,
        mutationGeneration: 0,
        pendingRequest: null,
        drafts: { order: "", customer: "" },
        importantDraft: false,
        editingComment: "",
        editDraft: "",
        returnFocus: null,
    };

    function escapeHtml(value) {
        if (window.frappe && frappe.utils && typeof frappe.utils.escape_html === "function") {
            return frappe.utils.escape_html(String(value ?? ""));
        }
        return String(value ?? "")
            .replaceAll("&", "&amp;")
            .replaceAll("<", "&lt;")
            .replaceAll(">", "&gt;")
            .replaceAll('"', "&quot;")
            .replaceAll("'", "&#039;");
    }

    function uuid() {
        try {
            if (window.crypto && typeof window.crypto.randomUUID === "function") {
                return window.crypto.randomUUID();
            }
        } catch (error) {
            // Fall through to a collision-resistant browser-local operation id.
        }
        const random = Math.random().toString(36).slice(2);
        return `note-${Date.now().toString(36)}-${random}`;
    }

    function apiCall(method, args) {
        if (!window.frappe || typeof frappe.call !== "function") {
            return Promise.reject(new Error("Frappe API is not available."));
        }
        return frappe.call({ method, args, freeze: false }).then(response => response && response.message);
    }

    function errorMessage(error) {
        if (!error) return "تعذر تنفيذ العملية. حاول مرة أخرى.";
        if (error.message) return String(error.message);
        if (error.exc_type || error.exception) return "تعذر تنفيذ العملية. حاول مرة أخرى.";
        return String(error);
    }

    function creationLabel(value) {
        if (!value) return "";
        if (window.frappe && frappe.datetime && typeof frappe.datetime.str_to_user === "function") {
            try {
                return frappe.datetime.str_to_user(value);
            } catch (error) {
                // Keep a stable fallback if a server value is not parseable locally.
            }
        }
        return String(value);
    }

    function mountedRoot() {
        if (state.root && state.root.isConnected) return state.root;
        if (typeof document === "undefined" || !document.body) return null;

        const root = document.createElement("div");
        root.className = "almdina-notes-overlay";
        root.setAttribute("aria-hidden", "true");
        root.innerHTML = `
            <aside class="almdina-notes-panel" role="dialog" aria-modal="true" aria-labelledby="almdina-notes-title" dir="rtl">
                <div class="almdina-notes-panel-content"></div>
            </aside>
        `;
        document.body.appendChild(root);
        state.root = root;
        state.content = root.querySelector(".almdina-notes-panel-content");
        root.addEventListener("click", onClick);
        root.addEventListener("input", onInput);
        root.addEventListener("change", onChange);
        root.addEventListener("keydown", onKeydown);
        return root;
    }

    function contextCounts() {
        const counts = state.context && state.context.counts || {};
        return {
            order: Number(counts.order || 0),
            customer: Number(counts.customer || 0),
        };
    }

    function currentNotes() {
        if (!state.context) return [];
        return state.activeTab === "customer"
            ? (state.context.customer_notes || [])
            : (state.context.order_notes || []);
    }

    function noteByName(commentName) {
        const resolved = String(commentName || "").trim();
        if (!resolved) return null;
        return currentNotes().find(note => String(note && note.name || "") === resolved) || null;
    }

    function canCompose() {
        const permissions = state.context && state.context.permissions || {};
        if (state.activeTab === "customer") return permissions.can_add_customer_note === true;
        return permissions.can_add_order_note === true;
    }

    function canManageImportant() {
        const permissions = state.context && state.context.permissions || {};
        return state.activeTab === "order" && permissions.can_manage_important_note === true;
    }

    function customerAvailable() {
        const permissions = state.context && state.context.permissions || {};
        return Boolean(state.context && state.context.customer && permissions.can_view_customer_notes === true);
    }

    function renderHeader() {
        return `
            <header class="almdina-notes-header">
                <div>
                    <h2 id="almdina-notes-title">الملاحظات</h2>
                    <span class="almdina-notes-order-id">${escapeHtml(state.orderName)}</span>
                </div>
                <button type="button" class="almdina-notes-icon-button" data-notes-action="close" aria-label="إغلاق الملاحظات" title="إغلاق">×</button>
            </header>
        `;
    }

    function renderTabs() {
        const counts = contextCounts();
        const customerDisabled = !state.context || !state.context.customer;
        return `
            <div class="almdina-notes-tabs" role="tablist" aria-label="سياق الملاحظات">
                <button type="button" role="tab" class="almdina-notes-tab ${state.activeTab === "order" ? "is-active" : ""}" data-notes-action="tab" data-notes-tab="order" aria-selected="${state.activeTab === "order" ? "true" : "false"}">
                    الطلب <span>${counts.order}</span>
                </button>
                <button type="button" role="tab" class="almdina-notes-tab ${state.activeTab === "customer" ? "is-active" : ""}" data-notes-action="tab" data-notes-tab="customer" aria-selected="${state.activeTab === "customer" ? "true" : "false"}" ${customerDisabled ? "disabled" : ""}>
                    العميل <span>${counts.customer}</span>
                </button>
            </div>
        `;
    }

    function renderImportantNote() {
        if (state.activeTab !== "order" || !state.context) return "";
        const note = state.context.important_note;
        if (!note) {
            return `
                <section class="almdina-notes-important is-empty" aria-label="الملاحظة المهمة الحالية">
                    <div class="almdina-notes-section-label">الملاحظة المهمة الحالية</div>
                    <div class="almdina-notes-important-empty">لا توجد ملاحظة مهمة حاليًا.</div>
                </section>
            `;
        }
        return `
            <section class="almdina-notes-important" aria-label="الملاحظة المهمة الحالية">
                <div class="almdina-notes-important-heading">
                    <span class="almdina-notes-section-label">الملاحظة المهمة الحالية</span>
                    ${canManageImportant() ? '<button type="button" class="almdina-notes-link-button" data-notes-action="clear-important" ' + (state.mutating ? "disabled" : "") + '>إلغاء التعيين</button>' : ""}
                </div>
                <div class="almdina-notes-important-card">
                    <span class="almdina-notes-star" aria-hidden="true">★</span>
                    <div>
                        <strong>${escapeHtml(note.content || "")}</strong>
                        <div class="almdina-notes-meta">${escapeHtml(note.author || "")} ${note.creation ? `• ${escapeHtml(creationLabel(note.creation))}` : ""}${note.is_edited ? " • تم التعديل" : ""}</div>
                    </div>
                </div>
            </section>
        `;
    }

    function renderNoteEditor(note) {
        const value = state.editDraft || "";
        return `
            <div class="almdina-note-editor" data-comment-name="${escapeHtml(note.name || "")}">
                <textarea data-notes-input="edit-content" maxlength="${MAX_LENGTH}" rows="3" aria-label="تعديل الملاحظة" ${state.mutating ? "disabled" : ""}>${escapeHtml(value)}</textarea>
                <div class="almdina-note-editor-meta">
                    <span class="almdina-note-edit-counter">${value.length} / ${MAX_LENGTH}</span>
                    <div class="almdina-note-editor-actions">
                        <button type="button" class="btn btn-default btn-xs" data-notes-action="cancel-edit" ${state.mutating ? "disabled" : ""}>إلغاء</button>
                        <button type="button" class="btn btn-primary btn-xs" data-notes-action="save-edit" ${state.mutating || !value.trim() ? "disabled" : ""}>${state.mutating ? "جارٍ الحفظ..." : "حفظ التعديل"}</button>
                    </div>
                </div>
                ${state.error ? `<div class="almdina-notes-error" role="alert">${escapeHtml(state.error)}</div>` : ""}
            </div>
        `;
    }

    function renderNote(note) {
        const important = note && note.is_important === true;
        const editing = String(state.editingComment || "") === String(note && note.name || "");
        const pinAction = canManageImportant() && !important
            ? `<button type="button" class="almdina-note-pin" data-notes-action="pin" data-comment-name="${escapeHtml(note.name || "")}" ${state.mutating ? "disabled" : ""} aria-label="تعيين كملاحظة مهمة" title="تعيين كملاحظة مهمة">☆</button>`
            : important
                ? '<span class="almdina-note-pin is-important" aria-label="ملاحظة مهمة" title="ملاحظة مهمة">★</span>'
                : "";
        const editAction = note && note.can_edit === true && !editing
            ? `<button type="button" class="almdina-note-action" data-notes-action="edit" data-comment-name="${escapeHtml(note.name || "")}" ${state.mutating ? "disabled" : ""}>تعديل</button>`
            : "";
        const deleteAction = note && note.can_delete === true && !editing
            ? `<button type="button" class="almdina-note-action is-danger" data-notes-action="delete" data-comment-name="${escapeHtml(note.name || "")}" ${state.mutating ? "disabled" : ""}>حذف</button>`
            : "";
        const actions = pinAction || editAction || deleteAction
            ? `<div class="almdina-note-actions">${pinAction}${editAction}${deleteAction}</div>`
            : "";
        return `
            <article class="almdina-note-card ${important ? "is-important" : ""} ${editing ? "is-editing" : ""}">
                <div class="almdina-note-avatar" aria-hidden="true">${escapeHtml(String(note.author || "م").trim().slice(0, 1) || "م")}</div>
                <div class="almdina-note-body">
                    <div class="almdina-note-head">
                        <div>
                            <strong>${escapeHtml(note.author || note.author_user || "مستخدم")}</strong>
                            <span>${escapeHtml(creationLabel(note.creation))}${note.is_edited ? " • تم التعديل" : ""}</span>
                        </div>
                        ${actions}
                    </div>
                    ${editing ? renderNoteEditor(note) : `<p>${escapeHtml(note.content || "")}</p>`}
                </div>
            </article>
        `;
    }

    function renderNotesList() {
        if (state.activeTab === "customer" && !customerAvailable()) {
            return `
                <section class="almdina-notes-list-section">
                    <div class="almdina-notes-empty-state">لا تتوفر لك صلاحية ملاحظات العميل المرتبط بهذا الطلب.</div>
                </section>
            `;
        }
        const notes = currentNotes();
        return `
            <section class="almdina-notes-list-section" aria-label="كل الملاحظات">
                <div class="almdina-notes-section-label">كل الملاحظات</div>
                <div class="almdina-notes-list">
                    ${notes.length ? notes.map(renderNote).join("") : '<div class="almdina-notes-empty-state">لا توجد ملاحظات بعد.</div>'}
                </div>
            </section>
        `;
    }

    function renderActionError() {
        if (!state.error || state.editingComment) return "";
        return `<div class="almdina-notes-error almdina-notes-action-error" role="alert">${escapeHtml(state.error)}</div>`;
    }

    function renderComposer() {
        if (!canCompose()) return "";
        const value = state.drafts[state.activeTab] || "";
        const importantToggle = state.activeTab === "order" && canManageImportant()
            ? `
                <label class="almdina-notes-important-toggle">
                    <input type="checkbox" data-notes-input="important" ${state.importantDraft ? "checked" : ""} ${state.mutating ? "disabled" : ""}>
                    <span aria-hidden="true">★</span>
                    <span>تعيين كملاحظة مهمة</span>
                </label>
            `
            : "";
        return `
            <section class="almdina-notes-composer" aria-label="إضافة ملاحظة">
                <label for="almdina-notes-input">إضافة ملاحظة</label>
                <textarea id="almdina-notes-input" data-notes-input="content" maxlength="${MAX_LENGTH}" rows="3" placeholder="اكتب ملاحظة قصيرة وواضحة..." ${state.mutating ? "disabled" : ""}>${escapeHtml(value)}</textarea>
                <div class="almdina-notes-composer-meta">
                    <span class="almdina-notes-counter">${value.length} / ${MAX_LENGTH}</span>
                    ${importantToggle}
                </div>
                <button type="button" class="btn btn-primary almdina-notes-submit" data-notes-action="submit" ${state.mutating || !value.trim() ? "disabled" : ""}>
                    ${state.mutating ? "جارٍ الإضافة..." : "إضافة"}
                </button>
            </section>
        `;
    }

    function renderBody() {
        if (state.loading) {
            return '<div class="almdina-notes-loading" role="status" aria-live="polite"><span class="almdina-notes-spinner" aria-hidden="true"></span><span>جارٍ تحميل الملاحظات...</span></div>';
        }
        if (!state.context) {
            return `
                <div class="almdina-notes-load-error" role="alert">
                    <strong>تعذر تحميل الملاحظات.</strong>
                    <span>${escapeHtml(state.error || "تحقق من الاتصال وحاول مرة أخرى.")}</span>
                    <button type="button" class="btn btn-default" data-notes-action="retry-load">إعادة المحاولة</button>
                </div>
            `;
        }
        return `${renderTabs()}${renderImportantNote()}${renderNotesList()}${renderActionError()}${renderComposer()}`;
    }

    function render() {
        if (!state.content) return;
        state.content.innerHTML = `${renderHeader()}<div class="almdina-notes-scroll">${renderBody()}</div>`;
        const counter = state.content.querySelector(".almdina-notes-counter");
        if (counter) counter.textContent = `${(state.drafts[state.activeTab] || "").length} / ${MAX_LENGTH}`;
    }

    function emitContextUpdated(context) {
        if (!context || typeof document === "undefined" || typeof CustomEvent !== "function") return;
        document.dispatchEvent(new CustomEvent(NOTE_UPDATED_EVENT, {
            detail: {
                order_name: String(context.order || ""),
                counts: Object.assign({}, context.counts || {}),
                important_note_preview: String(context.important_note_preview || ""),
                important_note_comment: String(context.important_note_comment || ""),
            },
        }));
    }

    function installContext(context, { emit = false } = {}) {
        if (!context) return;
        state.context = context;
        if (state.activeTab === "customer" && !context.customer) state.activeTab = "order";
        if (emit) emitContextUpdated(context);
        render();
    }

    function loadCurrentOrder() {
        const orderName = state.orderName;
        if (!orderName) return Promise.resolve(null);
        const generation = ++state.loadGeneration;
        state.loading = true;
        state.error = "";
        state.context = null;
        state.editingComment = "";
        state.editDraft = "";
        render();
        return apiCall(METHODS.context, { order_name: orderName })
            .then(context => {
                if (generation !== state.loadGeneration || orderName !== state.orderName || !state.isOpen) return null;
                state.loading = false;
                installContext(context);
                return context;
            })
            .catch(error => {
                if (generation !== state.loadGeneration || orderName !== state.orderName || !state.isOpen) return null;
                state.loading = false;
                state.error = errorMessage(error);
                state.context = null;
                render();
                return null;
            });
    }

    function referenceArgs() {
        if (!state.context) return null;
        if (state.activeTab === "customer") {
            if (!customerAvailable()) return null;
            return {
                reference_doctype: CUSTOMER_DOCTYPE,
                reference_name: state.context.customer,
                order_name: state.orderName,
            };
        }
        return {
            reference_doctype: ORDER_DOCTYPE,
            reference_name: state.orderName,
            order_name: state.orderName,
        };
    }

    function requestIdFor(key) {
        if (!state.pendingRequest || state.pendingRequest.key !== key) {
            state.pendingRequest = { key, id: uuid() };
        }
        return state.pendingRequest.id;
    }

    function clearEditState() {
        state.editingComment = "";
        state.editDraft = "";
    }

    function performMutation(method, args, { clearDraft = false, clearEdit = false } = {}) {
        if (state.mutating) return Promise.resolve(null);
        const orderName = state.orderName;
        const activeTab = state.activeTab;
        const generation = ++state.mutationGeneration;
        state.mutating = true;
        state.error = "";
        render();
        return apiCall(method, args)
            .then(context => {
                // A successful server mutation belongs to its captured order even
                // if the drawer was closed or reopened elsewhere while in flight.
                // Keep list/form projections synchronized, but never let that stale
                // response take ownership of the new drawer lifecycle.
                emitContextUpdated(context);
                if (
                    generation !== state.mutationGeneration
                    || orderName !== state.orderName
                    || !state.isOpen
                ) {
                    return context;
                }
                state.mutating = false;
                if (clearDraft) {
                    state.drafts[activeTab] = "";
                    if (activeTab === "order") state.importantDraft = false;
                    state.pendingRequest = null;
                }
                if (clearEdit) clearEditState();
                installContext(context);
                return context;
            })
            .catch(error => {
                if (
                    generation !== state.mutationGeneration
                    || orderName !== state.orderName
                    || !state.isOpen
                ) {
                    return null;
                }
                state.mutating = false;
                state.error = errorMessage(error);
                render();
                return null;
            });
    }

    function submitCurrentDraft() {
        const reference = referenceArgs();
        if (!reference || !canCompose()) return;
        const content = String(state.drafts[state.activeTab] || "").trim();
        if (!content || content.length > MAX_LENGTH) return;
        const important = state.activeTab === "order" && state.importantDraft && canManageImportant();
        const key = JSON.stringify([state.orderName, state.activeTab, content, important ? 1 : 0]);
        performMutation(METHODS.add, {
            ...reference,
            content,
            request_id: requestIdFor(key),
            important: important ? 1 : 0,
        }, { clearDraft: true });
    }

    function beginEdit(commentName) {
        if (state.mutating) return;
        const note = noteByName(commentName);
        if (!note || note.can_edit !== true) return;
        state.editingComment = String(note.name || "");
        state.editDraft = String(note.content || "").slice(0, MAX_LENGTH);
        state.error = "";
        state.pendingRequest = null;
        render();
        const textarea = state.root && state.root.querySelector('[data-notes-input="edit-content"]');
        if (textarea) {
            textarea.focus({ preventScroll: true });
            textarea.setSelectionRange(textarea.value.length, textarea.value.length);
        }
    }

    function cancelEdit() {
        if (state.mutating) return;
        clearEditState();
        state.error = "";
        render();
    }

    function saveEdit() {
        const note = noteByName(state.editingComment);
        const reference = referenceArgs();
        if (!note || note.can_edit !== true || !reference) return;
        const content = String(state.editDraft || "").trim();
        if (!content || content.length > MAX_LENGTH) return;
        performMutation(METHODS.edit, {
            ...reference,
            comment_name: note.name,
            content,
        }, { clearEdit: true });
    }

    function confirmDelete(message, onConfirm) {
        if (window.frappe && typeof frappe.confirm === "function") {
            frappe.confirm(message, onConfirm);
            return;
        }
        if (typeof window.confirm === "function" && window.confirm(message)) onConfirm();
    }

    function deleteComment(commentName) {
        if (state.mutating) return;
        const note = noteByName(commentName);
        if (!note || note.can_delete !== true) return;
        confirmDelete("هل تريد حذف هذه الملاحظة؟ لا يمكن التراجع عن الحذف.", () => {
            const reference = referenceArgs();
            if (!reference || state.mutating) return;
            performMutation(METHODS.delete, {
                ...reference,
                comment_name: note.name,
            }, { clearEdit: state.editingComment === note.name });
        });
    }

    function pinComment(commentName) {
        const resolved = String(commentName || "").trim();
        if (!resolved || !canManageImportant()) return;
        performMutation(METHODS.pin, {
            order_name: state.orderName,
            comment_name: resolved,
        });
    }

    function clearImportant() {
        if (!canManageImportant()) return;
        performMutation(METHODS.clearImportant, { order_name: state.orderName });
    }

    function onClick(event) {
        if (!state.root) return;
        if (event.target === state.root) {
            close();
            return;
        }
        const actionNode = event.target.closest("[data-notes-action]");
        if (!actionNode || !state.root.contains(actionNode)) return;
        const action = actionNode.dataset.notesAction;
        if (action === "close") return close();
        if (action === "retry-load") return loadCurrentOrder();
        if (action === "tab") {
            const tab = actionNode.dataset.notesTab;
            if ((tab === "order" || tab === "customer") && tab !== state.activeTab) {
                state.activeTab = tab;
                state.error = "";
                state.pendingRequest = null;
                clearEditState();
                if (tab !== "order") state.importantDraft = false;
                render();
            }
            return;
        }
        if (action === "submit") return submitCurrentDraft();
        if (action === "edit") return beginEdit(actionNode.dataset.commentName);
        if (action === "cancel-edit") return cancelEdit();
        if (action === "save-edit") return saveEdit();
        if (action === "delete") return deleteComment(actionNode.dataset.commentName);
        if (action === "pin") return pinComment(actionNode.dataset.commentName);
        if (action === "clear-important") return clearImportant();
    }

    function onInput(event) {
        if (!event.target) return;
        if (event.target.dataset.notesInput === "content") {
            const value = String(event.target.value || "").slice(0, MAX_LENGTH);
            state.drafts[state.activeTab] = value;
            const counter = state.root && state.root.querySelector(".almdina-notes-counter");
            if (counter) counter.textContent = `${value.length} / ${MAX_LENGTH}`;
            const submit = state.root && state.root.querySelector('[data-notes-action="submit"]');
            if (submit && !state.mutating) submit.disabled = !value.trim();
            return;
        }
        if (event.target.dataset.notesInput === "edit-content") {
            const value = String(event.target.value || "").slice(0, MAX_LENGTH);
            state.editDraft = value;
            const counter = state.root && state.root.querySelector(".almdina-note-edit-counter");
            if (counter) counter.textContent = `${value.length} / ${MAX_LENGTH}`;
            const save = state.root && state.root.querySelector('[data-notes-action="save-edit"]');
            if (save && !state.mutating) save.disabled = !value.trim();
        }
    }

    function onChange(event) {
        if (!event.target || event.target.dataset.notesInput !== "important") return;
        state.importantDraft = event.target.checked === true;
    }

    function onKeydown(event) {
        if (event.key === "Escape" && state.isOpen) {
            event.preventDefault();
            if (state.editingComment && !state.mutating) {
                cancelEdit();
                return;
            }
            close();
            return;
        }
        if (event.key !== "Tab" || !state.isOpen) return;
        const panel = state.root && state.root.querySelector(".almdina-notes-panel");
        if (!panel) return;
        const focusable = [...panel.querySelectorAll('button:not([disabled]), textarea:not([disabled]), input:not([disabled]), [tabindex]:not([tabindex="-1"])')];
        if (!focusable.length) return;
        const first = focusable[0];
        const last = focusable[focusable.length - 1];
        if (event.shiftKey && document.activeElement === first) {
            event.preventDefault();
            last.focus();
        } else if (!event.shiftKey && document.activeElement === last) {
            event.preventDefault();
            first.focus();
        }
    }

    function invalidateTransientWork() {
        state.loadGeneration += 1;
        state.mutationGeneration += 1;
        state.loading = false;
        state.mutating = false;
    }

    function openForOrder(orderName, options = {}) {
        const resolved = String(orderName || "").trim();
        if (!resolved) return Promise.resolve(null);
        const root = mountedRoot();
        if (!root) return Promise.resolve(null);

        invalidateTransientWork();
        state.returnFocus = document.activeElement;
        state.isOpen = true;
        state.orderName = resolved;
        state.activeTab = options.tab === "customer" ? "customer" : "order";
        state.error = "";
        state.context = null;
        state.pendingRequest = null;
        state.drafts = { order: "", customer: "" };
        state.importantDraft = false;
        clearEditState();
        root.classList.add("is-open");
        root.setAttribute("aria-hidden", "false");
        document.body.classList.add("almdina-notes-open");
        render();
        const closeButton = root.querySelector('[data-notes-action="close"]');
        if (closeButton) closeButton.focus({ preventScroll: true });
        return loadCurrentOrder();
    }

    function close() {
        if (!state.root || !state.isOpen) return;
        state.isOpen = false;
        invalidateTransientWork();
        clearEditState();
        state.root.classList.remove("is-open");
        state.root.setAttribute("aria-hidden", "true");
        document.body.classList.remove("almdina-notes-open");
        const focus = state.returnFocus;
        state.returnFocus = null;
        if (focus && focus.isConnected && typeof focus.focus === "function") {
            try {
                focus.focus({ preventScroll: true });
            } catch (error) {
                focus.focus();
            }
        }
    }

    function refresh() {
        if (!state.isOpen || !state.orderName) return Promise.resolve(null);
        return loadCurrentOrder();
    }

    function destroy() {
        if (state.isOpen) close();
        invalidateTransientWork();
        if (state.root) {
            state.root.removeEventListener("click", onClick);
            state.root.removeEventListener("input", onInput);
            state.root.removeEventListener("change", onChange);
            state.root.removeEventListener("keydown", onKeydown);
            state.root.remove();
        }
        state.root = null;
        state.content = null;
        state.orderName = "";
        state.context = null;
        state.activeTab = "order";
        state.error = "";
        state.pendingRequest = null;
        state.drafts = { order: "", customer: "" };
        state.importantDraft = false;
        clearEditState();
        state.returnFocus = null;
    }

    if (window.frappe && frappe.router && typeof frappe.router.on === "function") {
        frappe.router.on("change", () => {
            if (state.isOpen) close();
        });
    }

    window.AlmdinaNotesPanel = Object.freeze({
        NOTE_UPDATED_EVENT,
        close,
        destroy,
        openForOrder,
        refresh,
    });
})();
