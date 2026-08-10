(() => {
    "use strict";

    const STYLE_ID = "dco-toolbar-stability-css";
    const REMOVE_LABELS = new Set([
        "إلغاء تخصيص قشاط الدرف",
        "إلغاء تخصيص قشاط الدرفة",
        "إلغاء تخصيص القشاط",
        "طباعة جدول القياسات",
        "طباعة القياسات",
        "طباعة خطة القص",
        "طباعة فاتورة الزبون",
        "Print Customer Invoice",
        "تصدير DXF لأوتوكاد",
        "Export DXF for AutoCAD",
        "تصدير DXF",
        "Export DXF",
        "تصدير DXF للرسم",
        "تصدير DXF للتعديل",
        "تنزيل DXF للإنتاج",
        "رفع ملف DXF",
        "استبدال ملف DXF",
        "اعتماد الرسم",
        "إعادة اعتماد الرسم",
        "Reset Piece Edge Customization",
        "Reset Edge Customization",
    ]);
    const ORDER = new Map([
        ["إعادة حساب خطة القص", 10],
        ["دورة الطلب", 40],
        ["عرض", 50],
    ]);

    function text(node) {
        return String(node && node.textContent || "")
            .replace(/[\u200e\u200f]/g, "")
            .replace(/\s+/g, " ")
            .trim();
    }

    function actionLabel(node) {
        if (!node) return "";
        if (node.matches("button,a")) return text(node);
        const trigger = node.querySelector(":scope > button, :scope > a");
        return text(trigger || node);
    }

    function domNode(value) {
        if (!value) return null;
        return value.nodeType ? value : (value[0] && value[0].nodeType ? value[0] : null);
    }

    function pageHead(frm) {
        const wrapper = domNode(frm && frm.wrapper);
        const page = wrapper && (wrapper.closest(".page-container") || wrapper.closest(".desk-page"));
        return (page && page.querySelector(".page-head")) || document.querySelector(".page-head");
    }

    function measurementRoot(frm) {
        const field = frm && frm.fields_dict && frm.fields_dict.pieces_fast_entry;
        return field && field.$wrapper ? field.$wrapper.get(0) : null;
    }

    function isArabic() {
        const lang = String(
            (frappe.boot && frappe.boot.lang) ||
            (frappe.boot && frappe.boot.user && frappe.boot.user.language) ||
            document.documentElement.lang ||
            ""
        ).toLowerCase();
        return lang === "ar" || lang.startsWith("ar-");
    }

    function installStyles() {
        if (document.getElementById(STYLE_ID)) return;
        const style = document.createElement("style");
        style.id = STYLE_ID;
        style.textContent = `
            .page-head.dco-stable-actions-head,
            .page-head.dco-stable-actions-head .page-head-content,
            .page-head.dco-stable-actions-head .page-actions {
                height:auto!important;
                max-height:none!important;
                overflow:visible!important;
            }
            .page-head.dco-stable-actions-head .page-actions,
            .page-head.dco-stable-actions-head .custom-actions,
            .page-head.dco-stable-actions-head .standard-actions {
                display:flex!important;
                visibility:visible!important;
                opacity:1!important;
                flex-wrap:wrap!important;
                align-items:center!important;
                gap:6px!important;
            }
            .page-head.dco-stable-actions-head .custom-actions > .btn,
            .page-head.dco-stable-actions-head .custom-actions > .btn-group,
            .page-head.dco-stable-actions-head .custom-actions > .dropdown {
                display:inline-flex!important;
                visibility:visible!important;
                opacity:1!important;
                flex:0 0 auto!important;
                margin:0!important;
            }
            .page-head.dco-stable-actions-head .custom-actions .btn {
                display:inline-flex!important;
                align-items:center!important;
                white-space:nowrap!important;
                visibility:visible!important;
                opacity:1!important;
            }

            /* Measurement toolbar contract: title + print + separate-window only. */
            .dco-fast-entry-toolbar > :not(.dco-fast-help):not(.dco-measurement-table-actions) {
                display:none!important;
            }
            .dco-fast-entry-toolbar .dco-fast-help > :not(.dco-measurement-title) {
                display:none!important;
            }

            @media(max-width:1200px){
                .page-head.dco-stable-actions-head .page-actions {
                    max-height:none!important;
                    overflow:visible!important;
                    padding-bottom:4px!important;
                }
            }
        `;
        document.head.appendChild(style);
    }

    function reconcileMeasurementToolbar(frm) {
        const root = measurementRoot(frm);
        const toolbar = root && root.querySelector(".dco-fast-entry-toolbar");
        if (!toolbar) return;

        const help = toolbar.querySelector(":scope > .dco-fast-help");
        const actions = toolbar.querySelector(":scope > .dco-measurement-table-actions");
        const titleText = isArabic() ? "جدول قياسات الدرف" : "Door Measurements Table";

        if (help) {
            const title = help.querySelector(":scope > .dco-measurement-title");
            const isExactTitle = help.children.length === 1
                && title
                && text(title) === titleText;
            if (!isExactTitle) {
                help.innerHTML = `<b class="dco-measurement-title">${titleText}</b>`;
            }
        }

        [...toolbar.children].forEach(child => {
            if (child !== help && child !== actions) child.remove();
        });

        if (actions) {
            [...actions.children].forEach(child => {
                if (!child.matches(".dco-print-measurements,.dco-open-measurements-window")) {
                    child.remove();
                }
            });
        }
    }

    function observeMeasurementToolbar(frm) {
        const root = measurementRoot(frm);
        if (!root || frm._dcoMeasurementToolbarObservedRoot === root) return;
        if (frm._dcoMeasurementToolbarObserver) frm._dcoMeasurementToolbarObserver.disconnect();

        let scheduled = false;
        const observer = new MutationObserver(() => {
            if (scheduled) return;
            scheduled = true;
            requestAnimationFrame(() => {
                scheduled = false;
                reconcileMeasurementToolbar(frm);
            });
        });
        observer.observe(root, { childList: true, subtree: true });
        frm._dcoMeasurementToolbarObserver = observer;
        frm._dcoMeasurementToolbarObservedRoot = root;
    }

    function removeLegacyButtons(frm, head) {
        REMOVE_LABELS.forEach(label => {
            try { frm.remove_custom_button(label); } catch (error) { /* button may not exist */ }
            try { frm.remove_custom_button(label, __("الرسم / DXF")); } catch (error) { /* optional group */ }
            try { frm.remove_custom_button(label, __("دورة الطلب")); } catch (error) { /* optional group */ }
            try { frm.remove_custom_button(label, __("طباعة")); } catch (error) { /* optional group */ }
        });
        head.querySelectorAll(".page-actions button,.page-actions a,.page-actions .dropdown-item").forEach(node => {
            const label = text(node);
            const isPlanPrint = label === "طباعة خطة القص" || /^print\s*cutting\s*plan$/i.test(label);
            const isDxfExport = /تصدير\s*DXF/i.test(label) || /^export\s*dxf/i.test(label);
            const isCustomerInvoicePrint = label === "طباعة فاتورة الزبون" || /^print\s*customer\s*invoice$/i.test(label);
            if (REMOVE_LABELS.has(label) || isPlanPrint || isDxfExport || isCustomerInvoicePrint) {
                const group = node.closest(".btn-group,.dropdown");
                if (node.matches(".dropdown-item") && group) node.remove();
                else (group && actionLabel(group) === text(node) ? group : node).remove();
            }
        });
    }

    function removeDrawingDxfGroup(head) {
        head.querySelectorAll(".custom-actions > .btn-group,.custom-actions > .dropdown").forEach(group => {
            const label = actionLabel(group);
            if (label === "الرسم / DXF" || /^drawing\s*\/\s*dxf$/i.test(label)) {
                group.remove();
            }
        });
    }

    function dedupeButtons(head) {
        const seen = new Map();
        const candidates = [...head.querySelectorAll(
            ".custom-actions > button,.custom-actions > a,.custom-actions > .btn-group,.custom-actions > .dropdown"
        )];
        candidates.forEach(node => {
            const label = actionLabel(node);
            if (!label) return;
            if (seen.has(label)) {
                node.remove();
                return;
            }
            seen.set(label, node);
            const order = ORDER.get(label);
            if (order !== undefined && node.style.order !== String(order)) {
                node.style.order = String(order);
            }
        });

        head.querySelectorAll(".dropdown-menu").forEach(menu => {
            const menuSeen = new Set();
            menu.querySelectorAll(".dropdown-item").forEach(item => {
                const label = text(item);
                if (!label) return;
                if (menuSeen.has(label)) item.remove();
                else menuSeen.add(label);
            });
        });
    }

    function removeEmptyGroups(head) {
        head.querySelectorAll(".custom-actions .btn-group,.custom-actions .dropdown").forEach(group => {
            const menu = group.querySelector(".dropdown-menu");
            if (menu && !menu.querySelector(".dropdown-item")) group.remove();
        });
    }

    function reconcile(frm) {
        installStyles();
        reconcileMeasurementToolbar(frm);
        const head = pageHead(frm);
        if (!head) return;
        if (!head.classList.contains("dco-stable-actions-head")) {
            head.classList.add("dco-stable-actions-head");
        }
        removeLegacyButtons(frm, head);
        removeDrawingDxfGroup(head);
        dedupeButtons(head);
        removeEmptyGroups(head);
    }

    function observe(frm) {
        observeMeasurementToolbar(frm);
        const head = pageHead(frm);
        if (!head || frm._dcoToolbarObservedHead === head) return;
        if (frm._dcoToolbarObserver) frm._dcoToolbarObserver.disconnect();
        let scheduled = false;
        const observer = new MutationObserver(() => {
            if (scheduled) return;
            scheduled = true;
            requestAnimationFrame(() => {
                scheduled = false;
                reconcile(frm);
            });
        });
        // Only structural changes need reconciliation. Observing our own class/style
        // changes would create a needless feedback loop after every form refresh.
        observer.observe(head, { childList: true, subtree: true });
        frm._dcoToolbarObserver = observer;
        frm._dcoToolbarObservedHead = head;
    }

    function schedule(frm) {
        reconcile(frm);
        observe(frm);
        [0, 80, 250, 650, 1200].forEach(delay => setTimeout(() => {
            reconcile(frm);
            observe(frm);
        }, delay));
    }

    frappe.ui.form.on("Door Cutting Order", {
        onload_post_render(frm) { schedule(frm); },
        refresh(frm) { schedule(frm); },
    });
})();
