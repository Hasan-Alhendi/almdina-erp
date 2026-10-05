(() => {
    "use strict";

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
        "تنزيل DXF المرفوع",
        "Download uploaded DXF",
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
    const MOBILE_PRIMARY_LEFT = new Set(["إرسال للإنتاج", "Send to Production"]);
    const MOBILE_PRIMARY_RIGHT = new Set([
        "إلغاء الطلب",
        "Cancel Order",
        "استئناف الطلب",
        "Resume Order",
    ]);
    const ORDER = new Map([
        ["إرسال للإنتاج", 5],
        ["إعادة حساب خطة القص", 10],
        ["إعادة للمسودة", 35],
        ["إرجاع لمرحلة سابقة", 36],
        ["نسخ الطلب", 70],
        ["إلغاء الطلب", 90],
        ["استئناف الطلب", 91],
        ["عرض", 50],
    ]);
    const ASYNC_ACTION_GROUPS = new Set(["صالة الإنتاج"]);

    function documentContext() {
        return window.AlmdinaDocumentContext || null;
    }

    function scheduleFrame(frm, key, callback) {
        const context = documentContext();
        if (context && typeof context.scheduleFrame === "function") {
            return context.scheduleFrame(frm, key, callback);
        }
        return requestAnimationFrame(() => {
            if (window.cur_frm === frm) callback(frm);
        });
    }

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


    function showMeasurementInputHelp() {
        const title = isArabic() ? "تعليمات إدخال القياسات" : "Measurement entry help";
        const message = isArabic()
            ? `
                <div dir="rtl" style="text-align:right;line-height:1.9">
                    <div><b>الإدخال السريع:</b> أدخل العرض ثم <kbd>Tab</kbd>، ثم الطول ثم <kbd>Enter</kbd> لإضافة السطر التالي.</div>
                    <div><b>التنقل:</b> استخدم الأسهم ← ↑ ↓ → للتنقل بين الخلايا.</div>
                    <div><b>القشاط:</b> نقرة على الضلع للتفعيل أو التعطيل، ونقرتان على الضلع لاختيار نوع القشاط.</div>
                    <div><b>التدوير:</b> نقرة واحدة على زر التدوير لتفعيله أو إلغائه.</div>
                    <div><b>القوائم:</b> القوائم قابلة للتمرير عند وجود خيارات إضافية.</div>
                    <div><b>المقاس النهائي:</b> الخصم النهائي يُحسب حسب سماكة القشاط في كل ضلع.</div>
                </div>`
            : `
                <div style="text-align:left;line-height:1.8">
                    <div><b>Fast entry:</b> enter width, press <kbd>Tab</kbd>, enter length, then <kbd>Enter</kbd> for the next row.</div>
                    <div><b>Navigation:</b> use the arrow keys to move between cells.</div>
                    <div><b>Edge banding:</b> click a side to toggle it; double-click a side to choose the edge type.</div>
                    <div><b>Rotation:</b> one click toggles rotation.</div>
                    <div><b>Lists:</b> option lists are scrollable when more choices are available.</div>
                    <div><b>Final size:</b> trim is calculated from the edge thickness on each side.</div>
                </div>`;
        frappe.msgprint({ title, message, indicator: "blue" });
    }

    function ensureMeasurementHelpAction(actions) {
        if (!actions) return;
        let button = actions.querySelector(":scope > .dco-input-help");
        if (!button) {
            button = document.createElement("button");
            button.type = "button";
            button.className = "btn btn-default btn-sm dco-input-help";
            button.textContent = "i";
            actions.appendChild(button);
        }
        const label = isArabic() ? "تعليمات إدخال القياسات" : "Measurement entry help";
        button.title = label;
        button.setAttribute("aria-label", label);
        if (button.dataset.helpBound !== "1") {
            button.dataset.helpBound = "1";
            button.addEventListener("click", event => {
                event.preventDefault();
                event.stopPropagation();
                showMeasurementInputHelp();
            });
        }
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
                if (!child.matches(".dco-print-measurements,.dco-open-measurements-window,.dco-input-help")) {
                    child.remove();
                }
            });
            ensureMeasurementHelpAction(actions);
        }
    }

    function observeMeasurementToolbar(frm) {
        const root = measurementRoot(frm);
        if (!root || !root.isConnected) {
            if (frm._dcoMeasurementToolbarObserver) frm._dcoMeasurementToolbarObserver.disconnect();
            frm._dcoMeasurementToolbarObserver = null;
            frm._dcoMeasurementToolbarObservedRoot = null;
            return;
        }
        if (
            frm._dcoMeasurementToolbarObservedRoot === root
            && frm._dcoMeasurementToolbarObserver
        ) return;
        if (frm._dcoMeasurementToolbarObserver) frm._dcoMeasurementToolbarObserver.disconnect();

        let scheduled = false;
        const observer = new MutationObserver(() => {
            if (scheduled) return;
            scheduled = true;
            scheduleFrame(frm, "measurement-toolbar-observer-frame", () => {
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

    function isSearchAction(node) {
        if (!node || !node.closest(".standard-actions")) return false;
        if (node.querySelector(".icon-search, .es-icon-sm[data-icon='search'], use[href*='search']")) {
            return true;
        }
        if (node.classList.contains("btn-open") && !text(node)) return true;
        const label = text(node);
        return /^(search|بحث)$/i.test(label);
    }

    function reconcileSearchPlacement(head) {
        const section = head && head.querySelector(".standard-items-section");
        const actions = head && head.querySelector(".page-actions");
        const searchBar = head && head.querySelector(".search-bar");
        const standardActions = actions && actions.querySelector(".standard-actions");
        if (!section || !actions || !searchBar || !standardActions) return;

        if (window.innerWidth <= 720) {
            if (searchBar.parentElement !== section) {
                section.insertBefore(searchBar, actions);
            }
            return;
        }

        if (searchBar.parentElement !== standardActions) {
            standardActions.insertBefore(searchBar, standardActions.firstChild);
        }
    }

    function clearMobileActionSlots(actions) {
        if (!actions) return;
        actions.querySelectorAll("[data-dco-mobile-slot]").forEach(node => {
            node.removeAttribute("data-dco-mobile-slot");
        });
        actions.closest(".page-head")?.querySelectorAll(".search-bar[data-dco-mobile-slot]").forEach(node => {
            node.removeAttribute("data-dco-mobile-slot");
        });
        actions.querySelectorAll(
            ".custom-actions > button,.custom-actions > a,.custom-mobile-actions > button,.custom-mobile-actions > a,.standard-actions > button,.standard-actions > .btn,.standard-actions > a,.menu-btn-group > button,.menu-btn-group > .btn"
        ).forEach(node => {
            node.style.removeProperty("--dco-mobile-grid-row");
            node.style.removeProperty("--dco-mobile-grid-col");
        });
    }

    function applyMobileActionSlots(head) {
        const actions = head && head.querySelector(".page-actions");
        if (!actions) return;
        clearMobileActionSlots(actions);
        if (window.innerWidth > 720) return;

        let secondaryIndex = 0;
        const assignSecondary = node => {
            const row = 3 + Math.floor(secondaryIndex / 2);
            const col = secondaryIndex % 2 === 0 ? "1 / 4" : "4 / 7";
            node.setAttribute("data-dco-mobile-slot", "secondary");
            node.style.setProperty("--dco-mobile-grid-row", String(row));
            node.style.setProperty("--dco-mobile-grid-col", col);
            secondaryIndex += 1;
        };

        actions.querySelectorAll(
            ".custom-actions > button,.custom-actions > a,.custom-mobile-actions > button,.custom-mobile-actions > a"
        ).forEach(node => {
            const label = actionLabel(node);
            if (
                node.classList.contains("dco-notes-toolbar-button")
                || label === "الملاحظات"
                || label === "Notes"
            ) {
                node.setAttribute("data-dco-mobile-slot", "utility-notes");
                return;
            }
            if (MOBILE_PRIMARY_LEFT.has(label)) {
                node.setAttribute("data-dco-mobile-slot", "primary-left");
                return;
            }
            if (MOBILE_PRIMARY_RIGHT.has(label)) {
                node.setAttribute("data-dco-mobile-slot", "primary-right");
                return;
            }
            if (label) assignSecondary(node);
        });

        actions.querySelectorAll(".standard-actions > button,.standard-actions > .btn,.standard-actions > a").forEach(node => {
            if (isSearchAction(node)) {
                node.setAttribute("data-dco-mobile-slot", "utility-search");
            }
        });

        actions.querySelectorAll(".menu-btn-group > button,.menu-btn-group > .btn").forEach(node => {
            node.setAttribute("data-dco-mobile-slot", "utility-menu");
        });

        const searchHost = head.querySelector(".search-bar .navbar-modal-search-mobile")
            || head.querySelector(".navbar-modal-search-mobile");
        if (searchHost) {
            const slotTarget = searchHost.closest(".search-bar") || searchHost;
            slotTarget.setAttribute("data-dco-mobile-slot", "utility-search");
        }
    }

    function dedupeButtons(head) {
        const seen = new Map();
        // Frappe owns grouped-action nodes and keeps internal references to them.
        // Removing a group directly from the DOM makes later asynchronous buttons
        // land in a detached node. Only dedupe ungrouped actions here.
        const candidates = [...head.querySelectorAll(
            ".custom-actions > button,.custom-actions > a"
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
            const group = menu.closest(".btn-group,.dropdown");
            if (ASYNC_ACTION_GROUPS.has(actionLabel(group))) return;
            const menuSeen = new Set();
            menu.querySelectorAll(".dropdown-item").forEach(item => {
                const label = text(item);
                if (!label) return;
                if (menuSeen.has(label)) item.remove();
                else menuSeen.add(label);
            });
        });
    }

    function anchorActionsToViewportLeft(head) {
        const actions = head && head.querySelector(".page-actions");
        if (!actions) return;
        if (window.innerWidth < 992) {
            actions.style.removeProperty("--dco-viewport-left-compensation");
            return;
        }

        // The actions container may already span the viewport while its visible
        // buttons remain aligned to the right. Measure the leftmost visible
        // control, not the container, then move the whole row to screen x=16.
        const property = "--dco-viewport-left-compensation";
        const current = Number.parseFloat(actions.style.getPropertyValue(property)) || 0;
        const visibleLefts = [...actions.querySelectorAll("button,a,.btn-group,.dropdown")]
            .filter(node => !node.closest(".dropdown-menu"))
            .map(node => {
                const rect = node.getBoundingClientRect();
                const style = window.getComputedStyle(node);
                return rect.width > 0
                    && rect.height > 0
                    && style.display !== "none"
                    && style.visibility !== "hidden"
                    ? rect.left
                    : null;
            })
            .filter(value => Number.isFinite(value));
        const actualLeft = visibleLefts.length
            ? Math.min(...visibleLefts)
            : actions.getBoundingClientRect().left;
        if (!Number.isFinite(actualLeft)) return;
        const corrected = current + (16 - actualLeft);
        if (Math.abs(corrected - current) > 0.5) {
            actions.style.setProperty(property, `${Math.round(corrected)}px`);
        }
    }

    function reconcile(frm, currentHead = null) {
        reconcileMeasurementToolbar(frm);
        const head = currentHead || (frm && frm._dco_presentation_head);
        if (!head || !head.isConnected) return false;
        removeLegacyButtons(frm, head);
        removeDrawingDxfGroup(head);
        dedupeButtons(head);
        reconcileSearchPlacement(head);
        applyMobileActionSlots(head);
        anchorActionsToViewportLeft(head);
        return true;
    }

    function observe(frm, currentHead = null) {
        observeMeasurementToolbar(frm);
        const head = currentHead || (frm && frm._dco_presentation_head);
        if (!head || !head.isConnected) {
            if (frm._dcoToolbarObserver) frm._dcoToolbarObserver.disconnect();
            frm._dcoToolbarObserver = null;
            frm._dcoToolbarObservedHead = null;
            return;
        }
        if (frm._dcoToolbarObservedHead === head && frm._dcoToolbarObserver) return;
        if (frm._dcoToolbarObserver) frm._dcoToolbarObserver.disconnect();
        let scheduled = false;
        const observer = new MutationObserver(() => {
            const revision = window.AlmdinaOrderRevisionUX;
            if (revision && typeof revision.syncPrimaryAction === "function") {
                // MutationObserver callbacks run before the browser paints. If
                // Frappe recreates its native Save button, restore the one owned
                // by RevisionUX in the same frame.
                revision.syncPrimaryAction(frm);
            }
            if (scheduled) return;
            scheduled = true;
            scheduleFrame(frm, "toolbar-observer-frame", () => {
                scheduled = false;
                reconcile(frm, frm._dco_presentation_head);
            });
        });
        // Only structural changes need reconciliation. Observing our own class/style
        // changes would create a needless feedback loop after every form refresh.
        observer.observe(head, { childList: true, subtree: true });
        frm._dcoToolbarObserver = observer;
        frm._dcoToolbarObservedHead = head;
    }

    function schedule(frm) {
        const head = frm && frm._dco_presentation_head;
        reconcile(frm, head);
        observe(frm, head);
    }

    window.AlmdinaDcoToolbarStabilityUx = Object.freeze({
        recoverPresentation(frm, head) {
            if (!frm || !head || !head.isConnected) return false;
            reconcile(frm, head);
            observe(frm, head);
            return frm._dcoToolbarObservedHead === head && Boolean(frm._dcoToolbarObserver);
        },
        isReady(frm, head) {
            return Boolean(
                frm
                && head
                && head.isConnected
                && frm._dcoToolbarObservedHead === head
                && frm._dcoToolbarObserver
            );
        },
        suspendPresentation(frm) {
            if (!frm) return false;
            ["_dcoToolbarObserver", "_dcoMeasurementToolbarObserver"].forEach(key => {
                if (frm[key] && typeof frm[key].disconnect === "function") frm[key].disconnect();
                frm[key] = null;
            });
            frm._dcoToolbarObservedHead = null;
            frm._dcoMeasurementToolbarObservedRoot = null;
            return true;
        },
    });

    if (typeof window.addEventListener === "function") {
        window.addEventListener("resize", () => {
            const frm = window.cur_frm;
            if (!frm || frm.doctype !== "Door Cutting Order") return;
            scheduleFrame(frm, "toolbar-viewport-anchor", () => reconcile(frm, frm._dco_presentation_head));
        });
    }
})();
