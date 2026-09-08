import os
from pathlib import Path

import frappe
import pytest
from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import Page, Playwright, expect

from ui_tests.pages.form_page import form_page  # noqa: F401

BENCH_PATH = Path(__file__).parents[3]
# Rewritten on every run, and left on disk so `playwright codegen --load-storage`
# can open an authenticated recorder.
AUTH_STATE = Path(__file__).parent / ".auth" / "admin.json"
GSP_URL = "https://asp.resilient.tech/**"
VIEWPORT = {"width": 1400, "height": 960}
TIMEOUT = 10_000

SITE = os.environ.get("SITE", "test-ui.localhost")
SITE_PORT = os.environ.get("SITE_PORT", "8000")
USER = os.environ.get("FRAPPE_USER", "Administrator")
PASSWORD = os.environ.get("ADMIN_PASSWORD", "admin")

NOTIFICATION_KEYS = (
    "needs_audit_trail_notification",
    "needs_item_tax_template_notification",
    "needs_new_gst_category_notification",
)

expect.set_options(timeout=TIMEOUT)


@pytest.fixture(scope="session")
def base_url() -> str:
    return os.environ.get("BASE_URL") or f"http://{SITE}:{SITE_PORT}"


@pytest.fixture(scope="session", autouse=True)
def site():
    sites_path = os.environ.get("FRAPPE_SITES_PATH") or str(BENCH_PATH / "sites")

    if not Path(sites_path, SITE).is_dir():
        pytest.fail(
            f"No site {SITE} under {sites_path}. Set SITE, or FRAPPE_SITES_PATH if the "
            "bench is not three levels above this file."
        )

    # frappe's file loggers resolve "../logs" relative to cwd, which is the bench's
    # sites/ dir only under bench itself; stream them instead of chdir'ing.
    os.environ.setdefault("FRAPPE_STREAM_LOGGING", "1")

    frappe.init(SITE, sites_path=sites_path)
    frappe.connect()

    for key in NOTIFICATION_KEYS:
        frappe.defaults.clear_default(key)
        frappe.defaults.clear_user_default(key)

    frappe.db.set_value("User", USER, "simultaneous_sessions", 10)
    frappe.db.commit()  # nosemgrep
    frappe.clear_cache()

    yield

    frappe.destroy()


@pytest.fixture(scope="session")
def storage_state(playwright: Playwright, base_url: str, site) -> str:
    api = playwright.request.new_context(base_url=base_url, fail_on_status_code=True)

    try:
        api.post("/api/method/login", form={"usr": USER, "pwd": PASSWORD})
        AUTH_STATE.parent.mkdir(parents=True, exist_ok=True)
        api.storage_state(path=AUTH_STATE)
    except PlaywrightError as error:
        pytest.fail(
            f"Could not log in as {USER} at {base_url}: {error}\n\n"
            f"Is a server running?  bench --site {SITE} serve --port {SITE_PORT}"
        )
    finally:
        api.dispose()

    return str(AUTH_STATE)


@pytest.fixture(scope="session")
def browser_type_launch_args(browser_type_launch_args: dict) -> dict:
    if not os.environ.get("CI"):
        return browser_type_launch_args

    return {
        **browser_type_launch_args,
        "args": [
            *browser_type_launch_args.get("args", []),
            "--no-sandbox",
            "--disable-dev-shm-usage",
            "--disable-gpu",
        ],
    }


@pytest.fixture(scope="session")
def browser_context_args(browser_context_args: dict, storage_state: str) -> dict:
    return {**browser_context_args, "viewport": VIEWPORT, "storage_state": storage_state}


@pytest.fixture(autouse=True)
def page_diagnostics(page: Page, request: pytest.FixtureRequest):
    page.set_default_timeout(TIMEOUT)
    page.route(GSP_URL, lambda route: route.abort("failed"))

    lines: list[str] = []
    page.on("console", lambda message: lines.append(f"[{message.type}] {message.text}"))
    page.on("pageerror", lambda error: lines.append(f"[pageerror] {error.message}"))

    yield lines

    report = getattr(request.node, "rep_call", None)
    if lines and (report is None or report.failed):
        print("\n--- browser console ---")
        print("\n".join(lines))


@pytest.fixture
def authenticated_desk(page: Page) -> Page:
    return page


@pytest.fixture
def doc(site):
    """Read a doc the browser just committed, and delete it when the test ends."""
    tracked = []

    def fetch(doctype, name):
        # This process runs at REPEATABLE READ, so its snapshot predates whatever
        # the server committed; commit to start a fresh one.
        frappe.db.commit()  # nosemgrep
        frappe.clear_document_cache(doctype, name)
        tracked.append((doctype, name))

        return frappe.get_doc(doctype, name)

    yield fetch

    for doctype, name in reversed(tracked):
        try:
            doc = frappe.get_doc(doctype, name)
            if doc.docstatus == 1:
                doc.cancel()

            frappe.delete_doc(doctype, name, force=True, ignore_permissions=True, delete_permanently=True)
        except Exception as error:
            print(f"could not clean up {doctype} {name}: {error}")

    frappe.db.commit()  # nosemgrep
