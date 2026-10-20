// Frappe v16.17.5, MIT-licensed source excerpt; no framework reimplementation.
// Source: https://github.com/frappe/frappe/blob/75baafaa0bde07a86bf28764383b93b5df97bc7e/frappe/public/js/frappe/model/perm.js#L191-L267
// Keep this exact native display-status behavior: hidden is presentation, not a grant.
frappe.perm.get_field_display_status = (df, doc, perm, explain) => {
		// returns the display status of a particular field
		// returns one of "Read", "Write" or "None"
		if (!perm && doc) {
			perm = frappe.perm.get_perm(doc.doctype, doc);
		}

		if (!perm) {
			let is_hidden = df && (cint(df.hidden) || cint(df.hidden_due_to_dependency));
			let is_read_only = df && (cint(df.read_only) || cint(df.is_virtual));
			return is_hidden ? "None" : is_read_only ? "Read" : "Write";
		}

		if (!df.permlevel) df.permlevel = 0;
		let p = perm[df.permlevel];
		let status = "None";

		// permission
		if (p) {
			if (p.write && !df.disabled && !df.is_virtual) {
				status = "Write";
			} else if (p.read) {
				status = "Read";
			}
		}
		if (explain) console.log("By Permission:" + status);

		// hidden
		if (cint(df.hidden)) status = "None";
		if (explain) console.log("By Hidden:" + status);

		// hidden due to dependency
		if (cint(df.hidden_due_to_dependency)) status = "None";
		if (explain) console.log("By Hidden Due To Dependency:" + status);

		if (!doc) {
			return status;
		}

		// submit
		if (status === "Write" && cint(doc.docstatus) > 0) status = "Read";
		if (explain) console.log("By Submit:" + status);

		// allow on submit
		// let allow_on_submit = df.fieldtype==="Table" ? 0 : cint(df.allow_on_submit);
		let allow_on_submit = cint(df.allow_on_submit);
		if (status === "Read" && allow_on_submit && cint(doc.docstatus) === 1 && p.write) {
			status = "Write";
		}
		if (explain) console.log("By Allow on Submit:" + status);

		// workflow state
		if (status === "Read" && cur_frm && cur_frm.state_fieldname) {
			// fields updated by workflow must be read-only
			if (
				cint(cur_frm.read_only) ||
				cur_frm.states.update_fields.includes(df.fieldname) ||
				df.fieldname == cur_frm.state_fieldname
			) {
				status = "Read";
			}
		}
		if (explain) console.log("By Workflow:" + status);

		// read only field is checked
		if (status === "Write" && (cint(df.read_only) || df.fieldtype === "Read Only")) {
			status = "Read";
		}
		if (explain) console.log("By Read Only:" + status);

		if (status === "Write" && df.set_only_once && !doc.__islocal) {
			status = "Read";
		}
		if (explain) console.log("By Set Only Once:" + status);

		return status;
	};

