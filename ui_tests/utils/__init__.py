from playwright.sync_api import Locator, expect

from ui_tests.pages.base_page import DESK_TIMEOUT


def wait_for_input_value(locator: Locator, value: str, timeout: int = DESK_TIMEOUT) -> None:
    expect(locator).to_have_value(value, timeout=timeout)


def dismiss_modals(form, timeout: int = DESK_TIMEOUT) -> list[str]:
    modals = form.get_modals()
    closed: list[str] = []

    while modals.count():
        modal = modals.last
        closed.append((modal.locator(".modal-title").first.inner_text() or "").strip())
        modal.locator(".btn-modal-close").first.click()
        modal.wait_for(state="hidden", timeout=timeout)

    return closed
