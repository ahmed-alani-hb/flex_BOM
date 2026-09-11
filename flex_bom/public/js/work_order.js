// Loaded after erpnext's work_order.js, so the bom_no query registered in
// refresh() replaces the core one (which filters strictly on production_item).

frappe.provide("flex_bom");

flex_bom.set_bom_hint = function (frm) {
	const field = frm.get_field("bom_no");
	if (!field) return;

	if (!frm.doc.bom_no) {
		frm.set_df_property("bom_no", "description", "");
		return;
	}

	frappe.db
		.get_value("BOM", frm.doc.bom_no, ["custom_is_flexible", "item"])
		.then((r) => {
			const bom = (r && r.message) || {};
			const description =
				bom.custom_is_flexible && bom.item !== frm.doc.production_item
					? __("Flexible BOM — quantities are based on {0}", [bom.item])
					: "";
			frm.set_df_property("bom_no", "description", description);
		});
};

frappe.ui.form.on("Work Order", {
	refresh(frm) {
		frm.set_query("bom_no", function () {
			if (!frm.doc.production_item) {
				frappe.msgprint(__("Please enter Production Item first"));
				return;
			}

			return {
				query: "flex_bom.api.flexible_bom_query",
				filters: {
					item: frm.doc.production_item,
					company: frm.doc.company,
				},
			};
		});

		flex_bom.set_bom_hint(frm);
	},

	bom_no(frm) {
		flex_bom.set_bom_hint(frm);
	},
});
