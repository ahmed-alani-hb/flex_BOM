"""Scoped relaxation of erpnext's BOM-ownership check.

`validate_bom_no()` is a module-level function that Work Order and Stock Entry
call directly, so it cannot be overridden by subclassing alone. Instead of
reimplementing their `validate()` methods (which would go stale on every
erpnext release), we swap the module attribute for the duration of the super
call and restore it in a `finally`. Frappe request and worker processes handle
one document at a time, so the swap is never visible to another document.
"""

from contextlib import contextmanager

from flex_bom.api import flexible_bom_matches


def make_lenient(core_validate_bom_no):
	def lenient_validate_bom_no(item, bom_no):
		if item and bom_no and flexible_bom_matches(item, bom_no):
			# Passing item=None keeps core's "BOM must be active" and "BOM must
			# be submitted" guards and skips only the ownership test.
			item = None

		return core_validate_bom_no(item, bom_no)

	return lenient_validate_bom_no


@contextmanager
def lenient_bom_validation(module):
	original = getattr(module, "validate_bom_no", None)
	if original is None:
		yield
		return

	module.validate_bom_no = make_lenient(original)
	try:
		yield
	finally:
		module.validate_bom_no = original
