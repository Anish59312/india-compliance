import pytest
from playwright.sync_api import Page

from ui_tests.pages.form_page import FormPage


class TestCiFailureCheck:
    @pytest.fixture(autouse=True)
    def open_form(self, authenticated_desk: Page):
        self.page = authenticated_desk
        self.form = FormPage(self.page, "Purchase Invoice")

    def test_locator_that_does_not_exist(self):
        self.form.navigate()
        self.form.fill_fields({"this_field_does_not_exist": "x"})

    def test_assertion_that_cannot_hold(self):
        self.form.navigate()

        assert self.form.get_status() == "Submitted", "a brand new form is never Submitted"
