"""Matching engine and whitelisted endpoints for flexible BOMs.

A flexible BOM declares, in its `custom_applicability` table, which items it may
be used for. `BOM.item` is left untouched and keeps acting as the *anchor item*:
it is what BOM costing, UOM and quantity scaling are based on, and what every
core report still reports against.
"""

import frappe
from frappe import _
from frappe.utils import cint

APPLY_ON_ITEM = "Item"
APPLY_ON_TEMPLATE = "Item Template"
APPLY_ON_GROUP = "Item Group"
APPLY_ON_ATTRIBUTE = "Item Attribute"

# Lower is more specific. Ties within "Item Group" are broken on nested-set
# depth: the deeper (more specific) group wins.
SPECIFICITY = {
	APPLY_ON_ITEM: 1,
	APPLY_ON_TEMPLATE: 2,
	APPLY_ON_ATTRIBUTE: 3,
	APPLY_ON_GROUP: 4,
}


def flex_enabled() -> bool:
	"""False until the custom fields exist (i.e. between install and migrate)."""
	if frappe.flags.get("flex_bom_ready") is None:
		frappe.flags.flex_bom_ready = bool(
			frappe.db.table_exists("Flex BOM Applicability")
			and frappe.db.has_column("BOM", "custom_is_flexible")
		)

	return frappe.flags.flex_bom_ready


def _item_context(item: str) -> frappe._dict | None:
	row = frappe.db.sql(
		"""
		SELECT i.name AS item_code, IFNULL(i.variant_of, '') AS variant_of,
			i.item_group, i.stock_uom, ig.lft AS group_lft, ig.rgt AS group_rgt
		FROM `tabItem` i
		LEFT JOIN `tabItem Group` ig ON ig.name = i.item_group
		WHERE i.name = %(item)s
		""",
		{"item": item},
		as_dict=True,
	)

	return row[0] if row else None


def get_matching_boms(item: str, company: str | None = None, only_submitted: bool = True) -> list:
	"""Flexible BOMs usable for `item`, most specific first.

	Each entry carries the applicability row that matched it, so callers can
	explain *why* a BOM matched and rank candidates for auto-selection.
	"""
	if not item or not flex_enabled():
		return []

	ctx = _item_context(item)
	if not ctx:
		return []

	conditions = ["b.custom_is_flexible = 1"]
	values = dict(ctx)

	if only_submitted:
		conditions.append("b.docstatus = 1")
		conditions.append("b.is_active = 1")

	if company:
		conditions.append("b.company = %(company)s")
		values["company"] = company

	rows = frappe.db.sql(
		"""
		SELECT
			b.name AS bom,
			b.item AS anchor_item,
			a.apply_on,
			a.item_group AS matched_group,
			IFNULL(ig.lft, 0) AS group_lft
		FROM `tabFlex BOM Applicability` a
		INNER JOIN `tabBOM` b ON b.name = a.parent
		LEFT JOIN `tabItem Group` ig ON ig.name = a.item_group
		WHERE a.parenttype = 'BOM'
			AND a.parentfield = 'custom_applicability'
			AND {conditions}
			AND (
				(a.apply_on = 'Item' AND a.item_code = %(item_code)s)
				OR (a.apply_on = 'Item Template' AND %(variant_of)s <> ''
					AND a.item_template = %(variant_of)s)
				OR (a.apply_on = 'Item Group' AND (
					(a.include_child_groups = 0 AND a.item_group = %(item_group)s)
					OR (a.include_child_groups = 1
						AND ig.lft <= %(group_lft)s AND ig.rgt >= %(group_rgt)s)
				))
				OR (a.apply_on = 'Item Attribute' AND EXISTS (
					SELECT 1 FROM `tabItem Variant Attribute` iva
					WHERE iva.parent = %(item_code)s
						AND iva.parenttype = 'Item'
						AND iva.attribute = a.item_attribute
						AND iva.attribute_value = a.attribute_value
				))
			)
		""".format(conditions=" AND ".join(conditions)),
		values,
		as_dict=True,
	)

	# Keep the strongest matching row per BOM, then rank the BOMs.
	best_per_bom: dict[str, frappe._dict] = {}
	for row in rows:
		row.specificity = SPECIFICITY.get(row.apply_on, 99)
		current = best_per_bom.get(row.bom)
		if not current or (row.specificity, -row.group_lft) < (current.specificity, -current.group_lft):
			best_per_bom[row.bom] = row

	return sorted(best_per_bom.values(), key=lambda r: (r.specificity, -r.group_lft, r.bom))


def flexible_bom_matches(item: str, bom_no: str) -> bool:
	"""Does `bom_no` declare itself applicable to `item`?

	Draft / inactive BOMs are included on purpose: the caller hands those to
	core validation anyway, so the user gets "BOM must be submitted" rather than
	the misleading "BOM does not belong to Item".
	"""
	if not (item and bom_no):
		return False

	return any(match.bom == bom_no for match in get_matching_boms(item, only_submitted=False))


def get_best_flexible_bom(item: str, company: str | None = None, alert: bool = False) -> str | None:
	"""The single most specific flexible BOM for `item`, or None when ambiguous."""
	matches = get_matching_boms(item, company)
	if not matches:
		return None

	best = matches[0]
	tied = [m for m in matches if (m.specificity, m.group_lft) == (best.specificity, best.group_lft)]
	if len(tied) > 1:
		if alert:
			frappe.msgprint(
				_("{0} flexible BOMs match Item {1} equally well: {2}. Please pick one.").format(
					len(tied), frappe.bold(item), ", ".join(m.bom for m in tied)
				),
				indicator="orange",
				alert=True,
			)
		return None

	return best.bom


