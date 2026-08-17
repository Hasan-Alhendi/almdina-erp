(() => {
    "use strict";

    const PAGE_ROUTE = "door-drawing";
    const STYLESHEETS = Object.freeze([
        Object.freeze({ id: "almdina-door-drawing-professional-css", href: "/assets/almdina_erp/css/door_drawing_professional.css" }),
        Object.freeze({ id: "almdina-door-drawing-professional-page-css", href: "/assets/almdina_erp/css/door_drawing_professional_page.css" }),
    ]);
    const CORE_MODULES = Object.freeze([
        "/assets/almdina_erp/js/door_drawing_v4/domain/geometry.js",
        "/assets/almdina_erp/js/door_drawing_v4/domain/document.js",
        "/assets/almdina_erp/js/door_drawing_v4/domain/dimension.js",
        "/assets/almdina_erp/js/door_drawing_v4/domain/constraint.js",
        "/assets/almdina_erp/js/door_drawing_v4/application/geometry_commands.js",
        "/assets/almdina_erp/js/door_drawing_v4/application/dimension_commands.js",
        "/assets/almdina_erp/js/door_drawing_v4/application/constraint_commands.js",
        "/assets/almdina_erp/js/door_drawing_v4/application/constraint_solver.js",
        "/assets/almdina_erp/js/door_drawing_v4/application/constraint_inference.js",
        "/assets/almdina_erp/js/door_drawing_v4/application/driving_dimension_commands.js",
        "/assets/almdina_erp/js/door_drawing_v4/application/manufacturing_projection.js",
        "/assets/almdina_erp/js/door_drawing_v4/application/snap_resolver.js",
        "/assets/almdina_erp/js/door_drawing_v4/application/stroke_interpreter.js",
        "/assets/almdina_erp/js/door_drawing_v4/application/hit_test.js",
        "/assets/almdina_erp/js/door_drawing_v4/application/command_history.js",
        "/assets/almdina_erp/js/door_drawing_v4/application/tool_state_machine.js",
        "/assets/almdina_erp/js/door_drawing_v4/application/viewport.js",
        "/assets/almdina_erp/js/door_drawing_v4/infrastructure/persistence_adapter.js",
        "/assets/almdina_erp/js/door_drawing_v4/presentation/canvas_renderer.js",
        "/assets/almdina_erp/js/door_drawing_v4/professional/editor_session.js",
        "/assets/almdina_erp/js/door_drawing_v4/professional/keyboard_controller.js",
        "/assets/almdina_erp/js/door_drawing_v4/professional/editor_view_model.js",
        "/assets/almdina_erp/js/door_drawing_v4/professional/selection_overlay.js",
        "/assets/almdina_erp/js/door_drawing_v4/professional/workspace_shell.js",
        "/assets/almdina_erp/js/door_drawing_v4/professional/editor_controller.js",
        "/assets/almdina_erp/js/door_drawing_v4/professional/workspace_api.js",
        "/assets/almdina_erp/js/door_drawing_v4/professional/workspace_controller.js",
    ]);

    function ensurePageScaffold(wrapper) {
        if (wrapper.querySelector(".layout-main-section")) return;
        if (!frappe.ui || typeof frappe.ui.make_app_page !== "function") {
            throw new Error("Frappe page scaffold factory is unavailable");
        }
        frappe.ui.make_app_page({
            parent: wrapper,
            title: __("رسم الدرفة الخاصة"),
            single_column: true,
        });
        if (!wrapper.querySelector(".layout-main-section")) {
            throw new Error("Door drawing page scaffold did not create a main section");
        }
    }

    function ensureStyles() {
        const frontend = window.AlmdinaFrontend;
        if (frontend && typeof frontend.ensureStylesheet === "function") {
            return Promise.all(STYLESHEETS.map(item => frontend.ensureStylesheet(item.href, { id: item.id })));
        }
        return Promise.all(STYLESHEETS.map(item => Promise.resolve(frappe.require(item.href))));
    }

    function bootstrap(wrapper) {
        ensurePageScaffold(wrapper);
        if (wrapper.__almdinaDoorDrawingProfessionalPromise) return wrapper.__almdinaDoorDrawingProfessionalPromise;
        wrapper.classList.add("ald-prof-page");
        const modulePromise = CORE_MODULES.reduce(
            (promise, asset) => promise.then(() => Promise.resolve(frappe.require(asset))),
            Promise.resolve()
        );
        wrapper.__almdinaDoorDrawingProfessionalPromise = Promise.all([ensureStyles(), modulePromise]).catch(error => {
            wrapper.__almdinaDoorDrawingProfessionalPromise = null;
            throw error;
        });
        return wrapper.__almdinaDoorDrawingProfessionalPromise;
    }

    function routeContext() {
        const route = frappe.get_route();
        return Object.freeze({
            orderName: String(route[1] || "").trim(),
            pieceName: String(route[2] || "").trim(),
        });
    }

    function showBootstrapError(wrapper, error) {
        console.error("Door Drawing workspace bootstrap failed", error);
        let main = wrapper.querySelector(".layout-main-section");
        if (!main) {
            try {
                ensurePageScaffold(wrapper);
                main = wrapper.querySelector(".layout-main-section");
            } catch (scaffoldError) {
                console.error("Door Drawing page scaffold failed", scaffoldError);
            }
        }
        if (main) {
            main.innerHTML = '<div class="ald-prof-fatal">تعذر تحميل مساحة الرسم. أعد تحميل الصفحة ثم حاول مرة أخرى.</div>';
        }
    }

    function ensureController(wrapper) {
        ensurePageScaffold(wrapper);
        return bootstrap(wrapper).then(() => {
            if (wrapper.__almdinaDoorDrawingController) return wrapper.__almdinaDoorDrawingController;
            const factory = window.AlmdinaDoorDrawingProfessional && window.AlmdinaDoorDrawingProfessional.WorkspaceController;
            if (!factory || typeof factory.mount !== "function") throw new Error("Professional drawing workspace did not initialize");
            wrapper.__almdinaDoorDrawingController = factory.mount(wrapper);
            return wrapper.__almdinaDoorDrawingController;
        });
    }

    function enterFullscreenMode() {
        document.body.classList.add("ald-professional-drawing-active");
    }

    function leaveFullscreenMode() {
        document.body.classList.remove("ald-professional-drawing-active");
    }

    function bindLifecycle(wrapper) {
        if (wrapper.__almdinaDoorDrawingLifecycleBound) return;
        wrapper.__almdinaDoorDrawingLifecycleBound = true;
        $(wrapper)
            .off("hide.aldProfessionalDoorDrawing")
            .on("hide.aldProfessionalDoorDrawing", () => {
                leaveFullscreenMode();
                const controller = wrapper.__almdinaDoorDrawingController;
                if (controller && typeof controller.suspend === "function") controller.suspend();
            });
    }

    frappe.pages[PAGE_ROUTE].on_page_load = function (wrapper) {
        try {
            ensurePageScaffold(wrapper);
            bindLifecycle(wrapper);
            ensureController(wrapper).catch(error => showBootstrapError(wrapper, error));
        } catch (error) {
            showBootstrapError(wrapper, error);
        }
    };

    frappe.pages[PAGE_ROUTE].on_page_show = function (wrapper) {
        try {
            ensurePageScaffold(wrapper);
            enterFullscreenMode();
            bindLifecycle(wrapper);
        } catch (error) {
            leaveFullscreenMode();
            showBootstrapError(wrapper, error);
            return;
        }
        ensureController(wrapper).then(controller => {
            const context = routeContext();
            if (!context.orderName || !context.pieceName) {
                controller.showRouteError("رابط الرسم غير مكتمل. افتح الرسم من داخل الطلب.");
                return;
            }
            controller.open(context);
        }).catch(error => {
            leaveFullscreenMode();
            showBootstrapError(wrapper, error);
        });
    };
})();
