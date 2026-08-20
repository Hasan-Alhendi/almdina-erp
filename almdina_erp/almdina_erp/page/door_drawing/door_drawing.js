(() => {
    "use strict";
    const PAGE_ROUTE = "door-drawing";
    const STYLE = "/assets/almdina_erp/css/special_shape_documentation.css";
    const MODULES = Object.freeze([
        "/assets/almdina_erp/js/special_shape_documentation/domain/document.js",
        "/assets/almdina_erp/js/special_shape_documentation/application/history.js",
        "/assets/almdina_erp/js/special_shape_documentation/application/templates.js",
        "/assets/almdina_erp/js/special_shape_documentation/application/smart_pen.js",
        "/assets/almdina_erp/js/special_shape_documentation/application/element_transform.js",
        "/assets/almdina_erp/js/special_shape_documentation/infrastructure/workspace_api.js",
        "/assets/almdina_erp/js/special_shape_documentation/presentation/canvas_renderer.js",
        "/assets/almdina_erp/js/special_shape_documentation/presentation/workspace_shell.js",
        "/assets/almdina_erp/js/special_shape_documentation/presentation/workspace_controller.js",
    ]);
    function scaffold(wrapper) {
        if (wrapper.querySelector(".layout-main-section")) return;
        frappe.ui.make_app_page({ parent: wrapper, title: __("توثيق الدرفة الخاصة"), single_column: true });
        if (!wrapper.querySelector(".layout-main-section")) throw new Error("Documentation page scaffold is unavailable");
    }
    function ensureStyle() {
        const frontend = window.AlmdinaFrontend;
        return frontend && typeof frontend.ensureStylesheet === "function"
            ? frontend.ensureStylesheet(STYLE, { id: "almdina-special-shape-documentation-css" })
            : frappe.require(STYLE);
    }
    function bootstrap(wrapper) {
        scaffold(wrapper); if (wrapper.__almdinaDocumentationBoot) return wrapper.__almdinaDocumentationBoot;
        const modules = MODULES.reduce((promise, asset) => promise.then(() => frappe.require(asset)), Promise.resolve());
        wrapper.__almdinaDocumentationBoot = Promise.all([ensureStyle(), modules]).catch(error => { wrapper.__almdinaDocumentationBoot = null; throw error; });
        return wrapper.__almdinaDocumentationBoot;
    }
    function controller(wrapper) {
        return bootstrap(wrapper).then(() => {
            if (wrapper.__almdinaDocumentationController) return wrapper.__almdinaDocumentationController;
            const factory = window.AlmdinaSpecialShapeDocumentation && window.AlmdinaSpecialShapeDocumentation.WorkspaceController;
            if (!factory) throw new Error("Documentation workspace did not initialize");
            wrapper.__almdinaDocumentationController = factory.mount(wrapper); return wrapper.__almdinaDocumentationController;
        });
    }
    function route() { const value = frappe.get_route(); return { orderName: String(value[1] || "").trim(), pieceName: String(value[2] || "").trim() }; }
    function fail(wrapper, error) { console.error("Special-shape documentation bootstrap failed", error); scaffold(wrapper); wrapper.querySelector(".layout-main-section").innerHTML = '<div class="ald-doc-message is-error">تعذر تحميل مساحة التوثيق. أعد تحميل الصفحة ثم حاول مرة أخرى.</div>'; }
    function enter() { document.body.classList.add("ald-special-shape-documentation-active"); }
    function leave() { document.body.classList.remove("ald-special-shape-documentation-active"); }
    frappe.pages[PAGE_ROUTE].on_page_load = wrapper => { scaffold(wrapper); $(wrapper).off("hide.aldDocumentation").on("hide.aldDocumentation", () => { leave(); const active = wrapper.__almdinaDocumentationController; if (active) active.suspend(); }); controller(wrapper).catch(error => fail(wrapper, error)); };
    frappe.pages[PAGE_ROUTE].on_page_show = wrapper => { enter(); controller(wrapper).then(active => { const context = route(); if (!context.orderName || !context.pieceName) active.showRouteError("رابط التوثيق غير مكتمل. افتحه من داخل الطلب."); else active.open(context); }).catch(error => { leave(); fail(wrapper, error); }); };
})();
