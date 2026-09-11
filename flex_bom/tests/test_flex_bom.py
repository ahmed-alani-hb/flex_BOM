import frappe
from frappe.tests.utils import FrappeTestCase

from erpnext.controllers.item_variant import create_variant
from erpnext.stock.doctype.item.test_item import make_item
from erpnext.stock.doctype.stock_entry.stock_entry_utils import make_stock_entry

from flex_bom.api import flexible_bom_query, get_best_flexible_bom, get_item_details

PARENT_GROUP = "_Flex Parent Group"
CHILD_GROUP = "_Flex Child Group"
ATTRIBUTE = "_Flex Colour"


def get_company() -> str:
	if frappe.db.exists("Company", "_Test Company"):
		return "_Test Company"

	return frappe.defaults.get_defaults().get("company") or frappe.get_all("Company", pluck="name")[0]


def get_warehouse(company: str) -> str:
	warehouses = frappe.get_all(
		"Warehouse", filters={"company": company, "is_group": 0}, pluck="name", limit=1
	)
	if warehouses:
		return warehouses[0]

	return frappe.get_doc(
		{"doctype": "Warehouse", "warehouse_name": "_Flex Stores", "company": company}
	).insert().name


def ensure_item_group(name: str, parent: str, is_group: int = 0) -> str:
	if not frappe.db.exists("Item Group", name):
		frappe.get_doc(
			{
				"doctype": "Item Group",
				"item_group_name": name,
				"parent_item_group": parent,
				"is_group": is_group,
			}
		).insert()

	return name


def ensure_attribute() -> str:
	if not frappe.db.exists("Item Attribute", ATTRIBUTE):
		frappe.get_doc(
			{
				"doctype": "Item Attribute",
				"attribute_name": ATTRIBUTE,
				"item_attribute_values": [
					{"attribute_value": "Red", "abbr": "R"},
					{"attribute_value": "Blue", "abbr": "B"},
				],
			}
		).insert()

	return ATTRIBUTE


