(() => {
    "use strict";
    const root = window.AlmdinaSpecialShapeDocumentation = window.AlmdinaSpecialShapeDocumentation || Object.create(null);
    const SERVICE = "almdina_erp.almdina_erp.services.special_shape_workspace_service";
    function call(method, args) { return frappe.call({ method: `${SERVICE}.${method}`, args, freeze: false }).then(response => response.message); }
    root.WorkspaceApi = Object.freeze({
        load(orderName, pieceName) { return call("get_drawing_workspace", { order_name: orderName, piece_name: pieceName }); },
        save(orderName, pieceName, documentationJson) { return call("save_documentation_workspace", { order_name: orderName, piece_name: pieceName, documentation_json: documentationJson }); },
        upload(orderName, pieceName, fileName, contentBase64) { return call("upload_reference_image", { order_name: orderName, piece_name: pieceName, file_name: fileName, content_base64: contentBase64 }); },
        removeImage(orderName, pieceName, fileUrl) { return call("remove_reference_image", { order_name: orderName, piece_name: pieceName, file_url: fileUrl }); },
    });
})();
