(() => {
    "use strict";

    if (window.AlmdinaCuttingPlanSurfaceBootstrap) return;

    const DOCTYPE = "Door Cutting Order";
    const RECOVERY_DELAY_MS = 120;
    const MODULES = Object.freeze([
        Object.freeze({
            global: "AlmdinaCuttingPlanRender",
            asset: "/assets/almdina_erp/js/door_cutting_order/cutting_plan/door_cutting_order_cutting_plan_renderer.js",
        }),
        Object.freeze({
            global: "AlmdinaDoorCuttingPlanUX",
            asset: "/assets/almdina_erp/js/door_cutting_order/cutting_plan/door_cutting_order_plan_ux.js",
        }),
        Object.freeze({
            global: "AlmdinaPlanControlsUX",
            asset: "/assets/almdina_erp/js/door_cutting_order/cutting_plan/door_cutting_order_plan_controls_ux.js",
        }),
        Object.freeze({
            global: "AlmdinaPlanTabsUX",
            asset: "/assets/almdina_erp/js/door_cutting_order/cutting_plan/door_cutting_order_plan_tabs_ux.js",
        }),
        Object.freeze({
            global: "AlmdinaPlanContentUX",
            asset: "/assets/almdina_erp/js/door_cutting_order/cutting_plan/door_cutting_order_plan_content_ux.js",
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

    function workspaceActive(frm) {
        const coordinator = window.AlmdinaWorkspaceSyncCoordinator;
        if (coordinator && typeof coordinator.isActive === "function") {
            return coordinator.isActive(frm, "plan");
        }
        const fieldname = String(
            frm
            && frm.layout
            && frm.layout.current_tab
            && frm.layout.current_tab.df
            && frm.layout.current_tab.df.fieldname
            || ""
        );
        return fieldname === "results_tab";
    }

    function permissionVersion() {
        const api = permissions();
        return api && typeof api.version === "function" ? Number(api.version() || 0) : 0;
    }

    function surfaceSignature(frm) {
        const doc = frm && frm.doc || {};
        return [
            doc.name || "",
            doc.modified || "",
            doc.status || "",
            doc.packing_mode || "",
            doc.optimization_time_limit_sec || "",
            doc.calculated_plan_input_hash || "",
            doc.calculated_plan_metadata_hash || "",
            doc.approved_plan_source || "",
            Number(doc.plan_needs_recalculation || 0),
            String(doc.cutting_plan_json || "").length,
            String(doc.system_plan_json || "").length,
            String(doc.custom_plan_json || "").length,
            permissionVersion(),
        ].join("::");
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
            let metadataChanged = false;
            if (field.df) {
                if (Number(field.df.permlevel || 0) !== 0) {
                    field.df.permlevel = 0;
                    metadataChanged = true;
                }
                if (Number(field.df.hidden || 0) !== 0) {
                    field.df.hidden = 0;
                    metadataChanged = true;
                }
                if (Number(field.df.hidden_due_to_dependency || 0) !== 0) {
                    field.df.hidden_due_to_dependency = 0;
                    metadataChanged = true;
                }
            }
            // Refreshing an HTML field destroys its children. Only do it when
            // stale metadata actually changed; ordinary permission/settle passes
            // must preserve the already-rendered plan and command controls.
            if (metadataChanged && typeof field.refresh === "function") field.refresh();
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
        const ready = surfaceReady(frm);
        if (ready) frm.__almdinaPlanSurfaceSignature = surfaceSignature(frm);
        return ready;
    }

    async function recover(frm) {
        if (!isOrderForm(frm)) return false;
        // The Plan surface is intentionally lazy. Hidden workspaces must not
        // compete with Order Entry for CPU, module loading, or server reads.
        if (!workspaceActive(frm)) return true;
        const identity = documentIdentity(frm);

        if (!canViewPlan(frm)) {
            // Do not erase a valid surface while the capability matrix is still
            // loading. A resolved denial may clear it once, without a later flash.
            if (permissionVersion() <= 0) return false;
            clearProtectedSurface(frm);
            return false;
        }

        const signature = surfaceSignature(frm);
        if (
            frm.__almdinaPlanSurfaceSignature === signature
            && surfaceReady(frm)
        ) {
            return true;
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
            frm.__almdinaPlanSurfaceTimer = null;
        }
        if (!workspaceActive(frm)) return;
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

    window.addEventListener("almdina:workspace-activated", (event) => {
        const detail = event && event.detail || {};
        const names = Array.isArray(detail.resources) ? detail.resources : [];
        if (!names.includes("plan")) return;
        schedule(detail.frm || window.cur_frm);
    });

    window.AlmdinaCuttingPlanSurfaceBootstrap = Object.freeze({
        canViewPlan,
        workspaceActive,
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
                if (!isOrderForm(frm) || !canViewPlan(frm) || !workspaceActive(frm)) return true;
                return surfaceReady(frm);
            },
            recover(frm) { return recover(frm); },
        });
    }

    // This file can be lazy-loaded after the current Form refresh already ran.
    // Recover only when Plan is the active workspace; hidden tabs are intentionally
    // excluded from the initial Order Entry critical path.
    window.setTimeout(() => schedule(window.cur_frm), 0);
})();