class TestFlexBOM(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()

		cls.company = get_company()
		cls.warehouse = get_warehouse(cls.company)
		cls.currency = frappe.get_cached_value("Company", cls.company, "default_currency")

		ensure_item_group(PARENT_GROUP, "All Item Groups", is_group=1)
		ensure_item_group(CHILD_GROUP, PARENT_GROUP)
		ensure_attribute()

		defaults = {"is_stock_item": 1, "stock_uom": "Nos"}
		cls.rm = make_item("_Flex RM", defaults).name
		cls.anchor = make_item("_Flex Anchor", defaults).name
		cls.target = make_item("_Flex Target", defaults).name
		cls.outsider = make_item("_Flex Outsider", defaults).name
		cls.in_child_group = make_item("_Flex Grouped", {**defaults, "item_group": CHILD_GROUP}).name
		cls.kg_item = make_item(
			"_Flex Grouped Kg", {**defaults, "item_group": CHILD_GROUP, "stock_uom": "Kg"}
		).name

		cls.template = make_item(
			"_Flex Template",
			{
				**defaults,
				"has_variants": 1,
				"attributes": [{"attribute": ATTRIBUTE}],
			},
		).name
		cls.variant = cls.make_variant(cls.template, "Red")

	@classmethod
	def make_variant(cls, template: str, value: str) -> str:
		code = f"{template}-{value}"
		if frappe.db.exists("Item", code):
			return code

		variant = create_variant(template, {ATTRIBUTE: value})
		variant.item_code = code
		variant.item_name = code
		variant.insert()

		return variant.name

	# ------------------------------------------------------------------ helpers

	def make_bom(self, anchor=None, applicability=None, submit=True, qty=1):
		bom = frappe.new_doc("BOM")
		bom.item = anchor or self.anchor
		bom.company = self.company
		bom.currency = self.currency
		bom.quantity = qty
		bom.append("items", {"item_code": self.rm, "qty": 2, "rate": 100})

		if applicability is not None:
			bom.custom_is_flexible = 1
			for row in applicability:
				bom.append("custom_applicability", row)

		bom.insert()
		if submit:
			bom.submit()

		return bom

	def make_work_order(self, item, bom_no, qty=1, submit=False):
		wo = frappe.new_doc("Work Order")
		wo.production_item = item
		wo.bom_no = bom_no
		wo.qty = qty
		wo.company = self.company
		wo.source_warehouse = self.warehouse
		wo.wip_warehouse = self.warehouse
		wo.fg_warehouse = self.warehouse
		wo.skip_transfer = 1
		wo.insert()

		if submit:
			wo.submit()

		return wo

	# -------------------------------------------------------------------- tests

	def test_item_row_allows_work_order_for_another_item(self):
		bom = self.make_bom(applicability=[{"apply_on": "Item", "item_code": self.target}])

		wo = self.make_work_order(self.target, bom.name, qty=3, submit=True)

		self.assertEqual(wo.docstatus, 1)
		self.assertEqual(wo.required_items[0].item_code, self.rm)
		self.assertEqual(wo.required_items[0].required_qty, 6)

	def test_item_group_row_covers_child_group_only(self):
		bom = self.make_bom(
			applicability=[
				{"apply_on": "Item Group", "item_group": PARENT_GROUP, "include_child_groups": 1}
			]
		)

		self.assertTrue(self.make_work_order(self.in_child_group, bom.name))

		with self.assertRaises(frappe.ValidationError):
			self.make_work_order(self.outsider, bom.name)

	def test_item_group_row_without_child_groups(self):
		bom = self.make_bom(
			applicability=[
				{"apply_on": "Item Group", "item_group": PARENT_GROUP, "include_child_groups": 0}
			]
		)

		with self.assertRaises(frappe.ValidationError):
			self.make_work_order(self.in_child_group, bom.name)

	def test_template_row_covers_variants(self):
		bom = self.make_bom(applicability=[{"apply_on": "Item Template", "item_template": self.template}])

		self.assertTrue(self.make_work_order(self.variant, bom.name))

	def test_attribute_row_matches_attribute_value(self):
		bom = self.make_bom(
			applicability=[
				{"apply_on": "Item Attribute", "item_attribute": ATTRIBUTE, "attribute_value": "Red"}
			]
		)

		self.assertTrue(self.make_work_order(self.variant, bom.name))

		blue = self.make_variant(self.template, "Blue")
		with self.assertRaises(frappe.ValidationError):
			self.make_work_order(blue, bom.name)

	def test_uom_mismatch_blocks_work_order(self):
		bom = self.make_bom(
			applicability=[
				{"apply_on": "Item Group", "item_group": CHILD_GROUP, "include_child_groups": 1}
			]
		)

		with self.assertRaises(frappe.ValidationError):
			self.make_work_order(self.kg_item, bom.name)

	def test_uom_mismatch_blocks_bom_save(self):
		with self.assertRaises(frappe.ValidationError):
			self.make_bom(applicability=[{"apply_on": "Item", "item_code": self.kg_item}], submit=False)

	def test_flexible_bom_requires_applicability_rows(self):
		bom = frappe.new_doc("BOM")
		bom.item = self.anchor
		bom.company = self.company
		bom.currency = self.currency
		bom.custom_is_flexible = 1
		bom.append("items", {"item_code": self.rm, "qty": 1, "rate": 100})

		with self.assertRaises(frappe.ValidationError):
			bom.insert()

	def test_link_query_lists_flexible_bom_for_matching_item_only(self):
		bom = self.make_bom(applicability=[{"apply_on": "Item", "item_code": self.target}])

		matching = flexible_bom_query("BOM", "", "name", 0, 20, {"item": self.target})
		self.assertIn(bom.name, [row[0] for row in matching])

		other = flexible_bom_query("BOM", "", "name", 0, 20, {"item": self.outsider})
		self.assertNotIn(bom.name, [row[0] for row in other])

	def test_prefill_picks_most_specific_match(self):
		group_bom = self.make_bom(
			applicability=[
				{"apply_on": "Item Group", "item_group": PARENT_GROUP, "include_child_groups": 1}
			]
		)
		item_bom = self.make_bom(
			applicability=[{"apply_on": "Item", "item_code": self.in_child_group}]
		)

		self.assertEqual(get_best_flexible_bom(self.in_child_group), item_bom.name)
		self.assertEqual(get_item_details(self.in_child_group).get("bom_no"), item_bom.name)
		self.assertTrue(group_bom.name)

	def test_prefill_skipped_when_ambiguous(self):
		self.make_bom(applicability=[{"apply_on": "Item", "item_code": self.target}])
		self.make_bom(applicability=[{"apply_on": "Item", "item_code": self.target}])

		self.assertIsNone(get_best_flexible_bom(self.target))
		self.assertFalse(get_item_details(self.target).get("bom_no"))

	def test_non_flexible_bom_still_rejected_for_other_item(self):
		bom = self.make_bom()

		with self.assertRaises(frappe.ValidationError):
			self.make_work_order(self.target, bom.name)

	def test_manufacture_entry_against_flexible_bom(self):
		from erpnext.manufacturing.doctype.work_order.work_order import (
			make_stock_entry as make_wo_stock_entry,
		)

		bom = self.make_bom(applicability=[{"apply_on": "Item", "item_code": self.target}])
		wo = self.make_work_order(self.target, bom.name, qty=1, submit=True)

		make_stock_entry(
			item_code=self.rm,
			qty=10,
			to_warehouse=self.warehouse,
			rate=100,
			company=self.company,
		)

		entry = frappe.get_doc(make_wo_stock_entry(wo.name, "Manufacture", 1))
		entry.insert()
		entry.submit()

		self.assertEqual(entry.docstatus, 1)
		consumed = [row.item_code for row in entry.items if row.s_warehouse]
		self.assertIn(self.rm, consumed)
		self.assertEqual(frappe.db.get_value("Work Order", wo.name, "produced_qty"), 1)
