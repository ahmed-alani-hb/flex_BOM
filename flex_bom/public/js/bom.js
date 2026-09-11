frappe.ui.form.on("BOM", {
	setup(frm) {
		frm.set_query("item_code", "custom_applicability", () => ({
			filters: { has_variants: 0, disabled: 0 },
		}));

		frm.set_query("item_template", "custom_applicability", () => ({
			filters: { has_variants: 1, disabled: 0 },
		}));
	},

	refresh(frm) {
		if (frm.doc.custom_is_flexible && !frm.is_new()) {
			frm.add_custom_button(__("Preview Applicable Items"), () =>
				flex_bom.preview_applicable_items(frm)
			);
		}
	},

	custom_is_flexible(frm) {
		if (frm.doc.custom_is_flexible && frm.doc.is_default) {
			frm.set_value("is_default", 0);
			frappe.show_alert({
				message: __("A flexible BOM cannot be the default BOM of an item."),
				indicator: "orange",
			});
		}
	},
});

frappe.provide("flex_bom");

flex_bom.preview_applicable_items = function (frm) {
	frappe.call({
		method: "flex_bom.api.get_applicable_items",
		args: { bom: frm.doc.name, limit: 100 },
		freeze: true,
		callback(r) {
			const items = r.message || [];
			const body = items.length
				? `<ol>${items.map((i) => `<li>${frappe.utils.escape_html(i)}</li>`).join("")}</ol>`
				: `<p class="text-muted">${__("No items match these rules yet.")}</p>`;

			new frappe.ui.Dialog({
				title: __("Applicable Items ({0})", [items.length]),
				fields: [{ fieldtype: "HTML", options: body }],
			}).show();
		},
	});
};
