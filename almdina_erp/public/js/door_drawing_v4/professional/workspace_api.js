(() => {
    "use strict";
    const root = window.AlmdinaDoorDrawingProfessional = window.AlmdinaDoorDrawingProfessional || Object.create(null);
    const SERVICE = "almdina_erp.almdina_erp.services.special_shape_workspace_service";
    function call(method, args) { return frappe.call({ method: `${SERVICE}.${method}`, args, freeze: false }).then(response => response.message); }
    root.WorkspaceApi = Object.freeze({
        load(orderName, pieceName) { return call("get_drawing_workspace", { order_name: orderName, piece_name: pieceName }); },
        save(orderName, pieceName, drawingJson, geometryJson) { return call("save_drawing_workspace", { order_name: orderName, piece_name: pieceName, drawing_json: drawingJson, geometry_json: geometryJson }); },
    });
})();
