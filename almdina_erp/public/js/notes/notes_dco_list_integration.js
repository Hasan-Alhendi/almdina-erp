(() => {
    "use strict";

    const DOCTYPE = "Door Cutting Order";
    const UPDATED_EVENT = "almdina:notes-context-updated";
    const IMPORTANT_FIELD = "important_note_preview";
    let activeListView = null;

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

    function rootNode(listview) {
        const wrapper = listview && listview.page && listview.page.wrapper;
        return wrapper && (wrapper.nodeType ? wrapper : wrapper[0]);
    }

    function columnFieldname(column) {
        return String(column && column.df && column.df.fieldname || "").trim();
    }

    function arraysMatch(left, right) {
        return left.length === right.length && left.every((value, index) => value === right[index]);
    }

    function importantColumnDefinition() {
        if (!window.frappe || !frappe.meta || typeof frappe.meta.get_docfield !== "function") return null;
        const df = frappe.meta.get_docfield(DOCTYPE, IMPORTANT_FIELD);
        return df ? { type: "Field", df } : null;
    }

    function reorderImportantColumn(listview) {
        const columns = listview && listview.columns;
        if (!Array.isArray(columns) || !columns.length) return false;
        const names = columns.map(columnFieldname);
        const notesIndex = names.indexOf("order_notes");
        const importantIndex = names.indexOf(IMPORTANT_FIELD);
        if (notesIndex < 0 || importantIndex < 0 || importantIndex === notesIndex + 1) return false;

        const important = columns.splice(importantIndex, 1)[0];
        const nextNotesIndex = columns.findIndex(column => columnFieldname(column) === "order_notes");
        columns.splice(nextNotesIndex + 1, 0, important);
        return true;
    }

    function ensureImportantColumn(listview) {
        const columns = listview && listview.columns;
        if (!Array.isArray(columns) || !columns.length) return false;
        if (columns.some(column => columnFieldname(column) === IMPORTANT_FIELD)) {
            return reorderImportantColumn(listview);
        }

        // Frappe's saved List View layout can omit an in_list_view field even
        // though the value is fetched. ALMADINA-156 makes the current important
        // note a mandatory operational signal, so restore only this read-only
        // projection column without rewriting the user's saved layout.
        const important = importantColumnDefinition();
        if (!important) return false;
        const notesIndex = columns.findIndex(column => columnFieldname(column) === "order_notes");
        if (notesIndex >= 0) {
            columns.splice(notesIndex + 1, 0, important);
        } else {
            // If a user intentionally hid the legacy order_notes column, preserve
            // that choice while still showing the mandatory important signal.
            const tagIndex = columns.findIndex(column => column && column.type === "Tag");
            columns.splice(tagIndex >= 0 ? tagIndex + 1 : Math.min(1, columns.length), 0, important);
        }
        return true;
    }

    function reconcileColumns(listview) {
        if (!listview || listview._almdinaNotesReconcilingColumns) return;
        const before = (listview.columns || []).map(columnFieldname);
        if (!ensureImportantColumn(listview)) return;
        const after = (listview.columns || []).map(columnFieldname);
        if (arraysMatch(before, after)) return;

        listview._almdinaNotesReconcilingColumns = true;
        try {
            if (typeof listview.render_header === "function") listview.render_header(true);
            if (typeof listview.render_list === "function") listview.render_list();
        } finally {
            listview._almdinaNotesReconcilingColumns = false;
        }
    }

    function disposeRuntime(listview) {
        if (!listview) return;
        const root = rootNode(listview);
        if (listview._almdinaNotesObserver) {
            listview._almdinaNotesObserver.disconnect();
            listview._almdinaNotesObserver = null;
        }
        if (listview._almdinaNotesFrame != null) {
            const cancelFrame = window.cancelAnimationFrame || window.clearTimeout;
            if (typeof cancelFrame === "function") cancelFrame(listview._almdinaNotesFrame);
            listview._almdinaNotesFrame = null;
        }
        if (root && listview._almdinaNotesClickHandler) {
            root.removeEventListener("click", listview._almdinaNotesClickHandler);
        }
        listview._almdinaNotesClickHandler = null;
        listview._almdinaNotesClickInstalled = false;
        if (activeListView === listview) activeListView = null;
    }

    function schedule(listview) {
        if (!listview || listview._almdinaNotesFrame != null) return;
        const requestFrame = window.requestAnimationFrame || (callback => window.setTimeout(callback, 16));
        listview._almdinaNotesFrame = requestFrame(() => {
            listview._almdinaNotesFrame = null;
            const root = rootNode(listview);
            if (!root || !root.isConnected) {
                disposeRuntime(listview);
                return;
            }
            reconcileColumns(listview);
            reconcileMobileCards(listview);
        });
    }

    function docByName(listview, name) {
        return (listview && listview.data || []).find(doc => String(doc && doc.name || "") === String(name || "")) || null;
    }

    function rowOrderName(container) {
        if (!container) return "";
        const dataNode = container.matches && container.matches("[data-name]")
            ? container
            : container.querySelector && container.querySelector("[data-name]");
        if (dataNode && dataNode.dataset && dataNode.dataset.name) return String(dataNode.dataset.name);
        const card = container.querySelector && container.querySelector(".dco-mobile-order-card[data-order-name]");
        if (card && card.dataset.orderName) return String(card.dataset.orderName);
        const link = container.querySelector && container.querySelector("a[href*='/door-cutting-order/']");
        if (!link) return "";
        const segment = String(link.getAttribute("href") || "").split("/").filter(Boolean).pop();
        return segment ? decodeURIComponent(segment) : "";
    }

    function importantButton(orderName, preview) {
        const button = document.createElement("button");
        button.type = "button";
        button.className = "dco-card-important-note";
        button.dataset.orderName = orderName;
        button.setAttribute("aria-label", `فتح الملاحظة المهمة: ${preview}`);
        button.title = preview;
        button.innerHTML = `
            <span class="dco-card-important-note-icon" aria-hidden="true">★</span>
            <span class="dco-card-important-note-copy">
                <span>ملاحظة مهمة</span>
                <strong>${escapeHtml(preview)}</strong>
            </span>
        `;
        return button;
    }

    function reconcileMobileCard(listview, container) {
        const card = container && container.querySelector && container.querySelector(".dco-mobile-order-card");
        if (!card) return;
        const orderName = String(card.dataset.orderName || rowOrderName(container) || "").trim();
        if (!orderName) return;
        const doc = docByName(listview, orderName);
        const preview = String(doc && doc[IMPORTANT_FIELD] || "").trim();
        let existing = card.querySelector(".dco-card-important-note");
        if (!preview) {
            if (existing) existing.remove();
            return;
        }
        if (existing && existing.dataset.preview === preview) return;

        const next = importantButton(orderName, preview);
        next.dataset.preview = preview;
        if (existing) {
            existing.replaceWith(next);
            return;
        }
        const date = card.querySelector(".dco-card-date-row");
        const action = card.querySelector(".dco-card-actions, .dco-card-complete-state");
        if (date) card.insertBefore(next, date);
        else if (action) card.insertBefore(next, action);
        else card.appendChild(next);
    }

    function reconcileMobileCards(listview) {
        const root = rootNode(listview);
        if (!root || !root.classList.contains("dco-order-card-layout")) return;
        root.querySelectorAll(".list-row-container").forEach(container => reconcileMobileCard(listview, container));
    }

    function openPanel(orderName) {
        const panel = window.AlmdinaNotesPanel;
        if (panel && typeof panel.openForOrder === "function") {
            panel.openForOrder(orderName);
            return;
        }
        frappe.set_route("Form", DOCTYPE, orderName);
    }

    function installClickDelegation(listview) {
        const root = rootNode(listview);
        if (!root || listview._almdinaNotesClickInstalled) return;
        const handler = event => {
            const target = event.target.closest(".dco-important-note-link, .dco-card-important-note");
            if (!target || !root.contains(target)) return;
            const orderName = String(target.dataset.orderName || "").trim();
            if (!orderName) return;
            event.preventDefault();
            event.stopPropagation();
            openPanel(orderName);
        };
        root.addEventListener("click", handler);
        listview._almdinaNotesClickHandler = handler;
        listview._almdinaNotesClickInstalled = true;
    }

    function installObserver(listview) {
        if (!listview || listview._almdinaNotesObserver || typeof MutationObserver !== "function") return;
        const root = rootNode(listview);
        const result = root && root.querySelector(".result");
        if (!result) return;
        const observer = new MutationObserver(mutations => {
            if (!root.isConnected) {
                disposeRuntime(listview);
                return;
            }
            const relevant = mutations.some(mutation =>
                [...mutation.addedNodes].some(node =>
                    node.nodeType === 1
                    && (node.matches(".list-row-container, .dco-mobile-order-card")
                        || node.querySelector(".list-row-container, .dco-mobile-order-card"))
                )
            );
            if (relevant) schedule(listview);
        });
        observer.observe(result, { childList: true, subtree: true });
        listview._almdinaNotesObserver = observer;
    }

    function installRuntime(listview) {
        if (!listview || listview.doctype !== DOCTYPE) return;
        if (activeListView && activeListView !== listview) disposeRuntime(activeListView);
        activeListView = listview;
        installClickDelegation(listview);
        installObserver(listview);
        schedule(listview);
    }

    function formatter(value, df, doc) {
        const preview = String(value || "").trim();
        if (!preview) return "";
        const orderName = String(doc && doc.name || "").trim();
        const short = preview.length > 58 ? `${preview.slice(0, 57).trim()}…` : preview;
        return `
            <button type="button" class="dco-important-note-link" data-order-name="${escapeHtml(orderName)}" title="${escapeHtml(preview)}" aria-label="فتح الملاحظة المهمة: ${escapeHtml(preview)}">
                <span class="dco-important-note-star" aria-hidden="true">★</span>
                <span class="dco-important-note-text">${escapeHtml(short)}</span>
            </button>
        `;
    }

    frappe.listview_settings = frappe.listview_settings || {};
    const existing = frappe.listview_settings[DOCTYPE] || {};
    const originalOnload = existing.onload;
    const originalRefresh = existing.refresh;
    frappe.listview_settings[DOCTYPE] = Object.assign({}, existing, {
        add_fields: [...new Set([...(existing.add_fields || []), IMPORTANT_FIELD])],
        formatters: Object.assign({}, existing.formatters || {}, {
            [IMPORTANT_FIELD]: formatter,
        }),
        onload(listview) {
            if (typeof originalOnload === "function") originalOnload(listview);
            installRuntime(listview);
        },
        refresh(listview) {
            if (typeof originalRefresh === "function") originalRefresh(listview);
            installRuntime(listview);
        },
    });

    document.addEventListener(UPDATED_EVENT, event => {
        const detail = event && event.detail || {};
        const listview = activeListView;
        const root = rootNode(listview);
        if (!listview || !root || !root.isConnected || listview.doctype !== DOCTYPE) {
            disposeRuntime(listview);
            return;
        }
        const orderName = String(detail.order_name || "").trim();
        const doc = docByName(listview, orderName);
        if (!doc) return;
        doc[IMPORTANT_FIELD] = String(detail.important_note_preview || "");
        schedule(listview);
    });

    if (window.frappe && frappe.router && typeof frappe.router.on === "function") {
        frappe.router.on("change", () => {
            const listview = activeListView;
            if (!listview) return;
            const route = typeof frappe.get_route === "function" ? frappe.get_route() : [];
            const isCurrentList = Array.isArray(route)
                && route[0] === "List"
                && route[1] === DOCTYPE;
            if (!isCurrentList) disposeRuntime(listview);
        });
    }

    window.AlmdinaDcoNotesListIntegration = Object.freeze({
        IMPORTANT_FIELD,
        disposeRuntime,
        ensureImportantColumn,
        formatter,
        reconcileColumns,
        reconcileMobileCards,
    });
})();
