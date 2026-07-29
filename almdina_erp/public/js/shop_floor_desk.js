(() => {
	"use strict";

	const HOME = "shop-floor-inbox";

	function is_shop_floor_only() {
		return Boolean(window.frappe && frappe.boot && frappe.boot.almdina_shop_floor_only);
	}

	function allowed_route(route) {
		const raw = String(route || "")
			.replace(/^#\/?/, "")
			.replace(/^\//, "")
			.toLowerCase();
		const path = raw.startsWith("app/") ? raw.slice(4) : raw;
		if (!path || path === "app" || path === "desk") return true;
		if (path === HOME || path.startsWith(HOME + "/")) return true;
		if (path.startsWith("shop-floor")) return true;
		if (path === "login" || path === "me") return true;
		return false;
	}

	function go_inbox() {
		try {
			if (frappe.set_route) {
				frappe.set_route(HOME);
				return;
			}
		} catch (e) {
			/* fall through */
		}
		window.location.href = "/app/" + HOME;
	}

	function inject_css() {
		if (document.getElementById("almdina-shop-floor-only-style")) return;
		const style = document.createElement("style");
		style.id = "almdina-shop-floor-only-style";
		style.textContent = `
			body.almdina-shop-floor-only .body-sidebar,
			body.almdina-shop-floor-only .body-sidebar-container,
			body.almdina-shop-floor-only .body-sidebar-placeholder,
			body.almdina-shop-floor-only .desk-sidebar,
			body.almdina-shop-floor-only .standard-sidebar,
			body.almdina-shop-floor-only .workspace-sidebar,
			body.almdina-shop-floor-only .sidebar-item-container,
			body.almdina-shop-floor-only .sidebar-resize-handle,
			body.almdina-shop-floor-only .collapse-sidebar-link,
			body.almdina-shop-floor-only .sidebar-toggle-btn,
			body.almdina-shop-floor-only .app-switcher-menu,
			body.almdina-shop-floor-only .apps-list,
			body.almdina-shop-floor-only .app-logo,
			body.almdina-shop-floor-only .awesomebar,
			body.almdina-shop-floor-only .search-bar,
			body.almdina-shop-floor-only #navbar-breadcrumbs,
			body.almdina-shop-floor-only .desktop-icon-grid,
			body.almdina-shop-floor-only .notifications-icon,
			body.almdina-shop-floor-only .dropdown-help,
			body.almdina-shop-floor-only .onboarding-sidebar,
			body.almdina-shop-floor-only .user-onboarding,
			body.almdina-shop-floor-only .list-sidebar,
			body.almdina-shop-floor-only .layout-side-section,
			body.almdina-shop-floor-only .page-head .page-icon-group,
			body.almdina-shop-floor-only .page-head .menu-btn-group {
				display: none !important;
			}

			body.almdina-shop-floor-only .main-section,
			body.almdina-shop-floor-only .layout-main-section-wrapper,
			body.almdina-shop-floor-only .container.page-body,
			body.almdina-shop-floor-only .content.page-container {
				max-width: 100% !important;
				margin: 0 !important;
			}
			body.almdina-shop-floor-only .page-container,
			body.almdina-shop-floor-only .page-body {
				padding-left: 0 !important;
				padding-right: 0 !important;
			}
			body.almdina-shop-floor-only .page-head {
				padding: 6px 12px !important;
				min-height: 44px !important;
			}

			/* Shop floor tabs (rendered inside the page, never wiped on refresh) */
			.almdina-sf-tabs {
				position: sticky;
				top: 0;
				z-index: 50;
				display: flex;
				flex-wrap: wrap;
				align-items: center;
				gap: 8px;
				padding: 10px;
				background: var(--fg-color, #fff);
				border-bottom: 1px solid var(--border-color, #e5e7eb);
			}
			.almdina-sf-tab {
				appearance: none;
				border: 1px solid var(--border-color, #dfe3e8);
				background: var(--control-bg, #fff);
				color: var(--text-color, #1f272e);
				min-height: 44px;
				padding: 8px 16px;
				border-radius: 10px;
				font-size: 15px;
				font-weight: 700;
				cursor: pointer;
			}
			.almdina-sf-tab.is-active {
				background: var(--primary, #2490ef);
				border-color: var(--primary, #2490ef);
				color: #fff;
			}
			.almdina-sf-refresh {
				margin-inline-start: auto;
				min-height: 44px !important;
				font-weight: 700;
			}

			.almdina-sf-shell { padding: 12px 10px 24px; }
			.almdina-sf-list-title { font-size: 1.05rem; font-weight: 800; margin: 0 0 10px; }
			.almdina-sf-list { display: grid; gap: 10px; }
			.almdina-sf-order-card {
				padding: 14px !important;
				border-radius: 14px !important;
				border: 1px solid var(--border-color, #e5e7eb) !important;
				box-shadow: 0 1px 2px rgba(0,0,0,.04);
				cursor: pointer;
				-webkit-tap-highlight-color: transparent;
			}
			.almdina-sf-order-card .sf-open-btn,
			.almdina-sf-actions .btn {
				min-height: 44px;
				padding: 10px 16px;
				font-size: 15px;
				font-weight: 700;
				border-radius: 10px;
			}
			.almdina-sf-actions {
				display: flex;
				flex-wrap: wrap;
				gap: 8px;
				margin-bottom: 10px;
			}
			.almdina-sf-detail-title { font-size: 1.15rem; margin: 0 0 4px; }
			.almdina-sf-pieces-wrap,
			.almdina-sf-plan-wrap {
				overflow: auto;
				-webkit-overflow-scrolling: touch;
				border: 1px solid var(--border-color, #e5e7eb);
				border-radius: 12px;
				background: #fff;
				padding: 8px;
			}
			.almdina-sf-account-card {
				border: 1px solid var(--border-color, #e5e7eb);
				border-radius: 14px;
				padding: 16px;
				background: var(--fg-color, #fff);
				max-width: 520px;
			}
			.almdina-sf-account-row {
				display: flex;
				justify-content: space-between;
				gap: 12px;
				padding: 10px 0;
				border-bottom: 1px solid var(--border-color, #edf0f2);
				font-size: 14px;
			}
			.almdina-sf-account-row:last-of-type { border-bottom: 0; }
			.almdina-sf-logout {
				width: 100%;
				min-height: 48px;
				margin-top: 16px;
				font-size: 16px;
				font-weight: 800;
				border-radius: 12px;
			}

			/* Hard hide any DXF export action for non-drawing shop-floor roles */
			body.almdina-no-dxf-export button.export-dxf,
			body.almdina-no-dxf-export .btn.export-dxf {
				display: none !important;
			}

			@media (max-width: 600px) {
				.almdina-sf-tab { flex: 1 1 calc(33% - 8px); padding: 8px 6px; font-size: 14px; }
				.almdina-sf-refresh { flex: 1 1 100%; margin-inline-start: 0; }
				.almdina-sf-actions .btn { flex: 1 1 calc(50% - 8px); }
			}
		`;
		document.head.appendChild(style);
	}

	function hide_desk_chrome() {
		document.body.classList.add("almdina-shop-floor-only");
		const roles = (frappe.user_roles || []).concat(
			(frappe.boot && frappe.boot.user && frappe.boot.user.roles) || []
		);
		const can_export =
			roles.includes("عامل رسم") ||
			roles.includes("Production Manager") ||
			roles.includes("System Manager");
		document.body.classList.toggle("almdina-no-dxf-export", !can_export);
		if (!can_export) {
			// Belt-and-suspenders: remove any leftover export buttons from the DOM.
			const kill = () => {
				document.querySelectorAll("button, a.btn").forEach((el) => {
					const t = (el.textContent || "").trim();
					if (/تصدير\s*DXF/i.test(t) || /^export\s*dxf/i.test(t)) {
						el.remove();
					}
				});
			};
			kill();
			setTimeout(kill, 300);
			setTimeout(kill, 1200);
			if (!document.body._almdina_dxf_kill_observer && typeof MutationObserver !== "undefined") {
				const obs = new MutationObserver(kill);
				obs.observe(document.body, { childList: true, subtree: true });
				document.body._almdina_dxf_kill_observer = obs;
			}
		}
		inject_css();
		const selectors = [
			".body-sidebar",
			".body-sidebar-container",
			".desk-sidebar",
			".standard-sidebar",
			".workspace-sidebar",
			".awesomebar",
			".desktop-icon-grid",
			".notifications-icon",
			".dropdown-help",
			".sidebar-toggle-btn",
			".app-switcher-menu",
			"#navbar-breadcrumbs",
		].join(", ");
		document.querySelectorAll(selectors).forEach((el) => {
			el.style.setProperty("display", "none", "important");
		});
	}

	function guard_routes() {
		if (!frappe.router) return;

		const original_set = frappe.set_route;
		if (original_set && !original_set.__almdina_shop_floor_guard) {
			const wrapped = function () {
				const args = Array.prototype.slice.call(arguments);
				const joined = args
					.flat(Infinity)
					.filter((x) => x !== undefined && x !== null && x !== "")
					.map(String)
					.join("/");
				if (!allowed_route(joined) && !allowed_route("app/" + joined)) {
					frappe.show_alert({
						message: __("هذه الصفحة غير متاحة لحساب عامل الصالة."),
						indicator: "orange",
					});
					return go_inbox();
				}
				return original_set.apply(this, args);
			};
			wrapped.__almdina_shop_floor_guard = true;
			frappe.set_route = wrapped;
		}

		if (!frappe.router.__almdina_shop_floor_change) {
			frappe.router.__almdina_shop_floor_change = true;
			frappe.router.on("change", () => {
				hide_desk_chrome();
				const route = (frappe.get_route_str && frappe.get_route_str()) || "";
				if (!allowed_route(route) && !allowed_route("app/" + route)) {
					go_inbox();
				}
			});
		}
	}

	function enforce_home() {
		const route = (frappe.get_route_str && frappe.get_route_str()) || "";
		const path = String(window.location.pathname || "");
		if (
			!route ||
			route === "desktop" ||
			route.toLowerCase().startsWith("workspaces") ||
			path.endsWith("/app") ||
			path.endsWith("/app/") ||
			path.endsWith("/desk") ||
			path.endsWith("/desk/")
		) {
			go_inbox();
			return;
		}
		if (!allowed_route(route) && !allowed_route("app/" + route)) {
			go_inbox();
		}
	}

	function boot_workspaces() {
		try {
			if (frappe.boot && frappe.boot.workspaces && Array.isArray(frappe.boot.workspaces.pages)) {
				frappe.boot.workspaces.pages = frappe.boot.workspaces.pages.filter(
					(p) => p && (p.name === "Shop Floor" || p.title === "Shop Floor" || p.title === "صالة الإنتاج")
				);
			}
			if (frappe.boot) {
				frappe.boot.allowed_workspaces = (frappe.boot.workspaces && frappe.boot.workspaces.pages) || [];
				frappe.boot.home_page = HOME;
			}
		} catch (e) {
			console.warn("almdina shop floor workspace trim failed", e);
		}
	}

	function init() {
		if (!is_shop_floor_only()) return;
		boot_workspaces();
		hide_desk_chrome();
		guard_routes();
		enforce_home();
		[300, 900, 2000].forEach((ms) => setTimeout(hide_desk_chrome, ms));
	}

	// Desk does not define frappe.ready (it only exists on website pages), so wait
	// for the desk bootinfo to land before locking the UI down.
	function wait_for_boot(attempt) {
		if (window.frappe && frappe.boot) {
			init();
			return;
		}
		if (attempt > 60) return;
		setTimeout(() => wait_for_boot(attempt + 1), 150);
	}

	if (document.readyState === "loading") {
		document.addEventListener("DOMContentLoaded", () => wait_for_boot(0));
	} else {
		wait_for_boot(0);
	}
})();
