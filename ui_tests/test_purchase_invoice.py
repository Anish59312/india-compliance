import frappe
import pytest

from ui_tests.pages.form_page import FormPage
from ui_tests.utils.transaction import (
    fill_items_table,
    verify_autofill_attributes,
    verify_taxes_table,
)


class TestPurchaseInvoice:
    @pytest.fixture(scope="class", autouse=True)
    @staticmethod
    def setup(request, site):
        request.cls.company = frappe.get_doc("Company", "_Test Indian Registered Company")
        request.cls.supplier = frappe.get_doc("Supplier", "_Test Registered Supplier")
        request.cls.item = frappe.get_doc("Item", "_Test Trading Goods 1")
        request.cls.state = request.cls.company.gstin[:2]

    @pytest.fixture(autouse=True)
    def open_form(self, authenticated_desk, saved_doc):
        self.page = authenticated_desk
        self.saved_doc = saved_doc
        self.form = FormPage(self.page, "Purchase Invoice")

    def test_in_state_supplier_gets_cgst_and_sgst(self):
        assert self.supplier.gstin[:2] == self.state

        self.form.navigate()
        self.form.fill_fields({"supplier": self.supplier.name, "bill_no": "UI-TEST-001"})

        fill_items_table(self.form, [{"item_code": self.item.name, "qty": 1, "rate": 100}])

        verify_autofill_attributes(self.form, "place_of_supply", self.state)

        self.form.save()
        self.saved_doc("Purchase Invoice", self.form.name)

        assert self.form.get_status() == "Draft"

        verify_taxes_table(
            self.form,
            [
                {"account_head": "CGST", "rate": 9},
                {"account_head": "SGST", "rate": 9},
            ],
        )
