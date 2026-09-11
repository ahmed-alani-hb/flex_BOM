import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

CUSTOM_FIELDS = {
	"BOM": [
		{
			"fieldname": "custom_is_flexible",
			"label": "Flexible BOM (Applies to Multiple Items)",
			"fieldtype": "Check",
			"insert_after": "is_active",
			"default": "0",
			"description": (
				"When enabled, this BOM can be selected on a Work Order for any item listed in"
				" Applicable Items below, not only for the item it is built on."
			),
		},
		{
			"fieldname": "custom_applicability_section",
			"label": "Flexible BOM Applicability",
			"fieldtype": "Section Break",
			"insert_after": "custom_is_flexible",
			"depends_on": "eval:doc.custom_is_flexible",
		},
		{
			"fieldname": "custom_applicability",
			"label": "Applicable Items",
			"fieldtype": "Table",
			"options": "Flex BOM Applicability",
			"insert_after": "custom_applicability_section",
			"depends_on": "eval:doc.custom_is_flexible",
		},
	]
}


def after_install():
	create_flex_bom_custom_fields()


def after_migrate():
	create_flex_bom_custom_fields()


def create_flex_bom_custom_fields():
	"""Idempotent -- create_custom_fields() updates existing fields in place."""
	create_custom_fields(CUSTOM_FIELDS, ignore_validate=True)


def before_uninstall():
	"""Drop the custom fields. BOM data itself is left untouched."""
	for doctype, fields in CUSTOM_FIELDS.items():
		for field in fields:
			name = frappe.db.get_value(
				"Custom Field", {"dt": doctype, "fieldname": field["fieldname"]}, "name"
			)
			if name:
				frappe.delete_doc("Custom Field", name, ignore_permissions=True)
