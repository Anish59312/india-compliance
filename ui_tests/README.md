# UI Tests

Browser tests for the Desk, written with
[Playwright&#39;s Python bindings](https://playwright.dev/python/docs/intro)
and run by `pytest`. `bench run-tests` cannot run them — it is frappe's
unittest runner and finds no `TestCase`.

## Install

`bench setup requirements --dev` installs `pytest`, `pytest-playwright` and
`pytest-timeout` from `pyproject.toml`. It does **not** install a browser —
pip ships the driver, not the binary. Download it once:

```bash
bench setup requirements --dev
playwright install chromium
```

## One-time setup

Run the tests against a dedicated test site, and populate it with test data:

```bash
bench --site {site_name} execute india_compliance.tests.before_tests
```

If the site should listen on another port, serve it on that port.

## Configure

Copy the example file and set `SITE` and `SITE_PORT` to match that server.
`conftest.py` loads `.env`, so nothing needs exporting:

```bash
cp .env.example .env
```

## Run

From the app directory, with the server up:

```bash
cd <bench>/apps/india_compliance/ui_tests

# everything
pytest

# a single file
pytest tests/test_purchase_invoice.py

# a single test
pytest tests/test_purchase_invoice.py::TestPurchaseInvoice::test_in_state_supplier_gets_cgst_and_sgst
```

### Run with a visible browser (headed mode)

The browser is headless by default. Add `--headed` to watch the run in a
visible window:

```bash
# everything, in a visible browser
pytest --headed

# one file, slowed down enough to follow
pytest --headed --slowmo 500 tests/test_purchase_invoice.py
```

`--slowmo` takes milliseconds and pauses before each action. To stop on a
line and step through it in the Playwright Inspector, call `page.pause()`
inside the test.

### Traces, video and screenshots

`--tracing=retain-on-failure --video=retain-on-failure --screenshot=only-on-failure` are already set in `pyproject.toml`, so a
failing test leaves its artifacts under `test-results/` and a passing one
leaves nothing behind. Open a trace in the viewer for a DOM snapshot,
network log and console output at every step:

```bash
playwright show-trace test-results/{test-name}/trace.zip
```

To keep them for passing tests too, override on the command line:

```bash
pytest --tracing=on --video=on --screenshot=on
```

## Writing a test

`FormPage` (`pages/form_page.py`) drives a Desk form: it fills fields by
fieldname, handles Link dropdowns and child-table grids, saves, and waits for
the app to settle after every change. Tests call it, never raw locators.

The `form_page` fixture is autouse, so `self.form_page("Purchase Invoice")`
gives you an open form on a logged-in desk.

```python
class TestPurchaseInvoice:
    @pytest.fixture(scope="class", autouse=True)
    @staticmethod
    def setup(request, site):
        request.cls.supplier = frappe.get_doc(
            "Supplier", "_Test Registered Supplier"
        )
        request.cls.item = frappe.get_doc("Item", "_Test Trading Goods 1")

    def test_something(self):
        form = self.form_page("Purchase Invoice")
        form.fill_fields(
            {"supplier": self.supplier.name, "bill_no": "UI-TEST-001"}
        )
        fill_items_table(
            form, [{"item_code": self.item.name, "qty": 1, "rate": 100}]
        )
        form.save()
```

Read records with `frappe.get_doc` in the class-scoped `setup` fixture.
**CI has only what `india_compliance.tests.before_tests` seeds from
`tests/test_records.json`** — a record you created by hand locally does not
exist there, and the test fails with `DoesNotExistError`.

Assert anything a client script computes **before** the save. Move it after,
and a server hook setting the same field will make a broken client script
look fine.

**Every document the test saves is deleted when it ends** — cancelled first
if submitted. `form.save()` registers the name with the `doc` fixture, which
deletes it in teardown, so nothing survives the run and there is nothing to
clean up by hand. The browser commits through the server, so a rollback is
impossible; deletion is the only mechanism. Anything you create outside
`form.save()` — `frappe.get_doc(...).insert()`, a submit from a dialog — is
**not** tracked. Pass it through the `doc` fixture yourself:

```python
def test_something(self, doc):
    ...
    doc("Purchase Invoice", name)    # read it, and delete it at test end
```

## Recording with codegen

Codegen opens two windows — a browser, and a recorded test file.

```bash
cd <bench>/apps/india_compliance/ui_tests
```

**First time** — creates `ui_tests/.auth/admin.json`. Log in as
Administrator in the window that opens, then close it; the session is written
to that file:

```bash
playwright codegen --save-storage=.auth/admin.json \
  "http://{site_name}:8000/login?redirect-to=/app"
```

**Every time after**

```bash
playwright codegen --load-storage=.auth/admin.json \
  "http://{site_name}:8000/app"
```
