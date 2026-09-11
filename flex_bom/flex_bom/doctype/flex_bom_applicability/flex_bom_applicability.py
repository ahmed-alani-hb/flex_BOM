from frappe.model.document import Document


class FlexBOMApplicability(Document):
	# begin: auto-generated types
	# This code is auto-generated. Do not modify anything in this block.

	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from frappe.types import DF

		apply_on: DF.Literal["Item", "Item Template", "Item Group", "Item Attribute"]
		attribute_value: DF.Data | None
		include_child_groups: DF.Check
		item_attribute: DF.Link | None
		item_code: DF.Link | None
		item_group: DF.Link | None
		item_template: DF.Link | None
		parent: DF.Data
		parentfield: DF.Data
		parenttype: DF.Data
	# end: auto-generated types

	pass
