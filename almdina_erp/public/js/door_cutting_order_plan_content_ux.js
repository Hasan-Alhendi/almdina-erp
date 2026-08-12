(() => {
    "use strict";

    const STYLE_ID = "dco-plan-content-layout-css-v2";

    function isArabic() {
        const lang = String(
            (frappe.boot && frappe.boot.lang) ||
            (frappe.boot && frappe.boot.user && frappe.boot.user.language) ||
            document.documentElement.lang ||
            ""
        ).toLowerCase();
        return lang === "ar" || lang.startsWith("ar-");
    }

    function sectionElement(frm, fieldname) {
        const field = frm && frm.fields_dict && frm.fields_dict[fieldname];
        if (!field || !field.$wrapper) return $();
        const section = field.$wrapper.closest(".form-section");
        return section.length ? section : field.$wrapper;
    }

    function installStyles() {
        if (document.getElementById(STYLE_ID)) return;
        const style = document.createElement("style");
        style.id = STYLE_ID;
        style.textContent = `
            .dco-optimizer-card > .section-body,
            .dco-optimizer-card .section-body:first-of-type {
                display:flex !important;
                flex-wrap:wrap !important;
                align-items:flex-start !important;
            }
            .dco-plan-action-row {
                flex:0 0 100% !important;
                width:100% !important;
                max-width:100% !important;
                padding:2px 15px 0 !important;
                margin-top:2px !important;
            }
            .dco-plan-action-row > [data-fieldname="plan_control_actions"],
            .dco-plan-action-row > .frappe-control {
                width:100% !important;
                max-width:none !important;
                margin-bottom:0 !important;
            }
            [data-fieldname="plan_control_actions"] .dco-plan-actions-shell {
                margin:0 !important;
                padding:14px !important;
                border:1px solid var(--border-color,#dfe3e8) !important;
                border-radius:14px !important;
                background:linear-gradient(180deg,rgba(248,250,252,.92),rgba(248,250,252,.55)) !important;
                box-shadow:none !important;
            }
            [data-fieldname="plan_control_actions"] .dco-plan-actions-title {
                display:flex !important;
                align-items:center !important;
                justify-content:space-between !important;
                gap:12px !important;
                margin-bottom:11px !important;
            }
            [data-fieldname="plan_control_actions"] .dco-plan-actions-title strong {
                font-size:13px !important;
                font-weight:900 !important;
            }
            [data-fieldname="plan_control_actions"] .dco-plan-mode-hint {
                max-width:620px;
                padding:5px 9px;
                border-radius:999px;
                background:var(--card-bg,#fff);
                border:1px solid var(--border-color,#e2e8f0);
                font-size:10px !important;
                line-height:1.45 !important;
                color:var(--text-muted,#66717e);
            }
            [data-fieldname="plan_control_actions"] .dco-plan-actions {
                display:grid !important;
                grid-template-columns:repeat(2,minmax(190px,1fr)) !important;
                gap:9px !important;
                width:100% !important;
            }
            [data-fieldname="plan_control_actions"] .dco-plan-actions > .btn {
                width:100% !important;
                min-width:0 !important;
                min-height:42px !important;
                margin:0 !important;
                border-radius:10px !important;
                font-weight:850 !important;
            }
            [data-fieldname="plan_control_actions"] .dco-plan-document-actions {
                display:flex !important;
                align-items:center !important;
                gap:8px !important;
                flex-wrap:wrap !important;
                margin-top:11px !important;
                padding-top:11px !important;
                border-top:1px dashed var(--border-color,#dfe3e8) !important;
            }
            [data-fieldname="plan_control_actions"] .dco-plan-document-actions .btn {
                min-height:36px !important;
                border-radius:9px !important;
                font-weight:800 !important;
                margin:0 !important;
            }
            [data-fieldname="plan_control_actions"] .dco-plan-note {
                margin-top:10px !important;
                padding-top:9px !important;
                border-top:1px dashed var(--border-color,#dfe3e8) !important;
                color:var(--text-muted,#66717e);
            }
            [data-fieldname="cutting_plan_html"] .dco-plan-tabs {
                width:max-content;
                max-width:100%;
                display:flex !important;
                align-items:center !important;
                gap:4px !important;
                padding:4px !important;
                margin:0 0 12px auto !important;
                border:1px solid var(--border-color,#dfe3e8);
                border-radius:11px;
                background:var(--subtle-fg,#f6f8fa);
            }
            [data-fieldname="cutting_plan_html"] .dco-plan-tabs .btn {
                min-height:34px !important;
                border-radius:8px !important;
                border-color:transparent !important;
                box-shadow:none !important;
                font-weight:800 !important;
            }
            [data-fieldname="cutting_plan_html"] .dco-plan-tab-content > .dco-cutting-plan {
                margin-top:0 !important;
                padding-top:0 !important;
            }
            [data-fieldname="cutting_plan_html"] .dco-special-raw-coverage {
                margin-top:0 !important;
            }
            @media (max-width:760px) {
                .dco-plan-action-row { padding-inline:8px !important; }
                [data-fieldname="plan_control_actions"] .dco-plan-actions {
                    grid-template-columns:1fr !important;
                }
                [data-fieldname="plan_control_actions"] .dco-plan-actions-title {
                    align-items:flex-start !important;
                    flex-direction:column !important;
                }
                [data-fieldname="plan_control_actions"] .dco-plan-mode-hint {
                    max-width:100% !important;
                    border-radius:9px !important;
                }
                [data-fieldname="plan_control_actions"] .dco-plan-document-actions .btn {
                    flex:1 1 180px;
                }
                [data-fieldname="cutting_plan_html"] .dco-plan-tabs {
                    width:100%;
                    margin-inline:0 !important;
                }
                [data-fieldname="cutting_plan_html"] .dco-plan-tabs .btn {
                    flex:1 1 0;
                    min-width:0;
                }
            }
            @media (max-width:520px) {
                [data-fieldname="plan_control_actions"] .dco-plan-document-actions .btn {
                    flex:1 1 100%;
                    width:100%;
                }
                [data-fieldname="cutting_plan_html"] .dco-plan-tabs {
                    align-items:stretch !important;
                    flex-direction:column !important;
                }
            }
        `;
        document.head.appendChild(style);
    }

    function localizePlanSections(frm) {
        if (!isArabic()) return;
        const labels = {
            cut_geometry_section: "إعدادات تنفيذ القص",
            optimizer_section: "محرك خطة القص",
            plan_result_section: "نتيجة الخطة الحالية",
            plan_section: "توزيع القطع على الألواح",
            totals_section: "تفاصيل الحساب والتكلفة",
        };
        Object.entries(labels).forEach(([fieldname, label]) => {
            if (frm.fields_dict[fieldname]) frm.set_df_property(fieldname, "label", label);
        });
    }

    function movePlanActionsToFullWidth(frm) {
        const field = frm && frm.fields_dict && frm.fields_dict.plan_control_actions;
        const section = sectionElement(frm, "optimizer_section");
        if (!field || !field.$wrapper || !field.$wrapper.length || !section.length) return;

        const body = section.find(".section-body").first();
        if (!body.length) return;

        let host = body.children(".dco-plan-action-row").first();
        if (!host.length) {
            host = $('<div class="dco-plan-action-row"></div>');
            body.append(host);
        }
        const wrapper = field.$wrapper.get(0);
        if (wrapper && !host.get(0).contains(wrapper)) {
            host.append(field.$wrapper);
        }
    }

    function cleanRenderedPlan(frm) {
        const field = frm.fields_dict.cutting_plan_html;
        if (!field || !field.$wrapper) return;
        const root = field.$wrapper.get(0);
        if (!root) return;

        root.querySelectorAll(".dco-cutting-plan").forEach(planRoot => {
            const heading = planRoot.querySelector(":scope > h2");
            if (heading) heading.remove();

            planRoot.querySelectorAll(
                ":scope > .dco-plan-header-cards, :scope > .dco-summary-grid, :scope > .dco-piece-groups"
            ).forEach(el => el.remove());

            [...planRoot.children].forEach(child => {
                if (!(child instanceof HTMLElement)) return;
                if (child.classList.contains("dco-sheet-card")) return;
                if (child.classList.contains("dco-special-raw-coverage")) return;
                const text = (child.textContent || "").replace(/\s+/g, " ").trim();
                const isDuplicatedHeader =
                    (text.includes("الطلب:") && (text.includes("الزبون:") || text.includes("اللوح:") || text.includes("الصنف:"))) ||
                    (text.includes("مقاس اللوح الكامل") && text.includes("سماكة القص"));
                const isMethodDuplicate = text.startsWith("طريقة الترتيب:") || text.includes("طريقة الترتيب:");
                if (isDuplicatedHeader || isMethodDuplicate) child.remove();
            });
        });

        // The normal order form already has one authoritative optimizer/control
        // surface above the board layout. The DrawingPlan panel remains available
        // in shop-floor/inbox contexts where that form surface does not exist.
        root.querySelectorAll(
            ".dco-drawing-plan-panel-host, .dco-drawing-plan-panel"
        ).forEach(el => el.remove());
    }

    function installObserver(frm) {
        const field = frm.fields_dict.cutting_plan_html;
        if (!field || !field.$wrapper) return;
        const root = field.$wrapper.get(0);
        if (!root || root._dcoPlanContentObserver) return;

        let scheduled = false;
        const observer = new MutationObserver(() => {
            if (scheduled) return;
            scheduled = true;
            requestAnimationFrame(() => {
                scheduled = false;
                cleanRenderedPlan(frm);
            });
        });
        observer.observe(root, { childList: true, subtree: true });
        root._dcoPlanContentObserver = observer;
    }

    function apply(frm) {
        installStyles();
        localizePlanSections(frm);
        movePlanActionsToFullWidth(frm);
        cleanRenderedPlan(frm);
        installObserver(frm);
        requestAnimationFrame(() => {
            movePlanActionsToFullWidth(frm);
            cleanRenderedPlan(frm);
        });
        window.setTimeout(() => {
            movePlanActionsToFullWidth(frm);
            cleanRenderedPlan(frm);
        }, 350);
    }

    frappe.ui.form.on("Door Cutting Order", {
        onload_post_render(frm) { apply(frm); },
        refresh(frm) { apply(frm); },
        cutting_plan_json(frm) { apply(frm); },
        packing_mode(frm) { requestAnimationFrame(() => movePlanActionsToFullWidth(frm)); },
        optimization_time_limit_sec(frm) { requestAnimationFrame(() => movePlanActionsToFullWidth(frm)); },
        refresh_plan_controls(frm) { requestAnimationFrame(() => apply(frm)); },
    });

    if (window && typeof window.addEventListener === "function") {
        window.addEventListener("almdina:permissions-updated", () => {
            const frm = window.cur_frm;
            if (frm && frm.doctype === "Door Cutting Order") apply(frm);
        });
    }
})();
