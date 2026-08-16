(() => {
    "use strict";

    if (window.AlmdinaPlanContentUX) return;

    const ZERO_MARGIN_EPSILON_MM = 0.001;

    function documentContext() {
        return window.AlmdinaDocumentContext || null;
    }

    function styles() {
        const owner = window.AlmdinaPlanContentStyles;
        if (!owner || typeof owner.install !== "function") {
            throw new Error("AlmdinaPlanContentStyles must load before AlmdinaPlanContentUX");
        }
        return owner;
    }

    function boardPresenter() {
        const presenter = window.AlmdinaPlanBoardPresenter;
        if (
            !presenter
            || typeof presenter.layoutBoardGallery !== "function"
            || typeof presenter.installInteractions !== "function"
        ) {
            throw new Error("AlmdinaPlanBoardPresenter must load before AlmdinaPlanContentUX");
        }
        return presenter;
    }

    function capture(frm) {
        const context = documentContext();
        return context && typeof context.capture === "function"
            ? context.capture(frm)
            : `${frm.doctype || ""}::${frm.doc && frm.doc.name || "__new__"}`;
    }

    function isCurrent(frm, token) {
        const context = documentContext();
        if (context && typeof context.isCurrent === "function") {
            return context.isCurrent(frm, token);
        }
        return Boolean(window.cur_frm === frm);
    }

    function tokenKey(token) {
        if (!token || typeof token !== "object") return String(token || "");
        return `${String(token.identity || "")}::${Number(token.generation || 0)}`;
    }

    function scheduleFrame(frm, key, callback) {
        const context = documentContext();
        if (context && typeof context.scheduleFrame === "function") {
            return context.scheduleFrame(frm, key, callback);
        }
        const token = capture(frm);
        return window.requestAnimationFrame(() => {
            if (isCurrent(frm, token)) callback(frm, token);
        });
    }

    function schedule(frm, key, callback, delay) {
        const context = documentContext();
        if (context && typeof context.schedule === "function") {
            return context.schedule(frm, key, callback, delay);
        }
        const token = capture(frm);
        return window.setTimeout(() => {
            if (isCurrent(frm, token)) callback(frm, token);
        }, delay);
    }

    function sectionElement(frm, fieldname) {
        const field = frm && frm.fields_dict && frm.fields_dict[fieldname];
        if (!field || !field.$wrapper) return $();
        const section = field.$wrapper.closest(".form-section");
        return section.length ? section : field.$wrapper;
    }

    function installStyles() {
        styles().install();
    }

    function applyArabicPlanLabels(frm) {
        const labels = {
            cut_geometry_section: "إعدادات تنفيذ القص",
            optimizer_section: "محرك خطة القص",
            plan_result_section: "نتيجة الخطة الحالية",
            plan_section: "توزيع القطع على الألواح",
            totals_section: "تفاصيل الحساب والتكلفة",
        };
        Object.entries(labels).forEach(([fieldname, label]) => {
            const field = frm.fields_dict[fieldname];
            if (field && field.df && field.df.label !== label) {
                frm.set_df_property(fieldname, "label", label);
            }
        });
    }

    function stabilizePlanActionsLayout(frm) {
        const field = frm && frm.fields_dict && frm.fields_dict.plan_control_actions;
        const section = sectionElement(frm, "plan_actions_section");
        if (!field || !field.$wrapper || !field.$wrapper.length) return;

        // Keep the control inside Frappe's native layout. Moving a ControlHTML
        // wrapper into an ad-hoc row leaves it detached when Frappe repaints a
        // section, while fields_dict still points at the detached node.
        field.$wrapper.addClass("dco-plan-actions-native");
        if (section.length) section.addClass("dco-plan-actions-section");
    }

    function escapeHtml(value) {
        return String(value ?? "")
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;")
            .replace(/'/g, "&#039;");
    }

    function parsePlanSnapshot(frm) {
        if (!frm || !frm.doc) return null;
        const tabs = window.AlmdinaPlanTabsUX;
        const activeTab = frm.__almdina_active_plan_tab;
        if (tabs && activeTab && typeof tabs.getPlanForTab === "function") {
            const active = tabs.getPlanForTab(frm, activeTab);
            if (active && typeof active === "object") return active;
        }
        const raw = frm.doc.system_plan_json || frm.doc.cutting_plan_json;
        if (!raw) return null;
        if (typeof raw === "object") return raw;
        try {
            const parsed = JSON.parse(raw);
            return parsed && typeof parsed === "object" ? parsed : null;
        } catch (error) {
            return null;
        }
    }

    function normalizedMarginNotes(plan) {
        if (!plan || typeof plan !== "object") return [];
        const policy = plan.margin_policy || {};
        const source = Array.isArray(plan.margin_notes)
            ? plan.margin_notes
            : (Array.isArray(policy.notes) ? policy.notes : []);
        return source
            .map(note => String(note || "").trim())
            .filter(Boolean);
    }

    function numericMargin(value) {
        const parsed = Number(value);
        return Number.isFinite(parsed) ? parsed : null;
    }

    function isZeroMargin(value) {
        const numeric = numericMargin(value);
        return numeric !== null && Math.abs(numeric) <= ZERO_MARGIN_EPSILON_MM;
    }

    function zeroMarginEdges(policy) {
        const source = policy || {};
        return [
            ["right", source.right_mm],
            ["left", source.left_mm],
            ["top", source.top_mm],
            ["bottom", source.bottom_mm],
        ]
            .filter(([, value]) => isZeroMargin(value))
            .map(([edge]) => edge);
    }

    function marginPolicySignature(plan, notes) {
        const policy = (plan && plan.margin_policy) || {};
        return JSON.stringify({
            notes,
            left_mm: policy.left_mm,
            right_mm: policy.right_mm,
            top_mm: policy.top_mm,
            bottom_mm: policy.bottom_mm,
        });
    }

    function marginEdgeBadges(policy) {
        const edges = [
            ["يمين", policy.right_mm],
            ["يسار", policy.left_mm],
            ["أعلى", policy.top_mm],
            ["أسفل", policy.bottom_mm],
        ];
        return edges
            .filter(([, value]) => value !== null && value !== undefined && value !== "")
            .map(([label, value]) => {
                const zeroClass = isZeroMargin(value) ? " is-zero" : "";
                return `<span class="dco-margin-policy-alert__edge${zeroClass}">${label}: ${escapeHtml(value)} مم</span>`;
            })
            .join("");
    }

    function buildMarginPolicyAlert(plan, notes, signature) {
        const policy = (plan && plan.margin_policy) || {};
        const zeroEdges = zeroMarginEdges(policy);
        const hasOriginalEdge = zeroEdges.length > 0;
        const summary = hasOriginalEdge
            ? "تم استخدام حافة أصلية من اللوح؛ افحص استقامتها قبل التنفيذ."
            : "تم تخفيض الهامش تلقائيًا بالقدر اللازم للحفاظ على قياسات القطع.";
        const detailNotes = hasOriginalEdge ? notes : [];
        const alert = document.createElement("div");
        alert.className = "dco-margin-policy-alert";
        alert.dataset.marginSignature = signature;
        alert.setAttribute("role", "status");
        alert.setAttribute("aria-live", "polite");
        alert.innerHTML = `
            <span class="dco-margin-policy-alert__icon" aria-hidden="true">⚠</span>
            <div class="dco-margin-policy-alert__body">
                <strong class="dco-margin-policy-alert__title">تنبيه هامش التشذيب</strong>
                <span class="dco-margin-policy-alert__summary">${escapeHtml(summary)}</span>
                ${detailNotes.length ? `<div class="dco-margin-policy-alert__details">${detailNotes.map(note => `<div class="dco-margin-policy-alert__note">${escapeHtml(note)}</div>`).join("")}</div>` : ""}
                <div class="dco-margin-policy-alert__edges">${marginEdgeBadges(policy)}</div>
            </div>
        `;
        return alert;
    }

    function ensureMarginPolicyAlert(planRoot, plan) {
        const existing = planRoot.querySelector(":scope > .dco-margin-policy-alert");
        const notes = normalizedMarginNotes(plan);
        if (!notes.length) {
            if (existing) existing.remove();
            return;
        }

        const signature = marginPolicySignature(plan, notes);
        if (existing && existing.dataset.marginSignature === signature) return;

        const alert = buildMarginPolicyAlert(plan, notes, signature);
        if (existing) {
            existing.replaceWith(alert);
            return;
        }

        const firstSheet = planRoot.querySelector(":scope > .dco-sheet-card");
        const gallery = planRoot.querySelector(":scope > .dco-board-gallery");
        const anchor = firstSheet || gallery;
        if (anchor) {
            planRoot.insertBefore(alert, anchor);
        } else {
            planRoot.appendChild(alert);
        }
    }

    function originalEdgeLabel(edge) {
        const labels = {
            right: "حافة أصلية · يمين",
            left: "حافة أصلية · يسار",
            top: "حافة أصلية · أعلى",
            bottom: "حافة أصلية · أسفل",
        };
        return labels[edge] || "حافة أصلية";
    }

    function buildOriginalEdgeMarker(edge) {
        const marker = document.createElement("span");
        marker.className = `dco-board-original-edge dco-board-original-edge--${edge}`;
        marker.setAttribute("aria-hidden", "true");
        marker.innerHTML = `<span class="dco-board-original-edge__label">${escapeHtml(originalEdgeLabel(edge))}</span>`;
        return marker;
    }

    function ensureOriginalBoardEdges(planRoot, plan) {
        const policy = (plan && plan.margin_policy) || {};
        const edges = zeroMarginEdges(policy);
        const signature = edges.join("|");

        planRoot.querySelectorAll(".dco-sheet-board").forEach(board => {
            if (board.dataset.originalEdgeSignature === signature) return;
            board.querySelectorAll(":scope > .dco-board-original-edge").forEach(marker => marker.remove());
            edges.forEach(edge => board.appendChild(buildOriginalEdgeMarker(edge)));
            board.dataset.originalEdgeSignature = signature;
        });
    }

    function cleanRenderedPlan(frm) {
        const token = capture(frm);
        if (!isCurrent(frm, token)) return false;
        const field = frm.fields_dict.cutting_plan_html;
        if (!field || !field.$wrapper) return false;
        const root = field.$wrapper.get(0);
        if (!root) return false;
        root.dataset.almdinaOrder = String(frm.doc && frm.doc.name || "");

        const plan = parsePlanSnapshot(frm);
        const presenter = boardPresenter();
        root.querySelectorAll(".dco-cutting-plan").forEach(planRoot => {
            const heading = planRoot.querySelector(":scope > h2");
            if (heading) heading.remove();

            planRoot.querySelectorAll(
                ":scope > .dco-plan-header-cards, :scope > .dco-summary-grid, :scope > .dco-piece-groups"
            ).forEach(el => el.remove());

            [...planRoot.children].forEach(child => {
                if (!(child instanceof HTMLElement)) return;
                if (child.classList.contains("dco-sheet-card")) return;
                if (child.classList.contains("dco-board-gallery")) return;
                if (child.classList.contains("dco-special-raw-coverage")) return;
                if (child.classList.contains("dco-margin-policy-alert")) return;
                const text = (child.textContent || "").replace(/\s+/g, " ").trim();
                const isDuplicatedHeader =
                    (text.includes("الطلب:") && (text.includes("الزبون:") || text.includes("اللوح:") || text.includes("الصنف:"))) ||
                    (text.includes("مقاس اللوح الكامل") && text.includes("سماكة القص"));
                const isMethodDuplicate = text.startsWith("طريقة الترتيب:") || text.includes("طريقة الترتيب:");
                if (isDuplicatedHeader || isMethodDuplicate) child.remove();
            });

            ensureMarginPolicyAlert(planRoot, plan);
            presenter.layoutBoardGallery(planRoot);
            ensureOriginalBoardEdges(planRoot, plan);
        });

        root.querySelectorAll(
            ".dco-drawing-plan-panel-host, .dco-drawing-plan-panel"
        ).forEach(el => el.remove());
        presenter.installInteractions(root);
        return true;
    }

    function isReady(frm) {
        const field = frm && frm.fields_dict && frm.fields_dict.cutting_plan_html;
        const root = field && field.$wrapper && field.$wrapper.get(0);
        const orderName = String(frm && frm.doc && frm.doc.name || "");
        if (!root || root.dataset.almdinaOrder !== orderName) return false;
        const planRoots = [...root.querySelectorAll(".dco-cutting-plan")];
        return planRoots.every(planRoot => {
            if (String(planRoot.getAttribute("data-almdina-order") || "") !== orderName) {
                return false;
            }
            const directCards = planRoot.querySelectorAll(":scope > .dco-sheet-card");
            if (directCards.length) return false;
            const cards = planRoot.querySelectorAll(".dco-sheet-card");
            if (cards.length && !planRoot.querySelector(":scope > .dco-board-gallery")) return false;
            return ![...planRoot.children].some(child =>
                String(child.textContent || "").replace(/\s+/g, " ").includes("طريقة الترتيب:")
            );
        });
    }

    function installObserver(frm) {
        const field = frm.fields_dict.cutting_plan_html;
        if (!field || !field.$wrapper) return;
        const root = field.$wrapper.get(0);
        if (!root) return;
        const identity = capture(frm);
        const identityKey = tokenKey(identity);
        if (
            root._dcoPlanContentObserver
            && root._dcoPlanContentObserverIdentity === identityKey
        ) return;
        if (root._dcoPlanContentObserver) root._dcoPlanContentObserver.disconnect();

        let scheduled = false;
        const observer = new MutationObserver(() => {
            if (!isCurrent(frm, identity)) return;
            if (scheduled) return;
            scheduled = true;
            scheduleFrame(frm, "plan-content-observer-frame", () => {
                scheduled = false;
                cleanRenderedPlan(frm);
            });
        });
        observer.observe(root, { childList: true, subtree: true });
        root._dcoPlanContentObserver = observer;
        root._dcoPlanContentObserverIdentity = identityKey;
        const context = documentContext();
        if (context && typeof context.registerObserver === "function") {
            context.registerObserver(frm, "plan-content-observer", observer);
        }
    }

    function installResizeObserver(frm) {
        const field = frm.fields_dict.cutting_plan_html;
        if (!field || !field.$wrapper) return;
        const root = field.$wrapper.get(0);
        if (!root) return;
        const identity = capture(frm);
        const identityKey = tokenKey(identity);
        if (
            root._dcoPlanContentResizeObserver
            && root._dcoPlanContentResizeObserverIdentity === identityKey
        ) return;
        if (root._dcoPlanContentResizeObserver) root._dcoPlanContentResizeObserver.disconnect();

        let scheduled = false;
        const relayout = () => {
            if (!isCurrent(frm, identity)) return;
            if (scheduled) return;
            scheduled = true;
            scheduleFrame(frm, "plan-content-resize-frame", () => {
                scheduled = false;
                root.querySelectorAll(".dco-cutting-plan").forEach(planRoot => {
                    boardPresenter().layoutBoardGallery(planRoot);
                });
            });
        };

        if (typeof ResizeObserver === "function") {
            const observer = new ResizeObserver(relayout);
            observer.observe(root);
            root._dcoPlanContentResizeObserver = observer;
            const context = documentContext();
            if (context && typeof context.registerObserver === "function") {
                context.registerObserver(frm, "plan-content-resize-observer", observer);
            }
        } else {
            window.addEventListener("resize", relayout);
            const fallback = { disconnect() { window.removeEventListener("resize", relayout); } };
            root._dcoPlanContentResizeObserver = fallback;
            const context = documentContext();
            if (context && typeof context.registerObserver === "function") {
                context.registerObserver(frm, "plan-content-resize-observer", fallback);
            }
        }
        root._dcoPlanContentResizeObserverIdentity = identityKey;
    }

    function apply(frm) {
        const identity = capture(frm);
        if (!isCurrent(frm, identity)) return false;
        installStyles();
        applyArabicPlanLabels(frm);
        stabilizePlanActionsLayout(frm);
        cleanRenderedPlan(frm);
        installObserver(frm);
        installResizeObserver(frm);
        scheduleFrame(frm, "plan-content-apply-frame", () => {
            stabilizePlanActionsLayout(frm);
            cleanRenderedPlan(frm);
        });
        schedule(frm, "plan-content-apply-delay", () => {
            stabilizePlanActionsLayout(frm);
            cleanRenderedPlan(frm);
        }, 350);
        return isReady(frm);
    }

    window.AlmdinaPlanContentUX = Object.freeze({
        apply,
        cleanRenderedPlan,
        isReady,
        parsePlanSnapshot,
    });

    frappe.ui.form.on("Door Cutting Order", {
        onload_post_render(frm) { apply(frm); },
        refresh(frm) { apply(frm); },
        cutting_plan_json(frm) { apply(frm); },
        packing_mode(frm) { scheduleFrame(frm, "plan-content-packing-mode", () => stabilizePlanActionsLayout(frm)); },
        optimization_time_limit_sec(frm) { scheduleFrame(frm, "plan-content-optimizer-time", () => stabilizePlanActionsLayout(frm)); },
        refresh_plan_controls(frm) { scheduleFrame(frm, "plan-content-refresh-controls", () => apply(frm)); },
    });

    if (window && typeof window.addEventListener === "function") {
        window.addEventListener("almdina:permissions-updated", () => {
            const frm = window.cur_frm;
            if (frm && frm.doctype === "Door Cutting Order") apply(frm);
        });
    }
})();
