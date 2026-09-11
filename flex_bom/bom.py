"""Validation for the flexible-BOM applicability table (doc_events on BOM)."""

import frappe
from frappe import _

from flex_bom.api import (
	APPLY_ON_ATTRIBUTE,
	APPLY_ON_GROUP,
	APPLY_ON_ITEM,
	APPLY_ON_TEMPLATE,
	flex_enabled,
)

# Fields each apply_on keeps; everything else on the row is cleared so stale
# values can never leak into a later match.
ROW_FIELDS = {
	APPLY_ON_ITEM: ["item_code"],
	APPLY_ON_TEMPLATE: ["item_template"],
	APPLY_ON_GROUP: ["item_group", "include_child_groups"],
	APPLY_ON_ATTRIBUTE: ["item_attribute", "attribute_value"],
}

ALL_ROW_FIELDS = [f for fields in ROW_FIELDS.values() for f in fields]


def validate(doc, method=None):
	if not flex_enabled() or not doc.get("custom_is_flexible"):
		return

	rows = doc.get("custom_applicability") or []
	if not rows:
		frappe.throw(
			_("A flexible BOM needs at least one row in {0}.").format(frappe.bold(_("Applicable Items"))),
			title=_("Applicability Missing"),
		)

	if doc.is_default:
		doc.is_default = 0
		frappe.msgprint(
			_("A flexible BOM cannot be the default BOM of {0}; {1} has been unchecked.").format(
				doc.item, frappe.bold(_("Is Default"))
			),
			indicator="orange",
			alert=True,
		)

	anchor_uom = frappe.db.get_value("Item", doc.item, "stock_uom")
	seen = set()

	for row in rows:
		_clear_unused_fields(row)
		_validate_row(row, doc, anchor_uom)

		key = (row.apply_on,) + tuple(str(row.get(f) or "") for f in ALL_ROW_FIELDS)
		if key in seen:
			frappe.throw(_("Row #{0}: duplicate applicability rule.").format(row.idx))
		seen.add(key)


def _clear_unused_fields(row):
	keep = ROW_FIELDS.get(row.apply_on, [])
	for field in ALL_ROW_FIELDS:
		if field not in keep and row.get(field):
			row.set(field, None if field != "include_child_groups" else 0)


def _validate_row(row, doc, anchor_uom):
	if row.apply_on == APPLY_ON_ITEM:
		_require(row, "item_code", _("Item"))
		item = frappe.db.get_value("Item", row.item_code, ["has_variants", "stock_uom"], as_dict=True)
		if item.has_variants:
			frappe.throw(
				_("Row #{0}: {1} is a template item. Use Apply On = {2} to cover all its variants.").format(
					row.idx, frappe.bold(row.item_code), frappe.bold(_("Item Template"))
				)
			)
		_validate_uom(row, row.item_code, item.stock_uom, anchor_uom, doc)

	elif row.apply_on == APPLY_ON_TEMPLATE:
		_require(row, "item_template", _("Item Template"))
		item = frappe.db.get_value("Item", row.item_template, ["has_variants", "stock_uom"], as_dict=True)
		if not item.has_variants:
			frappe.throw(
				_("Row #{0}: {1} is not a template item (it has no variants).").format(
					row.idx, frappe.bold(row.item_template)
				)
			)
		_validate_uom(row, row.item_template, item.stock_uom, anchor_uom, doc)

	elif row.apply_on == APPLY_ON_GROUP:
		_require(row, "item_group", _("Item Group"))

	elif row.apply_on == APPLY_ON_ATTRIBUTE:
		_require(row, "item_attribute", _("Item Attribute"))
		_require(row, "attribute_value", _("Attribute Value"))

		if not frappe.db.get_value("Item Attribute", row.item_attribute, "numeric_values"):
			exists = frappe.db.exists(
				"Item Attribute Value",
				{"parent": row.item_attribute, "attribute_value": row.attribute_value},
			)
			if not exists:
				frappe.throw(
					_("Row #{0}: {1} is not a value of Item Attribute {2}.").format(
						row.idx, frappe.bold(row.attribute_value), frappe.bold(row.item_attribute)
					)
				)


def _require(row, fieldname, label):
	if not row.get(fieldname):
		frappe.throw(
			_("Row #{0}: {1} is required when Apply On is {2}.").format(
				row.idx, frappe.bold(label), frappe.bold(_(row.apply_on))
			)
		)


def _validate_uom(row, item, item_uom, anchor_uom, doc):
	"""Cheap subset of the Work Order UOM guard, caught at BOM save time."""
	if item_uom == anchor_uom:
		return

	frappe.throw(
		_(
			"Row #{0}: {1} is stocked in {2} but this BOM is based on {3} ({4})."
			" Quantities would be scaled incorrectly."
		).format(row.idx, frappe.bold(item), frappe.bold(item_uom), doc.item, frappe.bold(anchor_uom)),
		title=_("Stock UOM Mismatch"),
	)
