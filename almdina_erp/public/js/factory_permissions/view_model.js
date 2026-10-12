(() => {
    "use strict";

    if (window.AlmdinaFactoryPermissionsViewModel) return;

    function unique(values) {
        return [...new Set((values || []).map(value => String(value || "")).filter(Boolean))];
    }

    function create(options = {}) {
        const translate = typeof options.translate === "function" ? options.translate : value => String(value || "");

        function t(message, replacements) {
            return replacements ? translate(message, replacements) : translate(message);
        }

        function completeCatalog(catalog, working) {
            const groups = (catalog || []).map(group => ({
                ...group,
                capabilities: Array.isArray(group.capabilities) ? group.capabilities.slice() : [],
            }));
            const presented = new Set(
                groups.flatMap(group => group.capabilities.map(item => String(item.key || "")).filter(Boolean))
            );
            const missing = Object.keys(working || {}).filter(key => !presented.has(key));
            if (missing.length) {
                groups.push({
                    key: "unclassified",
                    label: t("Other permissions"),
                    description: t("Permissions that exist on the server but were not categorized in the management interface. They appear here automatically so that no assignable permission is hidden."),
                    capabilities: missing.sort().map(key => ({
                        key,
                        label: key,
                        description: t("System permission registered in the role matrix."),
                        risk: "normal",
                        standard: false,
                        permission_type: key,
                    })),
                });
            }
            return groups.filter(group => group.capabilities.length);
        }

        function capabilityKeys(catalog, working) {
            return unique(completeCatalog(catalog, working).flatMap(group => (
                group.capabilities.map(item => item.key)
            )));
        }

        function groupCapabilityKeys(catalog, working, groupKey) {
            const group = completeCatalog(catalog, working).find(item => (
                String(item.key || "") === String(groupKey || "")
            ));
            return group ? unique(group.capabilities.map(item => item.key)) : [];
        }

        function roleMenu(roles, query, selectedRole) {
            const needle = String(query || "").trim().toLowerCase();
            return (roles || [])
                .filter(role => !needle || String(role.name || "").toLowerCase().includes(needle))
                .map(role => ({
                    name: String(role.name || ""),
                    deskAccess: Boolean(role.desk_access),
                    selected: String(role.name || "") === String(selectedRole || ""),
                }));
        }

        function permissionBadge(capability) {
            if (!capability.standard) return null;
            const labels = {
                read: t("Read + select"),
                create: t("Create"),
                write: t("Edit"),
                delete: t("Delete"),
            };
            const permissionType = String(capability.permission_type || "");
            const permission = labels[permissionType] || permissionType;
            return { kind: "permission", label: t("Frappe: {0}", [permission]) };
        }

        function capabilityModel(capability, working) {
            const badges = [];
            const permission = permissionBadge(capability);
            if (permission) badges.push(permission);
            if (capability.standard) badges.push({ kind: "standard", label: t("Core Frappe permission") });
            if (capability.risk === "critical") badges.push({ kind: "critical", label: t("Critical") });
            else if (capability.risk === "sensitive") badges.push({ kind: "sensitive", label: t("Sensitive") });
            return {
                key: String(capability.key || ""),
                label: String(capability.label || ""),
                description: String(capability.description || ""),
                checked: working && working[capability.key] === true,
                badges,
            };
        }

        function permissionGroups(catalog, working) {
            return completeCatalog(catalog, working).map(group => ({
                key: String(group.key || ""),
                label: String(group.label || ""),
                description: String(group.description || ""),
                count: group.capabilities.length,
                capabilities: group.capabilities.map(item => capabilityModel(item, working)),
            }));
        }

        function bulkControls(catalog, working) {
            const groups = completeCatalog(catalog, working).map(group => {
                const keys = unique(group.capabilities.map(item => item.key));
                return {
                    key: String(group.key || ""),
                    allEnabled: keys.length > 0 && keys.every(key => working && working[key] === true),
                };
            });
            const keys = capabilityKeys(catalog, working);
            return {
                groups,
                globalAllEnabled: keys.length > 0 && keys.every(key => working && working[key] === true),
            };
        }

        function stats(catalog, working, changes) {
            const keys = capabilityKeys(catalog, working);
            const criticalKeys = new Set(
                completeCatalog(catalog, working)
                    .flatMap(group => group.capabilities || [])
                    .filter(item => item.risk === "critical")
                    .map(item => item.key)
            );
            return {
                total: keys.length,
                enabled: keys.filter(key => working && working[key] === true).length,
                critical: keys.filter(key => working && working[key] === true && criticalKeys.has(key)).length,
                changes: Array.isArray(changes) ? changes.length : 0,
            };
        }

        function impact(data) {
            const resolved = data || {};
            const impactData = resolved.impact || {};
            const navigation = impactData.navigation || {};
            const changes = Array.isArray(resolved.changes) ? resolved.changes : [];
            const sections = navigation.sections || {};
            const sectionLabels = {
                orders: t("Orders"),
                costing: t("Cost"),
                planning: t("Cutting plan"),
                drawing: t("Drawing"),
                production: t("Production"),
                quality: t("Quality"),
                workforce: t("Users"),
                factory_settings: t("Settings"),
                master_data: t("Basic data"),
                administration: t("Administration"),
                reports: t("Reports"),
            };
            const home = navigation.home_page === "shop-floor-inbox"
                ? t("Production floor")
                : navigation.home_page === "almdina-erp"
                    ? t("Almdina main interface")
                    : t("Does not change the home page");
            const source = resolved.source
                ? resolved.source.kind === "import"
                    ? t("Source: JSON file from role {0}", [String(resolved.source.role || "")])
                    : t("External preview source")
                : "";
            return {
                home,
                workspaces: Array.isArray(navigation.workspaces) ? navigation.workspaces.map(String) : [],
                sections: Object.keys(sections)
                    .filter(key => sections[key] === true)
                    .map(key => sectionLabels[key] || key),
                warning: resolved.requires_self_lockout_confirmation
                    ? t("This change removes your last permission to manage permissions. After saving you may not be able to return to the page.")
                    : "",
                source,
                changes: changes.slice(0, 12).map(change => ({
                    label: String(change.label || change.key || ""),
                    action: change.after ? t("Grant") : t("Cancel"),
                })),
            };
        }

        function audit(rows) {
            return (Array.isArray(rows) ? rows : []).slice(0, 10).map(row => ({
                changedBy: String(row.changed_by || ""),
                changedOn: String(row.changed_on || ""),
                changedCapabilities: String(row.changed_capabilities || ""),
            }));
        }

        return Object.freeze({
            completeCatalog,
            capabilityKeys,
            groupCapabilityKeys,
            roleMenu,
            permissionGroups,
            bulkControls,
            stats,
            impact,
            audit,
        });
    }

    window.AlmdinaFactoryPermissionsViewModel = Object.freeze({ create });
})();
