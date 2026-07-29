(() => {
	"use strict";

	const ALLOWED_APP = "almdina_erp";
	const ALLOWED_MODULES = ["Almdina ERP"];

	function is_order_entry_only() {
		return Boolean(window.frappe && frappe.boot && frappe.boot.almdina_order_entry_only);
	}

	function trim_boot() {
		const boot = frappe.boot;

		if (boot.apps_data && Array.isArray(boot.apps_data.apps)) {
			boot.apps_data.apps = boot.apps_data.apps.filter((app) => app && app.name === ALLOWED_APP);
			boot.apps_data.is_desk_apps = 1;
		}

		if (Array.isArray(boot.desktop_icons)) {
			boot.desktop_icons = boot.desktop_icons.filter((icon) => {
				if (!icon) return false;
				const module = icon.module_name || icon.label || "";
				return ALLOWED_MODULES.includes(module) || icon.app === ALLOWED_APP;
			});
		}

		if (boot.workspaces && Array.isArray(boot.workspaces.pages)) {
			boot.workspaces.pages = boot.workspaces.pages.filter(
				(p) => p && ALLOWED_MODULES.includes(p.module)
			);
			boot.allowed_workspaces = boot.workspaces.pages;
		}
	}

	function inject_css() {
		if (document.getElementById("almdina-order-entry-style")) return;
		const style = document.createElement("style");
		style.id = "almdina-order-entry-style";
		style.textContent = `
			body.almdina-order-entry-only .dropdown-menu-item[data-name="erpnext"],
			body.almdina-order-entry-only .dropdown-menu-item[data-name="frappe"],
			body.almdina-order-entry-only .app-card[data-app-name="erpnext"],
			body.almdina-order-entry-only .app-card[data-app-name="frappe"] {
				display: none !important;
			}
		`;
		document.head.appendChild(style);
	}

	function hide_other_apps() {
		document.body.classList.add("almdina-order-entry-only");
		inject_css();
		document
			.querySelectorAll(".dropdown-menu-item[data-app-route], .app-card[data-app-name]")
			.forEach((el) => {
				const name = el.getAttribute("data-name") || el.getAttribute("data-app-name") || "";
				const route = el.getAttribute("data-app-route") || "";
				const is_almdina = name === ALLOWED_APP || route.includes("almdina");
				if (!is_almdina && name) {
					el.style.setProperty("display", "none", "important");
				}
			});
	}

	function init() {
		if (!is_order_entry_only()) return;
		trim_boot();
		hide_other_apps();
		[400, 1200, 2500].forEach((ms) => setTimeout(hide_other_apps, ms));
		if (frappe.router && !frappe.router.__almdina_order_entry) {
			frappe.router.__almdina_order_entry = true;
			frappe.router.on("change", hide_other_apps);
		}
	}

	// Desk has no frappe.ready(); wait for bootinfo to be attached instead.
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
