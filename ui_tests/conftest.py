import os
import time
from pathlib import Path

import frappe
import pytest
from playwright.sync_api import Browser, Page, expect

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

DESK_SETTLED = """() => {
    const f = window.frappe;
    if (!f?.app) return false;
    if (f.request.ajax_count !== 0) return false;

    return document.body.dataset.ajaxState !== "triggered";
}"""

DESK_TIMEOUT = 15_000


def desk_ready(page: Page) -> None:
    """The desk's equivalent of wait_for_load_state("networkidle")."""
    page.wait_for_function(DESK_SETTLED, timeout=DESK_TIMEOUT)
    expect(page.locator(".layout-main-section:visible").first).not_to_be_empty()


def poll_doc(page: Page, pick, matches, message: str, timeout: int = 10_000, interval: int = 250):
    """Retry a read of cur_frm.doc until `matches` holds.

    Client scripts settle fields asynchronously and expect() cannot poll a JS
    expression, so a single evaluate() races them.
    """

    def read():
        return pick(
            page.evaluate("() => window.cur_frm ? JSON.parse(JSON.stringify(window.cur_frm.doc)) : {}")
        )

    deadline = time.monotonic() + timeout / 1000
    value = read()

    while not matches(value):
        if time.monotonic() >= deadline:
            raise AssertionError(f"{message}\n  last value: {value!r}")

        time.sleep(interval / 1000)
        value = read()

    return value


@pytest.hookimpl(tryfirst=True, hookwrapper=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    setattr(item, f"report_{call.when}", outcome.get_result())


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
    frappe.db.commit()
    frappe.clear_cache()

    yield

    frappe.destroy()


@pytest.fixture(scope="session")
def storage_state(browser: Browser, base_url: str, site) -> str:
    context = browser.new_context(base_url=base_url)

    ping = context.request.get("/api/method/ping")
    if not ping.ok:
        context.close()
        pytest.fail(
            f"No Frappe server at {base_url}. Start one with:\n\n"
            f"    cd {BENCH_PATH} && bench --site {SITE} serve --port {SITE_PORT}\n"
        )

    login = context.request.post("/api/method/login", form={"usr": USER, "pwd": PASSWORD})
    if not login.ok:
        context.close()
        pytest.fail(f"login as {USER} failed: {login.text()}")

    AUTH_STATE.parent.mkdir(parents=True, exist_ok=True)
    context.storage_state(path=str(AUTH_STATE))
    context.close()

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

    report = getattr(request.node, "report_call", None)
    if lines and (report is None or report.failed):
        print("\n--- browser console ---")
        print("\n".join(lines))


@pytest.fixture
def authenticated_desk(page: Page) -> Page:
    """A page logged in and sitting on a settled desk."""
    page.goto("/app")
    desk_ready(page)

    return page


@pytest.fixture
def saved_doc(site):
    """Read a doc the browser just committed, and delete it when the test ends."""
    tracked = []

    def fetch(doctype, name):
        # This process runs at REPEATABLE READ, so its snapshot predates whatever
        # the server committed; commit to start a fresh one.
        frappe.db.commit()
        frappe.clear_document_cache(doctype, name)
        tracked.append((doctype, name))

        return frappe.get_doc(doctype, name)

    yield fetch

    for doctype, name in reversed(tracked):
        frappe.delete_doc(doctype, name, force=True, ignore_permissions=True, delete_permanently=True)

    frappe.db.commit()
