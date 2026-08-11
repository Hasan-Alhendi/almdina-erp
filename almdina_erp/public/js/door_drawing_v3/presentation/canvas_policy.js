(() => {
    "use strict";

    const root = window.AlmdinaDoorDrawingV3 = window.AlmdinaDoorDrawingV3 || Object.create(null);
    const Base = root.ShapeView;
    if (!Base || typeof Base.render !== "function") {
        throw new Error("Door Drawing V3 canvas view must load before canvas policy");
    }

    function removeInlineMeasurements(controller) {
        const canvas = controller && controller.canvas;
        if (!canvas || typeof canvas.querySelectorAll !== "function") return 0;
        const nodes = Array.from(canvas.querySelectorAll(".ddv3-measure"));
        nodes.forEach(node => node.remove());
        return nodes.length;
    }

    function render(controller) {
        const result = Base.render(controller);
        removeInlineMeasurements(controller);
        return result;
    }

    root.ShapeView = Object.freeze({
        ...Base,
        render,
        removeInlineMeasurements,
    });
})();
