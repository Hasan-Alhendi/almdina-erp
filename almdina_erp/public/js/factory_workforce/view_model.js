(() => {
    "use strict";

    if (window.AlmdinaFactoryWorkforceViewModel) return;

    function create(options = {}) {
        const translate = options.translate;
        if (typeof translate !== "function") {
            throw new Error("Factory workforce view-model translator is unavailable");
        }
        const t = (message, replacements) => replacements ? translate(message, replacements) : translate(message);

        function can(data, capability) {
            return Boolean(data && data.permissions && data.permissions[capability] === true);
        }

        function actionAllowed(user, action) {
            return Boolean(
                user
                && user.actions
                && user.actions[action]
                && user.actions[action].allowed === true
            );
        }

        function findUser(users, email) {
            return (users || []).find(user => user && user.email === email) || null;
        }

        function normalizeRoute(value) {
            const route = String(value || "").trim();
            if (!route || /^https?:\/\//.test(route) || route.startsWith("/")) return route;
            return `/${route}`;
        }

        function roleHomePolicy(roles, selectedRoles = []) {
            const catalog = new Map((roles || []).map(role => [String(role && role.name || ""), role || {}]));
            const configured = (selectedRoles || [])
                .map(name => {
                    const role = catalog.get(String(name)) || {};
                    return { role: String(name), homePage: normalizeRoute(role.home_page) };
                })
                .filter(item => item.homePage);
            const routes = [...new Set(configured.map(item => item.homePage))];
            return {
                configured,
                routes,
                hasConflict: routes.length > 1,
            };
        }

        function roleOptions(roles, query = "") {
            const needle = String(query || "").toLowerCase();
            return (roles || [])
                .filter(role => String(role && role.name || "").toLowerCase().includes(needle))
                .map(role => {
                    const homePage = normalizeRoute(role.home_page);
                    const access = role.desk_access ? t("Desk access") : t("Role without Desk");
                    return {
                        value: role.name,
                        description: homePage
                            ? `${access} · ${t("Login page")}: ${homePage}`
                            : `${access} · ${t("Login page not specified")}`,
                    };
                });
        }

        function summaryCards(summary = {}) {
            return [
                { label: t("Total factory accounts"), value: summary.total || 0 },
                { label: t("Enabled accounts"), value: summary.enabled || 0 },
                { label: t("Disabled accounts"), value: summary.disabled || 0 },
                { label: t("Assigned active stages"), value: summary.active_assignments || 0 },
            ];
        }

        function languageName(code, languages) {
            const normalized = String(code || "").trim();
            const match = (languages || []).find(language => language && language.code === normalized);
            if (match && match.name) return String(match.name);
            return normalized;
        }

        function userModel(user, data) {
            const activeAssignments = Number(user && user.active_assignments || 0);
            const roles = Array.isArray(user && user.roles) ? user.roles : [];
            const navigation = user && user.navigation || {};
            const roleHomes = Array.isArray(navigation.role_home_pages) ? navigation.role_home_pages : [];
            const configuredRoutes = roleHomes.map(item => item.home_page).filter(Boolean);
            return {
                raw: user,
                email: user.email,
                name: user.full_name || user.email,
                enabled: Boolean(user.enabled),
                activeAssignments,
                roles,
                languageLabel: languageName(user.language, data && data.languages),
                defaultWorkspace: user.default_workspace || "—",
                lastActive: user.last_active || "—",
                roleHomeSummary: configuredRoutes.length ? configuredRoutes.join(" · ") : t("By Frappe / not specified"),
                roleHomeConflict: navigation.role_home_conflict === true,
                defaultWorkspaceConflict: navigation.default_workspace_conflict === true,
                canEdit: actionAllowed(user, "edit") || actionAllowed(user, "assign_roles"),
                canResetPassword: actionAllowed(user, "reset_password"),
                canDisable: actionAllowed(user, "disable"),
                canEnable: actionAllowed(user, "enable"),
                showActiveAssignmentWarning: activeAssignments > 0 && can(data, "disable_users"),
            };
        }

        function availableUserModel(user) {
            return {
                raw: user,
                email: user.email,
                name: user.full_name || user.email,
                enabled: Boolean(user.enabled),
                source: user.default_app || t("No default app"),
                defaultWorkspace: user.default_workspace || "—",
                lastActive: user.last_active || "—",
            };
        }

        function page(data) {
            return {
                search: String(data.search || ""),
                enabled: String(data.enabled || "all"),
                canCreateUsers: can(data, "create_users"),
                canAssignRoles: can(data, "assign_user_roles"),
                summary: summaryCards(data.summary || {}),
                users: (data.users || []).map(user => userModel(user, data)),
                availableUsers: (data.availableUsers || []).map(availableUserModel),
            };
        }

        return Object.freeze({
            can,
            actionAllowed,
            findUser,
            normalizeRoute,
            roleHomePolicy,
            roleOptions,
            languageName,
            summaryCards,
            userModel,
            availableUserModel,
            page,
        });
    }

    window.AlmdinaFactoryWorkforceViewModel = Object.freeze({ create });
})();
