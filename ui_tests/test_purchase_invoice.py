import re
from collections.abc import Callable

from playwright.sync_api import Page, expect

from ui_tests.conftest import desk_ready, poll_doc
from ui_tests.records import get_test_record


class TestPurchaseInvoice:
    def test_in_state_supplier_gets_cgst_and_sgst(
        self,
        authenticated_desk: Page,
        saved_doc: Callable[[str, str], object],
    ) -> None:
        """A supplier in the company's own state is taxed CGST + SGST, never IGST."""
        page = authenticated_desk
        company = get_test_record("Company", "_Test Indian Registered Company")
        supplier = get_test_record("Supplier", "_Test Registered Supplier")
        item = get_test_record("Item", "_Test Trading Goods 1")
        state = company.gstin[:2]

        assert supplier.gstin[:2] == state, (
            f"{supplier.name} ({supplier.gstin}) and {company.name} ({company.gstin}) "
            "must share a state code for the intra-state expectation to hold"
        )

        page.goto("/app/purchase-invoice/new")
        expect(page.locator("body")).to_have_attribute(
            "data-route", re.compile(r"^Form/Purchase Invoice/new-purchase-invoice-")
        )
        desk_ready(page)

        supplier_input = page.locator('[data-fieldname="supplier"]:not(.search) input:visible').first
        supplier_dropdown = supplier_input.locator("xpath=..").get_by_role("listbox")
        supplier_input.click()
        expect(supplier_dropdown).to_be_visible()
        supplier_input.press_sequentially(supplier.name, delay=50)
        expect(supplier_dropdown.get_by_role("option").first).to_contain_text(supplier.name)
        supplier_input.press("Enter")
        expect(supplier_input).to_have_value(supplier.name)
        desk_ready(page)

        page.locator('[data-fieldname="bill_no"]:not(.search) input:visible').first.fill("UI-TEST-001")

        items = page.locator('.frappe-control[data-fieldname="items"]')
        rows = items.locator(".grid-row[data-idx]")
        # ERPNext may or may not seed a blank item row depending on defaults.
        if rows.count() == 0:
            items.locator(".grid-add-row").click()
        expect(rows).to_have_count(1)

        # Cells in a collapsed row render as read-only .static-area, and the row's Link
        # controls do not exist at all until it is open.
        row = items.locator('.grid-row[data-idx="1"]')
        if "grid-row-open" not in (row.get_attribute("class") or ""):
            row.locator(".btn-open-row").click()
        expect(row).to_have_class(re.compile("grid-row-open"))

        item_input = row.locator('[data-fieldname="item_code"]:not(.search) input:visible').first
        item_dropdown = item_input.locator("xpath=..").get_by_role("listbox")
        item_input.click()
        expect(item_dropdown).to_be_visible()
        item_input.press_sequentially(item.name, delay=50)
        expect(item_dropdown.get_by_role("option").first).to_contain_text(item.name)
        item_input.press("Enter")
        desk_ready(page)

        row.locator('[data-fieldname="qty"] .form-control:visible').first.fill("1")
        row.locator('[data-fieldname="rate"] .form-control:visible').first.fill("100")
        row.locator(".grid-collapse-row").click()
        desk_ready(page)

        # place_of_supply and the tax rows are both filled in by client scripts that run
        # after the item lands, so a single read races them.
        poll_doc(
            page,
            lambda doc: (doc.get("place_of_supply") or "").split("-")[0],
            lambda value: value == state,
            f"place_of_supply should be in state {state}",
        )
        poll_doc(
            page,
            lambda doc: doc.get("taxes") or [],
            lambda taxes: len(taxes) == 2,
            "expected exactly two GST tax rows (CGST + SGST)",
        )

        # Wait on savedocs rather than the status pill: a validation error also leaves the
        # form looking idle.
        with page.expect_response(
            lambda response: (
                "frappe.desk.form.save.savedocs" in response.url and response.request.method == "POST"
            )
        ) as saved:
            page.locator('.page-container:visible button[data-label="Save"]').first.click()

        assert saved.value.status == 200, f"savedocs: {saved.value.text()}"
        desk_ready(page)

        invoice = saved_doc("Purchase Invoice", page.evaluate("() => window.cur_frm.doc.name"))

        assert invoice.docstatus == 0
        assert invoice.company == company.name
        assert invoice.place_of_supply.startswith(state)
        assert invoice.taxes_and_charges, "a GST tax template was applied"

        heads = [tax.account_head for tax in invoice.taxes]
        assert any("CGST" in head for head in heads), f"CGST row in {heads}"
        assert any("SGST" in head for head in heads), f"SGST row in {heads}"
        assert not any("IGST" in head for head in heads), f"no IGST row in {heads}"

        cgst, sgst = invoice.taxes
        assert cgst.rate > 0, "CGST rate is set"
        assert sgst.rate == cgst.rate, "SGST rate equals CGST rate"
