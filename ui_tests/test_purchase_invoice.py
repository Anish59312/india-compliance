import re

import pytest
from playwright.sync_api import expect

from ui_tests.conftest import desk_ready
from ui_tests.records import get_test_record
from ui_tests.transaction import fill_items_table, verify_autofill_attributes, verify_taxes_table


class TestPurchaseInvoice:
    @pytest.fixture(autouse=True)
    def setup(self, authenticated_desk, saved_doc):
        self.page = authenticated_desk
        self.saved_doc = saved_doc
        self.company = get_test_record("Company", "_Test Indian Registered Company")
        self.supplier = get_test_record("Supplier", "_Test Registered Supplier")
        self.item = get_test_record("Item", "_Test Trading Goods 1")
        self.state = self.company.gstin[:2]

    def test_in_state_supplier_gets_cgst_and_sgst(self):
        assert self.supplier.gstin[:2] == self.state

        page = self.page
        page.goto("/app/purchase-invoice/new")
        expect(page.locator("body")).to_have_attribute(
            "data-route", re.compile(r"^Form/Purchase Invoice/new-purchase-invoice-")
        )
        desk_ready(page)

        supplier_input = page.locator('[data-fieldname="supplier"]:not(.search) input:visible').first
        supplier_dropdown = supplier_input.locator("xpath=..").get_by_role("listbox")
        supplier_input.click()
        supplier_input.press_sequentially(self.supplier.name, delay=50)
        expect(supplier_dropdown.get_by_role("option").first).to_contain_text(self.supplier.name)
        supplier_input.press("Enter")
        expect(supplier_input).to_have_value(self.supplier.name)
        desk_ready(page)

        page.locator('[data-fieldname="bill_no"]:not(.search) input:visible').first.fill("UI-TEST-001")

        fill_items_table(page, [{"item_code": self.item.name, "qty": 1, "rate": 100}])

        verify_autofill_attributes(page, "place_of_supply", self.state)

        with page.expect_response(
            lambda response: (
                "frappe.desk.form.save.savedocs" in response.url and response.request.method == "POST"
            )
        ) as saved:
            page.locator('.page-container:visible button[data-label="Save"]').first.click()

        assert saved.value.status == 200, f"savedocs: {saved.value.text()}"
        desk_ready(page)

        self.saved_doc("Purchase Invoice", page.evaluate("() => window.cur_frm.doc.name"))

        verify_taxes_table(
            page,
            [
                {"account_head": "CGST", "rate": 9},
                {"account_head": "SGST", "rate": 9},
            ],
        )
