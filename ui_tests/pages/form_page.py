import re

from playwright.sync_api import Locator, Page, expect

from ui_tests.pages.base_page import BasePage


class FormPage(BasePage):
    def __init__(self, page: Page, doctype: str, name: str | None = None, track=None):
        super().__init__(page)
        self.doctype = doctype
        self.name = name
        self.track = track
        self.doctype_slug = doctype.lower().replace(" ", "-")

    def navigate(self) -> "FormPage":
        route = self.name or "new"
        self.page.goto(f"/app/{self.doctype_slug}/{route}")

        if self.name:
            expect(self.page.locator("body")).to_have_attribute(
                "data-route", f"Form/{self.doctype}/{self.name}"
            )
        else:
            expect(self.page.locator("body")).to_have_attribute(
                "data-route",
                re.compile(rf"^Form/{re.escape(self.doctype)}/new-{re.escape(self.doctype_slug)}-"),
            )

        self.wait_for_load()

        return self

    def fill_fields(self, values: dict) -> "FormPage":
        for fieldname, value in values.items():
            self.set_field(self.page, fieldname, value)
            self.wait_for_load()

        return self

    def set_field(self, scope, fieldname: str, value) -> None:
        control = scope.locator(f'[data-fieldname="{fieldname}"][data-fieldtype]:not(.search)')
        fieldtype = control.first.get_attribute("data-fieldtype")

        if fieldtype in ("Link", "Dynamic Link"):
            self.set_link(scope, fieldname, str(value))
        elif fieldtype == "Select":
            self.control(scope, fieldname, "select").select_option(str(value))
        elif fieldtype == "Check":
            checkbox = self.control(scope, fieldname, "input")
            if bool(value) != checkbox.is_checked():
                checkbox.set_checked(bool(value))
        else:
            self.control(scope, fieldname, "input").fill(str(value))

    def set_link(self, scope, fieldname: str, value: str) -> None:
        input_ = self.control(scope, fieldname, "input")
        dropdown = input_.locator("xpath=..").get_by_role("listbox")

        input_.click()
        input_.press_sequentially(value, delay=50)
        expect(dropdown.get_by_role("option").first).to_contain_text(value)
        input_.press("Enter")
        expect(input_).to_have_value(value)

    def control(self, scope, fieldname: str, tag: str) -> Locator:
        return scope.locator(f'[data-fieldname="{fieldname}"]:not(.search) {tag}:visible').first

    def get_field_value(self, fieldname: str) -> str:
        return self.control(self.page, fieldname, "input").input_value()

    def grid(self, tablefield: str) -> Locator:
        return self.page.locator(f'.frappe-control[data-fieldname="{tablefield}"]')

    def get_table_row_count(self, tablefield: str) -> int:
        return self.grid(tablefield).locator(".grid-row[data-idx]").count()

    def open_table_row(self, tablefield: str, row_idx: int = 1) -> Locator:
        grid = self.grid(tablefield)
        rows = grid.locator(".grid-row[data-idx]")

        while rows.count() < row_idx:
            grid.locator(".grid-add-row").click()
            expect(rows).to_have_count(row_idx)

        row = grid.locator(f'.grid-row[data-idx="{row_idx}"]')
        expect(row).to_be_visible()

        if "grid-row-open" not in (row.get_attribute("class") or ""):
            row.locator(".btn-open-row").click()

        expect(row).to_contain_class("grid-row-open")

        return row

    def fill_table_row(self, tablefield: str, row_idx: int, values: dict) -> "FormPage":
        row = self.open_table_row(tablefield, row_idx)

        for fieldname, value in values.items():
            self.set_field(row, fieldname, value)
            self.wait_for_load()

        row.locator(".grid-collapse-row").click()
        self.wait_for_load()

        return self

    def fill_table(self, tablefield: str, rows: list[dict]) -> "FormPage":
        for row_idx, values in enumerate(rows, start=1):
            self.fill_table_row(tablefield, row_idx, values)

        return self

    def doc(self) -> dict:
        return self.page.evaluate(
            "() => window.cur_frm ? JSON.parse(JSON.stringify(window.cur_frm.doc)) : {}"
        )

    def wait_for_value(self, fieldname: str, value, timeout: int = 10_000):
        return self.page.wait_for_function(
            "([field, expected]) => {"
            " const doc = window.cur_frm?.doc;"
            " if (!doc) return null;"
            " const actual = doc[field];"
            " return String(actual ?? '').includes(String(expected)) ? actual : null;"
            "}",
            arg=[fieldname, value],
            timeout=timeout,
            polling=100,
        ).json_value()

    def wait_for_row_count(self, tablefield: str, count: int, timeout: int = 10_000) -> None:
        self.page.wait_for_function(
            "([field, expected]) => (window.cur_frm?.doc?.[field] || []).length === expected",
            arg=[tablefield, count],
            timeout=timeout,
            polling=100,
        )

    def is_dirty(self) -> bool:
        return bool(self.page.evaluate("() => window.cur_frm.is_dirty()"))

    def save(self) -> "FormPage":
        with self.page.expect_response(
            lambda response: (
                "frappe.desk.form.save.savedocs" in response.url and response.request.method == "POST"
            )
        ) as saved:
            self.control_button("Save").click()

        assert saved.value.status == 200, f"savedocs: {saved.value.text()}"

        self.page.wait_for_function(
            "() => window.cur_frm && !window.cur_frm.is_dirty()", timeout=10_000, polling=100
        )
        self.wait_for_load()
        self.name = self.page.evaluate("() => window.cur_frm.doc.name")

        if self.track:
            #
            self.track(self.doctype, self.name)

        return self

    def submit(self) -> "FormPage":
        self.control_button("Submit").click()
        self.page.locator(".modal:visible").get_by_role("button", name="Yes").first.click()
        self.wait_for_load()

        return self

    def control_button(self, label: str) -> Locator:
        return self.page.locator(f'.page-container:visible button[data-label="{label}"]').first

    def get_status(self) -> str:
        return (
            self.page.locator('.page-container:visible [data-testid="page-status"]')
            .first.inner_text()
            .strip()
        )

    def assert_field_value(self, fieldname: str, expected) -> "FormPage":
        expect(self.control(self.page, fieldname, "input")).to_have_value(str(expected))

        return self
