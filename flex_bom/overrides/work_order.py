import frappe
from frappe import _

from erpnext.manufacturing.doctype.work_order import work_order as work_order_module
from erpnext.manufacturing.doctype.work_order.work_order import WorkOrder

from flex_bom.api import flex_enabled, flexible_bom_matches
from flex_bom.overrides.utils import lenient_bom_validation


class FlexWorkOrder(WorkOrder):
	def validate(self):
		self.validate_flexible_bom_uom()

		with lenient_bom_validation(work_order_module):
			super().validate()

	def validate_flexible_bom_uom(self):
		"""A BOM's quantities are expressed in its anchor item's stock UOM and
		scaled by the Work Order qty, so producing an item measured in another
		UOM would silently yield wrong required quantities."""
		if not (self.bom_no and self.production_item) or not flex_enabled():
			return

		bom = frappe.db.get_value(
			"BOM", self.bom_no, ["item", "custom_is_flexible"], as_dict=True
		)
		if not bom or not bom.custom_is_flexible or bom.item == self.production_item:
			return

		if not flexible_bom_matches(self.production_item, self.bom_no):
			return

		anchor_uom = frappe.db.get_value("Item", bom.item, "stock_uom")
		item_uom = frappe.db.get_value("Item", self.production_item, "stock_uom")
		if anchor_uom == item_uom:
			return

		frappe.throw(
			_(
				"Flexible BOM {0} is based on Item {1} ({2}), but {3} is stocked in {4}."
				" Quantities would be scaled incorrectly. Use a BOM whose stock UOM matches."
			).format(
				frappe.bold(self.bom_no),
				bom.item,
				frappe.bold(anchor_uom),
				self.production_item,
				frappe.bold(item_uom),
			),
			title=_("Stock UOM Mismatch"),
		)
