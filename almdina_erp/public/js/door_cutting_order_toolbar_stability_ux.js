(() => {
    "use strict";

    const STYLE_ID = "dco-toolbar-stability-css";
    const REMOVE_LABELS = new Set([
        "إلغاء تخصيص قشاط الدرف",
        "إلغاء تخصيص قشاط الدرفة",
        "إلغاء تخصيص القشاط",
        "طباعة جدول القياسات",
        "طباعة القياسات",
        "Reset Piece Edge Customization",
        "Reset Edge Customization",
    ]);
    const ORDER = new Map([
        ["إعادة حساب خطة القص", 10],
        ["طباعة خطة القص", 20],
        ["تصدير DXF لأوتوكاد", 30],
        ["تصدير DXF", 30],
        ["دورة الطلب", 40],
        ["عرض", 50],
        ["المخزون", 60],
    ]);

    function text(node) {
        return String(node && node.textContent || "")
            .replace(/[\u200e\u200f]/g, "")
            .replace(/\s+/g, " ")
            .trim();
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
                flex:0 0 auto!important;
                margin:0!important;
            }
            .page-head.dco-stable-actions-head .custom-actions .btn {
                white-space:nowrap!important;
                visibility:visible!important;
                opacity:1!important;
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

    function removeLegacyButtons(frm, head) {
        REMOVE_LABELS.forEach(label => {
            try { frm.remove_custom_button(label); } catch (error) { /* button may not exist */ }
        });
        head.querySelectorAll(".page-actions button,.page-actions a,.page-actions .dropdown-item").forEach(node => {
            if (REMOVE_LABELS.has(text(node))) {
                const group = node.closest(".btn-group,.dropdown");
                if (node.matches(".dropdown-item") && group) node.remove();
                else (group && text(group) === text(node) ? group : node).remove();
            }
        });
    }

    function dedupeButtons(head) {
        const seen = new Map();
        const candidates = [...head.querySelectorAll(
            ".custom-actions > button,.custom-actions > a,.custom-actions > .btn-group,.custom-actions > .dropdown"
        )];
        candidates.forEach(node => {
            const label = text(node);
            if (!label) return;
            if (seen.has(label)) {
                node.remove();
                return;
            }
            seen.set(label, node);
            const order = ORDER.get(label);
            if (order !== undefined) node.style.order = String(order);
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
        const head = pageHead(frm);
        if (!head) return;
        head.classList.add("dco-stable-actions-head");
        removeLegacyButtons(frm, head);
        dedupeButtons(head);
        removeEmptyGroups(head);
    }

    function observe(frm) {
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
        observer.observe(head, { childList: true, subtree: true, attributes: true, attributeFilter: ["class", "style"] });
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