def _native_boms(item: str) -> list[str]:
	"""BOMs core would already offer for this item (own BOMs + template BOMs)."""
	variant_of = frappe.db.get_value("Item", item, "variant_of")
	items = [item] + ([variant_of] if variant_of else [])

	return frappe.get_all(
		"BOM",
		filters={"item": ["in", items], "docstatus": 1, "is_active": 1},
		pluck="name",
		order_by="is_default desc, name asc",
	)


def _native_default_bom(item: str, project: str | None = None) -> str | None:
	"""Mirrors the default-BOM lookup in erpnext work_order.get_item_details()."""
	filters = {"item": item, "project": project} if project else {"item": item, "is_default": 1, "docstatus": 1}
	bom_no = frappe.db.get_value("BOM", filters)
	if bom_no:
		return bom_no

	variant_of = frappe.db.get_value("Item", item, "variant_of")
	if variant_of:
		return frappe.db.get_value("BOM", {"item": variant_of, "is_default": 1})

	return None


@frappe.whitelist()
@frappe.validate_and_sanitize_search_inputs
def flexible_bom_query(doctype, txt, searchfield, start, page_len, filters):
	"""Link query for Work Order.bom_no: the item's own BOMs plus flexible matches."""
	frappe.has_permission("BOM", "read", throw=True)

	if isinstance(filters, (list, tuple)):
		filters = {f[0]: f[-1] for f in filters if len(f) >= 2}

	filters = frappe._dict(filters or {})
	item = filters.get("item")
	if not item:
		return []

	company = filters.get("company")
	names = _native_boms(item)
	native = set(names)
	names += [m.bom for m in get_matching_boms(item, company) if m.bom not in native]

	if not names:
		return []

	rows = frappe.get_all(
		"BOM",
		filters={"name": ["in", names]},
		fields=["name", "item", "item_name"],
	)
	by_name = {row.name: row for row in rows}

	txt = (txt or "").lower()
	out = []
	for name in names:
		row = by_name.get(name)
		if not row or txt not in name.lower():
			continue

		label = (
			_("Flexible — based on {0}").format(row.item)
			if name not in native
			else (row.item_name or row.item)
		)
		out.append([name, row.item, label])

	return out[cint(start) : cint(start) + cint(page_len or 20)]


@frappe.whitelist()
def get_applicable_items(bom: str, limit: int = 100) -> list[str]:
	"""Resolve a flexible BOM's rules to actual items, for the preview dialog."""
	frappe.has_permission("BOM", "read", throw=True)

	doc = frappe.get_doc("BOM", bom)
	if not doc.get("custom_is_flexible"):
		return [doc.item]

	limit = cint(limit) or 100
	items: list[str] = []

	def add(names):
		for name in names:
			if name and name not in items:
				items.append(name)

	for row in doc.get("custom_applicability") or []:
		if len(items) >= limit:
			break

		if row.apply_on == APPLY_ON_ITEM and row.item_code:
			add([row.item_code])
		elif row.apply_on == APPLY_ON_TEMPLATE and row.item_template:
			add(frappe.get_all("Item", filters={"variant_of": row.item_template}, pluck="name", limit=limit))
		elif row.apply_on == APPLY_ON_GROUP and row.item_group:
			if row.include_child_groups:
				lft, rgt = frappe.db.get_value("Item Group", row.item_group, ["lft", "rgt"])
				groups = frappe.get_all(
					"Item Group", filters={"lft": [">=", lft], "rgt": ["<=", rgt]}, pluck="name"
				)
			else:
				groups = [row.item_group]

			add(
				frappe.get_all(
					"Item",
					filters={"item_group": ["in", groups], "has_variants": 0, "disabled": 0},
					pluck="name",
					limit=limit,
				)
			)
		elif row.apply_on == APPLY_ON_ATTRIBUTE and row.item_attribute:
			add(
				frappe.get_all(
					"Item Variant Attribute",
					filters={
						"attribute": row.item_attribute,
						"attribute_value": row.attribute_value,
						"parenttype": "Item",
					},
					pluck="parent",
					limit=limit,
				)
			)

	return items[:limit]


@frappe.whitelist()
def get_item_details(item, project=None, skip_bom_info=False, throw=True):
	"""Wraps erpnext work_order.get_item_details() to prefill a flexible BOM.

	Core is left in charge whenever it can answer: the flexible match is only
	used when the item has neither its own default BOM nor a template one.
	"""
	from erpnext.manufacturing.doctype.work_order.work_order import (
		check_if_scrap_warehouse_mandatory,
	)
	from erpnext.manufacturing.doctype.work_order.work_order import (
		get_item_details as core_get_item_details,
	)

	skip_bom_info = cint(skip_bom_info)

	if skip_bom_info or not flex_enabled() or _native_default_bom(item, project):
		return core_get_item_details(item, project=project, skip_bom_info=skip_bom_info, throw=throw)

	bom_no = get_best_flexible_bom(item, alert=True)
	if not bom_no:
		return core_get_item_details(item, project=project, throw=throw)

	res = core_get_item_details(item, project=project, skip_bom_info=True)
	if not res:
		return res

	bom_data = frappe.db.get_value(
		"BOM",
		bom_no,
		["project", "allow_alternative_item", "transfer_material_against"],
		as_dict=1,
	)
	# NOTE: unlike core we do not copy BOM.item_name onto the result -- on a
	# flexible BOM that is the anchor item's name, not the item being produced.
	res["bom_no"] = bom_no
	res["project"] = project or bom_data.pop("project")
	res.update(bom_data)
	res.update(check_if_scrap_warehouse_mandatory(bom_no))
	res["flex_bom"] = 1

	return res
