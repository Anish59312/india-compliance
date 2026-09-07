from playwright.sync_api import Page, expect

DESK_SETTLED = """() => {
    const f = window.frappe;
    if (!f?.app) return false;
    if (f.request.ajax_count !== 0) return false;

    return document.body.dataset.ajaxState !== "triggered";
}"""

DESK_TIMEOUT = 15_000


class BasePage:
    def __init__(self, page: Page):
        self.page = page

    def wait_for_load(self, timeout: int = DESK_TIMEOUT) -> None:
        self.page.wait_for_function(DESK_SETTLED, timeout=timeout, polling=100)
        expect(self.page.locator(".layout-main-section:visible").first).not_to_be_empty()

    def reload(self) -> None:
        self.page.reload()
        self.wait_for_load()

    def get_url(self) -> str:
        return self.page.url

    def click_button(self, text: str) -> None:
        self.page.locator(".page-container:visible").get_by_role(
            "button", name=text, exact=True
        ).first.click()
        self.wait_for_load()

    def click_action(self, name: str) -> None:
        self.click_button("Actions")
        self.page.locator('.es-menu [role="menuitem"]', has_text=name).first.click()
        self.wait_for_load()

    def assert_no_modal(self) -> None:
        expect(self.page.locator(".modal:visible")).to_have_count(0)
