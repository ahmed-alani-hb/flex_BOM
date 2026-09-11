app_name = "flex_bom"
app_title = "Flex BOM"
app_publisher = "Honey Bird"
app_description = "Flexible BOMs for ERPNext: one BOM usable by many items, item groups, variants or attribute values, selectable at Work Order creation time."
app_email = "admin@honey-bird.net"
app_license = "mit"

required_apps = ["frappe/erpnext"]

# ---------------------------------------------------------------------------
# Client scripts
# ---------------------------------------------------------------------------
# Loaded after the core form scripts, so the bom_no query registered here wins
# over the one core sets in erpnext/manufacturing/doctype/work_order/work_order.js
doctype_js = {
	"Work Order": "public/js/work_order.js",
	"BOM": "public/js/bom.js",
}

# ---------------------------------------------------------------------------
# Server overrides
# ---------------------------------------------------------------------------
# Both classes relax exactly one check -- "does this BOM belong to this item" --
# and only for BOMs that legitimately match via the applicability table.
override_doctype_class = {
	"Work Order": "flex_bom.overrides.work_order.FlexWorkOrder",
	"Stock Entry": "flex_bom.overrides.stock_entry.FlexStockEntry",
}

# Prefills bom_no on the Work Order from the best flexible match when the
# production item has no default BOM of its own.
override_whitelisted_methods = {
	"erpnext.manufacturing.doctype.work_order.work_order.get_item_details": "flex_bom.api.get_item_details",
}

doc_events = {
	"BOM": {
		"validate": "flex_bom.bom.validate",
	},
}

# ---------------------------------------------------------------------------
# Install / migrate
# ---------------------------------------------------------------------------
after_install = "flex_bom.install.after_install"
after_migrate = "flex_bom.install.after_migrate"
before_uninstall = "flex_bom.install.before_uninstall"
