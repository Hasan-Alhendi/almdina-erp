(() => {
    "use strict";
    const root = window.AlmdinaDoorDrawingProfessional = window.AlmdinaDoorDrawingProfessional || Object.create(null);
    const DRAWING_SERVICE = "almdina_erp.almdina_erp.services.special_shape_workspace_service";
    const REFERENCE_SERVICE = "almdina_erp.almdina_erp.services.special_shape_reference_image_service";
    function call(service, method, args) { return frappe.call({ method: `${service}.${method}`, args, freeze: false }).then(response => response.message); }
    root.WorkspaceApi = Object.freeze({
        load(orderName, pieceName) { return call(DRAWING_SERVICE, "get_drawing_workspace", { order_name: orderName, piece_name: pieceName }); },
        save(orderName, pieceName, drawingJson, geometryJson) { return call(DRAWING_SERVICE, "save_drawing_workspace", { order_name: orderName, piece_name: pieceName, drawing_json: drawingJson, geometry_json: geometryJson }); },
        loadReferenceImage(orderName, pieceName) { return call(REFERENCE_SERVICE, "get_reference_image", { order_name: orderName, piece_name: pieceName }); },
        saveReferenceImage(orderName, pieceName, imageDataUrl, metadataJson) { return call(REFERENCE_SERVICE, "save_reference_image", { order_name: orderName, piece_name: pieceName, image_data_url: imageDataUrl, metadata_json: metadataJson }); },
        removeReferenceImage(orderName, pieceName) { return call(REFERENCE_SERVICE, "remove_reference_image", { order_name: orderName, piece_name: pieceName }); },
    });
})();
