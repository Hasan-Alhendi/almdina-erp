(() => {
    "use strict";

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
        "/assets/almdina_erp/js/door_drawing_v4/application/hit_test.js",
        "/assets/almdina_erp/js/door_drawing_v4/application/command_history.js",
        "/assets/almdina_erp/js/door_drawing_v4/application/tool_state_machine.js",
        "/assets/almdina_erp/js/door_drawing_v4/application/viewport.js",
        "/assets/almdina_erp/js/door_drawing_v4/infrastructure/persistence_adapter.js",
        "/assets/almdina_erp/js/door_drawing_v4/presentation/canvas_renderer.js",
        "/assets/almdina_erp/js/door_drawing_v4/professional/editor_session.js",
        "/assets/almdina_erp/js/door_drawing_v4/professional/keyboard_controller.js",
        "/assets/almdina_erp/js/door_drawing_v4/professional/workspace_shell.js",
        "/assets/almdina_erp/js/door_drawing_v4/professional/editor_controller.js",
        "/assets/almdina_erp/js/door_drawing_v4/professional/workspace_api.js",
        "/assets/almdina_erp/js/door_drawing_v4/professional/workspace_controller.js"
    ]);
    const STYLESHEET = "/assets/almdina_erp/css/door_drawing_professional.css";

    function bootstrap(wrapper) {
        if (wrapper.__almdinaDoorDrawingProfessionalPromise) return wrapper.__almdinaDoorDrawingProfessionalPromise;
        wrapper.classList.add("ald-prof-page");
        const frontend = window.AlmdinaFrontend;
        const stylePromise = frontend && typeof frontend.ensureStylesheet === "function"
            ? frontend.ensureStylesheet(STYLESHEET, { id: "almdina-door-drawing-professional-css" })
            : Promise.resolve(frappe.require(STYLESHEET));
        const modulePromise = CORE_MODULES.reduce(
            (promise, asset) => promise.then(() => Promise.resolve(frappe.require(asset))),
            Promise.resolve()
        );
        wrapper.__almdinaDoorDrawingProfessionalPromise = Promise.all([stylePromise, modulePromise]);
        return wrapper.__almdinaDoorDrawingProfessionalPromise;
    }

    function routeContext() {
        const route = frappe.get_route();
        return Object.freeze({
            orderName: String(route[1] || "").trim(),
            pieceName: String(route[2] || "").trim(),
        });
    }

    frappe.pages["door-drawing"].on_page_load = function (wrapper) {
        bootstrap(wrapper).then(() => {
            const controller = window.AlmdinaDoorDrawingProfessional && window.AlmdinaDoorDrawingProfessional.WorkspaceController;
            if (!controller || typeof controller.mount !== "function") throw new Error("Professional drawing workspace did not initialize");
            wrapper.__almdinaDoorDrawingController = controller.mount(wrapper);
        }).catch(error => {
            console.error("Door Drawing workspace bootstrap failed", error);
            const main = wrapper.querySelector(".layout-main-section");
            if (main) main.innerHTML = '<div class="ald-prof-fatal">تعذر تحميل مساحة الرسم. أعد تحميل الصفحة ثم حاول مرة أخرى.</div>';
        });
    };

    frappe.pages["door-drawing"].on_page_show = function (wrapper) {
        bootstrap(wrapper).then(() => {
            const controller = wrapper.__almdinaDoorDrawingController;
            if (!controller) return;
            const context = routeContext();
            if (!context.orderName || !context.pieceName) {
                controller.showRouteError("رابط الرسم غير مكتمل. افتح الرسم من داخل الطلب.");
                return;
            }
            controller.open(context);
        });
    };

    frappe.pages["door-drawing"].on_page_hide = function (wrapper) {
        const controller = wrapper.__almdinaDoorDrawingController;
        if (controller && typeof controller.suspend === "function") controller.suspend();
    };
})();
