import frappe

BEFORE_TESTS = "india_compliance.tests.before_tests"


def get_test_record(doctype: str, name: str):
    """Fetch a record seeded from india_compliance/tests/test_records.json."""
    if not frappe.db.exists(doctype, name):
        raise LookupError(
            f'No {doctype} named "{name}". Either it was renamed in test_records.json, '
            f"or {BEFORE_TESTS} has not been run on this site."
        )

    return frappe.get_doc(doctype, name)
