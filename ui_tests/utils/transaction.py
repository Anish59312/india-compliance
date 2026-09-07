def verify_autofill_attributes(form, fieldname, value):
    form.wait_for_value(fieldname, value)


def verify_taxes_table(form, rows, tablefield="taxes"):
    form.wait_for_row_count(tablefield, len(rows))
    actual_rows = form.doc().get(tablefield) or []

    for actual, expected in zip(actual_rows, rows, strict=True):
        for fieldname, value in expected.items():
            got = actual.get(fieldname)
            matched = str(value) in str(got or "") if isinstance(value, str) else got == value

            assert matched, f"{tablefield}.{fieldname}: expected {value!r}, got {got!r}"


def fill_items_table(form, rows, tablefield="items"):
    form.fill_table(tablefield, rows)
