(() => {
    "use strict";

    const root = window.AlmdinaDoorDrawingWorkspace = window.AlmdinaDoorDrawingWorkspace || Object.create(null);

    function call(method, args, options = {}) {
        if (!window.frappe || typeof frappe.call !== "function") {
            return Promise.reject(new Error("Frappe RPC is not available"));
        }
        return frappe.call({
            method,
            args,
            freeze: Boolean(options.freeze),
            freeze_message: options.freezeMessage,
        }).then(response => response && response.message ? response.message : {});
    }

    function load(orderName, pieceName) {
        return call(
            "almdina_erp.almdina_erp.services.special_shape_workspace_service.get_drawing_workspace",
            { order_name: orderName, piece_name: pieceName }
        );
    }

    function save(orderName, pieceName, drawingJson, geometryJson) {
        return call(
            "almdina_erp.almdina_erp.services.special_shape_workspace_service.save_drawing_workspace",
            {
                order_name: orderName,
                piece_name: pieceName,
                drawing_json: drawingJson,
                geometry_json: geometryJson,
            },
            { freeze: true, freezeMessage: "يتم حفظ الرسم…" }
        );
    }

    function saveReferenceImage(orderName, pieceName, imageDataUrl, metadata) {
        return call(
            "almdina_erp.almdina_erp.services.special_shape_workspace_service.save_reference_image",
            {
                order_name: orderName,
                piece_name: pieceName,
                image_data_url: imageDataUrl,
                metadata_json: metadata,
            },
            { freeze: true, freezeMessage: "يتم حفظ صورة الدرفة…" }
        );
    }

    function removeReferenceImage(orderName, pieceName) {
        return call(
            "almdina_erp.almdina_erp.services.special_shape_workspace_service.remove_reference_image",
            { order_name: orderName, piece_name: pieceName },
            { freeze: true, freezeMessage: "يتم حذف صورة الدرفة…" }
        );
    }

    root.Api = Object.freeze({
        load,
        save,
        saveReferenceImage,
        removeReferenceImage,
    });
})();