(() => {
    "use strict";
    const PAGE_ROUTE = "door-drawing";
    const STYLE = "/assets/almdina_erp/css/special_shape_documentation.css";
    const ASSET_ROOT = "/assets/almdina_erp/js/special_shape_documentation";
    const MODULES = Object.freeze([
        `${ASSET_ROOT}/domain/reference_crop.js`,
        `${ASSET_ROOT}/domain/document.js`,
        `${ASSET_ROOT}/application/history.js`,
        `${ASSET_ROOT}/application/templates.js`,
        `${ASSET_ROOT}/application/smart_pen.js`,
        `${ASSET_ROOT}/application/element_transform.js`,
        `${ASSET_ROOT}/application/element_clipboard.js`,
        `${ASSET_ROOT}/application/keyboard_shortcuts.js`,
        `${ASSET_ROOT}/infrastructure/workspace_api.js`,
        `${ASSET_ROOT}/infrastructure/scanner_bridge.js`,
        `${ASSET_ROOT}/presentation/canvas_viewport.js`,
        `${ASSET_ROOT}/presentation/canvas_renderer.js`,
        `${ASSET_ROOT}/presentation/workspace_shell.js`,
        `${ASSET_ROOT}/presentation/workspace_controller.js`,
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
    function renderBootState(wrapper) {
        if (wrapper.__almdinaDocumentationController) return;
        const main = wrapper.querySelector(".layout-main-section");
        if (!main || main.querySelector(".ald-doc-boot")) return;
        main.innerHTML = `<style>
            .ald-doc-boot{min-height:70vh;display:grid;place-items:center;padding:32px;background:#f3f5f8;color:#172033}
            .ald-doc-boot-card{width:min(420px,90vw);padding:28px;border:1px solid #e5e9f1;border-radius:18px;background:#fff;box-shadow:0 18px 50px rgba(15,23,42,.08);text-align:center}
            .ald-doc-boot-spinner{width:42px;height:42px;margin:0 auto 16px;border:4px solid #dbe7ff;border-top-color:#0b5fff;border-radius:50%;animation:ald-doc-boot-spin .8s linear infinite}
            .ald-doc-boot strong{display:block;font-size:18px}.ald-doc-boot span{display:block;margin-top:7px;color:#667085;font-size:13px}
            @keyframes ald-doc-boot-spin{to{transform:rotate(360deg)}}@media(prefers-reduced-motion:reduce){.ald-doc-boot-spinner{animation:none}}
        </style><div class="ald-doc-boot" role="status" aria-live="polite">
            <div class="ald-doc-boot-card">
                <div class="ald-doc-boot-spinner" aria-hidden="true"></div>
                <strong>جار فتح توثيق الدرفة…</strong>
                <span>نجهّز الصورة وأدوات الرسم</span>
            </div>
        </div>`;
    }
    function loadModules() {
        return Promise.all(MODULES.map(asset => frappe.require(asset)));
    }
    function bootstrap(wrapper) {
        scaffold(wrapper); if (wrapper.__almdinaDocumentationBoot) return wrapper.__almdinaDocumentationBoot;
        renderBootState(wrapper);
        wrapper.__almdinaDocumentationBoot = Promise.all([ensureStyle(), loadModules()]).catch(error => { wrapper.__almdinaDocumentationBoot = null; throw error; });
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
