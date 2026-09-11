from erpnext.stock.doctype.stock_entry import stock_entry as stock_entry_module
from erpnext.stock.doctype.stock_entry.stock_entry import StockEntry

from flex_bom.overrides.utils import lenient_bom_validation


class FlexStockEntry(StockEntry):
	"""StockEntry.validate_bom() re-checks the finished-item row's bom_no, which
	set_work_order_details() copies from the Work Order. Without this override a
	Work Order on a flexible BOM could be submitted but never manufactured."""

	def validate(self):
		with lenient_bom_validation(stock_entry_module):
			super().validate()
