(() => {
    "use strict";

    if (window.AlmdinaFactoryProductionSettingsCatalogLabels) return;

    // Same stable-ID → English message-ID map as the cutting-plan editor.
    // Legacy catalog rows may still send Arabic labels; resolve only known IDs.
    const CATALOG_MESSAGE_IDS = Object.freeze({
        optimization_catalog: Object.freeze({
            auto: "Automatic",
            auto_pro: "Auto Pro (recommended)",
            deep_search: "Deep Search",
            optimal: "Optimal Search",
            maxrects: "MaxRects",
            guillotine: "Guillotine",
            shelf: "Shelf packing",
            skyline: "Skyline",
            cp_sat_ortools: "Constraint programming — CP-SAT",
            mip_cbc: "Mixed-integer programming — CBC",
            scip: "SCIP solver",
            highs: "HiGHS solver",
            gecode: "Gecode constraint solver",
            chuffed: "Chuffed constraint solver",
            genetic: "Genetic algorithm",
            simulated_annealing: "Simulated annealing",
        }),
        machine_type_catalog: Object.freeze({
            Auto: "Automatic",
            "CNC Router": "CNC Router",
            "Panel Saw": "Panel Saw",
        }),
    });

    function messageId(catalogName, entryId) {
        const catalog = CATALOG_MESSAGE_IDS[catalogName];
        const key = String(entryId == null ? "" : entryId).trim();
        return catalog && catalog[key] ? catalog[key] : "";
    }

    function resolveLabel(catalogName, entryId, rawLabel, translate) {
        const id = String(entryId == null ? "" : entryId).trim();
        const mid = messageId(catalogName, id);
        if (mid) {
            return typeof translate === "function" ? translate(mid) : mid;
        }
        const raw = String(rawLabel == null ? "" : rawLabel).trim();
        return raw || id;
    }

    function localizeEntry(catalogName, entry, translate) {
        const id = String(entry && entry.id || "").trim();
        const rawLabel = String((entry && entry.label) || id || "").trim();
        return {
            id,
            label: resolveLabel(catalogName, id, rawLabel, translate),
            available: !(entry && entry.available === false),
            messageId: messageId(catalogName, id) || "",
            rawLabel,
        };
    }

    window.AlmdinaFactoryProductionSettingsCatalogLabels = Object.freeze({
        CATALOG_MESSAGE_IDS,
        messageId,
        resolveLabel,
        localizeEntry,
    });
})();
