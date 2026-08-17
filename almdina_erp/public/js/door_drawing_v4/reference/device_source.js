(() => {
    "use strict";

    const root = window.AlmdinaDoorDrawingReference = window.AlmdinaDoorDrawingReference || Object.create(null);

    function pick() {
        return new Promise(resolve => {
            const input = document.createElement("input");
            input.type = "file";
            input.accept = "image/png,image/jpeg,.png,.jpg,.jpeg";
            input.multiple = false;
            input.style.position = "fixed";
            input.style.left = "-10000px";
            input.style.opacity = "0";

            let settled = false;
            function finish(file) {
                if (settled) return;
                settled = true;
                input.remove();
                resolve(file || null);
            }

            input.addEventListener("change", () => finish(input.files && input.files[0]), { once: true });
            window.addEventListener("focus", () => {
                window.setTimeout(() => {
                    if (!settled && (!input.files || !input.files.length)) finish(null);
                }, 500);
            }, { once: true });

            document.body.appendChild(input);
            input.click();
        });
    }

    root.DeviceSource = Object.freeze({ pick });
})();