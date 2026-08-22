(() => {
    "use strict";

    const root = window.AlmdinaSpecialShapeDocumentation = window.AlmdinaSpecialShapeDocumentation || Object.create(null);

    function create(documentContract, transform) {
        if (!documentContract || !transform) throw new Error("Element clipboard dependencies are unavailable");
        let copied = null;

        function copy(element) {
            copied = element ? documentContract.clone(element) : null;
            return Boolean(copied);
        }

        function paste(offsetMm = 20) {
            if (!copied) return null;
            const offset = Number.isFinite(Number(offsetMm)) ? Number(offsetMm) : 20;
            const next = transform.translate(documentContract.clone(copied), offset, offset);
            next.id = documentContract.id(next.type || "element");
            copied = documentContract.clone(next);
            return next;
        }

        function clear() { copied = null; }
        function canPaste() { return Boolean(copied); }

        return Object.freeze({ copy, paste, clear, canPaste });
    }

    root.ElementClipboard = Object.freeze({ create });
})();
