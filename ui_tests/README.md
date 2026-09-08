# UI Tests

Browser tests for the Desk, written with [Playwright's Python bindings](https://playwright.dev/python/docs/intro)
and run by `pytest`. `bench run-tests` cannot run them — it is frappe's unittest runner and
finds no `TestCase`.

## Install

 installs `pytest`, `pytest-playwright` and `pytest-timeout`
from `pyproject.toml`. It does **not** install a browser — pip ships the driver, not the
binary. Download it once:

```bash
bench setup requirements --dev
playwright install chromium
```
## One-time setup

Run the tests against a dedicated test site. We will need to populate this site with test data.
```bash
bench new-site {site_name} --install-app india_compliance

bench --site {site_name} execute india_compliance.tests.before_tests
```
Then start the default server. Default port is 8000, but this will work on other ports too.
```bash
bench start
```

## Run

From the app directory, with the server up:

```bash
cd <bench>/apps/india_compliance

# everything
SITE={site_name} SITE_PORT=8000 ../../env/bin/pytest

# one test
SITE={site_name} SITE_PORT=8000 ../../env/bin/pytest -k test_in_state_supplier_gets_cgst_and_sgst
```

Add `--headed` to watch the browser. Failures write a trace to `test-results/`; open it with
`../../env/bin/playwright show-trace <path>`.
Put both commands in a `tasks.json` you will run them dozens of times a day, and the
`SITE` prefix is easy to forget.

## Writing a test

`FormPage` (`pages/form_page.py`) drives a Desk form: it fills fields by fieldname, handles
Link dropdowns and child-table grids, saves, and waits for the app to settle after every
change. Tests call it, never raw locators.

The `form_page` fixture is autouse, so `self.form_page("Purchase Invoice")` gives you an
open form on a logged-in desk.

```python
class TestPurchaseInvoice:
    @pytest.fixture(scope="class", autouse=True)
    @staticmethod
    def setup(request, site):
        request.cls.supplier = frappe.get_doc("Supplier", "_Test Registered Supplier")
        request.cls.item = frappe.get_doc("Item", "_Test Trading Goods 1")

    def test_something(self):
        form = self.form_page("Purchase Invoice")
        form.fill_fields({"supplier": self.supplier.name, "bill_no": "UI-TEST-001"})
        fill_items_table(form, [{"item_code": self.item.name, "qty": 1, "rate": 100}])
        form.save()
```

Read records with `frappe.get_doc` in the class-scoped `setup` fixture. **CI has only what
`india_compliance.tests.before_tests` seeds from `tests/test_records.json`** — a record you
created by hand locally does not exist there, and the test fails with `DoesNotExistError`.

Assert anything a client script computes **before** the save. Move it after, and a server
hook setting the same field will make a broken client script look fine.

**Every document the test saves is deleted when it ends** — cancelled first if submitted.
`form.save()` registers the name with the `doc` fixture, which deletes it in teardown, so
nothing survives the run and nothing to clean up by hand. The browser commits through the
server, so a rollback is impossible; deletion is the only mechanism. Anything you create
outside `form.save()` — `frappe.get_doc(...).insert()`, a submit from a dialog — is **not**
tracked. Pass it through the `doc` fixture yourself:

```python
def test_something(self, doc):
    ...
    doc("Purchase Invoice", name)    # read it, and delete it when the test ends
```

## Recording with codegen

Run these from the app directory, with the env activated. They open two windows - a browser and a recorded test file.

**First time** — creates `ui_tests/.auth/admin.json`. Log in as Administrator in the window
that opens, close it, and the session is written to that file:

```bash
playwright codegen --save-storage=ui_tests/.auth/admin.json "http://{site_name}:8000/login?redirect-to=/app"
```

**Every time after** — reads that file and opens straight on an authenticated desk:

```bash
playwright codegen --load-storage=ui_tests/.auth/admin.json "http://{site_name}:8000/app"
```

