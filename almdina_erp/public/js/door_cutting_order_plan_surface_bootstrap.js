(() => {
    "use strict";

    if (window.AlmdinaCuttingPlanSurfaceBootstrap) return;

    const DOCTYPE = "Door Cutting Order";
    const RECOVERY_DELAY_MS = 120;
    const MODULES = Object.freeze([
        Object.freeze({
            global: "AlmdinaCuttingPlanRender",
            asset: "/assets/almdina_erp/js/door_cutting_order_cutting_plan_renderer.js",
        }),
        Object.freeze({
            global: "AlmdinaDoorCuttingPlanUX",
            asset: "/assets/almdina_erp/js/door_cutting_order_plan_ux.js",
        }),
        Object.freeze({
            global: "AlmdinaPlanControlsUX",
            asset: "/assets/almdina_erp/js/door_cutting_order_plan_controls_ux.js",
        }),
        Object.freeze({
            global: "AlmdinaPlanTabsUX",
            asset: "/assets/almdina_erp/js/door_cutting_order_plan_tabs_ux.js",
        }),
        Object.freeze({
            global: "AlmdinaPlanContentUX",
            asset: "/assets/almdina_erp/js/door_cutting_order_plan_content_ux.js",
        }),
    ]);

    let modulePromise = null;

    function isOrderForm(frm) {
        return Boolean(frm && frm.doctype === DOCTYPE && frm.doc);
    }

    function permissions() {
        return window.AlmdinaPermissions || null;
    }

    function canViewPlan(frm) {
        const api = permissions();
        if (!api) return false;
        if (typeof api.canDocument === "function") {
            return Boolean(api.canDocument(frm, "view_cutting_plan"));
        }
        return typeof api.can === "function" && Boolean(api.can("view_cutting_plan"));
    }

    function documentIdentity(frm) {
        const context = window.AlmdinaDocumentContext;
        if (context && typeof context.capture === "function") {
            return context.capture(frm);
        }
        return `${frm.doctype || ""}::${frm.doc && frm.doc.name || "__new__"}`;
    }

    function isCurrent(frm, identity) {
        const context = window.AlmdinaDocumentContext;
        if (context && typeof context.isCurrent === "function") {
            return context.isCurrent(frm, identity);
        }
        return Boolean(window.cur_frm === frm && documentIdentity(frm) === identity);
    }

    function wrapper(frm, fieldname) {
        const field = frm && frm.fields_dict && frm.fields_dict[fieldname];
        return field && field.$wrapper ? field.$wrapper : null;
    }

    function clearProtectedSurface(frm) {
        const actions = wrapper(frm, "plan_control_actions");
        const layout = wrapper(frm, "cutting_plan_html");
        if (actions) actions.empty();
        if (layout) layout.empty();
    }

    function wrapperNode(target) {
        if (!target) return null;
        return target.nodeType ? target : (target[0] || null);
    }

    function wrapperAttached(frm, target) {
        const node = wrapperNode(target);
        const root = frm && wrapperNode(frm.wrapper);
        if (!node || !root || typeof root.contains !== "function") return true;
        return root.contains(node);
    }

    function reattachActionField(frm, field) {
        if (!field || !field.$wrapper || wrapperAttached(frm, field.$wrapper)) return;
        const section = wrapper(frm, "plan_actions_section");
        if (!section || typeof section.find !== "function") return;
        const body = section.find(".section-body").first();
        if (body.length && typeof body.append === "function") {
            body.append(field.$wrapper);
        }
    }

    function restoreProtectedFieldAccess(frm) {
        ["plan_control_actions", "cutting_plan_html"].forEach(fieldname => {
            const field = frm && frm.fields_dict && frm.fields_dict[fieldname];
            if (!field || !field.$wrapper) return;

            // These HTML containers carry no business data. Authorization is
            // enforced by canViewPlan plus the per-command capabilities; stale
            // site metadata must not leave an authorized container hidden.
            if (field.df) {
                field.df.permlevel = 0;
                field.df.hidden = 0;
                field.df.hidden_due_to_dependency = 0;
            }
            if (typeof field.refresh === "function") field.refresh();
            if (typeof field.$wrapper.removeClass === "function") {
                field.$wrapper.removeClass("hide-control");
            }
            if (typeof field.$wrapper.show === "function") field.$wrapper.show();
            if (fieldname === "plan_control_actions") reattachActionField(frm, field);
        });
    }

    function setWrapperOrder(target, orderName) {
        if (!target) return;
        if (typeof target.attr === "function") {
            target.attr("data-almdina-order", orderName);
            return;
        }
        const node = target.nodeType ? target : (target[0] || null);
        if (node && node.dataset) node.dataset.almdinaOrder = orderName;
    }

    function wrapperOrder(target) {
        if (!target) return "";
        if (typeof target.attr === "function") {
            return String(target.attr("data-almdina-order") || "");
        }
        const node = target.nodeType ? target : (target[0] || null);
        return String(node && node.dataset && node.dataset.almdinaOrder || "");
    }

    function surfaceReady(frm) {
        const actions = wrapper(frm, "plan_control_actions");
        const layout = wrapper(frm, "cutting_plan_html");
        const orderName = String(frm && frm.doc && frm.doc.name || "");
        const content = window.AlmdinaPlanContentUX;
        return Boolean(
            actions
            && layout
            && wrapperAttached(frm, actions)
            && wrapperAttached(frm, layout)
            && wrapperOrder(actions) === orderName
            && wrapperOrder(layout) === orderName
            && actions.find(".dco-plan-actions-shell").length
            && layout.find(".dco-plan-tab-content").length
            && layout.children().length
            && content
            && typeof content.isReady === "function"
            && content.isReady(frm)
        );
    }

    async function ensureModules() {
        if (MODULES.every(module => Boolean(window[module.global]))) return true;
        if (modulePromise) return modulePromise;

        modulePromise = (async () => {
            for (const module of MODULES) {
                if (window[module.global]) continue;
                await frappe.require(module.asset);
                if (!window[module.global]) {
                    throw new Error(`Cutting-plan module did not initialize: ${module.global}`);
                }
            }
            return true;
        })().finally(() => {
            modulePromise = null;
        });

        return modulePromise;
    }

    async function renderSurface(frm) {
        const identity = documentIdentity(frm);
        const presenter = window.AlmdinaDoorCuttingPlanUX;
        const controls = window.AlmdinaPlanControlsUX;
        const tabs = window.AlmdinaPlanTabsUX;
        const content = window.AlmdinaPlanContentUX;

        if (!presenter || typeof presenter.refresh !== "function") {
            throw new Error("AlmdinaDoorCuttingPlanUX.refresh is unavailable");
        }
        if (!tabs || typeof tabs.afterRender !== "function") {
            throw new Error("AlmdinaPlanTabsUX.afterRender is unavailable");
        }
        if (!content || typeof content.apply !== "function") {
            throw new Error("AlmdinaPlanContentUX.apply is unavailable");
        }

        restoreProtectedFieldAccess(frm);
        await Promise.resolve(presenter.refresh(frm));
        if (!isCurrent(frm, identity)) return false;
        setWrapperOrder(wrapper(frm, "plan_control_actions"), String(frm.doc.name || ""));
        if (controls && typeof controls.apply === "function") {
            controls.apply(frm);
        }
        const tabsShown = tabs.afterRender(frm);
        if (!tabsShown) {
            // Keep plan commands visible even when no plan-tab grant is active.
            const layout = wrapper(frm, "cutting_plan_html");
            if (layout && !layout.children().length) {
                layout.html(
                    `<div class="dco-plan-tab-content" style="padding:16px;color:#666;text-align:center;border:1px dashed #ccd3da;border-radius:12px;background:#fafafa;">${__(
                        "لا توجد صلاحية لعرض تبويبات خطة القص."
                    )}</div>`
                );
            }
        }
        setWrapperOrder(wrapper(frm, "cutting_plan_html"), String(frm.doc.name || ""));
        content.apply(frm);
        return surfaceReady(frm);
    }

    async function recover(frm) {
        if (!isOrderForm(frm)) return false;
        const identity = documentIdentity(frm);

        if (!canViewPlan(frm)) {
            clearProtectedSurface(frm);
            return false;
        }

        await ensureModules();
        if (!isCurrent(frm, identity)) return false;

        restoreProtectedFieldAccess(frm);
        const ready = await renderSurface(frm);
        if (!isCurrent(frm, identity)) return false;
        if (!ready) {
            throw new Error("Cutting-plan surface remained empty after recovery");
        }
        return true;
    }

    function schedule(frm) {
        if (!isOrderForm(frm)) return;
        if (frm.__almdinaPlanSurfaceTimer) {
            window.clearTimeout(frm.__almdinaPlanSurfaceTimer);
        }
        frm.__almdinaPlanSurfaceTimer = window.setTimeout(() => {
            frm.__almdinaPlanSurfaceTimer = null;
            recover(frm).catch(error => {
                console.error("Failed to recover Almdina cutting-plan surface", error);
            });
        }, RECOVERY_DELAY_MS);
    }

    frappe.ui.form.on(DOCTYPE, {
        onload_post_render(frm) { schedule(frm); },
        refresh(frm) { schedule(frm); },
        almdina_edit_session_changed(frm) { schedule(frm); },
    });

    window.addEventListener("almdina:permissions-updated", () => {
        schedule(window.cur_frm);
    });

    window.AlmdinaCuttingPlanSurfaceBootstrap = Object.freeze({
        canViewPlan,
        ensureModules,
        recover,
        renderSurface,
        restoreProtectedFieldAccess,
        schedule,
        surfaceReady,
    });

    const documentContext = window.AlmdinaDocumentContext;
    if (documentContext && typeof documentContext.registerSurface === "function") {
        documentContext.registerSurface("cutting-plan", {
            isReady(frm) {
                if (!isOrderForm(frm) || !canViewPlan(frm)) return true;
                return surfaceReady(frm);
            },
            recover(frm) { return recover(frm); },
        });
    }

    // This file can be lazy-loaded after the current Form refresh already ran.
    // Recover the active order immediately instead of waiting for another event.
    window.setTimeout(() => schedule(window.cur_frm), 0);
})();
