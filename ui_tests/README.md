# UI Tests

Desk browser tests, written with [Playwright's Python bindings](https://playwright.dev/python/docs/intro)
and run by `pytest`. They drive a real Chromium against a running Frappe site.

`bench run-tests` cannot run these — it is frappe's unittest runner and will find no
`TestCase`. Use `pytest`.

## Layout

```
ui_tests/
  conftest.py                fixtures: site, auth, authenticated_desk, saved_doc
  pages/
    base_page.py             BasePage — waiting, buttons, Actions menu
    form_page.py             FormPage — fields, child tables, save, submit, status
  utils/
    transaction.py           domain helpers over FormPage
  test_*.py                  the tests
```

`pages/` is the Page Object Model: `BasePage` owns everything generic to a Desk page,
`FormPage` extends it with document-form behaviour. `utils/` holds thin domain helpers
that read as the business rule rather than as form mechanics.

## One-time setup

```bash
cd <bench>

# 1. install the dev dependencies (pytest, pytest-playwright, pytest-timeout)
bench setup requirements --dev

# 2. install the browser
./env/bin/playwright install chromium

# 3. seed the records the tests look up. Idempotent — safe to re-run.
bench --site ic_test.localhost execute india_compliance.tests.before_tests
```

## Running

A server must already be running; the suite does not start one. The bench's own
`bench start` on port 8000 is enough — it resolves the site from the `Host` header, so
`ic_test.localhost:8000` reaches that site without a dedicated server.

```bash
cd <bench>/apps/india_compliance

SITE=ic_test.localhost SITE_PORT=8000 ../../env/bin/pytest
```

| Goal | Command |
| --- | --- |
| one test | `pytest ui_tests/test_purchase_invoice.py::TestPurchaseInvoice::test_in_state_supplier_gets_cgst_and_sgst` |
| by name | `pytest -k cgst` |
| one file | `pytest ui_tests/test_purchase_invoice.py` |
| watch the browser | `pytest --headed` |
| live browser console | `pytest -s` |
| slow it down | `pytest --headed --slowmo 500` |
| list without running | `pytest --co` |

`SITE` and `SITE_PORT` default to `test-ui.localhost` and `8000` (see `conftest.py`), so
pass `SITE` explicitly unless that is the site you want.

### From VS Code

`.vscode/tasks.json` has the same commands, prompting for site and port (defaults
`ic_test.localhost` / `8000`). **Tasks: Run Task** →

- **UI: Run nearest test** — the test at or above the cursor, headed
- **UI: Run all tests** — the whole suite, headless
- **UI: Run current file (headed)**
- **UI: Serve test site** / **UI: Seed test records**
- **UI: New test (template + codegen)** — scaffolds a file, then opens the recorder
- **UI: Debug one test (Inspector)** / **UI: Open last trace**

## Debugging a failure

Traces are kept for failures only (`--tracing=retain-on-failure`) and land in
`test-results/<test-id>/trace.zip`. A trace holds the DOM snapshot, network log and
action timeline at the moment it broke:

```bash
../../env/bin/playwright show-trace test-results/*/trace.zip
```

The browser console and any uncaught page errors are printed under
`Captured stdout teardown` for each failing test.

To step through a test in a real browser, put `page.pause()` where you want to stop and
run **headed**:

```bash
SITE=ic_test.localhost SITE_PORT=8000 ../../env/bin/pytest --headed -s --timeout=0 -k <name>
```

`--headed` is required: headless, `page.pause()` is a silent no-op and the test runs
straight past it. `--timeout=0` stops `pytest-timeout` killing the session while you read
the screen. The window that opens has **Record** and **Pick locator**, so it doubles as a
recorder for extending the test from real mid-test state.

`PWDEBUG=1` opens the plain Inspector instead — step and Pick locator, but no Record.

## Writing a test

```python
class TestPurchaseInvoice:
    @pytest.fixture(scope="class", autouse=True)
    @staticmethod
    def setup(request, site):
        request.cls.company = frappe.get_doc("Company", "_Test Indian Registered Company")
        request.cls.state = request.cls.company.gstin[:2]

    @pytest.fixture(autouse=True)
    def open_form(self, authenticated_desk, saved_doc):
        self.page = authenticated_desk
        self.saved_doc = saved_doc
        self.form = FormPage(self.page, "Purchase Invoice")

    def test_something(self):
        self.form.navigate()
        self.form.fill_fields({"supplier": self.supplier.name, "bill_no": "UI-TEST-001"})
        fill_items_table(self.form, [{"item_code": self.item.name, "qty": 1, "rate": 100}])

        verify_autofill_attributes(self.form, "place_of_supply", self.state)

        self.form.save()
        self.saved_doc("Purchase Invoice", self.form.name)
```

The class-scoped fixture reads records once per class and takes `site`, which is what
connects this process to the database. It is a `@staticmethod` writing to `request.cls`
on purpose: pytest builds a **new instance of the test class per test method**, so
attributes set on `self` in a class-scoped fixture would not be visible to later tests,
and pytest 10 removes the instance-method form entirely.

### Fixtures

- `authenticated_desk` — a page already logged in and sitting on a settled desk.
- `saved_doc(doctype, name)` — reads a document the browser just created and deletes it
  when the test ends. Call it for anything the test saves, or the record is left behind.
- `site` — connects this process to the database. Session-scoped and autouse.
- `frappe.get_doc(doctype, name)` — read records straight from the database. **CI has only
  the records `india_compliance.tests.before_tests` seeds from `tests/test_records.json`**
  — anything created by hand in a local site does not exist there, so a test that depends
  on one fails in CI with `DoesNotExistError`.

### FormPage

| Method | Does |
| --- | --- |
| `navigate()` | Open the form, assert the route, wait for the desk |
| `fill_fields({fieldname: value})` | Set top-level fields, dispatching on `data-fieldtype` |
| `fill_table(tablefield, [{...}, ...])` | Add/open rows and fill each, one row per dict |
| `fill_table_row(tablefield, idx, {...})` | One row (1-based, matching `data-idx`) |
| `open_table_row(tablefield, idx)` | Row locator, guaranteed to exist and be open |
| `get_field_value` / `assert_field_value` | Read or assert a control's value |
| `wait_for_value(fieldname, value)` | Wait for a client script to settle a field |
| `wait_for_row_count(tablefield, n)` | Wait for a child table to reach `n` rows |
| `doc()` | `cur_frm.doc` as a plain dict |
| `save()` | Click Save, assert `savedocs` returned 200, set `self.name` |
| `submit()` | Actions → Submit, confirm the dialog |
| `get_status()` | The status pill's text |
| `is_dirty()` | `cur_frm.is_dirty()` |

`fill_fields` and `fill_table` need no `fieldtype` argument — the Desk exposes
`data-fieldtype` on every control and grid cell, so Link, Select, Check and plain inputs
are detected. A Link only commits a value chosen from its own dropdown, which is why
`set_link` types with `press_sequentially` and presses Enter rather than calling `fill`.

`BasePage.wait_for_load()` polls frappe's own idle state via `page.wait_for_function`
(`frappe.request.ajax_count` and `body[data-ajax-state]`) and then asserts the main
section is non-empty. It deliberately does **not** use `wait_for_load_state`: desk
navigation is client-side so `load` never fires again, and `networkidle` returns at
moments unrelated to the desk's work — swapping it in made this suite fail 5 runs out of 5.

### utils/transaction.py

`fill_items_table`, `verify_autofill_attributes` and `verify_taxes_table` take the
`FormPage` and read as the rule under test. `verify_taxes_table` compares strings by
substring, so `{"account_head": "CGST"}` matches `Input Tax CGST - _TIRC`.

Where an assertion goes matters. A value set by a **client script** must be checked before
the save; after it, a server hook setting the same field would mask a broken script.
Anything the **server** owns is checked after the save.

## Recording with codegen

```bash
cd <bench>/apps/india_compliance
SITE=ic_test.localhost SITE_PORT=8000 ../../env/bin/pytest -q   # refreshes the login state

../../env/bin/playwright codegen \
  --target python-pytest \
  --load-storage=ui_tests/.auth/admin.json \
  --viewport-size "1400,960" \
  "http://ic_test.localhost:8000/app/purchase-invoice/new"
```

A recording is not a test. Before committing one:

1. Drop the `page.goto("http://…")` and any login clicks — `authenticated_desk` covers both.
2. Replace hardcoded record names with `frappe.get_doc(...)` reads in the setup fixture.
3. Move field and grid interactions onto `FormPage` — `fill_fields`, `fill_table`. The
   recording's raw locators work, but they carry no wait, and omitting waits is the main
   reason a recording passes locally and fails in CI.
4. Delete any `page.wait_for_timeout(...)`.
5. Swap ambiguous `get_by_role(...)` locators for the `[data-fieldname="…"]` form — the
   desk keeps hidden pages in the DOM, so role queries often match several elements and
   trip strict mode.
6. Remove `page.pause()`.

## CI

`.github/workflows/ui-tests.yml`. On a pull request it runs only when the paths filter
matches; pushes to the release branches and `workflow_dispatch` always run it. Failures
upload `test-results/` (traces) and print the site's Error Log plus `logs/bench-start.log`.
