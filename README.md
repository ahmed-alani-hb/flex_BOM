# Flex BOM

Flexible BOMs for **ERPNext v15**: let one BOM serve many items — a whole item group, every
variant of a template, or every item carrying a given attribute value — and pick it at **Work
Order** creation time, without pre-assigning it to the item.

No core files are patched and no fork is needed: the app ships custom fields, one child DocType,
two document-class overrides and one whitelisted-method override, all through standard hooks.

## Why

In stock ERPNext, `BOM.item` is a required Link and every consumer keys off it:

| Enforcement | Core location (v15) |
|---|---|
| Work Order `bom_no` dropdown filtered to the production item | `work_order.js` → `frm.set_query("bom_no", …)` |
| `BOM {0} does not belong to Item {1}` | `bom.py` → `validate_bom_no()`, called from `work_order.py:153` |
| Same check on the finished-item row | `stock_entry.py:1812` → `validate_bom()` |
| Default BOM prefill | `work_order.py` → `get_item_details()` |

Flex BOM relaxes exactly those four points — and nothing else.

## How it works

A BOM gains a **Flexible BOM** checkbox and an **Applicable Items** table. `BOM.item` is left
alone and acts as the *anchor item*: BOM costing, stock UOM and quantity scaling are still based
on it, and every core report keeps working unchanged.

Each applicability row matches items by one of:

| Apply On | Matches |
|---|---|
| **Item** | that exact item |
| **Item Template** | every variant of the template |
| **Item Group** | items in that group, and in child groups when *Include Child Groups* is on |
| **Item Attribute** | items whose variant attribute has the given value (e.g. Colour = Red) |

When several flexible BOMs match, the most specific wins — Item → Item Template → Item Attribute
→ Item Group (deeper group beats shallower). Auto-prefill happens only when the production item
has **no** default BOM of its own (its own or its template's); if two BOMs tie, nothing is
prefilled and the candidates are listed so a human chooses.

Safety rails:

- A flexible BOM cannot be `Is Default`, so `Item.default_bom` is never hijacked.
- Stock UOM must match the anchor item's — checked at BOM save for Item/Template rows, and at
  Work Order save for every item (quantities would otherwise be scaled wrongly).
- Core's "BOM must be active" and "BOM must be submitted" checks stay in force; only the
  ownership test is skipped, and only for BOMs that genuinely declare the item.

## Install

```bash
bench get-app https://github.com/ahmed-alani-hb/flex_bom.git
bench --site <site> install-app flex_bom
bench --site <site> migrate
```

The custom fields are created on install and re-asserted on every `migrate`.
`bench --site <site> uninstall-app flex_bom` removes them again; BOM data is untouched.

## Usage

1. Open a BOM, tick **Flexible BOM (Applies to Multiple Items)**.
2. Add **Applicable Items** rows, save and submit.
3. Use **Preview Applicable Items** to see exactly which items the rules resolve to.
4. On a Work Order, pick the production item — matching flexible BOMs now appear in the **BOM No**
   dropdown, labelled *Flexible — based on \<anchor item\>*.

## Tests

```bash
bench --site <site> run-tests --app flex_bom
```

Covers each match type, the "most specific wins" ranking, both UOM guards, the link query, the
ambiguity case, a regression test that non-flexible BOMs are still rejected for unrelated items,
and a full lane test (Work Order → Manufacture Stock Entry) that exercises the Stock Entry override.
The suite uses `_Test Company` when present and otherwise falls back to the site's default company.

## Scope and limits

Deliberately **Work Order-scoped**. These keep core behaviour and ignore flexible BOMs:

- Production Plan, Sales Order → Work Order, Material Request planning
- Subcontracting (Purchase Order / Subcontracting Order `bom`)
- BOM Explorer / Where-Used / BOM Stock reports, `Item.default_bom`

Also worth knowing:

- Keep *Manufacturing Settings → Validate Components and Quantities Per BOM* **off**. It compares a
  Manufacture entry against a BOM that is deliberately not item-exact.
- A flexible BOM's cost is computed from its anchor item, so use it where the recipe is genuinely
  item-independent. Finished-goods valuation still comes from actual consumption, not BOM cost.
- Pinned to ERPNext v15 — `validate_bom_no()` differs in v14.

## License

MIT
