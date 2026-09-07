from playwright.sync_api import expect

from ui_tests.conftest import desk_ready, poll_doc


def fill_items_table(page, rows, tablefield="items"):
    grid = page.locator(f'.frappe-control[data-fieldname="{tablefield}"]')
    grid_rows = grid.locator(".grid-row[data-idx]")

    for idx, values in enumerate(rows, start=1):
        while grid_rows.count() < idx:
            grid.locator(".grid-add-row").click()
            expect(grid_rows).to_have_count(idx)

        row = grid.locator(f'.grid-row[data-idx="{idx}"]')
        expect(row).to_be_visible()

        if "grid-row-open" not in (row.get_attribute("class") or ""):
            row.locator(".btn-open-row").click()

        expect(row).to_contain_class("grid-row-open")

        for fieldname, value in values.items():
            cell = row.locator(f'[data-fieldname="{fieldname}"][data-fieldtype]:not(.search)')
            input_ = cell.locator("input:visible").first

            if cell.first.get_attribute("data-fieldtype") in ("Link", "Dynamic Link"):
                dropdown = input_.locator("xpath=..").get_by_role("listbox")
                input_.click()
                input_.press_sequentially(str(value), delay=50)
                expect(dropdown.get_by_role("option").first).to_contain_text(str(value))
                input_.press("Enter")
                expect(input_).to_have_value(str(value))
            else:
                input_.fill(str(value))

            desk_ready(page)

        row.locator(".grid-collapse-row").click()
        desk_ready(page)


def verify_autofill_attributes(page, fieldname, value):
    poll_doc(
        page,
        lambda doc: doc.get(fieldname),
        lambda actual: str(value) in str(actual or ""),
        f"{fieldname} should be autofilled to {value!r}",
    )


def verify_taxes_table(page, rows, tablefield="taxes"):
    actual_rows = poll_doc(
        page,
        lambda doc: doc.get(tablefield) or [],
        lambda found: len(found) == len(rows),
        f"expected {len(rows)} rows in {tablefield}",
    )

    for actual, expected in zip(actual_rows, rows, strict=True):
        for fieldname, value in expected.items():
            got = actual.get(fieldname)
            matched = str(value) in str(got or "") if isinstance(value, str) else got == value

            assert matched, f"{tablefield}.{fieldname}: expected {value!r}, got {got!r}"
